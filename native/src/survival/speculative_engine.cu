#include "spoolstream/speculative_engine.h"
#include "spoolstream/memory_manager.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace spoolstream::core {
namespace {

constexpr int kPredictThreads = 128;
constexpr float kLowestDeviceFloat = -3.4028234663852886e+38F;

std::string format_error(const std::string& message) {
    return "speculative engine: " + message;
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(format_error(message));
    }
}

void validate_config(const SpeculativeConfig& config) {
    require_condition(config.hidden_size > 0, "hidden_size must be positive");
    require_condition(config.vocab_size > 0, "vocab_size must be positive");
    require_condition(config.max_nodes > 0, "max_nodes must be positive");
    require_condition(config.top_k > 0, "top_k must be positive");
    require_condition(config.top_k <= config.vocab_size, "top_k cannot exceed vocab_size");
    require_condition(config.max_nodes >= config.top_k,
                      "max_nodes must be at least top_k for fixed candidate trees");
}

std::vector<int> copy_and_validate_parents(const int* device_parents, int node_count) {
    require_condition(device_parents != nullptr, "device_parents is null");
    require_condition(node_count > 0, "node_count must be positive");

    std::vector<int> parents(static_cast<size_t>(node_count));
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(parents.data(),
                                     device_parents,
                                     sizeof(int) * parents.size(),
                                     cudaMemcpyDeviceToHost));

    require_condition(parents[0] == -1 || parents[0] == 0,
                      "root parent must be -1 or 0");
    for (int node = 1; node < node_count; ++node) {
        if (parents[static_cast<size_t>(node)] < 0 ||
            parents[static_cast<size_t>(node)] >= node) {
            std::ostringstream oss;
            oss << "malformed parent at node " << node << ": "
                << parents[static_cast<size_t>(node)];
            throw std::runtime_error(format_error(oss.str()));
        }
    }
    return parents;
}

__device__ bool logit_is_better(float candidate,
                                int candidate_token,
                                float current,
                                int current_token) {
    return candidate > current || (candidate == current && candidate_token < current_token);
}

__global__ void eagle_predict_heads_kernel(const half* hidden_states,
                                           const half* head_weights,
                                           const half* head_bias,
                                           half* candidate_logits,
                                           int* candidate_tokens,
                                           int sequence_length,
                                           int hidden_size,
                                           int vocab_size,
                                           int top_k) {
    const int row = blockIdx.x;
    if (row >= sequence_length) {
        return;
    }

    for (int vocab = threadIdx.x; vocab < vocab_size; vocab += blockDim.x) {
        float accumulator = 0.0f;
        for (int hidden = 0; hidden < hidden_size; ++hidden) {
            const half lhs =
                hidden_states[static_cast<size_t>(row) * hidden_size + hidden];
            const half rhs =
                head_weights[static_cast<size_t>(hidden) * vocab_size + vocab];
            accumulator += __half2float(lhs) * __half2float(rhs);
        }
        if (head_bias != nullptr) {
            accumulator += __half2float(head_bias[vocab]);
        }
        candidate_logits[static_cast<size_t>(row) * vocab_size + vocab] =
            __float2half(accumulator);
    }

    __syncthreads();

    if (threadIdx.x == 0) {
        for (int rank = 0; rank < top_k; ++rank) {
            float best_value = kLowestDeviceFloat;
            int best_token = 0;
            bool found = false;

            for (int token = 0; token < vocab_size; ++token) {
                bool already_selected = false;
                for (int prior = 0; prior < rank; ++prior) {
                    const int prior_token =
                        candidate_tokens[static_cast<size_t>(row) * top_k + prior];
                    if (prior_token == token) {
                        already_selected = true;
                        break;
                    }
                }
                if (already_selected) {
                    continue;
                }

                const float value = __half2float(
                    candidate_logits[static_cast<size_t>(row) * vocab_size + token]);
                if (!found || logit_is_better(value, token, best_value, best_token)) {
                    best_value = value;
                    best_token = token;
                    found = true;
                }
            }

            candidate_tokens[static_cast<size_t>(row) * top_k + rank] = best_token;
        }
    }
}

__device__ bool is_ancestor_or_self(int possible_ancestor,
                                    int node,
                                    const int* parents,
                                    int node_count) {
    int cursor = node;
    for (int depth = 0; depth < node_count; ++depth) {
        if (cursor == possible_ancestor) {
            return true;
        }
        if (cursor <= 0) {
            return false;
        }
        cursor = parents[cursor];
    }
    return false;
}

