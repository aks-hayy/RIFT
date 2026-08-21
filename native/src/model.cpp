#include "spoolstream/model.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <unordered_map>

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream model validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream in(path, std::ios::binary);
    require_condition(static_cast<bool>(in), "unable to open file: " + path.string());
    std::ostringstream buffer;
    buffer << in.rdbuf();
    return buffer.str();
}

enum class JsonKind {
    Null,
    Bool,
    Number,
    String,
    Array,
    Object
};

struct Json {
    JsonKind kind = JsonKind::Null;
    bool boolean = false;
    double number = 0.0;
    std::string string;
    std::vector<Json> array;
    std::map<std::string, Json> object;
};

class JsonParser {
public:
    explicit JsonParser(std::string_view source) : source_(source) {
    }

    Json parse() {
        Json value = parse_value();
        skip_ws();
        require_condition(pos_ == source_.size(), "trailing data after JSON document");
        return value;
    }

private:
    Json parse_value() {
        skip_ws();
        require_condition(pos_ < source_.size(), "unexpected end of JSON");
        const char ch = source_[pos_];
        if (ch == 'n') {
            expect_literal("null");
            return Json{};
        }
        if (ch == 't') {
            expect_literal("true");
            Json out;
            out.kind = JsonKind::Bool;
            out.boolean = true;
            return out;
        }
        if (ch == 'f') {
            expect_literal("false");
            Json out;
            out.kind = JsonKind::Bool;
            out.boolean = false;
            return out;
        }
        if (ch == '"') {
            Json out;
            out.kind = JsonKind::String;
            out.string = parse_string();
            return out;
        }
        if (ch == '[') {
            return parse_array();
        }
        if (ch == '{') {
            return parse_object();
        }
        if (ch == '-' || std::isdigit(static_cast<unsigned char>(ch))) {
            return parse_number();
        }
        fail("unexpected JSON character");
    }

    Json parse_array() {
        Json out;
        out.kind = JsonKind::Array;
        ++pos_;
        skip_ws();
        if (consume(']')) {
            return out;
        }
        while (true) {
            out.array.push_back(parse_value());
            skip_ws();
            if (consume(']')) {
                return out;
            }
            require_condition(consume(','), "expected ',' in JSON array");
        }
    }

    Json parse_object() {
        Json out;
        out.kind = JsonKind::Object;
        ++pos_;
        skip_ws();
        if (consume('}')) {
            return out;
        }
        while (true) {
            skip_ws();
            require_condition(pos_ < source_.size() && source_[pos_] == '"',
                              "expected object key string");
            const std::string key = parse_string();
            skip_ws();
            require_condition(consume(':'), "expected ':' after object key");
            out.object.emplace(key, parse_value());
            skip_ws();
            if (consume('}')) {
                return out;
            }
            require_condition(consume(','), "expected ',' in JSON object");
        }
    }

    Json parse_number() {
        const size_t start = pos_;
        if (source_[pos_] == '-') {
            ++pos_;
        }
        while (pos_ < source_.size() && std::isdigit(static_cast<unsigned char>(source_[pos_]))) {
            ++pos_;
        }
        if (pos_ < source_.size() && source_[pos_] == '.') {
            ++pos_;
            while (pos_ < source_.size() && std::isdigit(static_cast<unsigned char>(source_[pos_]))) {
                ++pos_;
            }
        }
        if (pos_ < source_.size() && (source_[pos_] == 'e' || source_[pos_] == 'E')) {
            ++pos_;
            if (pos_ < source_.size() && (source_[pos_] == '+' || source_[pos_] == '-')) {
                ++pos_;
            }
            while (pos_ < source_.size() && std::isdigit(static_cast<unsigned char>(source_[pos_]))) {
                ++pos_;
            }
        }
        Json out;
        out.kind = JsonKind::Number;
        out.number = std::stod(std::string(source_.substr(start, pos_ - start)));
        return out;
    }

