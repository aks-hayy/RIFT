#include "spoolstream/transformer_executor.h"

#include "spoolstream/memory_manager.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace spoolstream::core {
namespace {

constexpr int kThreads = 256;

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream transformer executor validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

size_t checked_count(int rows, int cols, const std::string& context) {
    require_condition(rows > 0, context + " rows must be positive");
    require_condition(cols > 0, context + " cols must be positive");
    const auto r = static_cast<size_t>(rows);
    const auto c = static_cast<size_t>(cols);
    require_condition(r <= std::numeric_limits<size_t>::max() / c,
                      context + " size overflows size_t");
    return r * c;
}

__device__ __forceinline__ float silu(float value) {
    return value / (1.0f + expf(-value));
}

__global__ void rmsnorm_kernel(const half* input,
                               const half* weight,
                               half* output,
                               int hidden_size,
                               float epsilon) {
    extern __shared__ float shared[];
    const int row = blockIdx.x;
    const int lane = threadIdx.x;
    const int base = row * hidden_size;

    float sum = 0.0f;
    for (int col = lane; col < hidden_size; col += blockDim.x) {
        const float value = __half2float(input[base + col]);
        sum += value * value;
    }
    shared[lane] = sum;
    __syncthreads();

    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (lane < stride) {
            shared[lane] += shared[lane + stride];
        }
        __syncthreads();
    }

    const float inv_rms = rsqrtf(shared[0] / static_cast<float>(hidden_size) + epsilon);
    for (int col = lane; col < hidden_size; col += blockDim.x) {
        const float value = __half2float(input[base + col]);
        const float scale = __half2float(weight[col]);
        output[base + col] = __float2half(value * inv_rms * scale);
    }
}

__global__ void rope_kernel(half* q,
                            half* k,
                            int tokens,
                            int num_heads,
                            int num_kv_heads,
                            int head_dim,
                            int position_offset,
                            float rope_theta) {
    const int pair_count = head_dim / 2;
    const int total_q = tokens * num_heads * pair_count;
    const int total_k = tokens * num_kv_heads * pair_count;
    const int total = total_q + total_k;
    const int linear = blockIdx.x * blockDim.x + threadIdx.x;
    if (linear >= total) {
        return;
    }

    const bool is_q = linear < total_q;
    const int local = is_q ? linear : linear - total_q;
    const int heads = is_q ? num_heads : num_kv_heads;
    half* tensor = is_q ? q : k;
    const int pair_index = local % pair_count;
    const int head = (local / pair_count) % heads;
    const int token = local / (pair_count * heads);
    const int base = (token * heads + head) * head_dim + pair_index * 2;

    const float exponent = static_cast<float>(pair_index * 2) / static_cast<float>(head_dim);
    const float frequency = powf(rope_theta, -exponent);
    const float angle = static_cast<float>(position_offset + token) * frequency;
    float sin_value = 0.0f;
    float cos_value = 0.0f;
    sincosf(angle, &sin_value, &cos_value);

    const float x0 = __half2float(tensor[base]);
    const float x1 = __half2float(tensor[base + 1]);
    tensor[base] = __float2half(x0 * cos_value - x1 * sin_value);
    tensor[base + 1] = __float2half(x0 * sin_value + x1 * cos_value);
}

__global__ void residual_add_kernel(const half* lhs,
                                    const half* rhs,
                                    half* output,
                                    int element_count) {
    const int index = blockIdx.x * blockDim.x + threadIdx.x;
    if (index < element_count) {
        output[index] = __float2half(__half2float(lhs[index]) + __half2float(rhs[index]));
    }
}

__global__ void swiglu_kernel(const half* gate,
                              const half* up,
                              half* output,
                              int element_count) {
    const int index = blockIdx.x * blockDim.x + threadIdx.x;
    if (index < element_count) {
        const float gate_value = __half2float(gate[index]);
        const float up_value = __half2float(up[index]);
        output[index] = __float2half(silu(gate_value) * up_value);
    }
}

__global__ void copy_half_kernel(const half* input, half* output, int element_count) {
    const int index = blockIdx.x * blockDim.x + threadIdx.x;
    if (index < element_count) {
        output[index] = input[index];
    }
}

__global__ void token_embedding_lookup_kernel(const half* embeddings,
                                              int token_id,
                                              half* output,
                                              int hidden_size) {
    const int index = blockIdx.x * blockDim.x + threadIdx.x;
    if (index < hidden_size) {
        output[index] = embeddings[token_id * hidden_size + index];
    }
}

__global__ void dense_matmul_fp16_kernel(const half* lhs,
                                         const half* rhs,
                                         const half* bias,
                                         half* output,
                                         int m,
                                         int n,
                                         int k) {
    const int col = blockIdx.x * blockDim.x + threadIdx.x;
    const int row = blockIdx.y * blockDim.y + threadIdx.y;
    if (row >= m || col >= n) {
        return;
    }

    float sum = bias == nullptr ? 0.0f : __half2float(bias[col]);
    for (int kk = 0; kk < k; ++kk) {
        const float a = __half2float(lhs[row * k + kk]);
        const float b = __half2float(rhs[kk * n + col]);
        sum += a * b;
    }
    output[row * n + col] = __float2half(sum);
}

__global__ void dense_lm_head_tile_kernel(const half* hidden,
                                          const half* lm_head_tile,
                                          half* logits,
                                          int rows,
                                          int hidden_size) {
    __shared__ float partial[kThreads];
    const int row = blockIdx.x;
    const int lane = threadIdx.x;
    if (row >= rows) {
        return;
    }

    float sum = 0.0f;
    for (int col = lane; col < hidden_size; col += blockDim.x) {
        sum += __half2float(hidden[col]) *
               __half2float(lm_head_tile[row * hidden_size + col]);
    }
    partial[lane] = sum;
    __syncthreads();

    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (lane < stride) {
            partial[lane] += partial[lane + stride];
        }
        __syncthreads();
    }

    if (lane == 0) {
        logits[row] = __float2half(partial[0]);
    }
}

__global__ void greedy_last_token_kernel(const half* logits,
                                         int tokens,
                                         int vocab_size,
                                         int* output_token,
                                         float* output_logit) {
    __shared__ float best_values[kThreads];
    __shared__ int best_indices[kThreads];
    const int lane = threadIdx.x;
    const int row_offset = (tokens - 1) * vocab_size;

    float best_value = -3.402823466e+38F;
    int best_index = 0;
    for (int col = lane; col < vocab_size; col += blockDim.x) {
        const float value = __half2float(logits[row_offset + col]);
        if (value > best_value || (value == best_value && col < best_index)) {
            best_value = value;
            best_index = col;
        }
    }
    best_values[lane] = best_value;
    best_indices[lane] = best_index;
    __syncthreads();

    for (int stride = blockDim.x / 2; stride > 0; stride >>= 1) {
        if (lane < stride) {
            const float rhs_value = best_values[lane + stride];
            const int rhs_index = best_indices[lane + stride];
            if (rhs_value > best_values[lane] ||
                (rhs_value == best_values[lane] && rhs_index < best_indices[lane])) {
                best_values[lane] = rhs_value;
                best_indices[lane] = rhs_index;
            }
        }
        __syncthreads();
    }

    if (lane == 0) {
        *output_token = best_indices[0];
        *output_logit = best_values[0];
    }
}

__global__ void causal_attention_prefill_kernel(const half* q,
                                                const half* k,
                                                const half* v,
                                                half* output,
                                                int tokens,
                                                int num_attention_heads,
                                                int num_key_value_heads,
                                                int head_dim) {
    const int dim = blockIdx.x * blockDim.x + threadIdx.x;
    const int head = blockIdx.y;
    const int token = blockIdx.z;
    if (dim >= head_dim) {
        return;
    }

    const int kv_group = num_attention_heads / num_key_value_heads;
    const int kv_head = head / kv_group;
    const float scale = rsqrtf(static_cast<float>(head_dim));

    float max_logit = -3.402823466e+38F;
    for (int source = 0; source <= token; ++source) {
        float dot = 0.0f;
        for (int d = 0; d < head_dim; ++d) {
            const int q_index = (token * num_attention_heads + head) * head_dim + d;
            const int k_index = (source * num_key_value_heads + kv_head) * head_dim + d;
            dot += __half2float(q[q_index]) * __half2float(k[k_index]);
        }
        max_logit = fmaxf(max_logit, dot * scale);
    }

    float denom = 0.0f;
    float weighted = 0.0f;
    for (int source = 0; source <= token; ++source) {
        float dot = 0.0f;
        for (int d = 0; d < head_dim; ++d) {
            const int q_index = (token * num_attention_heads + head) * head_dim + d;
            const int k_index = (source * num_key_value_heads + kv_head) * head_dim + d;
            dot += __half2float(q[q_index]) * __half2float(k[k_index]);
        }
        const float weight = expf(dot * scale - max_logit);
        const int v_index = (source * num_key_value_heads + kv_head) * head_dim + dim;
        denom += weight;
        weighted += weight * __half2float(v[v_index]);
    }

    const int out_index = (token * num_attention_heads + head) * head_dim + dim;
    output[out_index] = __float2half(weighted / denom);
}