__global__ void generate_tree_attention_mask_kernel(const int* parents,
                                                    half* mask,
                                                    int node_count) {
    const int linear = blockIdx.x * blockDim.x + threadIdx.x;
    const int total = node_count * node_count;
    if (linear >= total) {
        return;
    }

    const int row = linear / node_count;
    const int col = linear - row * node_count;
    const bool allowed = is_ancestor_or_self(row, col, parents, node_count);
    mask[linear] = allowed ? __float2half(0.0f) : __ushort_as_half(0xFC00U);
}

} // namespace

void launch_eagle_predict_heads(const half* hidden_states,
                                const half* head_weights,
                                const half* head_bias,
                                half* candidate_logits,
                                int* candidate_tokens,
                                int sequence_length,
                                const SpeculativeConfig& config,
                                cudaStream_t stream) {
    validate_config(config);
    require_condition(sequence_length > 0, "sequence_length must be positive");
    require_condition(sequence_length <= config.max_nodes,
                      "sequence_length cannot exceed max_nodes");
    require_condition(hidden_states != nullptr, "hidden_states is null");
    require_condition(head_weights != nullptr, "head_weights is null");
    require_condition(candidate_logits != nullptr, "candidate_logits is null");
    require_condition(candidate_tokens != nullptr, "candidate_tokens is null");

    eagle_predict_heads_kernel<<<sequence_length, kPredictThreads, 0, stream>>>(
        hidden_states,
        head_weights,
        head_bias,
        candidate_logits,
        candidate_tokens,
        sequence_length,
        config.hidden_size,
        config.vocab_size,
        config.top_k);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

void generate_tree_attention_mask(const int* device_parents,
                                  half* device_mask,
                                  int node_count,
                                  cudaStream_t stream) {
    require_condition(device_mask != nullptr, "device_mask is null");
    copy_and_validate_parents(device_parents, node_count);

    const int total = node_count * node_count;
    const int threads = 256;
    const int blocks = (total + threads - 1) / threads;
    generate_tree_attention_mask_kernel<<<blocks, threads, 0, stream>>>(
        device_parents,
        device_mask,
        node_count);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

VerificationResult verify_speculative_tree_greedy(const half* main_logits,
                                                  const SpeculativeTree& tree,
                                                  int vocab_size,
                                                  cudaStream_t stream) {
    require_condition(stream == nullptr,
                      "verify_speculative_tree_greedy currently returns host data and requires the default stream");
    require_condition(main_logits != nullptr, "main_logits is null");
    require_condition(tree.device_tokens != nullptr, "tree.device_tokens is null");
    require_condition(vocab_size > 0, "vocab_size must be positive");

    const std::vector<int> parents =
        copy_and_validate_parents(tree.device_parents, tree.node_count);

    std::vector<int> tokens(static_cast<size_t>(tree.node_count));
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(tokens.data(),
                                     tree.device_tokens,
                                     sizeof(int) * tokens.size(),
                                     cudaMemcpyDeviceToHost));

    const size_t logits_count =
        static_cast<size_t>(tree.node_count) * static_cast<size_t>(vocab_size);
    std::vector<half> logits(logits_count);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(logits.data(),
                                     main_logits,
                                     sizeof(half) * logits.size(),
                                     cudaMemcpyDeviceToHost));

    std::vector<int> argmax_tokens(static_cast<size_t>(tree.node_count), 0);
    for (int node = 0; node < tree.node_count; ++node) {
        float best_value = -std::numeric_limits<float>::infinity();
        int best_token = 0;
        for (int token = 0; token < vocab_size; ++token) {
            const float value = __half2float(
                logits[static_cast<size_t>(node) * static_cast<size_t>(vocab_size) +
                       static_cast<size_t>(token)]);
            if (value > best_value || (value == best_value && token < best_token)) {
                best_value = value;
                best_token = token;
            }
        }
        argmax_tokens[static_cast<size_t>(node)] = best_token;
    }

    VerificationResult result{};
    result.accepted_count = 0;
    result.terminal_node = 0;

    int current_node = 0;
    while (true) {
        int selected_child = -1;
        for (int node = 1; node < tree.node_count; ++node) {
            if (parents[static_cast<size_t>(node)] != current_node) {
                continue;
            }
            if (tokens[static_cast<size_t>(node)] ==
                argmax_tokens[static_cast<size_t>(node)]) {
                selected_child = node;
                break;
            }
        }

        if (selected_child < 0) {
            break;
        }

        current_node = selected_child;
        result.terminal_node = selected_child;
        ++result.accepted_count;
    }

    return result;
}

} // namespace spoolstream::core