    std::string parse_string() {
        require_condition(consume('"'), "expected string opening quote");
        std::string out;
        while (pos_ < source_.size()) {
            const char ch = source_[pos_++];
            if (ch == '"') {
                return out;
            }
            if (ch != '\\') {
                out.push_back(ch);
                continue;
            }
            require_condition(pos_ < source_.size(), "unterminated JSON escape");
            const char esc = source_[pos_++];
            switch (esc) {
                case '"':
                case '\\':
                case '/':
                    out.push_back(esc);
                    break;
                case 'b':
                    out.push_back('\b');
                    break;
                case 'f':
                    out.push_back('\f');
                    break;
                case 'n':
                    out.push_back('\n');
                    break;
                case 'r':
                    out.push_back('\r');
                    break;
                case 't':
                    out.push_back('\t');
                    break;
                case 'u':
                    require_condition(pos_ + 4 <= source_.size(),
                                      "short unicode escape");
                    out.push_back('?');
                    pos_ += 4;
                    break;
                default:
                    fail("unsupported JSON escape");
            }
        }
        fail("unterminated JSON string");
    }

    void expect_literal(std::string_view literal) {
        require_condition(source_.substr(pos_, literal.size()) == literal,
                          "expected JSON literal");
        pos_ += literal.size();
    }

    bool consume(char expected) {
        if (pos_ < source_.size() && source_[pos_] == expected) {
            ++pos_;
            return true;
        }
        return false;
    }

    void skip_ws() {
        while (pos_ < source_.size() &&
               std::isspace(static_cast<unsigned char>(source_[pos_]))) {
            ++pos_;
        }
    }

    std::string_view source_;
    size_t pos_ = 0;
};

const Json& require_member(const Json& value, const std::string& key) {
    require_condition(value.kind == JsonKind::Object, "expected JSON object");
    const auto it = value.object.find(key);
    require_condition(it != value.object.end(), "missing JSON member '" + key + "'");
    return it->second;
}

const Json* find_member(const Json& value, const std::string& key) {
    if (value.kind != JsonKind::Object) {
        return nullptr;
    }
    const auto it = value.object.find(key);
    return it == value.object.end() ? nullptr : &it->second;
}

std::string as_string(const Json& value, const std::string& context) {
    require_condition(value.kind == JsonKind::String, context + " must be a string");
    return value.string;
}

int as_int(const Json& value, const std::string& context) {
    require_condition(value.kind == JsonKind::Number, context + " must be a number");
    require_condition(std::floor(value.number) == value.number, context + " must be an integer");
    require_condition(value.number >= static_cast<double>(std::numeric_limits<int>::min()) &&
                          value.number <= static_cast<double>(std::numeric_limits<int>::max()),
                      context + " is out of int range");
    return static_cast<int>(value.number);
}

double as_double(const Json& value, const std::string& context) {
    require_condition(value.kind == JsonKind::Number, context + " must be a number");
    return value.number;
}

bool as_bool(const Json& value, const std::string& context) {
    require_condition(value.kind == JsonKind::Bool, context + " must be a boolean");
    return value.boolean;
}

int optional_int(const Json& object, const std::string& key, int fallback) {
    const Json* value = find_member(object, key);
    return value == nullptr ? fallback : as_int(*value, key);
}

double optional_double(const Json& object, const std::string& key, double fallback) {
    const Json* value = find_member(object, key);
    return value == nullptr ? fallback : as_double(*value, key);
}

std::string optional_string(const Json& object,
                            const std::string& key,
                            const std::string& fallback) {
    const Json* value = find_member(object, key);
    return value == nullptr ? fallback : as_string(*value, key);
}

bool optional_bool(const Json& object, const std::string& key, bool fallback) {
    const Json* value = find_member(object, key);
    return value == nullptr ? fallback : as_bool(*value, key);
}

bool contains_token(const std::string& haystack, const std::string& needle) {
    return haystack.find(needle) != std::string::npos;
}

ModelQuantization parse_quantization(const Json& root) {
    const std::string explicit_quant = optional_string(root, "quantization_format", "");
    const std::string torch_dtype = optional_string(root, "torch_dtype", "");
    const Json* quant_config = find_member(root, "quantization_config");
    std::string quant_method;
    if (quant_config != nullptr) {
        quant_method = optional_string(*quant_config, "quant_method", "");
    }
    const std::string joined = explicit_quant + " " + quant_method + " " + torch_dtype;
    if (contains_token(joined, "awq") || contains_token(joined, "AWQ")) {
        return ModelQuantization::AWQ_INT4;
    }
    if (contains_token(joined, "gptq") || contains_token(joined, "GPTQ")) {
        return ModelQuantization::GPTQ_INT4;
    }
    if (contains_token(joined, "bf16") || contains_token(joined, "bfloat16")) {
        return ModelQuantization::BF16;
    }
    if (contains_token(joined, "fp16") || contains_token(joined, "float16")) {
        return ModelQuantization::FP16;
    }
    return ModelQuantization::UNKNOWN;
}