__global__ void store_kv_cache_token_kernel(const half* k_token,
                                            const half* v_token,
                                            half* k_cache,
                                            half* v_cache,
                                            int token_index,
                                            int num_key_value_heads,
                                            int head_dim) {
    const int linear = blockIdx.x * blockDim.x + threadIdx.x;
    const int token_values = num_key_value_heads * head_dim;
    if (linear >= token_values) {
        return;
    }
    const int cache_index = token_index * token_values + linear;
    k_cache[cache_index] = k_token[linear];
    v_cache[cache_index] = v_token[linear];
}

__global__ void causal_attention_decode_kernel(const half* q_token,
                                               const half* k_cache,
                                               const half* v_cache,
                                               half* output,
                                               int cached_tokens,
                                               int num_attention_heads,
                                               int num_key_value_heads,
                                               int head_dim) {
    const int dim = blockIdx.x * blockDim.x + threadIdx.x;
    const int head = blockIdx.y;
    if (dim >= head_dim) {
        return;
    }

    const int kv_group = num_attention_heads / num_key_value_heads;
    const int kv_head = head / kv_group;
    const float scale = rsqrtf(static_cast<float>(head_dim));

    float max_logit = -3.402823466e+38F;
    for (int source = 0; source < cached_tokens; ++source) {
        float dot = 0.0f;
        for (int d = 0; d < head_dim; ++d) {
            const int q_index = head * head_dim + d;
            const int k_index = (source * num_key_value_heads + kv_head) * head_dim + d;
            dot += __half2float(q_token[q_index]) * __half2float(k_cache[k_index]);
        }
        max_logit = fmaxf(max_logit, dot * scale);
    }

    float denom = 0.0f;
    float weighted = 0.0f;
    for (int source = 0; source < cached_tokens; ++source) {
        float dot = 0.0f;
        for (int d = 0; d < head_dim; ++d) {
            const int q_index = head * head_dim + d;
            const int k_index = (source * num_key_value_heads + kv_head) * head_dim + d;
            dot += __half2float(q_token[q_index]) * __half2float(k_cache[k_index]);
        }
        const float weight = expf(dot * scale - max_logit);
        const int v_index = (source * num_key_value_heads + kv_head) * head_dim + dim;
        denom += weight;
        weighted += weight * __half2float(v_cache[v_index]);
    }

    const int out_index = head * head_dim + dim;
    output[out_index] = __float2half(weighted / denom);
}

void validate_pointer(const void* ptr, const std::string& name) {
    require_condition(ptr != nullptr, name + " pointer cannot be null");
}

int blocks_for(int element_count) {
    require_condition(element_count > 0, "element_count must be positive");
    return (element_count + kThreads - 1) / kThreads;
}

void validate_layer_config(const LlamaDecoderLayerConfig& config) {
    require_condition(config.tokens > 0, "tokens must be positive");
    require_condition(config.hidden_size > 0, "hidden_size must be positive");
    require_condition(config.intermediate_size > 0, "intermediate_size must be positive");
    require_condition(config.num_attention_heads > 0, "num_attention_heads must be positive");
    require_condition(config.num_key_value_heads > 0, "num_key_value_heads must be positive");
    require_condition(config.head_dim > 0, "head_dim must be positive");
    require_condition(config.position_offset >= 0, "position_offset must be non-negative");
    require_condition(config.rope_theta > 0.0f, "rope_theta must be positive");
    require_condition(config.rms_norm_epsilon > 0.0f, "rms_norm_epsilon must be positive");
    require_condition(config.hidden_size == config.num_attention_heads * config.head_dim,
                      "hidden_size must equal num_attention_heads * head_dim");
    require_condition(config.num_attention_heads % config.num_key_value_heads == 0,
                      "num_attention_heads must be divisible by num_key_value_heads");
}

void validate_layer_weights(const LlamaDecoderLayerWeights& weights) {
    validate_pointer(weights.attn_norm, "attn_norm");
    validate_pointer(weights.q_proj, "q_proj");
    validate_pointer(weights.k_proj, "k_proj");
    validate_pointer(weights.v_proj, "v_proj");
    validate_pointer(weights.o_proj, "o_proj");
    validate_pointer(weights.mlp_norm, "mlp_norm");
    validate_pointer(weights.gate_proj, "gate_proj");
    validate_pointer(weights.up_proj, "up_proj");
    validate_pointer(weights.down_proj, "down_proj");
}

void validate_quantized_view(const QuantizedProjectionRuntimeView& view,
                             QuantizedProjectionRole role,
                             int input_features,
                             int output_features,
                             const std::string& name) {
    validate_pointer(view.projection, name + ".projection");
    validate_pointer(view.device_qweight, name + ".device_qweight");
    validate_pointer(view.device_scales, name + ".device_scales");
    validate_pointer(view.device_zeros, name + ".device_zeros");
    require_condition(view.projection->role == role, name + " projection role mismatch");
    require_condition(view.input_features == input_features,
                      name + " input_features mismatch");
    require_condition(view.output_features == output_features,
                      name + " output_features mismatch");
    require_condition(view.gemm_config.k == input_features,
                      name + " GEMM k mismatch");
    require_condition(view.gemm_config.n == output_features,
                      name + " GEMM n mismatch");
    require_condition(view.gemm_config.m > 0,
                      name + " GEMM m must be positive");
}

void validate_quantized_layer_weights(const QuantizedLlamaDecoderLayerWeights& weights,
                                      const LlamaDecoderLayerConfig& config) {
    validate_pointer(weights.attn_norm, "attn_norm");
    validate_pointer(weights.mlp_norm, "mlp_norm");
    const int kv_hidden = config.num_key_value_heads * config.head_dim;
    validate_quantized_view(weights.q_proj,
                            QuantizedProjectionRole::ATTN_Q,
                            config.hidden_size,
                            config.hidden_size,
                            "q_proj");
    validate_quantized_view(weights.k_proj,
                            QuantizedProjectionRole::ATTN_K,
                            config.hidden_size,
                            kv_hidden,
                            "k_proj");
    validate_quantized_view(weights.v_proj,
                            QuantizedProjectionRole::ATTN_V,
                            config.hidden_size,
                            kv_hidden,
                            "v_proj");
    validate_quantized_view(weights.o_proj,
                            QuantizedProjectionRole::ATTN_O,
                            config.hidden_size,
                            config.hidden_size,
                            "o_proj");
    validate_quantized_view(weights.gate_proj,
                            QuantizedProjectionRole::MLP_GATE,
                            config.hidden_size,
                            config.intermediate_size,
                            "gate_proj");
    validate_quantized_view(weights.up_proj,
                            QuantizedProjectionRole::MLP_UP,
                            config.hidden_size,
                            config.intermediate_size,
                            "up_proj");
    validate_quantized_view(weights.down_proj,
                            QuantizedProjectionRole::MLP_DOWN,
                            config.intermediate_size,
                            config.hidden_size,
                            "down_proj");
}

const TensorPlacement* find_role_placement(const LayerExecutionPlan& plan, TensorRole role) {
    for (const TensorPlacement& placement : plan.placements) {
        if (placement.role == role) {
            return &placement;
        }
    }
    return nullptr;
}

void require_projection_role(const QuantizedProjection& projection,
                             QuantizedProjectionRole role,
                             const char* name) {
    require_condition(projection.role == role,
                      std::string(name) + " projection role mismatch");
}

struct SamplingCandidate {
    int token_id;
    float logit;
    float weight;
};

bool better_candidate(const SamplingCandidate& lhs, const SamplingCandidate& rhs) {
    return lhs.logit > rhs.logit ||
           (lhs.logit == rhs.logit && lhs.token_id < rhs.token_id);
}

double next_unit_interval(uint64_t& state) {
    state = state * 6364136223846793005ULL + 1442695040888963407ULL;
    return static_cast<double>(state >> 11) *
           (1.0 / 9007199254740992.0);
}

