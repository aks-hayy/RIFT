#include "spoolstream/model.h"
#include "spoolstream/streaming_store.h"
#include "spoolstream/memory_manager.h"

#include <cuda_runtime_api.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct TensorFixture {
    std::string name;
    std::string dtype;
    std::vector<int64_t> shape;
    std::vector<uint8_t> payload;
};

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_),
                                             sizeof(T) * count_));
        }
    }

    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;

    ~DeviceBuffer() {
        if (ptr_ != nullptr) {
            cudaFree(ptr_);
        }
    }

    T* get() {
        return ptr_;
    }

    std::vector<T> copy_to_host() const {
        std::vector<T> host(count_);
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                         ptr_,
                                         sizeof(T) * count_,
                                         cudaMemcpyDeviceToHost));
        return host;
    }

private:
    T* ptr_ = nullptr;
    size_t count_ = 0;
};

void require_true(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

template <typename Fn>
void require_throw(Fn&& fn, const std::string& message) {
    try {
        fn();
    } catch (const std::runtime_error&) {
        return;
    }
    throw std::runtime_error("expected runtime_error: " + message);
}

std::filesystem::path make_case_dir(const std::string& name) {
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path root =
        std::filesystem::temp_directory_path() /
        ("spoolstream_model_" + name + "_" + std::to_string(stamp));
    std::filesystem::create_directories(root);
    return root;
}

void write_u64_le(std::ofstream& out, uint64_t value) {
    for (size_t i = 0; i < 8; ++i) {
        const char byte = static_cast<char>((value >> (i * 8)) & 0xFFU);
        out.write(&byte, 1);
    }
}

std::string shape_json(const std::vector<int64_t>& shape) {
    std::string out = "[";
    for (size_t i = 0; i < shape.size(); ++i) {
        if (i != 0) {
            out += ",";
        }
        out += std::to_string(shape[i]);
    }
    out += "]";
    return out;
}

std::vector<uint8_t> make_payload(size_t byte_count, uint8_t seed) {
    std::vector<uint8_t> payload(byte_count);
    for (size_t i = 0; i < byte_count; ++i) {
        payload[i] = static_cast<uint8_t>((seed + i * 13U) & 0xFFU);
    }
    return payload;
}

void write_shard(const std::filesystem::path& path,
                 const std::vector<TensorFixture>& tensors) {
    std::string header = "{";
    size_t offset = 0;
    for (size_t i = 0; i < tensors.size(); ++i) {
        const TensorFixture& tensor = tensors[i];
        if (i != 0) {
            header += ",";
        }
        header += "\"" + tensor.name + "\":{\"dtype\":\"" + tensor.dtype +
                  "\",\"shape\":" + shape_json(tensor.shape) + ",\"data_offsets\":[" +
                  std::to_string(offset) + "," +
                  std::to_string(offset + tensor.payload.size()) + "]}";
        offset += tensor.payload.size();
    }
    header += "}";

    std::ofstream out(path, std::ios::binary);
    write_u64_le(out, static_cast<uint64_t>(header.size()));
    out.write(header.data(), static_cast<std::streamsize>(header.size()));
    for (const TensorFixture& tensor : tensors) {
        out.write(reinterpret_cast<const char*>(tensor.payload.data()),
                  static_cast<std::streamsize>(tensor.payload.size()));
    }
}

void write_index(const std::filesystem::path& dir,
                 const std::vector<std::pair<std::string, std::string>>& entries) {
    std::string json = "{\"metadata\":{\"total_size\":0},\"weight_map\":{";
    for (size_t i = 0; i < entries.size(); ++i) {
        if (i != 0) {
            json += ",";
        }
        json += "\"" + entries[i].first + "\":\"" + entries[i].second + "\"";
    }
    json += "}}";
    std::ofstream out(dir / "model.safetensors.index.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

void write_config(const std::filesystem::path& dir) {
    const std::string json =
        "{"
        "\"model_type\":\"llama\","
        "\"hidden_size\":8,"
        "\"intermediate_size\":16,"
        "\"num_hidden_layers\":2,"
        "\"num_attention_heads\":2,"
        "\"num_key_value_heads\":1,"
        "\"vocab_size\":16,"
        "\"max_position_embeddings\":128,"
        "\"rope_theta\":10000.0,"
        "\"rms_norm_eps\":0.000001,"
        "\"quantization_config\":{\"quant_method\":\"awq\"}"
        "}";
    std::ofstream out(dir / "config.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

void write_qwen2_bf16_config(const std::filesystem::path& dir) {
    const std::string json =
        "{"
        "\"model_type\":\"qwen2\","
        "\"architectures\":[\"Qwen2ForCausalLM\"],"
        "\"hidden_size\":8,"
        "\"intermediate_size\":16,"
        "\"num_hidden_layers\":2,"
        "\"num_attention_heads\":2,"
        "\"num_key_value_heads\":1,"
        "\"vocab_size\":32,"
        "\"max_position_embeddings\":1024,"
        "\"rope_theta\":1000000.0,"
        "\"rms_norm_eps\":0.000001,"
        "\"tie_word_embeddings\":true,"
        "\"torch_dtype\":\"bfloat16\""
        "}";
    std::ofstream out(dir / "config.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

void write_tokenizer(const std::filesystem::path& dir) {
    const std::string sp = "\xE2\x96\x81";
    const std::string json =
        "{\"model\":{\"type\":\"BPE\",\"vocab\":{"
        "\"<unk>\":0,\"<s>\":1,\"</s>\":2,\"" + sp + "Hello\":3,\"" +
        sp + "world\":4,\"!\":5,\"H\":6,\"e\":7,\"l\":8,\"o\":9"
        "}},\"unk_token\":{\"id\":0},\"bos_token\":{\"id\":1},\"eos_token\":{\"id\":2}}";
    std::ofstream out(dir / "tokenizer.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

std::filesystem::path make_checkpoint() {
    const auto dir = make_case_dir("checkpoint");
    write_config(dir);
    write_tokenizer(dir);

    const std::vector<TensorFixture> tensors = {
        {"model.embed_tokens.weight", "F16", {16, 8}, make_payload(256, 1)},
        {"model.layers.0.self_attn.q_proj.qweight", "I32", {4}, make_payload(16, 2)},
        {"model.layers.0.self_attn.q_proj.scales", "F16", {1, 8}, make_payload(16, 3)},
        {"model.layers.0.self_attn.q_proj.qzeros", "I32", {1}, make_payload(4, 4)},
        {"model.layers.1.mlp.down_proj.weight", "F16", {2, 8}, make_payload(32, 5)},
        {"model.norm.weight", "F16", {8}, make_payload(16, 6)},
        {"lm_head.weight", "F16", {16, 8}, make_payload(256, 7)},
    };
    write_shard(dir / "model-00001-of-00001.safetensors", tensors);

    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model-00001-of-00001.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

const spoolstream::core::ManifestTensor& require_tensor(
    const spoolstream::core::ModelManifest& manifest,
    const std::string& name) {
    for (const auto& tensor : manifest.tensors) {
        if (tensor.metadata.name == name) {
            return tensor;
        }
    }
    throw std::runtime_error("missing manifest tensor: " + name);
}

void test_config_tokenizer_manifest_and_profile() {
    const auto dir = make_checkpoint();
    const auto config = spoolstream::core::load_model_config(dir);
    require_true(config.hidden_size == 8, "hidden_size mismatch");
    require_true(config.num_hidden_layers == 2, "layer count mismatch");
    require_true(config.quantization == spoolstream::core::ModelQuantization::AWQ_INT4,
                 "quantization mismatch");

    const auto tokenizer = spoolstream::core::load_tokenizer_json(dir / "tokenizer.json");
    const std::vector<int> ids =
        spoolstream::core::encode_tokenizer_text(tokenizer, " Hello world!", true);
    require_true(ids.size() == 4, "tokenizer id count mismatch");
    require_true(ids[0] == 1 && ids[1] == 3 && ids[2] == 4 && ids[3] == 5,
                 "tokenizer encode mismatch");
    const std::string decoded =
        spoolstream::core::decode_tokenizer_tokens(tokenizer, ids, true);
    require_true(decoded == " Hello world!", "tokenizer decode mismatch: " + decoded);

    const auto manifest = spoolstream::core::build_model_manifest(dir, "STRICT", 1024);
    require_true(manifest.tensors.size() == 7, "manifest tensor count mismatch");
    require_true(require_tensor(manifest, "model.embed_tokens.weight").role ==
                     spoolstream::core::TensorRole::TOKEN_EMBEDDING,
                 "embedding role mismatch");
    require_true(require_tensor(manifest, "model.layers.0.self_attn.q_proj.qweight").role ==
                     spoolstream::core::TensorRole::QUANT_QWEIGHT,
                 "qweight role mismatch");
    require_true(require_tensor(manifest, "lm_head.weight").role ==
                     spoolstream::core::TensorRole::LM_HEAD,
                 "lm_head role mismatch");

    spoolstream::core::MemoryBudget budget{};
    budget.max_vram_bytes = 8ULL * 1024ULL * 1024ULL * 1024ULL;
    budget.max_host_staging_bytes = 512;
    budget.max_host_resident_bytes = 128;
    budget.kv_cache_bytes = 1024;
    const auto profile = spoolstream::core::plan_model_profile(manifest, budget);
    require_true(profile.supported, "profile should be supported: " + profile.reason);
    require_true(profile.streaming_required, "profile should require streaming");
    require_true(profile.required_host_staging_bytes == 256,
                 "required host staging mismatch");

    budget.max_host_staging_bytes = 32;
    const auto rejected = spoolstream::core::plan_model_profile(manifest, budget);
    require_true(!rejected.supported, "profile should reject small staging budget");

    std::filesystem::remove_all(dir);
}

void test_qwen2_bf16_single_shard_manifest() {
    const auto dir = make_case_dir("qwen2_bf16");
    write_qwen2_bf16_config(dir);
    const std::vector<TensorFixture> tensors = {
        {"model.embed_tokens.weight", "BF16", {32, 8}, make_payload(512, 1)},
        {"model.layers.0.input_layernorm.weight", "BF16", {8}, make_payload(16, 2)},
        {"model.layers.0.self_attn.q_proj.weight", "BF16", {8, 8}, make_payload(128, 3)},
        {"model.layers.1.post_attention_layernorm.weight", "BF16", {8}, make_payload(16, 4)},
        {"model.layers.1.mlp.down_proj.weight", "BF16", {8, 16}, make_payload(256, 5)},
        {"model.norm.weight", "BF16", {8}, make_payload(16, 6)},
        {"lm_head.weight", "BF16", {32, 8}, make_payload(512, 7)},
    };
    write_shard(dir / "model.safetensors", tensors);

    const auto config = spoolstream::core::load_model_config(dir);
    require_true(config.family == spoolstream::core::ModelFamily::QWEN2,
                 "Qwen2 family mismatch");
    require_true(config.quantization == spoolstream::core::ModelQuantization::BF16,
                 "Qwen2 BF16 quantization mismatch");
    require_true(config.rope_theta == 1000000.0, "Qwen2 rope theta mismatch");
    require_true(config.tie_word_embeddings, "Qwen2 tied embedding flag mismatch");

    const auto manifest = spoolstream::core::build_model_manifest(dir, "STRICT", 1024);
    require_true(manifest.tensors.size() == tensors.size(), "Qwen2 manifest tensor count mismatch");
    require_true(manifest.topology.total_layers == 2, "Qwen2 layer count mismatch");
    require_true(require_tensor(manifest, "model.layers.0.self_attn.q_proj.weight").role ==
                     spoolstream::core::TensorRole::ATTN_Q,
                 "Qwen2 q_proj role mismatch");
    require_true(require_tensor(manifest, "model.layers.1.mlp.down_proj.weight").role ==
                     spoolstream::core::TensorRole::MLP_DOWN,
                 "Qwen2 down_proj role mismatch");

    std::filesystem::remove_all(dir);
}

void test_streaming_store_exact_read_and_h2d_copy() {
    const auto dir = make_checkpoint();
    const auto manifest = spoolstream::core::build_model_manifest(dir, "STRICT", 1024);
    const auto& tensor = require_tensor(manifest, "model.layers.1.mlp.down_proj.weight");

    auto store = spoolstream::core::create_streaming_tensor_store(dir, 64);
    const auto staged = spoolstream::core::stage_tensor_bytes(store, tensor);
    require_true(staged.byte_size == 32, "staged tensor size mismatch");
    const auto expected = make_payload(32, 5);
    require_true(std::memcmp(staged.host_ptr, expected.data(), expected.size()) == 0,
                 "staged payload mismatch");
    require_true(staged.device_uva_ptr != nullptr, "staged UVA pointer is null");

    DeviceBuffer<uint8_t> device(expected.size());
    spoolstream::core::copy_staged_tensor_to_device(store, device.get(), staged);
    const auto copied = device.copy_to_host();
    require_true(copied == expected, "H2D copied staged payload mismatch");

    spoolstream::core::destroy_streaming_tensor_store(store);
    require_true(store.host_staging_ptr == nullptr, "staging buffer was not nulled");

    auto too_small = spoolstream::core::create_streaming_tensor_store(dir, 8);
    require_throw([&]() {
        (void)spoolstream::core::stage_tensor_bytes(too_small, tensor);
    }, "staging too small");
    spoolstream::core::destroy_streaming_tensor_store(too_small);

    std::filesystem::remove_all(dir);
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_config_tokenizer_manifest_and_profile();
        test_qwen2_bf16_single_shard_manifest();
        test_streaming_store_exact_read_and_h2d_copy();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream model tests passed\n";
    return 0;
}