int special_token_id(const Json& root, const std::string& key) {
    const Json* value = find_member(root, key);
    if (value == nullptr) {
        return -1;
    }
    if (value->kind == JsonKind::Number) {
        return as_int(*value, key);
    }
    if (value->kind == JsonKind::Object) {
        const Json* id = find_member(*value, "id");
        return id == nullptr ? -1 : as_int(*id, key + ".id");
    }
    return -1;
}

std::string normalize_token_for_text(const std::string& token) {
    std::string out = token;
    constexpr const char* kSentencePieceSpace = "\xE2\x96\x81";
    size_t pos = 0;
    while ((pos = out.find(kSentencePieceSpace, pos)) != std::string::npos) {
        out.replace(pos, 3, " ");
        ++pos;
    }
    if (out.rfind("Ġ", 0) == 0) {
        out.replace(0, 2, " ");
    }
    return out;
}

std::string denormalize_for_lookup(const std::string& token) {
    if (!token.empty() && token[0] == ' ') {
        return std::string("\xE2\x96\x81") + token.substr(1);
    }
    return token;
}

TensorRole infer_tensor_role(const std::string& name) {
    if (contains_token(name, "embed_tokens")) {
        return TensorRole::TOKEN_EMBEDDING;
    }
    if (contains_token(name, ".qweight") || contains_token(name, "query_key_value.qweight")) {
        return TensorRole::QUANT_QWEIGHT;
    }
    if (contains_token(name, ".scales") || contains_token(name, ".qzeros") ||
        contains_token(name, ".zeros")) {
        return contains_token(name, ".scales") ? TensorRole::QUANT_SCALE : TensorRole::QUANT_ZERO;
    }
    if (contains_token(name, ".g_idx")) {
        return TensorRole::QUANT_GIDX;
    }
    if (contains_token(name, ".bias") &&
        (contains_token(name, "q_proj") || contains_token(name, "k_proj") ||
         contains_token(name, "v_proj") || contains_token(name, "o_proj") ||
         contains_token(name, "gate_proj") || contains_token(name, "up_proj") ||
         contains_token(name, "down_proj"))) {
        return TensorRole::QUANT_BIAS;
    }
    if (contains_token(name, "lm_head")) {
        return TensorRole::LM_HEAD;
    }
    if (contains_token(name, "model.norm") || contains_token(name, "final_layernorm")) {
        return TensorRole::FINAL_NORM;
    }
    if (contains_token(name, "input_layernorm")) {
        return TensorRole::ATTN_NORM;
    }
    if (contains_token(name, "post_attention_layernorm")) {
        return TensorRole::MLP_NORM;
    }
    if (contains_token(name, "q_proj.weight")) {
        return TensorRole::ATTN_Q;
    }
    if (contains_token(name, "k_proj.weight")) {
        return TensorRole::ATTN_K;
    }
    if (contains_token(name, "v_proj.weight")) {
        return TensorRole::ATTN_V;
    }
    if (contains_token(name, "o_proj.weight")) {
        return TensorRole::ATTN_O;
    }
    if (contains_token(name, "gate_proj.weight")) {
        return TensorRole::MLP_GATE;
    }
    if (contains_token(name, "up_proj.weight")) {
        return TensorRole::MLP_UP;
    }
    if (contains_token(name, "down_proj.weight")) {
        return TensorRole::MLP_DOWN;
    }
    return TensorRole::UNKNOWN;
}

std::string base_tensor_name(const std::string& name) {
    const char* suffixes[] = {
        ".qweight", ".weight", ".scales", ".qzeros", ".zeros", ".g_idx", ".bias"};
    for (const char* suffix : suffixes) {
        const size_t suffix_len = std::char_traits<char>::length(suffix);
        if (name.size() >= suffix_len &&
            name.compare(name.size() - suffix_len, suffix_len, suffix) == 0) {
            return name.substr(0, name.size() - suffix_len);
        }
    }
    return name;
}

int layer_id_from_tensor_name(const std::string& name) {
    const std::string markers[] = {"model.layers.", "layers.", "h.", "blocks."};
    for (const std::string& marker : markers) {
        const size_t pos = name.find(marker);
        if (pos == std::string::npos) {
            continue;
        }
        size_t cursor = pos + marker.size();
        size_t end = cursor;
        while (end < name.size() && std::isdigit(static_cast<unsigned char>(name[end]))) {
            ++end;
        }
        if (end > cursor) {
            return std::stoi(name.substr(cursor, end - cursor));
        }
    }
    return -1;
}

} // namespace