void validate_dense_lm_head_inputs(StreamingTensorStore& store,
                                   const ManifestTensor& lm_head_weight,
                                   const half* hidden_states,
                                   const half* final_norm_weight,
                                   ActivationWorkspace& workspace,
                                   int tokens,
                                   int hidden_size,
                                   int vocab_size,
                                   int vocab_tile_rows,
                                   float rms_norm_epsilon) {
    validate_pointer(hidden_states, "hidden_states");
    validate_pointer(final_norm_weight, "final_norm_weight");
    validate_pointer(store.host_staging_ptr, "store.host_staging_ptr");
    require_condition(tokens > 0, "tokens must be positive");
    require_condition(hidden_size > 0, "hidden_size must be positive");
    require_condition(vocab_size > 0, "vocab_size must be positive");
    require_condition(vocab_tile_rows > 0, "vocab_tile_rows must be positive");
    require_condition(rms_norm_epsilon > 0.0f, "rms_norm_epsilon must be positive");
    require_condition(lm_head_weight.role == TensorRole::LM_HEAD,
                      "lm_head_weight tensor role must be LM_HEAD");
    require_condition(lm_head_weight.metadata.data_type == "F16" ||
                          lm_head_weight.metadata.data_type == "FLOAT16" ||
                          lm_head_weight.metadata.data_type == "float16",
                      "dense lm_head_weight must be FP16");
    require_condition(lm_head_weight.metadata.shape.size() == 2,
                      "dense lm_head_weight must be rank-2");
    require_condition(lm_head_weight.metadata.shape[0] == vocab_size &&
                          lm_head_weight.metadata.shape[1] == hidden_size,
                      "dense lm_head_weight shape must be [vocab_size, hidden_size]");
    require_condition(workspace.tokens == tokens, "workspace token count mismatch");
    require_condition(workspace.hidden_size == hidden_size, "workspace hidden_size mismatch");
    validate_pointer(workspace.normalized, "workspace.normalized");
}

const QuantizedProjection& require_quantized_projection(
    const QuantizedAdapterReport& report,
    int layer_id,
    QuantizedProjectionRole role) {
    for (const QuantizedProjection& projection : report.projections) {
        if (projection.layer_id == layer_id && projection.role == role) {
            require_condition(projection.materializable,
                              std::string("projection is not materializable: ") +
                                  projection.base_name);
            return projection;
        }
    }
    fail("missing quantized projection for layer " + std::to_string(layer_id) +
         " role " + quantized_projection_role_name(role));
}

QuantizedProjectionMetadataWorkspace create_and_upload_zero_workspace(
    StreamingTensorStore& store,
    const QuantizedProjection& projection,
    cudaStream_t stream) {
    QuantizedProjectionMetadataWorkspace workspace =
        create_quantized_projection_metadata_workspace(projection);
    try {
        const StagedTensor staged = stage_tensor_bytes(store, *projection.zeros);
        upload_projection_zeros_to_workspace(workspace,
                                             projection,
                                             staged.host_ptr,
                                             staged.byte_size,
                                             stream);
        if (projection.g_idx != nullptr) {
            const StagedTensor gidx = stage_tensor_bytes(store, *projection.g_idx);
            upload_projection_gidx_to_workspace(workspace,
                                                projection,
                                                gidx.host_ptr,
                                                gidx.byte_size,
                                                stream);
        }
        return workspace;
    } catch (...) {
        destroy_quantized_projection_metadata_workspace(workspace);
        throw;
    }
}

void destroy_projection_workspaces(
    QuantizedProjectionMetadataWorkspace& q_workspace,
    QuantizedProjectionMetadataWorkspace& k_workspace,
    QuantizedProjectionMetadataWorkspace& v_workspace,
    QuantizedProjectionMetadataWorkspace& o_workspace,
    QuantizedProjectionMetadataWorkspace& gate_workspace,
    QuantizedProjectionMetadataWorkspace& up_workspace,
    QuantizedProjectionMetadataWorkspace& down_workspace) noexcept {
    destroy_quantized_projection_metadata_workspace(q_workspace);
    destroy_quantized_projection_metadata_workspace(k_workspace);
    destroy_quantized_projection_metadata_workspace(v_workspace);
    destroy_quantized_projection_metadata_workspace(o_workspace);
    destroy_quantized_projection_metadata_workspace(gate_workspace);
    destroy_quantized_projection_metadata_workspace(up_workspace);
    destroy_quantized_projection_metadata_workspace(down_workspace);
}

} // namespace

ActivationWorkspace create_activation_workspace(int tokens,
                                                int hidden_size,
                                                int intermediate_size) {
    require_condition(tokens > 0, "tokens must be positive");
    require_condition(hidden_size > 0, "hidden_size must be positive");
    require_condition(intermediate_size > 0, "intermediate_size must be positive");

    ActivationWorkspace workspace{};
    workspace.tokens = tokens;
    workspace.hidden_size = hidden_size;
    workspace.intermediate_size = intermediate_size;

    const size_t hidden_count = checked_count(tokens, hidden_size, "hidden workspace");
    const size_t intermediate_count =
        checked_count(tokens, intermediate_size, "intermediate workspace");
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.hidden),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.residual),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.normalized),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.q),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.k),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.v),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.attention_out),
                                          sizeof(half) * hidden_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.mlp_gate),
                                          sizeof(half) * intermediate_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.mlp_up),
                                          sizeof(half) * intermediate_count));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.mlp_down),
                                          sizeof(half) * hidden_count));
        return workspace;
    } catch (...) {
        destroy_activation_workspace(workspace);
        throw;
    }
}

void destroy_activation_workspace(ActivationWorkspace& workspace) noexcept {
    half** pointers[] = {
        &workspace.hidden,
        &workspace.residual,
        &workspace.normalized,
        &workspace.q,
        &workspace.k,
        &workspace.v,
        &workspace.attention_out,
        &workspace.mlp_gate,
        &workspace.mlp_up,
        &workspace.mlp_down,
    };
    for (half** ptr : pointers) {
        if (*ptr != nullptr) {
            cudaFree(*ptr);
            *ptr = nullptr;
        }
    }
    workspace.tokens = 0;
    workspace.hidden_size = 0;
    workspace.intermediate_size = 0;
}

