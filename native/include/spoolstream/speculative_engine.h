#pragma once

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

namespace spoolstream::core {

struct SpeculativeConfig {
    int hidden_size;
    int vocab_size;
    int max_nodes;
    int top_k;
};

struct SpeculativeTree {
    int* device_tokens;
    int* device_parents;
    int node_count;
};

struct VerificationResult {
    int accepted_count;
    int terminal_node;
};

void launch_eagle_predict_heads(const half* hidden_states,
                                const half* head_weights,
                                const half* head_bias,
                                half* candidate_logits,
                                int* candidate_tokens,
                                int sequence_length,
                                const SpeculativeConfig& config,
                                cudaStream_t stream = nullptr);

void generate_tree_attention_mask(const int* device_parents,
                                  half* device_mask,
                                  int node_count,
                                  cudaStream_t stream = nullptr);

VerificationResult verify_speculative_tree_greedy(const half* main_logits,
                                                  const SpeculativeTree& tree,
                                                  int vocab_size,
                                                  cudaStream_t stream = nullptr);

} // namespace spoolstream::core