ModelConfig load_model_config(const std::filesystem::path& checkpoint_directory) {
    const std::filesystem::path path = checkpoint_directory / "config.json";
    const Json root = JsonParser(read_text_file(path)).parse();
    require_condition(root.kind == JsonKind::Object, "config.json root must be an object");

    const std::string model_type = optional_string(root, "model_type", "llama");
    require_condition(model_type == "llama" || model_type == "mistral" ||
                          model_type == "qwen2",
                      "only LLaMA, Mistral, and Qwen2 decoder configs are supported");

    ModelConfig config{};
    config.family = model_type == "qwen2" ? ModelFamily::QWEN2 : ModelFamily::LLAMA;
    config.quantization = parse_quantization(root);
    config.hidden_size = as_int(require_member(root, "hidden_size"), "hidden_size");
    config.intermediate_size = as_int(require_member(root, "intermediate_size"),
                                      "intermediate_size");
    config.num_hidden_layers = as_int(require_member(root, "num_hidden_layers"),
                                      "num_hidden_layers");
    config.num_attention_heads = as_int(require_member(root, "num_attention_heads"),
                                        "num_attention_heads");
    config.num_key_value_heads = optional_int(root,
                                              "num_key_value_heads",
                                              config.num_attention_heads);
    config.vocab_size = as_int(require_member(root, "vocab_size"), "vocab_size");
    config.max_position_embeddings = optional_int(root, "max_position_embeddings", 4096);
    config.rope_theta = optional_double(root, "rope_theta", 10000.0);
    config.rms_norm_eps = optional_double(root, "rms_norm_eps", 1.0e-6);
    config.tie_word_embeddings = optional_bool(root, "tie_word_embeddings", false);
    config.model_type = model_type;

    require_condition(config.hidden_size > 0, "hidden_size must be positive");
    require_condition(config.intermediate_size > 0, "intermediate_size must be positive");
    require_condition(config.num_hidden_layers > 0, "num_hidden_layers must be positive");
    require_condition(config.num_attention_heads > 0, "num_attention_heads must be positive");
    require_condition(config.num_key_value_heads > 0, "num_key_value_heads must be positive");
    require_condition(config.vocab_size > 0, "vocab_size must be positive");
    require_condition(config.hidden_size % config.num_attention_heads == 0,
                      "hidden_size must be divisible by num_attention_heads");
    require_condition(config.num_attention_heads % config.num_key_value_heads == 0,
                      "num_attention_heads must be divisible by num_key_value_heads");
    return config;
}