void launch_rmsnorm(const half* input,
                    const half* weight,
                    half* output,
                    int rows,
                    int hidden_size,
                    float epsilon,
                    cudaStream_t stream) {
    validate_pointer(input, "input");
    validate_pointer(weight, "weight");
    validate_pointer(output, "output");
    checked_count(rows, hidden_size, "rmsnorm");
    require_condition(epsilon > 0.0f, "epsilon must be positive");
    rmsnorm_kernel<<<rows, kThreads, sizeof(float) * kThreads, stream>>>(
        input,
        weight,
        output,
        hidden_size,
        epsilon);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_rope(half* q,
                 half* k,
                 int tokens,
                 int num_heads,
                 int num_kv_heads,
                 int head_dim,
                 int position_offset,
                 float rope_theta,
                 cudaStream_t stream) {
    validate_pointer(q, "q");
    validate_pointer(k, "k");
    require_condition(tokens > 0, "tokens must be positive");
    require_condition(num_heads > 0, "num_heads must be positive");
    require_condition(num_kv_heads > 0, "num_kv_heads must be positive");
    require_condition(head_dim > 0 && (head_dim % 2) == 0, "head_dim must be positive and even");
    require_condition(position_offset >= 0, "position_offset must be non-negative");
    require_condition(rope_theta > 0.0f, "rope_theta must be positive");
    const int pair_count = head_dim / 2;
    const int total = tokens * (num_heads + num_kv_heads) * pair_count;
    rope_kernel<<<blocks_for(total), kThreads, 0, stream>>>(
        q,
        k,
        tokens,
        num_heads,
        num_kv_heads,
        head_dim,
        position_offset,
        rope_theta);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_residual_add(const half* lhs,
                         const half* rhs,
                         half* output,
                         int element_count,
                         cudaStream_t stream) {
    validate_pointer(lhs, "lhs");
    validate_pointer(rhs, "rhs");
    validate_pointer(output, "output");
    residual_add_kernel<<<blocks_for(element_count), kThreads, 0, stream>>>(
        lhs,
        rhs,
        output,
        element_count);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_swiglu(const half* gate,
                   const half* up,
                   half* output,
                   int element_count,
                   cudaStream_t stream) {
    validate_pointer(gate, "gate");
    validate_pointer(up, "up");
    validate_pointer(output, "output");
    swiglu_kernel<<<blocks_for(element_count), kThreads, 0, stream>>>(
        gate,
        up,
        output,
        element_count);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_copy_half(const half* input,
                      half* output,
                      int element_count,
                      cudaStream_t stream) {
    validate_pointer(input, "input");
    validate_pointer(output, "output");
    copy_half_kernel<<<blocks_for(element_count), kThreads, 0, stream>>>(
        input,
        output,
        element_count);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_token_embedding_lookup(const half* embeddings,
                                   int token_id,
                                   half* output,
                                   int vocab_size,
                                   int hidden_size,
                                   cudaStream_t stream) {
    validate_pointer(embeddings, "embeddings");
    validate_pointer(output, "output");
    require_condition(vocab_size > 0, "vocab_size must be positive");
    require_condition(hidden_size > 0, "hidden_size must be positive");
    require_condition(token_id >= 0 && token_id < vocab_size,
                      "token_id is out of embedding range");
    token_embedding_lookup_kernel<<<blocks_for(hidden_size), kThreads, 0, stream>>>(
        embeddings,
        token_id,
        output,
        hidden_size);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

PromptEmbeddingResult execute_prompt_embedding_lookup_streamed(
    StreamingTensorStore& store,
    const ManifestTensor& embedding_weight,
    const int* token_ids,
    int token_count,
    half* output,
    int vocab_size,
    int hidden_size,
    cudaStream_t stream) {
    validate_pointer(store.host_staging_ptr, "store.host_staging_ptr");
    validate_pointer(token_ids, "token_ids");
    validate_pointer(output, "output");
    require_condition(token_count > 0, "token_count must be positive");
    require_condition(vocab_size > 0, "vocab_size must be positive");
    require_condition(hidden_size > 0, "hidden_size must be positive");
    require_condition(embedding_weight.role == TensorRole::TOKEN_EMBEDDING,
                      "embedding_weight tensor role must be TOKEN_EMBEDDING");
    require_condition(embedding_weight.metadata.data_type == "F16" ||
                          embedding_weight.metadata.data_type == "FLOAT16" ||
                          embedding_weight.metadata.data_type == "float16",
                      "token embedding tensor must be FP16");
    require_condition(embedding_weight.metadata.shape.size() == 2,
                      "token embedding tensor must be rank-2");
    require_condition(embedding_weight.metadata.shape[0] == vocab_size &&
                          embedding_weight.metadata.shape[1] == hidden_size,
                      "token embedding tensor shape must be [vocab_size, hidden_size]");
    const size_t row_bytes = static_cast<size_t>(hidden_size) * sizeof(half);
    require_condition(row_bytes <= store.staging_capacity,
                      "token embedding row exceeds staging capacity");

    PromptEmbeddingResult result{};
    for (int token_index = 0; token_index < token_count; ++token_index) {
        const int token_id = token_ids[token_index];
        require_condition(token_id >= 0 && token_id < vocab_size,
                          "token_id is out of embedding range");
        const size_t tensor_offset = static_cast<size_t>(token_id) * row_bytes;
        const StagedTensor staged =
            stage_tensor_slice(store, embedding_weight, tensor_offset, row_bytes);
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(
            output + static_cast<size_t>(token_index) * static_cast<size_t>(hidden_size),
            staged.host_ptr,
            staged.byte_size,
            cudaMemcpyHostToDevice,
            stream));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
        result.bytes_streamed += staged.byte_size;
        ++result.tokens_embedded;
    }
    return result;
}

void launch_dense_matmul_fp16(const half* lhs,
                              const half* rhs,
                              const half* bias,
                              half* output,
                              int m,
                              int n,
                              int k,
                              cudaStream_t stream) {
    validate_pointer(lhs, "lhs");
    validate_pointer(rhs, "rhs");
    validate_pointer(output, "output");
    checked_count(m, k, "dense matmul lhs");
    checked_count(k, n, "dense matmul rhs");
    checked_count(m, n, "dense matmul output");

    constexpr dim3 block(16, 16);
    const dim3 grid((n + block.x - 1) / block.x, (m + block.y - 1) / block.y);
    dense_matmul_fp16_kernel<<<grid, block, 0, stream>>>(lhs, rhs, bias, output, m, n, k);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_causal_attention_prefill(const half* q,
                                     const half* k,
                                     const half* v,
                                     half* output,
                                     int tokens,
                                     int num_attention_heads,
                                     int num_key_value_heads,
                                     int head_dim,
                                     cudaStream_t stream) {
    validate_pointer(q, "q");
    validate_pointer(k, "k");
    validate_pointer(v, "v");
    validate_pointer(output, "output");
    require_condition(tokens > 0, "tokens must be positive");
    require_condition(num_attention_heads > 0, "num_attention_heads must be positive");
    require_condition(num_key_value_heads > 0, "num_key_value_heads must be positive");
    require_condition(head_dim > 0, "head_dim must be positive");
    require_condition(num_attention_heads % num_key_value_heads == 0,
                      "num_attention_heads must be divisible by num_key_value_heads");

    const dim3 block(128);
    const dim3 grid((head_dim + block.x - 1) / block.x,
                    num_attention_heads,
                    tokens);
    causal_attention_prefill_kernel<<<grid, block, 0, stream>>>(q,
                                                                k,
                                                                v,
                                                                output,
                                                                tokens,
                                                                num_attention_heads,
                                                                num_key_value_heads,
                                                                head_dim);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_store_kv_cache_token(const half* k_token,
                                 const half* v_token,
                                 half* k_cache,
                                 half* v_cache,
                                 int token_index,
                                 int cache_token_capacity,
                                 int num_key_value_heads,
                                 int head_dim,
                                 cudaStream_t stream) {
    validate_pointer(k_token, "k_token");
    validate_pointer(v_token, "v_token");
    validate_pointer(k_cache, "k_cache");
    validate_pointer(v_cache, "v_cache");
    require_condition(token_index >= 0, "token_index must be non-negative");
    require_condition(cache_token_capacity > 0, "cache_token_capacity must be positive");
    require_condition(token_index < cache_token_capacity,
                      "token_index exceeds cache token capacity");
    require_condition(num_key_value_heads > 0, "num_key_value_heads must be positive");
    require_condition(head_dim > 0, "head_dim must be positive");

    const int element_count = num_key_value_heads * head_dim;
    store_kv_cache_token_kernel<<<blocks_for(element_count), kThreads, 0, stream>>>(
        k_token,
        v_token,
        k_cache,
        v_cache,
        token_index,
        num_key_value_heads,
        head_dim);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_causal_attention_decode(const half* q_token,
                                    const half* k_cache,
                                    const half* v_cache,
                                    half* output,
                                    int cached_tokens,
                                    int num_attention_heads,
                                    int num_key_value_heads,
                                    int head_dim,
                                    cudaStream_t stream) {
    validate_pointer(q_token, "q_token");
    validate_pointer(k_cache, "k_cache");
    validate_pointer(v_cache, "v_cache");
    validate_pointer(output, "output");
    require_condition(cached_tokens > 0, "cached_tokens must be positive");
    require_condition(num_attention_heads > 0, "num_attention_heads must be positive");
    require_condition(num_key_value_heads > 0, "num_key_value_heads must be positive");
    require_condition(head_dim > 0, "head_dim must be positive");
    require_condition(num_attention_heads % num_key_value_heads == 0,
                      "num_attention_heads must be divisible by num_key_value_heads");

    const dim3 block(128);
    const dim3 grid((head_dim + block.x - 1) / block.x,
                    num_attention_heads);
    causal_attention_decode_kernel<<<grid, block, 0, stream>>>(q_token,
                                                               k_cache,
                                                               v_cache,
                                                               output,
                                                               cached_tokens,
                                                               num_attention_heads,
                                                               num_key_value_heads,
                                                               head_dim);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

LlamaDecoderLayerWeights resolve_llama_decoder_layer_weights(
    const void* device_layer_slot,
    const LayerExecutionPlan& plan) {
    validate_pointer(device_layer_slot, "device_layer_slot");
    require_condition(!plan.placements.empty(), "layer plan has no placements");
    const auto* base = static_cast<const unsigned char*>(device_layer_slot);
    auto resolve = [&](TensorRole role, const char* name) -> const half* {
        const TensorPlacement* placement = find_role_placement(plan, role);
        require_condition(placement != nullptr, std::string("missing placement for ") + name);
        require_condition((placement->slot_offset % alignof(half)) == 0,
                          std::string("placement is not half-aligned for ") + name);
        return reinterpret_cast<const half*>(base + placement->slot_offset);
    };

    LlamaDecoderLayerWeights weights{};
    weights.attn_norm = resolve(TensorRole::ATTN_NORM, "ATTN_NORM");
    weights.q_proj = resolve(TensorRole::ATTN_Q, "ATTN_Q");
    weights.k_proj = resolve(TensorRole::ATTN_K, "ATTN_K");
    weights.v_proj = resolve(TensorRole::ATTN_V, "ATTN_V");
    weights.o_proj = resolve(TensorRole::ATTN_O, "ATTN_O");
    weights.mlp_norm = resolve(TensorRole::MLP_NORM, "MLP_NORM");
    weights.gate_proj = resolve(TensorRole::MLP_GATE, "MLP_GATE");
    weights.up_proj = resolve(TensorRole::MLP_UP, "MLP_UP");
    weights.down_proj = resolve(TensorRole::MLP_DOWN, "MLP_DOWN");
    return weights;
}

QuantizedLlamaDecoderLayerWeights bind_quantized_llama_decoder_layer_weights(
    const void* device_layer_slot,
    const LayerExecutionPlan& plan,
    const QuantizedProjection& q_proj,
    const QuantizedProjectionMetadataWorkspace& q_workspace,
    const QuantizedProjection& k_proj,
    const QuantizedProjectionMetadataWorkspace& k_workspace,
    const QuantizedProjection& v_proj,
    const QuantizedProjectionMetadataWorkspace& v_workspace,
    const QuantizedProjection& o_proj,
    const QuantizedProjectionMetadataWorkspace& o_workspace,
    const QuantizedProjection& gate_proj,
    const QuantizedProjectionMetadataWorkspace& gate_workspace,
    const QuantizedProjection& up_proj,
    const QuantizedProjectionMetadataWorkspace& up_workspace,
    const QuantizedProjection& down_proj,
    const QuantizedProjectionMetadataWorkspace& down_workspace,
    int batch_tokens) {
    validate_pointer(device_layer_slot, "device_layer_slot");
    require_condition(!plan.placements.empty(), "layer plan has no placements");
    require_projection_role(q_proj, QuantizedProjectionRole::ATTN_Q, "q_proj");
    require_projection_role(k_proj, QuantizedProjectionRole::ATTN_K, "k_proj");
    require_projection_role(v_proj, QuantizedProjectionRole::ATTN_V, "v_proj");
    require_projection_role(o_proj, QuantizedProjectionRole::ATTN_O, "o_proj");
    require_projection_role(gate_proj, QuantizedProjectionRole::MLP_GATE, "gate_proj");
    require_projection_role(up_proj, QuantizedProjectionRole::MLP_UP, "up_proj");
    require_projection_role(down_proj, QuantizedProjectionRole::MLP_DOWN, "down_proj");

    const auto* base = static_cast<const unsigned char*>(device_layer_slot);
    auto resolve_norm = [&](TensorRole role, const char* name) -> const half* {
        const TensorPlacement* placement = find_role_placement(plan, role);
        require_condition(placement != nullptr, std::string("missing placement for ") + name);
        require_condition((placement->slot_offset % alignof(half)) == 0,
                          std::string("placement is not half-aligned for ") + name);
        return reinterpret_cast<const half*>(base + placement->slot_offset);
    };

    QuantizedLlamaDecoderLayerWeights weights{};
    weights.attn_norm = resolve_norm(TensorRole::ATTN_NORM, "ATTN_NORM");
    weights.q_proj = bind_quantized_projection_runtime_view(q_proj,
                                                            plan,
                                                            device_layer_slot,
                                                            q_workspace,
                                                            batch_tokens);
    weights.k_proj = bind_quantized_projection_runtime_view(k_proj,
                                                            plan,
                                                            device_layer_slot,
                                                            k_workspace,
                                                            batch_tokens);
    weights.v_proj = bind_quantized_projection_runtime_view(v_proj,
                                                            plan,
                                                            device_layer_slot,
                                                            v_workspace,
                                                            batch_tokens);
    weights.o_proj = bind_quantized_projection_runtime_view(o_proj,
                                                            plan,
                                                            device_layer_slot,
                                                            o_workspace,
                                                            batch_tokens);
    weights.mlp_norm = resolve_norm(TensorRole::MLP_NORM, "MLP_NORM");
    weights.gate_proj = bind_quantized_projection_runtime_view(gate_proj,
                                                               plan,
                                                               device_layer_slot,
                                                               gate_workspace,
                                                               batch_tokens);
    weights.up_proj = bind_quantized_projection_runtime_view(up_proj,
                                                             plan,
                                                             device_layer_slot,
                                                             up_workspace,
                                                             batch_tokens);
    weights.down_proj = bind_quantized_projection_runtime_view(down_proj,
                                                               plan,
                                                               device_layer_slot,
                                                               down_workspace,
                                                               batch_tokens);
    return weights;
}

void execute_llama_decoder_layer_prefill(const half* input,
                                         half* output,
                                         const LlamaDecoderLayerWeights& weights,
                                         ActivationWorkspace& workspace,
                                         const LlamaDecoderLayerConfig& config,
                                         cudaStream_t stream) {
    validate_pointer(input, "input");
    validate_pointer(output, "output");
    validate_layer_weights(weights);
    validate_layer_config(config);
    require_condition(workspace.tokens == config.tokens, "workspace token count mismatch");
    require_condition(workspace.hidden_size == config.hidden_size,
                      "workspace hidden_size mismatch");
    require_condition(workspace.intermediate_size == config.intermediate_size,
                      "workspace intermediate_size mismatch");
    validate_pointer(workspace.hidden, "workspace.hidden");
    validate_pointer(workspace.residual, "workspace.residual");
    validate_pointer(workspace.normalized, "workspace.normalized");
    validate_pointer(workspace.q, "workspace.q");
    validate_pointer(workspace.k, "workspace.k");
    validate_pointer(workspace.v, "workspace.v");
    validate_pointer(workspace.attention_out, "workspace.attention_out");
    validate_pointer(workspace.mlp_gate, "workspace.mlp_gate");
    validate_pointer(workspace.mlp_up, "workspace.mlp_up");
    validate_pointer(workspace.mlp_down, "workspace.mlp_down");

    const int hidden_count = config.tokens * config.hidden_size;
    const int kv_hidden = config.num_key_value_heads * config.head_dim;
    const int kv_count = config.tokens * kv_hidden;
    const int intermediate_count = config.tokens * config.intermediate_size;

    launch_copy_half(input, workspace.residual, hidden_count, stream);
    launch_rmsnorm(workspace.residual,
                   weights.attn_norm,
                   workspace.normalized,
                   config.tokens,
                   config.hidden_size,
                   config.rms_norm_epsilon,
                   stream);
    launch_dense_matmul_fp16(workspace.normalized,
                             weights.q_proj,
                             nullptr,
                             workspace.q,
                             config.tokens,
                             config.hidden_size,
                             config.hidden_size,
                             stream);
    launch_dense_matmul_fp16(workspace.normalized,
                             weights.k_proj,
                             nullptr,
                             workspace.k,
                             config.tokens,
                             kv_hidden,
                             config.hidden_size,
                             stream);
    launch_dense_matmul_fp16(workspace.normalized,
                             weights.v_proj,
                             nullptr,
                             workspace.v,
                             config.tokens,
                             kv_hidden,
                             config.hidden_size,
                             stream);
    launch_rope(workspace.q,
                workspace.k,
                config.tokens,
                config.num_attention_heads,
                config.num_key_value_heads,
                config.head_dim,
                config.position_offset,
                config.rope_theta,
                stream);
    launch_causal_attention_prefill(workspace.q,
                                    workspace.k,
                                    workspace.v,
                                    workspace.attention_out,
                                    config.tokens,
                                    config.num_attention_heads,
                                    config.num_key_value_heads,
                                    config.head_dim,
                                    stream);
    launch_dense_matmul_fp16(workspace.attention_out,
                             weights.o_proj,
                             nullptr,
                             workspace.hidden,
                             config.tokens,
                             config.hidden_size,
                             config.hidden_size,
                             stream);
    launch_residual_add(workspace.residual, workspace.hidden, workspace.residual, hidden_count, stream);
    launch_rmsnorm(workspace.residual,
                   weights.mlp_norm,
                   workspace.normalized,
                   config.tokens,
                   config.hidden_size,
                   config.rms_norm_epsilon,
                   stream);
    launch_dense_matmul_fp16(workspace.normalized,
                             weights.gate_proj,
                             nullptr,
                             workspace.mlp_gate,
                             config.tokens,
                             config.intermediate_size,
                             config.hidden_size,
                             stream);
    launch_dense_matmul_fp16(workspace.normalized,
                             weights.up_proj,
                             nullptr,
                             workspace.mlp_up,
                             config.tokens,
                             config.intermediate_size,
                             config.hidden_size,
                             stream);
    launch_swiglu(workspace.mlp_gate, workspace.mlp_up, workspace.mlp_gate, intermediate_count, stream);
    launch_dense_matmul_fp16(workspace.mlp_gate,
                             weights.down_proj,
                             nullptr,
                             workspace.mlp_down,
                             config.tokens,
                             config.hidden_size,
                             config.intermediate_size,
                             stream);
    launch_residual_add(workspace.residual, workspace.mlp_down, output, hidden_count, stream);
    if (kv_count <= 0) {
        fail("invalid KV projection size");
    }
}

void execute_quantized_llama_decoder_layer_prefill(
    const half* input,
    half* output,
    const QuantizedLlamaDecoderLayerWeights& weights,
    ActivationWorkspace& workspace,
    const LlamaDecoderLayerConfig& config,
    cudaStream_t stream) {
    validate_pointer(input, "input");
    validate_pointer(output, "output");
    validate_layer_config(config);
    validate_quantized_layer_weights(weights, config);
    require_condition(workspace.tokens == config.tokens, "workspace token count mismatch");
    require_condition(workspace.hidden_size == config.hidden_size,
                      "workspace hidden_size mismatch");
    require_condition(workspace.intermediate_size == config.intermediate_size,
                      "workspace intermediate_size mismatch");
    validate_pointer(workspace.hidden, "workspace.hidden");
    validate_pointer(workspace.residual, "workspace.residual");
    validate_pointer(workspace.normalized, "workspace.normalized");
    validate_pointer(workspace.q, "workspace.q");
    validate_pointer(workspace.k, "workspace.k");
    validate_pointer(workspace.v, "workspace.v");
    validate_pointer(workspace.attention_out, "workspace.attention_out");
    validate_pointer(workspace.mlp_gate, "workspace.mlp_gate");
    validate_pointer(workspace.mlp_up, "workspace.mlp_up");
    validate_pointer(workspace.mlp_down, "workspace.mlp_down");

    const int hidden_count = config.tokens * config.hidden_size;
    const int kv_hidden = config.num_key_value_heads * config.head_dim;
    const int kv_count = config.tokens * kv_hidden;
    const int intermediate_count = config.tokens * config.intermediate_size;

    launch_copy_half(input, workspace.residual, hidden_count, stream);
    launch_rmsnorm(workspace.residual,
                   weights.attn_norm,
                   workspace.normalized,
                   config.tokens,
                   config.hidden_size,
                   config.rms_norm_epsilon,
                   stream);
    launch_quantized_projection(workspace.normalized, workspace.q, weights.q_proj, nullptr, stream);
    launch_quantized_projection(workspace.normalized, workspace.k, weights.k_proj, nullptr, stream);
    launch_quantized_projection(workspace.normalized, workspace.v, weights.v_proj, nullptr, stream);
    launch_rope(workspace.q,
                workspace.k,
                config.tokens,
                config.num_attention_heads,
                config.num_key_value_heads,
                config.head_dim,
                config.position_offset,
                config.rope_theta,
                stream);
    launch_causal_attention_prefill(workspace.q,
                                    workspace.k,
                                    workspace.v,
                                    workspace.attention_out,
                                    config.tokens,
                                    config.num_attention_heads,
                                    config.num_key_value_heads,
                                    config.head_dim,
                                    stream);
    launch_quantized_projection(workspace.attention_out,
                                workspace.hidden,
                                weights.o_proj,
                                nullptr,
                                stream);
    launch_residual_add(workspace.residual, workspace.hidden, workspace.residual, hidden_count, stream);
    launch_rmsnorm(workspace.residual,
                   weights.mlp_norm,
                   workspace.normalized,
                   config.tokens,
                   config.hidden_size,
                   config.rms_norm_epsilon,
                   stream);
    launch_quantized_projection(workspace.normalized,
                                workspace.mlp_gate,
                                weights.gate_proj,
                                nullptr,
                                stream);
    launch_quantized_projection(workspace.normalized,
                                workspace.mlp_up,
                                weights.up_proj,
                                nullptr,
                                stream);
    launch_swiglu(workspace.mlp_gate, workspace.mlp_up, workspace.mlp_gate, intermediate_count, stream);
    launch_quantized_projection(workspace.mlp_gate,
                                workspace.mlp_down,
                                weights.down_proj,
                                nullptr,
                                stream);
    launch_residual_add(workspace.residual, workspace.mlp_down, output, hidden_count, stream);
    if (kv_count <= 0) {
        fail("invalid KV projection size");
    }
}

StreamedPrefillResult execute_streamed_llama_model_prefill(
    StreamingTensorStore& store,
    const ModelManifest& manifest,
    const LayerPlanSet& plans,
    const QuantizedAdapterReport& quantized_report,
    void* scratchpad_slot_a,
    void* scratchpad_slot_b,
    const half* input,
    half* output,
    ActivationWorkspace& workspace,
    const LlamaDecoderLayerConfig& base_config,
    cudaStream_t stream) {
    validate_pointer(input, "input");
    validate_pointer(output, "output");
    validate_pointer(scratchpad_slot_a, "scratchpad_slot_a");
    validate_pointer(scratchpad_slot_b, "scratchpad_slot_b");
    validate_pointer(store.host_staging_ptr, "store.host_staging_ptr");
    require_condition(quantized_report.supported, "quantized adapter report is unsupported");
    require_condition(manifest.config.num_hidden_layers > 0,
                      "manifest has no transformer layers");
    require_condition(plans.layers.size() ==
                          static_cast<size_t>(manifest.config.num_hidden_layers),
                      "layer plan count does not match manifest");
    validate_layer_config(base_config);
    require_condition(base_config.hidden_size == manifest.config.hidden_size,
                      "base config hidden_size does not match manifest");
    require_condition(base_config.intermediate_size == manifest.config.intermediate_size,
                      "base config intermediate_size does not match manifest");
    require_condition(base_config.num_attention_heads == manifest.config.num_attention_heads,
                      "base config attention heads do not match manifest");
    require_condition(base_config.num_key_value_heads == manifest.config.num_key_value_heads,
                      "base config kv heads do not match manifest");
    require_condition(workspace.tokens == base_config.tokens,
                      "workspace token count mismatch");
    require_condition(workspace.hidden_size == base_config.hidden_size,
                      "workspace hidden_size mismatch");
    require_condition(workspace.intermediate_size == base_config.intermediate_size,
                      "workspace intermediate_size mismatch");

    StreamedPrefillResult result{};
    const half* layer_input = input;
    for (int layer_id = 0; layer_id < manifest.config.num_hidden_layers; ++layer_id) {
        const LayerExecutionPlan& plan = require_layer_plan(plans, layer_id);
        void* slot = (layer_id & 1) == 0 ? scratchpad_slot_a : scratchpad_slot_b;
        ScheduledLayerTransfer transfer = schedule_layer_prefetch(store, plan, slot, stream);

        QuantizedProjectionMetadataWorkspace q_workspace{};
        QuantizedProjectionMetadataWorkspace k_workspace{};
        QuantizedProjectionMetadataWorkspace v_workspace{};
        QuantizedProjectionMetadataWorkspace o_workspace{};
        QuantizedProjectionMetadataWorkspace gate_workspace{};
        QuantizedProjectionMetadataWorkspace up_workspace{};
        QuantizedProjectionMetadataWorkspace down_workspace{};
        try {
            wait_for_layer_transfer(transfer);
            const QuantizedProjection& q_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::ATTN_Q);
            const QuantizedProjection& k_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::ATTN_K);
            const QuantizedProjection& v_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::ATTN_V);
            const QuantizedProjection& o_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::ATTN_O);
            const QuantizedProjection& gate_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::MLP_GATE);
            const QuantizedProjection& up_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::MLP_UP);
            const QuantizedProjection& down_proj = require_quantized_projection(
                quantized_report,
                layer_id,
                QuantizedProjectionRole::MLP_DOWN);

            q_workspace = create_and_upload_zero_workspace(store, q_proj, stream);
            k_workspace = create_and_upload_zero_workspace(store, k_proj, stream);
            v_workspace = create_and_upload_zero_workspace(store, v_proj, stream);
            o_workspace = create_and_upload_zero_workspace(store, o_proj, stream);
            gate_workspace = create_and_upload_zero_workspace(store, gate_proj, stream);
            up_workspace = create_and_upload_zero_workspace(store, up_proj, stream);
            down_workspace = create_and_upload_zero_workspace(store, down_proj, stream);

            const QuantizedLlamaDecoderLayerWeights weights =
                bind_quantized_llama_decoder_layer_weights(slot,
                                                           plan,
                                                           q_proj,
                                                           q_workspace,
                                                           k_proj,
                                                           k_workspace,
                                                           v_proj,
                                                           v_workspace,
                                                           o_proj,
                                                           o_workspace,
                                                           gate_proj,
                                                           gate_workspace,
                                                           up_proj,
                                                           up_workspace,
                                                           down_proj,
                                                           down_workspace,
                                                           base_config.tokens);
            half* layer_output =
                (layer_id == manifest.config.num_hidden_layers - 1) ? output : workspace.hidden;
            LlamaDecoderLayerConfig layer_config = base_config;
            execute_quantized_llama_decoder_layer_prefill(layer_input,
                                                          layer_output,
                                                          weights,
                                                          workspace,
                                                          layer_config,
                                                          stream);
            result.bytes_streamed += transfer.byte_count;
            ++result.layers_executed;
            layer_input = workspace.hidden;
            destroy_projection_workspaces(q_workspace,
                                          k_workspace,
                                          v_workspace,
                                          o_workspace,
                                          gate_workspace,
                                          up_workspace,
                                          down_workspace);
            destroy_scheduled_layer_transfer(transfer);
        } catch (...) {
            destroy_projection_workspaces(q_workspace,
                                          k_workspace,
                                          v_workspace,
                                          o_workspace,
                                          gate_workspace,
                                          up_workspace,
                                          down_workspace);
            destroy_scheduled_layer_transfer(transfer);
            throw;
        }
    }
    return result;
}

GreedyTokenResult execute_quantized_final_logits_greedy(
    const half* hidden_states,
    const half* final_norm_weight,
    const QuantizedProjectionRuntimeView& lm_head,
    ActivationWorkspace& workspace,
    half* logits,
    int tokens,
    int hidden_size,
    int vocab_size,
    float rms_norm_epsilon,
    cudaStream_t stream) {
    validate_pointer(hidden_states, "hidden_states");
    validate_pointer(final_norm_weight, "final_norm_weight");
    validate_pointer(logits, "logits");
    require_condition(tokens > 0, "tokens must be positive");
    require_condition(hidden_size > 0, "hidden_size must be positive");
    require_condition(vocab_size > 0, "vocab_size must be positive");
    require_condition(rms_norm_epsilon > 0.0f, "rms_norm_epsilon must be positive");
    require_condition(workspace.tokens == tokens, "workspace token count mismatch");
    require_condition(workspace.hidden_size == hidden_size, "workspace hidden_size mismatch");
    validate_pointer(workspace.normalized, "workspace.normalized");
    validate_quantized_view(lm_head,
                            QuantizedProjectionRole::LM_HEAD,
                            hidden_size,
                            vocab_size,
                            "lm_head");

    launch_rmsnorm(hidden_states,
                   final_norm_weight,
                   workspace.normalized,
                   tokens,
                   hidden_size,
                   rms_norm_epsilon,
                   stream);
    launch_quantized_projection(workspace.normalized, logits, lm_head, nullptr, stream);

    int* device_token = nullptr;
    float* device_logit = nullptr;
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&device_token), sizeof(int)));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&device_logit), sizeof(float)));
        greedy_last_token_kernel<<<1, kThreads, 0, stream>>>(logits,
                                                             tokens,
                                                             vocab_size,
                                                             device_token,
                                                             device_logit);
        SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
        GreedyTokenResult result{};
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(&result.token_id,
                                               device_token,
                                               sizeof(int),
                                               cudaMemcpyDeviceToHost,
                                               stream));
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(&result.logit,
                                               device_logit,
                                               sizeof(float),
                                               cudaMemcpyDeviceToHost,
                                               stream));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
        cudaFree(device_token);
        cudaFree(device_logit);
        return result;
    } catch (...) {
        if (device_token != nullptr) {
            cudaFree(device_token);
        }
        if (device_logit != nullptr) {
            cudaFree(device_logit);
        }
        throw;
    }
}

