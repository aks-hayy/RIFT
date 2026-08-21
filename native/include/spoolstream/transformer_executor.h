#pragma once

#include "spoolstream/layer_scheduler.h"
#include "spoolstream/kv_cache.h"
#include "spoolstream/quantized_adapter.h"

#include <cstddef>
#include <cstdint>

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

namespace spoolstream::core {

struct ActivationWorkspace {
    half* hidden;
    half* residual;
    half* normalized;
    half* q;
    half* k;
    half* v;
    half* attention_out;
    half* mlp_gate;
    half* mlp_up;
    half* mlp_down;
    int tokens;
    int hidden_size;
    int intermediate_size;
};

struct LlamaDecoderLayerWeights {
    const half* attn_norm;
    const half* q_proj;
    const half* k_proj;
    const half* v_proj;
    const half* o_proj;
    const half* mlp_norm;
    const half* gate_proj;
    const half* up_proj;
    const half* down_proj;
};

struct QuantizedLlamaDecoderLayerWeights {
    const half* attn_norm;
    QuantizedProjectionRuntimeView q_proj;
    QuantizedProjectionRuntimeView k_proj;
    QuantizedProjectionRuntimeView v_proj;
    QuantizedProjectionRuntimeView o_proj;
    const half* mlp_norm;
    QuantizedProjectionRuntimeView gate_proj;
    QuantizedProjectionRuntimeView up_proj;
    QuantizedProjectionRuntimeView down_proj;
};

struct LlamaDecoderLayerConfig {
    int tokens;
    int hidden_size;
    int intermediate_size;
    int num_attention_heads;
    int num_key_value_heads;
    int head_dim;
    int position_offset;
    float rope_theta;
    float rms_norm_epsilon;
};

struct StreamedPrefillResult {
    int layers_executed;
    size_t bytes_streamed;
};

struct GreedyTokenResult {
    int token_id;
    float logit;
};

struct DenseLmHeadGreedyResult {
    int token_id;
    float logit;
    size_t bytes_streamed;
    int tiles_processed;
};

struct PromptEmbeddingResult {
    int tokens_embedded;
    size_t bytes_streamed;
};

struct SamplingConfig {
    float temperature;
    int top_k;
    float top_p;
    float repetition_penalty;
    uint64_t seed;
};

struct SampledTokenResult {
    int token_id;
    float logit;
    size_t bytes_streamed;
    int tiles_processed;
};

struct GreedyDecodeConfig {
    int max_new_tokens;
    int eos_token_id;
    int sequence_id;
};

struct GreedyDecodeResult {
    int tokens_generated;
    int last_token_id;
};

ActivationWorkspace create_activation_workspace(int tokens,
                                                int hidden_size,
                                                int intermediate_size);

void destroy_activation_workspace(ActivationWorkspace& workspace) noexcept;

void launch_rmsnorm(const half* input,
                    const half* weight,
                    half* output,
                    int rows,
                    int hidden_size,
                    float epsilon,
                    cudaStream_t stream = nullptr);

void launch_rope(half* q,
                 half* k,
                 int tokens,
                 int num_heads,
                 int num_kv_heads,
                 int head_dim,
                 int position_offset,
                 float rope_theta,
                 cudaStream_t stream = nullptr);

void launch_residual_add(const half* lhs,
                         const half* rhs,
                         half* output,
                         int element_count,
                         cudaStream_t stream = nullptr);

void launch_swiglu(const half* gate,
                   const half* up,
                   half* output,
                   int element_count,
                   cudaStream_t stream = nullptr);

void launch_copy_half(const half* input,
                      half* output,
                      int element_count,
                      cudaStream_t stream = nullptr);

void launch_dense_matmul_fp16(const half* lhs,
                              const half* rhs,
                              const half* bias,
                              half* output,
                              int m,
                              int n,
                              int k,
                              cudaStream_t stream = nullptr);

void launch_causal_attention_prefill(const half* q,
                                     const half* k,
                                     const half* v,
                                     half* output,
                                     int tokens,
                                     int num_attention_heads,
                                     int num_key_value_heads,
                                     int head_dim,
                                     cudaStream_t stream = nullptr);

void launch_store_kv_cache_token(const half* k_token,
                                 const half* v_token,
                                 half* k_cache,
                                 half* v_cache,
                                 int token_index,
                                 int cache_token_capacity,
                                 int num_key_value_heads,
                                 int head_dim,
                                 cudaStream_t stream = nullptr);

void launch_causal_attention_decode(const half* q_token,
                                    const half* k_cache,
                                    const half* v_cache,
                                    half* output,
                                    int cached_tokens,
                                    int num_attention_heads,
                                    int num_key_value_heads,
                                    int head_dim,
                                    cudaStream_t stream = nullptr);

LlamaDecoderLayerWeights resolve_llama_decoder_layer_weights(
    const void* device_layer_slot,
    const LayerExecutionPlan& plan);

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
    int batch_tokens);

void execute_llama_decoder_layer_prefill(const half* input,
                                         half* output,
                                         const LlamaDecoderLayerWeights& weights,
                                         ActivationWorkspace& workspace,
                                         const LlamaDecoderLayerConfig& config,
                                         cudaStream_t stream = nullptr);

void execute_quantized_llama_decoder_layer_prefill(
    const half* input,
    half* output,
    const QuantizedLlamaDecoderLayerWeights& weights,
    ActivationWorkspace& workspace,
    const LlamaDecoderLayerConfig& config,
    cudaStream_t stream = nullptr);

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
    cudaStream_t stream = nullptr);

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
    cudaStream_t stream = nullptr);

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
    cudaStream_t stream = nullptr);

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
    cudaStream_t stream = nullptr);

void launch_token_embedding_lookup(const half* embeddings,
                                   int token_id,
                                   half* output,
                                   int vocab_size,
                                   int hidden_size,
                                   cudaStream_t stream = nullptr);

PromptEmbeddingResult execute_prompt_embedding_lookup_streamed(
    StreamingTensorStore& store,
    const ManifestTensor& embedding_weight,
    const int* token_ids,
    int token_count,
    half* output,
    int vocab_size,
    int hidden_size,
    cudaStream_t stream = nullptr);

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
    KVCacheRuntime* kv_cache = nullptr,
    cudaStream_t stream = nullptr);

} // namespace spoolstream::core