Tokenizer load_tokenizer_json(const std::filesystem::path& tokenizer_json_path) {
    const Json root = JsonParser(read_text_file(tokenizer_json_path)).parse();
    require_condition(root.kind == JsonKind::Object, "tokenizer.json root must be an object");
    const Json& model = require_member(root, "model");
    const Json& vocab = require_member(model, "vocab");
    require_condition(vocab.kind == JsonKind::Object, "model.vocab must be an object");

    Tokenizer tokenizer{};
    tokenizer.unknown_token_id = special_token_id(root, "unk_token");
    tokenizer.bos_token_id = special_token_id(root, "bos_token");
    tokenizer.eos_token_id = special_token_id(root, "eos_token");
    tokenizer.pad_token_id = special_token_id(root, "pad_token");

    for (const auto& entry : vocab.object) {
        TokenizerToken token{};
        token.token = entry.first;
        token.id = as_int(entry.second, "model.vocab." + entry.first);
        require_condition(token.id >= 0, "token id must be non-negative");
        tokenizer.vocabulary.push_back(token);
        if (token.token == "<unk>" && tokenizer.unknown_token_id < 0) {
            tokenizer.unknown_token_id = token.id;
        } else if (token.token == "<s>" && tokenizer.bos_token_id < 0) {
            tokenizer.bos_token_id = token.id;
        } else if (token.token == "</s>" && tokenizer.eos_token_id < 0) {
            tokenizer.eos_token_id = token.id;
        } else if (token.token == "<pad>" && tokenizer.pad_token_id < 0) {
            tokenizer.pad_token_id = token.id;
        }
    }
    const Json* added_tokens = find_member(root, "added_tokens");
    if (added_tokens != nullptr) {
        require_condition(added_tokens->kind == JsonKind::Array,
                          "added_tokens must be an array when present");
        for (const Json& added : added_tokens->array) {
            require_condition(added.kind == JsonKind::Object,
                              "added_tokens entries must be objects");
            const Json* content = find_member(added, "content");
            const Json* id = find_member(added, "id");
            if (content == nullptr || id == nullptr) {
                continue;
            }
            TokenizerToken token{};
            token.token = as_string(*content, "added_tokens.content");
            token.id = as_int(*id, "added_tokens.id");
            require_condition(token.id >= 0, "added token id must be non-negative");
            tokenizer.vocabulary.push_back(token);
            if ((token.token == "<|begin_of_text|>" || token.token == "<s>") &&
                tokenizer.bos_token_id < 0) {
                tokenizer.bos_token_id = token.id;
            } else if ((token.token == "<|end_of_text|>" || token.token == "</s>") &&
                       tokenizer.eos_token_id < 0) {
                tokenizer.eos_token_id = token.id;
            } else if ((token.token == "<unk>" || token.token == "<|unknown|>") &&
                       tokenizer.unknown_token_id < 0) {
                tokenizer.unknown_token_id = token.id;
            } else if ((token.token == "<pad>" || token.token == "<|pad|>") &&
                       tokenizer.pad_token_id < 0) {
                tokenizer.pad_token_id = token.id;
            }
        }
    }
    if (tokenizer.unknown_token_id < 0) {
        tokenizer.unknown_token_id =
            tokenizer.eos_token_id >= 0 ? tokenizer.eos_token_id :
            (tokenizer.bos_token_id >= 0 ? tokenizer.bos_token_id : 0);
    }
    require_condition(!tokenizer.vocabulary.empty(), "tokenizer vocabulary is empty");
    std::sort(tokenizer.vocabulary.begin(),
              tokenizer.vocabulary.end(),
              [](const TokenizerToken& lhs, const TokenizerToken& rhs) {
                  if (lhs.token.size() != rhs.token.size()) {
                      return lhs.token.size() > rhs.token.size();
                  }
                  return lhs.id < rhs.id;
              });
    return tokenizer;
}

std::vector<int> encode_tokenizer_text(const Tokenizer& tokenizer,
                                       const std::string& text,
                                       bool add_bos) {
    std::unordered_map<std::string, int> lookup;
    for (const TokenizerToken& token : tokenizer.vocabulary) {
        lookup.emplace(normalize_token_for_text(token.token), token.id);
        lookup.emplace(token.token, token.id);
    }

    std::vector<int> ids;
    if (add_bos && tokenizer.bos_token_id >= 0) {
        ids.push_back(tokenizer.bos_token_id);
    }
    size_t pos = 0;
    while (pos < text.size()) {
        bool matched = false;
        for (const TokenizerToken& token : tokenizer.vocabulary) {
            const std::string normalized = normalize_token_for_text(token.token);
            if (!normalized.empty() &&
                text.compare(pos, normalized.size(), normalized) == 0) {
                ids.push_back(token.id);
                pos += normalized.size();
                matched = true;
                break;
            }
        }
        if (!matched) {
            const std::string single(1, text[pos]);
            const auto it = lookup.find(single);
            ids.push_back(it == lookup.end() ? tokenizer.unknown_token_id : it->second);
            ++pos;
        }
    }
    return ids;
}

std::string decode_tokenizer_tokens(const Tokenizer& tokenizer,
                                    const std::vector<int>& token_ids,
                                    bool skip_special_tokens) {
    std::unordered_map<int, std::string> lookup;
    for (const TokenizerToken& token : tokenizer.vocabulary) {
        lookup.emplace(token.id, token.token);
    }
    std::string out;
    for (int id : token_ids) {
        if (skip_special_tokens &&
            (id == tokenizer.bos_token_id || id == tokenizer.eos_token_id ||
             id == tokenizer.pad_token_id)) {
            continue;
        }
        const auto it = lookup.find(id);
        if (it == lookup.end()) {
            continue;
        }
        out += normalize_token_for_text(it->second);
    }
    return out;
}