DenseLmHeadGreedyResult execute_dense_lm_head_greedy_streamed(
    StreamingTensorStore& store,
    const ManifestTensor& lm_head_weight,
    const half* hidden_states,
    const half* final_norm_weight,
    ActivationWorkspace& workspace,
    int tokens,
    int hidden_size,
    int vocab_size,
    int vocab_tile_rows,
    float rms_norm_epsilon,
    cudaStream_t stream) {
    validate_pointer(hidden_states, "hidden_states");
    validate_pointer(final_norm_weight, "final_norm_weight");
    validate_pointer(store.host_staging_ptr, "store.host_staging_ptr");
    require_condition(tokens > 0, "tokens must be positive");
    require_condition(hidden_size > 0, "hidden_size must be positive");
    require_condition(vocab_size > 0, "vocab_size must be positive");
    require_condition(vocab_tile_rows > 0, "vocab_tile_rows must be positive");
    require_condition(rms_norm_epsilon > 0.0f, "rms_norm_epsilon must be positive");
    require_condition(lm_head_weight.role == TensorRole::LM_HEAD,
                      "lm_head_weight tensor role must be LM_HEAD");
    require_condition(lm_head_weight.metadata.data_type == "F16" ||
                          lm_head_weight.metadata.data_type == "FLOAT16" ||
                          lm_head_weight.metadata.data_type == "float16",
                      "dense lm_head_weight must be FP16");
    require_condition(lm_head_weight.metadata.shape.size() == 2,
                      "dense lm_head_weight must be rank-2");
    require_condition(lm_head_weight.metadata.shape[0] == vocab_size &&
                          lm_head_weight.metadata.shape[1] == hidden_size,
                      "dense lm_head_weight shape must be [vocab_size, hidden_size]");
    require_condition(workspace.tokens == tokens, "workspace token count mismatch");
    require_condition(workspace.hidden_size == hidden_size, "workspace hidden_size mismatch");
    validate_pointer(workspace.normalized, "workspace.normalized");

    launch_rmsnorm(hidden_states,
                   final_norm_weight,
                   workspace.normalized,
                   tokens,
                   hidden_size,
                   rms_norm_epsilon,
                   stream);
    const half* last_hidden =
        workspace.normalized + static_cast<size_t>(tokens - 1) * static_cast<size_t>(hidden_size);

    half* device_tile_weights = nullptr;
    half* device_tile_logits = nullptr;
    const int tile_rows = std::min(vocab_tile_rows, vocab_size);
    const size_t tile_weight_count =
        checked_count(tile_rows, hidden_size, "dense lm_head tile");
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&device_tile_weights),
                                          tile_weight_count * sizeof(half)));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&device_tile_logits),
                                          static_cast<size_t>(tile_rows) * sizeof(half)));
        std::vector<half> host_logits(static_cast<size_t>(tile_rows));

        DenseLmHeadGreedyResult result{};
        result.token_id = 0;
        result.logit = -3.402823466e+38F;

        for (int vocab_start = 0; vocab_start < vocab_size; vocab_start += tile_rows) {
            const int rows = std::min(tile_rows, vocab_size - vocab_start);
            const size_t tile_bytes =
                static_cast<size_t>(rows) * static_cast<size_t>(hidden_size) * sizeof(half);
            const size_t tensor_offset =
                static_cast<size_t>(vocab_start) * static_cast<size_t>(hidden_size) *
                sizeof(half);
            const StagedTensor staged =
                stage_tensor_slice(store, lm_head_weight, tensor_offset, tile_bytes);
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(device_tile_weights,
                                                   staged.host_ptr,
                                                   staged.byte_size,
                                                   cudaMemcpyHostToDevice,
                                                   stream));
            dense_lm_head_tile_kernel<<<rows, kThreads, 0, stream>>>(last_hidden,
                                                                      device_tile_weights,
                                                                      device_tile_logits,
                                                                      rows,
                                                                      hidden_size);
            SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(host_logits.data(),
                                                   device_tile_logits,
                                                   static_cast<size_t>(rows) * sizeof(half),
                                                   cudaMemcpyDeviceToHost,
                                                   stream));
            SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
            for (int row = 0; row < rows; ++row) {
                const int token_id = vocab_start + row;
                const float logit = __half2float(host_logits[static_cast<size_t>(row)]);
                if (logit > result.logit ||
                    (logit == result.logit && token_id < result.token_id)) {
                    result.logit = logit;
                    result.token_id = token_id;
                }
            }
            result.bytes_streamed += staged.byte_size;
            ++result.tiles_processed;
        }

        cudaFree(device_tile_weights);
        cudaFree(device_tile_logits);
        return result;
    } catch (...) {
        if (device_tile_weights != nullptr) {
            cudaFree(device_tile_weights);
        }
        if (device_tile_logits != nullptr) {
            cudaFree(device_tile_logits);
        }
        throw;
    }
}

