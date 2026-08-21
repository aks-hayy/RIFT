#pragma once

#include "spoolstream/parser.h"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace spoolstream::core {

enum class ModelFamily {
    LLAMA,
    QWEN2
};

enum class ModelQuantization {
    UNKNOWN,
    AWQ_INT4,
    GPTQ_INT4,
    FP16,
    BF16
};

enum class TensorRole {
    UNKNOWN,
    TOKEN_EMBEDDING,
    FINAL_NORM,
    LM_HEAD,
    ATTN_NORM,
    ATTN_Q,
    ATTN_K,
    ATTN_V,
    ATTN_O,
    MLP_NORM,
    MLP_GATE,
    MLP_UP,
    MLP_DOWN,
    QUANT_BIAS,
    QUANT_SCALE,
    QUANT_ZERO,
    QUANT_GIDX,
    QUANT_QWEIGHT
};

struct ModelConfig {
    ModelFamily family;
    ModelQuantization quantization;
    int hidden_size;
    int intermediate_size;
    int num_hidden_layers;
    int num_attention_heads;
    int num_key_value_heads;
    int vocab_size;
    int max_position_embeddings;
    double rope_theta;
    double rms_norm_eps;
    bool tie_word_embeddings;
    std::string model_type;
};

struct TokenizerToken {
    std::string token;
    int id;
};

struct Tokenizer {
    std::vector<TokenizerToken> vocabulary;
    int unknown_token_id;
    int bos_token_id;
    int eos_token_id;
    int pad_token_id;
};

struct ManifestTensor {
    TensorMetaData metadata;
    TensorRole role;
    int layer_id;
    std::string base_name;
};

struct ModelManifest {
    ModelConfig config;
    ModelTopology topology;
    std::filesystem::path checkpoint_directory;
    std::vector<ManifestTensor> tensors;
    size_t total_streamable_bytes;
    size_t max_tensor_bytes;
};

struct MemoryBudget {
    size_t max_vram_bytes;
    size_t max_host_staging_bytes;
    size_t max_host_resident_bytes;
    size_t kv_cache_bytes;
};

struct ModelProfile {
    bool supported;
    bool streaming_required;
    std::string reason;
    size_t total_model_bytes;
    size_t required_scratchpad_bytes;
    size_t required_host_staging_bytes;
    size_t estimated_peak_vram_bytes;
    size_t estimated_peak_host_bytes;
};

ModelConfig load_model_config(const std::filesystem::path& checkpoint_directory);

Tokenizer load_tokenizer_json(const std::filesystem::path& tokenizer_json_path);

std::vector<int> encode_tokenizer_text(const Tokenizer& tokenizer,
                                       const std::string& text,
                                       bool add_bos);

std::string decode_tokenizer_tokens(const Tokenizer& tokenizer,
                                    const std::vector<int>& token_ids,
                                    bool skip_special_tokens);

ModelManifest build_model_manifest(const std::filesystem::path& checkpoint_directory,
                                   const std::string& memory_strategy,
                                   size_t strict_scratchpad_bytes =
                                       kDefaultStrictScratchpadBytes);

ModelProfile plan_model_profile(const ModelManifest& manifest,
                                const MemoryBudget& budget);

const char* tensor_role_name(TensorRole role) noexcept;

const char* model_quantization_name(ModelQuantization quantization) noexcept;

const char* model_family_name(ModelFamily family) noexcept;

} // namespace spoolstream::core