ModelManifest build_model_manifest(const std::filesystem::path& checkpoint_directory,
                                   const std::string& memory_strategy,
                                   size_t strict_scratchpad_bytes) {
    ModelManifest manifest{};
    manifest.config = load_model_config(checkpoint_directory);
    manifest.checkpoint_directory = checkpoint_directory;
    manifest.topology =
        parse_model_topology(checkpoint_directory, memory_strategy, strict_scratchpad_bytes);
    manifest.total_streamable_bytes = manifest.topology.total_model_bytes;
    manifest.max_tensor_bytes = 0;

    for (const TensorMetaData& tensor : manifest.topology.tensors) {
        ManifestTensor entry{};
        entry.metadata = tensor;
        entry.role = infer_tensor_role(tensor.name);
        entry.layer_id = layer_id_from_tensor_name(tensor.name);
        entry.base_name = base_tensor_name(tensor.name);
        manifest.max_tensor_bytes =
            std::max(manifest.max_tensor_bytes, tensor.end_offset - tensor.start_offset);
        manifest.tensors.push_back(entry);
    }

    require_condition(!manifest.tensors.empty(), "manifest contains no tensors");
    require_condition(manifest.config.num_hidden_layers == manifest.topology.total_layers,
                      "config layer count does not match SafeTensors topology");
    return manifest;
}

ModelProfile plan_model_profile(const ModelManifest& manifest,
                                const MemoryBudget& budget) {
    ModelProfile profile{};
    profile.total_model_bytes = manifest.total_streamable_bytes;
    profile.required_scratchpad_bytes = manifest.topology.w_max_bytes * 2U;
    profile.required_host_staging_bytes = manifest.max_tensor_bytes;
    profile.estimated_peak_vram_bytes =
        profile.required_scratchpad_bytes + budget.kv_cache_bytes;
    profile.estimated_peak_host_bytes = profile.required_host_staging_bytes;
    profile.streaming_required =
        manifest.total_streamable_bytes > budget.max_host_resident_bytes;

    if (budget.max_vram_bytes == 0 || budget.max_host_staging_bytes == 0) {
        profile.supported = false;
        profile.reason = "memory budgets must be positive";
        return profile;
    }
    if (profile.required_scratchpad_bytes > budget.max_vram_bytes) {
        profile.supported = false;
        profile.reason = "double-buffer scratchpad exceeds VRAM budget";
        return profile;
    }
    if (profile.required_host_staging_bytes > budget.max_host_staging_bytes) {
        profile.supported = false;
        profile.reason = "largest tensor exceeds pinned host staging budget";
        return profile;
    }
    profile.supported = true;
    profile.reason = profile.streaming_required ? "streaming mode required" : "host-resident mode possible";
    return profile;
}

const char* tensor_role_name(TensorRole role) noexcept {
    switch (role) {
        case TensorRole::TOKEN_EMBEDDING:
            return "TOKEN_EMBEDDING";
        case TensorRole::FINAL_NORM:
            return "FINAL_NORM";
        case TensorRole::LM_HEAD:
            return "LM_HEAD";
        case TensorRole::ATTN_NORM:
            return "ATTN_NORM";
        case TensorRole::ATTN_Q:
            return "ATTN_Q";
        case TensorRole::ATTN_K:
            return "ATTN_K";
        case TensorRole::ATTN_V:
            return "ATTN_V";
        case TensorRole::ATTN_O:
            return "ATTN_O";
        case TensorRole::MLP_NORM:
            return "MLP_NORM";
        case TensorRole::MLP_GATE:
            return "MLP_GATE";
        case TensorRole::MLP_UP:
            return "MLP_UP";
        case TensorRole::MLP_DOWN:
            return "MLP_DOWN";
        case TensorRole::QUANT_BIAS:
            return "QUANT_BIAS";
        case TensorRole::QUANT_SCALE:
            return "QUANT_SCALE";
        case TensorRole::QUANT_ZERO:
            return "QUANT_ZERO";
        case TensorRole::QUANT_GIDX:
            return "QUANT_GIDX";
        case TensorRole::QUANT_QWEIGHT:
            return "QUANT_QWEIGHT";
        default:
            return "UNKNOWN";
    }
}

const char* model_quantization_name(ModelQuantization quantization) noexcept {
    switch (quantization) {
        case ModelQuantization::AWQ_INT4:
            return "AWQ_INT4";
        case ModelQuantization::GPTQ_INT4:
            return "GPTQ_INT4";
        case ModelQuantization::FP16:
            return "FP16";
        case ModelQuantization::BF16:
            return "BF16";
        default:
            return "UNKNOWN";
    }
}

const char* model_family_name(ModelFamily family) noexcept {
    switch (family) {
        case ModelFamily::LLAMA:
            return "LLAMA";
        case ModelFamily::QWEN2:
            return "QWEN2";
        default:
            return "UNKNOWN";
    }
}

} // namespace spoolstream::core