SampledTokenResult execute_dense_lm_head_sample_streamed(
    StreamingTensorStore& store,
    const ManifestTensor& lm_head_weight,
    const half* hidden_states,
    const half* final_norm_weight,
    ActivationWorkspace& workspace,
    int tokens,
    int hidden_size,
    int vocab_size,
    int vocab_tile_rows,
    float rms_norm_epsilon,
    const int* recent_tokens,
    int recent_token_count,
    const SamplingConfig& sampling,
    cudaStream_t stream) {
    validate_dense_lm_head_inputs(store,
                                  lm_head_weight,
                                  hidden_states,
                                  final_norm_weight,
                                  workspace,
                                  tokens,
                                  hidden_size,
                                  vocab_size,
                                  vocab_tile_rows,
                                  rms_norm_epsilon);
    require_condition(recent_token_count >= 0, "recent_token_count must be non-negative");
    if (recent_token_count > 0) {
        validate_pointer(recent_tokens, "recent_tokens");
    }
    require_condition(sampling.temperature >= 0.0f, "sampling temperature must be non-negative");
    require_condition(sampling.top_k >= 0, "sampling top_k must be non-negative");
    require_condition(sampling.top_p > 0.0f && sampling.top_p <= 1.0f,
                      "sampling top_p must be in (0, 1]");
    require_condition(sampling.repetition_penalty >= 1.0f,
                      "sampling repetition_penalty must be at least 1");

    launch_rmsnorm(hidden_states,
                   final_norm_weight,
                   workspace.normalized,
                   tokens,
                   hidden_size,
                   rms_norm_epsilon,
                   stream);
    const half* last_hidden =
        workspace.normalized + static_cast<size_t>(tokens - 1) * static_cast<size_t>(hidden_size);

    half* device_tile_weights = nullptr;
    half* device_tile_logits = nullptr;
    const int tile_rows = std::min(vocab_tile_rows, vocab_size);
    const size_t tile_weight_count =
        checked_count(tile_rows, hidden_size, "dense lm_head sample tile");
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&device_tile_weights),
                                          tile_weight_count * sizeof(half)));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&device_tile_logits),
                                          static_cast<size_t>(tile_rows) * sizeof(half)));

        std::vector<half> host_tile_logits(static_cast<size_t>(tile_rows));
        std::vector<float> logits(static_cast<size_t>(vocab_size));
        SampledTokenResult result{};
        result.token_id = 0;
        result.logit = -3.402823466e+38F;

        for (int vocab_start = 0; vocab_start < vocab_size; vocab_start += tile_rows) {
            const int rows = std::min(tile_rows, vocab_size - vocab_start);
            const size_t tile_bytes =
                static_cast<size_t>(rows) * static_cast<size_t>(hidden_size) * sizeof(half);
            const size_t tensor_offset =
                static_cast<size_t>(vocab_start) * static_cast<size_t>(hidden_size) *
                sizeof(half);
            const StagedTensor staged =
                stage_tensor_slice(store, lm_head_weight, tensor_offset, tile_bytes);
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(device_tile_weights,
                                                   staged.host_ptr,
                                                   staged.byte_size,
                                                   cudaMemcpyHostToDevice,
                                                   stream));
            dense_lm_head_tile_kernel<<<rows, kThreads, 0, stream>>>(last_hidden,
                                                                      device_tile_weights,
                                                                      device_tile_logits,
                                                                      rows,
                                                                      hidden_size);
            SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(host_tile_logits.data(),
                                                   device_tile_logits,
                                                   static_cast<size_t>(rows) * sizeof(half),
                                                   cudaMemcpyDeviceToHost,
                                                   stream));
            SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
            for (int row = 0; row < rows; ++row) {
                logits[static_cast<size_t>(vocab_start + row)] =
                    __half2float(host_tile_logits[static_cast<size_t>(row)]);
            }
            result.bytes_streamed += staged.byte_size;
            ++result.tiles_processed;
        }

        if (sampling.repetition_penalty > 1.0f) {
            for (int index = 0; index < recent_token_count; ++index) {
                const int token_id = recent_tokens[index];
                if (token_id >= 0 && token_id < vocab_size) {
                    float& value = logits[static_cast<size_t>(token_id)];
                    value = value > 0.0f ? value / sampling.repetition_penalty
                                         : value * sampling.repetition_penalty;
                }
            }
        }

        std::vector<SamplingCandidate> candidates;
        candidates.reserve(static_cast<size_t>(vocab_size));
        for (int token_id = 0; token_id < vocab_size; ++token_id) {
            candidates.push_back({token_id, logits[static_cast<size_t>(token_id)], 0.0f});
        }
        std::sort(candidates.begin(), candidates.end(), better_candidate);
        if (sampling.top_k > 0 && sampling.top_k < static_cast<int>(candidates.size())) {
            candidates.resize(static_cast<size_t>(sampling.top_k));
        }

        if (sampling.temperature == 0.0f) {
            result.token_id = candidates.front().token_id;
            result.logit = candidates.front().logit;
        } else {
            const float inverse_temperature = 1.0f / sampling.temperature;
            float max_scaled = -3.402823466e+38F;
            for (const SamplingCandidate& candidate : candidates) {
                max_scaled = std::max(max_scaled, candidate.logit * inverse_temperature);
            }
            double total_weight = 0.0;
            for (SamplingCandidate& candidate : candidates) {
                candidate.weight = std::exp(candidate.logit * inverse_temperature - max_scaled);
                total_weight += static_cast<double>(candidate.weight);
            }
            require_condition(total_weight > 0.0, "sampling produced zero probability mass");

            if (sampling.top_p < 1.0f) {
                double cumulative = 0.0;
                size_t keep = 0;
                while (keep < candidates.size()) {
                    cumulative += static_cast<double>(candidates[keep].weight) / total_weight;
                    ++keep;
                    if (cumulative >= static_cast<double>(sampling.top_p)) {
                        break;
                    }
                }
                candidates.resize(std::max<size_t>(keep, 1));
                total_weight = 0.0;
                for (const SamplingCandidate& candidate : candidates) {
                    total_weight += static_cast<double>(candidate.weight);
                }
            }

            uint64_t state = sampling.seed == 0 ? 0x9E3779B97F4A7C15ULL : sampling.seed;
            const double threshold = next_unit_interval(state) * total_weight;
            double cumulative = 0.0;
            const SamplingCandidate* chosen = &candidates.back();
            for (const SamplingCandidate& candidate : candidates) {
                cumulative += static_cast<double>(candidate.weight);
                if (cumulative >= threshold) {
                    chosen = &candidate;
                    break;
                }
            }
            result.token_id = chosen->token_id;
            result.logit = chosen->logit;
        }

        cudaFree(device_tile_weights);
        cudaFree(device_tile_logits);
        return result;
    } catch (...) {
        if (device_tile_weights != nullptr) {
            cudaFree(device_tile_weights);
        }
        if (device_tile_logits != nullptr) {
            cudaFree(device_tile_logits);
        }
        throw;
    }
}

GreedyDecodeResult execute_greedy_decode_loop(
    StreamingTensorStore& store,
    const ModelManifest& manifest,
    const LayerPlanSet& plans,
    const QuantizedAdapterReport& quantized_report,
    void* scratchpad_slot_a,
    void* scratchpad_slot_b,
    const half* token_embeddings,
    int vocab_size,
    const half* final_norm_weight,
    const QuantizedProjectionRuntimeView& lm_head,
    int initial_token_id,
    int* output_tokens,
    int output_token_capacity,
    const GreedyDecodeConfig& decode_config,
    ActivationWorkspace& workspace,
    half* current_hidden,
    half* model_hidden,
    half* logits,
    KVCacheRuntime* kv_cache,
    cudaStream_t stream) {
    validate_pointer(token_embeddings, "token_embeddings");
    validate_pointer(final_norm_weight, "final_norm_weight");
    validate_pointer(output_tokens, "output_tokens");
    validate_pointer(current_hidden, "current_hidden");
    validate_pointer(model_hidden, "model_hidden");
    validate_pointer(logits, "logits");
    require_condition(decode_config.max_new_tokens > 0,
                      "max_new_tokens must be positive");
    require_condition(output_token_capacity >= decode_config.max_new_tokens,
                      "output token capacity is smaller than max_new_tokens");
    require_condition(decode_config.sequence_id >= 0,
                      "sequence_id must be non-negative");
    require_condition(vocab_size == manifest.config.vocab_size,
                      "vocab_size does not match manifest");
    require_condition(initial_token_id >= 0 && initial_token_id < vocab_size,
                      "initial_token_id is out of range");
    require_condition(workspace.tokens == 1,
                      "decode workspace must be configured for one token");
    require_condition(workspace.hidden_size == manifest.config.hidden_size,
                      "decode workspace hidden_size mismatch");
    require_condition(workspace.intermediate_size == manifest.config.intermediate_size,
                      "decode workspace intermediate_size mismatch");

    GreedyDecodeResult result{};
    int current_token = initial_token_id;
    for (int step = 0; step < decode_config.max_new_tokens; ++step) {
        launch_token_embedding_lookup(token_embeddings,
                                      current_token,
                                      current_hidden,
                                      vocab_size,
                                      manifest.config.hidden_size,
                                      stream);
        LlamaDecoderLayerConfig layer_config{};
        layer_config.tokens = 1;
        layer_config.hidden_size = manifest.config.hidden_size;
        layer_config.intermediate_size = manifest.config.intermediate_size;
        layer_config.num_attention_heads = manifest.config.num_attention_heads;
        layer_config.num_key_value_heads = manifest.config.num_key_value_heads;
        layer_config.head_dim =
            manifest.config.hidden_size / manifest.config.num_attention_heads;
        layer_config.position_offset = step;
        layer_config.rope_theta = static_cast<float>(manifest.config.rope_theta);
        layer_config.rms_norm_epsilon = static_cast<float>(manifest.config.rms_norm_eps);

        (void)execute_streamed_llama_model_prefill(store,
                                                   manifest,
                                                   plans,
                                                   quantized_report,
                                                   scratchpad_slot_a,
                                                   scratchpad_slot_b,
                                                   current_hidden,
                                                   model_hidden,
                                                   workspace,
                                                   layer_config,
                                                   stream);
        const GreedyTokenResult greedy = execute_quantized_final_logits_greedy(
            model_hidden,
            final_norm_weight,
            lm_head,
            workspace,
            logits,
            1,
            manifest.config.hidden_size,
            vocab_size,
            static_cast<float>(manifest.config.rms_norm_eps),
            stream);
        output_tokens[step] = greedy.token_id;
        current_token = greedy.token_id;
        ++result.tokens_generated;
        result.last_token_id = greedy.token_id;
        if (kv_cache != nullptr) {
            record_decode_token_in_kv_cache(*kv_cache,
                                            decode_config.sequence_id,
                                            step,
                                            greedy.token_id,
                                            stream);
        }
        if (decode_config.eos_token_id >= 0 &&
            greedy.token_id == decode_config.eos_token_id) {
            break;
        }
    }
    return result;
}

} // namespace spoolstream::core
