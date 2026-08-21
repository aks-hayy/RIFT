#include "spoolstream/quantized_adapter.h"

#include "spoolstream/kernels.h"
#include "spoolstream/memory_manager.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

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

    void copy_from_host(const std::vector<T>& host) {
        if (!host.empty()) {
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(ptr_,
                                             host.data(),
                                             sizeof(T) * host.size(),
                                             cudaMemcpyHostToDevice));
        }
    }

    std::vector<T> copy_to_host() const {
        std::vector<T> host(count_);
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                             ptr_,
                                             sizeof(T) * count_,
                                             cudaMemcpyDeviceToHost));
        }
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

struct TensorFixture {
    std::string name;
    std::string dtype;
    std::vector<int64_t> shape;
    std::vector<uint8_t> payload;
};

std::filesystem::path make_case_dir(const std::string& name) {
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path root =
        std::filesystem::temp_directory_path() /
        ("spoolstream_quantized_" + name + "_" + std::to_string(stamp));
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

template <typename T>
std::vector<uint8_t> bytes_from_vector(const std::vector<T>& values) {
    std::vector<uint8_t> bytes(sizeof(T) * values.size());
    if (!values.empty()) {
        std::memcpy(bytes.data(), values.data(), bytes.size());
    }
    return bytes;
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

void write_quant_config(const std::filesystem::path& dir) {
    const std::string json =
        "{"
        "\"model_type\":\"llama\","
        "\"hidden_size\":16,"
        "\"intermediate_size\":32,"
        "\"num_hidden_layers\":1,"
        "\"num_attention_heads\":2,"
        "\"num_key_value_heads\":1,"
        "\"vocab_size\":64,"
        "\"quantization_config\":{\"quant_method\":\"gptq\"}"
        "}";
    std::ofstream out(dir / "config.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

spoolstream::core::ManifestTensor make_tensor(const std::string& name,
                                              spoolstream::core::TensorRole role,
                                              int layer_id,
                                              const std::string& base_name,
                                              const std::string& dtype,
                                              std::vector<int64_t> shape,
                                              size_t bytes) {
    spoolstream::core::ManifestTensor tensor{};
    tensor.metadata.name = name;
    tensor.metadata.shard_file = "model.safetensors";
    tensor.metadata.start_offset = 0;
    tensor.metadata.end_offset = bytes;
    tensor.metadata.shape = std::move(shape);
    tensor.metadata.data_type = dtype;
    tensor.role = role;
    tensor.layer_id = layer_id;
    tensor.base_name = base_name;
    return tensor;
}

spoolstream::core::ModelManifest make_manifest(
    spoolstream::core::ModelQuantization quantization =
        spoolstream::core::ModelQuantization::AWQ_INT4) {
    spoolstream::core::ModelManifest manifest{};
    manifest.config.family = spoolstream::core::ModelFamily::LLAMA;
    manifest.config.quantization = quantization;
    manifest.config.hidden_size = 16;
    manifest.config.intermediate_size = 32;
    manifest.config.num_hidden_layers = 1;
    manifest.config.num_attention_heads = 2;
    manifest.config.num_key_value_heads = 1;
    manifest.config.vocab_size = 64;
    manifest.config.model_type = "llama";
    manifest.config.tie_word_embeddings = false;
    manifest.topology.total_layers = 1;
    return manifest;
}

void add_quant_family(spoolstream::core::ModelManifest& manifest,
                      const std::string& base,
                      int layer_id,
                      int input_features,
                      int output_features,
                      int groups,
                      bool packed_zeros,
                      bool include_scales = true,
                      bool include_gidx = false,
                      int gidx_size_override = -1) {
    const int packed_cols = output_features / 8;
    manifest.tensors.push_back(make_tensor(base + ".qweight",
                                           spoolstream::core::TensorRole::QUANT_QWEIGHT,
                                           layer_id,
                                           base,
                                           "I32",
                                           {input_features, packed_cols},
                                           static_cast<size_t>(input_features) *
                                               static_cast<size_t>(packed_cols) *
                                               sizeof(uint32_t)));
    if (include_scales) {
        manifest.tensors.push_back(make_tensor(base + ".scales",
                                               spoolstream::core::TensorRole::QUANT_SCALE,
                                               layer_id,
                                               base,
                                               "F16",
                                               {groups, output_features},
                                               static_cast<size_t>(groups) *
                                                   static_cast<size_t>(output_features) * 2U));
    }
    manifest.tensors.push_back(make_tensor(base + (packed_zeros ? ".qzeros" : ".zeros"),
                                           spoolstream::core::TensorRole::QUANT_ZERO,
                                           layer_id,
                                           base,
                                           packed_zeros ? "I32" : "F16",
                                           packed_zeros
                                               ? std::vector<int64_t>{groups, packed_cols}
                                               : std::vector<int64_t>{groups, output_features},
                                           packed_zeros
                                               ? static_cast<size_t>(groups) *
                                                     static_cast<size_t>(packed_cols) *
                                                     sizeof(uint32_t)
                                               : static_cast<size_t>(groups) *
                                                     static_cast<size_t>(output_features) * 2U));
    if (include_gidx) {
        const int gidx_size = gidx_size_override < 0 ? input_features : gidx_size_override;
        manifest.tensors.push_back(make_tensor(base + ".g_idx",
                                               spoolstream::core::TensorRole::QUANT_GIDX,
                                               layer_id,
                                               base,
                                               "I32",
                                               {gidx_size},
                                               static_cast<size_t>(gidx_size) *
                                                   sizeof(uint32_t)));
    }
}

void add_gptq_exllama_family(spoolstream::core::ModelManifest& manifest,
                             const std::string& base,
                             int layer_id,
                             int input_features,
                             int output_features,
                             int groups,
                             bool include_gidx = true,
                             int gidx_size_override = -1,
                             int qzeros_cols_override = -1) {
    const int qweight_rows = input_features / 8;
    const int packed_output_cols = output_features / 8;
    const int qzeros_cols = qzeros_cols_override < 0 ? packed_output_cols :
                                                        qzeros_cols_override;
    manifest.tensors.push_back(make_tensor(base + ".qweight",
                                           spoolstream::core::TensorRole::QUANT_QWEIGHT,
                                           layer_id,
                                           base,
                                           "I32",
                                           {qweight_rows, output_features},
                                           static_cast<size_t>(qweight_rows) *
                                               static_cast<size_t>(output_features) *
                                               sizeof(uint32_t)));
    manifest.tensors.push_back(make_tensor(base + ".scales",
                                           spoolstream::core::TensorRole::QUANT_SCALE,
                                           layer_id,
                                           base,
                                           "F16",
                                           {groups, output_features},
                                           static_cast<size_t>(groups) *
                                               static_cast<size_t>(output_features) * 2U));
    manifest.tensors.push_back(make_tensor(base + ".qzeros",
                                           spoolstream::core::TensorRole::QUANT_ZERO,
                                           layer_id,
                                           base,
                                           "I32",
                                           {groups, qzeros_cols},
                                           static_cast<size_t>(groups) *
                                               static_cast<size_t>(qzeros_cols) *
                                               sizeof(uint32_t)));
    if (include_gidx) {
        const int gidx_size = gidx_size_override < 0 ? input_features : gidx_size_override;
        manifest.tensors.push_back(make_tensor(base + ".g_idx",
                                               spoolstream::core::TensorRole::QUANT_GIDX,
                                               layer_id,
                                               base,
                                               "I32",
                                               {gidx_size},
                                               static_cast<size_t>(gidx_size) *
                                                   sizeof(uint32_t)));
    }
}

const spoolstream::core::QuantizedProjection& require_projection(
    const spoolstream::core::QuantizedAdapterReport& report,
    spoolstream::core::QuantizedProjectionRole role) {
    for (const auto& projection : report.projections) {
        if (projection.role == role) {
            return projection;
        }
    }
    throw std::runtime_error("missing projection role");
}

void test_direct_kernel_compatible_awq() {
    auto manifest = make_manifest();
    add_quant_family(manifest, "model.layers.0.self_attn.q_proj", 0, 16, 16, 2, false);
    add_quant_family(manifest, "model.layers.0.self_attn.k_proj", 0, 16, 8, 2, false);
    add_quant_family(manifest, "model.layers.0.mlp.gate_proj", 0, 16, 32, 4, false);

    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "direct AWQ report should be supported");
    require_true(report.issues.empty(), "direct AWQ report should have no issues");
    require_true(report.projections.size() == 3, "projection count mismatch");
    require_true(report.kernel_compatible_projection_count == 3,
                 "kernel compatible projection count mismatch");

    const auto& q = require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    require_true(q.input_features == 16, "q input features mismatch");
    require_true(q.output_features == 16, "q output features mismatch");
    require_true(q.group_count == 2, "q group count mismatch");
    require_true(q.group_size == 8, "q group size mismatch");
    require_true(q.zero_encoding == spoolstream::core::QuantizedZeroEncoding::FP16_EXPANDED,
                 "q zero encoding mismatch");
}

void test_packed_qzeros_real_checkpoint_layout() {
    auto manifest = make_manifest(spoolstream::core::ModelQuantization::GPTQ_INT4);
    add_quant_family(manifest, "model.layers.0.self_attn.o_proj", 0, 16, 16, 2, true);

    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "packed qzeros should be understood by adapter");
    require_true(report.issues.empty(), "packed qzeros should have no structural issues");
    require_true(report.kernel_compatible_projection_count == 0,
                 "packed qzeros should not be current-kernel compatible");
    require_true(report.materializable_projection_count == 1,
                 "packed qzeros should be materializable after Phase 10 fixup");
    const auto& projection =
        require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_O);
    require_true(projection.zero_encoding ==
                     spoolstream::core::QuantizedZeroEncoding::INT32_PACKED,
                 "packed qzeros encoding mismatch");
    require_true(projection.materializable, "packed qzeros projection should be materializable");
    require_true(projection.compatibility_notes.find("materializable") != std::string::npos,
                 "packed qzeros should report materializable path");
}

void test_missing_scales_rejected() {
    auto manifest = make_manifest();
    add_quant_family(manifest,
                     "model.layers.0.mlp.up_proj",
                     0,
                     16,
                     32,
                     2,
                     false,
                     false);

    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(!report.supported, "missing scales should be unsupported");
    require_true(!report.issues.empty(), "missing scales should report issue");
}

void test_malformed_gidx_rejected() {
    auto manifest = make_manifest();
    add_quant_family(manifest,
                     "model.layers.0.mlp.down_proj",
                     0,
                     32,
                     16,
                     4,
                     true,
                     true,
                     true,
                     8);

    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(!report.supported, "bad g_idx should be unsupported");
    require_true(!report.issues.empty(), "bad g_idx should report issue");
}

void test_qwen2_full_awq_projection_family() {
    auto manifest = make_manifest(spoolstream::core::ModelQuantization::AWQ_INT4);
    manifest.config.family = spoolstream::core::ModelFamily::QWEN2;
    manifest.config.model_type = "qwen2";
    manifest.config.num_hidden_layers = 2;
    manifest.config.vocab_size = 32;
    manifest.topology.total_layers = 2;

    for (int layer = 0; layer < manifest.config.num_hidden_layers; ++layer) {
        const std::string prefix =
            "model.layers." + std::to_string(layer);
        add_quant_family(manifest, prefix + ".self_attn.q_proj", layer, 16, 16, 2, true);
        add_quant_family(manifest, prefix + ".self_attn.k_proj", layer, 16, 8, 2, true);
        add_quant_family(manifest, prefix + ".self_attn.v_proj", layer, 16, 8, 2, true);
        add_quant_family(manifest, prefix + ".self_attn.o_proj", layer, 16, 16, 2, true);
        add_quant_family(manifest, prefix + ".mlp.gate_proj", layer, 16, 32, 2, true);
        add_quant_family(manifest, prefix + ".mlp.up_proj", layer, 16, 32, 2, true);
        add_quant_family(manifest, prefix + ".mlp.down_proj", layer, 32, 16, 2, true);
    }
    add_quant_family(manifest, "lm_head", -1, 16, 32, 2, true);

    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "Qwen2 AWQ/GPTQ projection family should be supported");
    require_true(report.issues.empty(), "Qwen2 quantized projection family should have no issues");
    require_true(report.projections.size() == 15, "Qwen2 projection count mismatch");
    require_true(report.materializable_projection_count == 15,
                 "Qwen2 materializable projection count mismatch");
    require_true(report.kernel_compatible_projection_count == 0,
                 "packed qzeros should require materialization before current kernel");
    require_true(require_projection(report,
                                    spoolstream::core::QuantizedProjectionRole::ATTN_K)
                     .output_features == 8,
                 "Qwen2 GQA k_proj output feature count mismatch");
    require_true(require_projection(report,
                                    spoolstream::core::QuantizedProjectionRole::LM_HEAD)
                     .layer_id == -1,
                 "Qwen2 lm_head should be model-level projection");
}

void test_gptq_exllama_layout_detection() {
    auto manifest = make_manifest(spoolstream::core::ModelQuantization::GPTQ_INT4);
    add_gptq_exllama_family(manifest,
                            "model.layers.0.self_attn.q_proj",
                            0,
                            16,
                            16,
                            2,
                            true);

    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "GPTQ ExLlama projection should be supported");
    require_true(report.issues.empty(), "GPTQ ExLlama projection should have no issues");
    require_true(report.materializable_projection_count == 1,
                 "GPTQ ExLlama materializable count mismatch");
    const auto& projection =
        require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    require_true(projection.weight_layout ==
                     spoolstream::core::QuantizedWeightLayout::GPTQ_EXLLAMA_INT4,
                 "GPTQ ExLlama layout mismatch");
    require_true(projection.qweight_rows == 2, "GPTQ ExLlama qweight row mismatch");
    require_true(projection.qweight_columns == 16, "GPTQ ExLlama qweight column mismatch");
    require_true(projection.input_features == 16, "GPTQ ExLlama input feature mismatch");
    require_true(projection.output_features == 16, "GPTQ ExLlama output feature mismatch");
    require_true(projection.group_count == 2, "GPTQ ExLlama group count mismatch");
    require_true(projection.group_size == 8, "GPTQ ExLlama group size mismatch");
    require_true(projection.g_idx != nullptr, "GPTQ ExLlama g_idx should be present");
}

void test_gptq_exllama_bad_shapes_rejected() {
    {
        auto manifest = make_manifest(spoolstream::core::ModelQuantization::GPTQ_INT4);
        add_gptq_exllama_family(manifest,
                                "model.layers.0.self_attn.q_proj",
                                0,
                                16,
                                16,
                                2,
                                true,
                                8);
        const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
        require_true(!report.supported, "bad GPTQ ExLlama g_idx shape should be unsupported");
        require_true(!report.issues.empty(), "bad GPTQ ExLlama g_idx shape should report issue");
    }
    {
        auto manifest = make_manifest(spoolstream::core::ModelQuantization::GPTQ_INT4);
        add_gptq_exllama_family(manifest,
                                "model.layers.0.self_attn.q_proj",
                                0,
                                16,
                                16,
                                2,
                                true,
                                -1,
                                3);
        const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
        require_true(!report.supported, "bad GPTQ ExLlama qzeros shape should be unsupported");
        require_true(!report.issues.empty(), "bad GPTQ ExLlama qzeros shape should report issue");
    }
}

std::vector<uint32_t> make_packed_qzeros(int groups, int output_features) {
    const int packed_cols = output_features / 8;
    std::vector<uint32_t> packed(static_cast<size_t>(groups) *
                                 static_cast<size_t>(packed_cols));
    for (int group = 0; group < groups; ++group) {
        for (int pack = 0; pack < packed_cols; ++pack) {
            uint32_t word = 0;
            for (int nibble = 0; nibble < 8; ++nibble) {
                const uint32_t value =
                    static_cast<uint32_t>((group * 3 + pack * 5 + nibble + 2) & 0x0F);
                word |= value << (4 * nibble);
            }
            packed[static_cast<size_t>(group) * static_cast<size_t>(packed_cols) +
                   static_cast<size_t>(pack)] = word;
        }
    }
    return packed;
}

void test_qzeros_expansion() {
    constexpr int groups = 2;
    constexpr int output_features = 16;
    const auto packed = make_packed_qzeros(groups, output_features);
    const auto expanded = spoolstream::core::expand_packed_qzeros_to_half(packed.data(),
                                                                         groups,
                                                                         output_features);
    require_true(expanded.size() == static_cast<size_t>(groups) * output_features,
                 "expanded qzeros size mismatch");
    for (int group = 0; group < groups; ++group) {
        for (int col = 0; col < output_features; ++col) {
            const int packed_cols = output_features / 8;
            const uint32_t word = packed[static_cast<size_t>(group) *
                                         static_cast<size_t>(packed_cols) +
                                         static_cast<size_t>(col / 8)];
            const uint32_t expected = (word >> (4 * (col & 7))) & 0x0FU;
            const float actual =
                __half2float(expanded[static_cast<size_t>(group) *
                                      static_cast<size_t>(output_features) +
                                      static_cast<size_t>(col)]);
            require_true(std::fabs(actual - static_cast<float>(expected)) < 0.001f,
                         "expanded qzero mismatch");
        }
    }
    require_throw([&]() {
        (void)spoolstream::core::expand_packed_qzeros_to_half(nullptr, groups, output_features);
    }, "null qzeros");
}

uint8_t quant_value_for(int k, int n) {
    return static_cast<uint8_t>((k * 3 + n * 5 + 7) & 0x0F);
}

std::vector<half> make_input(int m, int k) {
    std::vector<half> x(static_cast<size_t>(m) * static_cast<size_t>(k));
    for (int row = 0; row < m; ++row) {
        for (int col = 0; col < k; ++col) {
            const float value = static_cast<float>(((row * 7 + col * 3) % 11) - 5) *
                                0.03125f;
            x[static_cast<size_t>(row) * static_cast<size_t>(k) + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }
    return x;
}

std::vector<uint32_t> make_packed_weights(int k, int n) {
    std::vector<uint32_t> packed(static_cast<size_t>(k) * static_cast<size_t>(n / 8), 0);
    for (int row = 0; row < k; ++row) {
        for (int pack = 0; pack < n / 8; ++pack) {
            uint32_t word = 0;
            for (int nibble = 0; nibble < 8; ++nibble) {
                const int col = pack * 8 + nibble;
                word |= static_cast<uint32_t>(quant_value_for(row, col)) << (4 * nibble);
            }
            packed[static_cast<size_t>(row) * static_cast<size_t>(n / 8) +
                   static_cast<size_t>(pack)] = word;
        }
    }
    return packed;
}

std::vector<uint32_t> make_exllama_packed_weights(int k, int n) {
    std::vector<uint32_t> packed(static_cast<size_t>(k / 8) * static_cast<size_t>(n), 0);
    for (int pack_row = 0; pack_row < k / 8; ++pack_row) {
        for (int col = 0; col < n; ++col) {
            uint32_t word = 0;
            for (int nibble = 0; nibble < 8; ++nibble) {
                const int kk = pack_row * 8 + nibble;
                word |= static_cast<uint32_t>(quant_value_for(kk, col)) << (4 * nibble);
            }
            packed[static_cast<size_t>(pack_row) * static_cast<size_t>(n) +
                   static_cast<size_t>(col)] = word;
        }
    }
    return packed;
}

std::vector<int32_t> make_gidx(int k, int groups) {
    std::vector<int32_t> gidx(static_cast<size_t>(k));
    for (int kk = 0; kk < k; ++kk) {
        gidx[static_cast<size_t>(kk)] = static_cast<int32_t>((kk * 3 + 1) % groups);
    }
    return gidx;
}

std::vector<half> make_scales(int groups, int output_features) {
    std::vector<half> scales(static_cast<size_t>(groups) *
                             static_cast<size_t>(output_features));
    for (int group = 0; group < groups; ++group) {
        for (int col = 0; col < output_features; ++col) {
            const float value = 0.01875f + 0.00125f * static_cast<float>((group + col) % 5);
            scales[static_cast<size_t>(group) * static_cast<size_t>(output_features) +
                   static_cast<size_t>(col)] = __float2half(value);
        }
    }
    return scales;
}

std::vector<half> add_qzero_offset(std::vector<half> values, float offset) {
    for (half& value : values) {
        value = __float2half(__half2float(value) + offset);
    }
    return values;
}

std::filesystem::path make_streamed_quant_checkpoint(const std::vector<uint32_t>& packed_weights,
                                                     const std::vector<half>& scales,
                                                     const std::vector<uint32_t>& packed_qzeros,
                                                     int k,
                                                     int n,
                                                     int groups) {
    const auto dir = make_case_dir("streamed_slot");
    write_quant_config(dir);
    const int packed_cols = n / 8;
    const std::vector<TensorFixture> tensors = {
        {"model.layers.0.self_attn.q_proj.qweight",
         "I32",
         {k, packed_cols},
         bytes_from_vector(packed_weights)},
        {"model.layers.0.self_attn.q_proj.scales",
         "F16",
         {groups, n},
         bytes_from_vector(scales)},
        {"model.layers.0.self_attn.q_proj.qzeros",
         "I32",
         {groups, packed_cols},
         bytes_from_vector(packed_qzeros)},
    };
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

std::filesystem::path make_streamed_gptq_exllama_checkpoint(
    const std::vector<uint32_t>& packed_weights,
    const std::vector<half>& scales,
    const std::vector<uint32_t>& packed_qzeros,
    const std::vector<int32_t>& gidx,
    int k,
    int n,
    int groups) {
    const auto dir = make_case_dir("streamed_exllama");
    write_quant_config(dir);
    const int packed_k_rows = k / 8;
    const int packed_output_cols = n / 8;
    const std::vector<TensorFixture> tensors = {
        {"model.layers.0.self_attn.q_proj.qweight",
         "I32",
         {packed_k_rows, n},
         bytes_from_vector(packed_weights)},
        {"model.layers.0.self_attn.q_proj.scales",
         "F16",
         {groups, n},
         bytes_from_vector(scales)},
        {"model.layers.0.self_attn.q_proj.qzeros",
         "I32",
         {groups, packed_output_cols},
         bytes_from_vector(packed_qzeros)},
        {"model.layers.0.self_attn.q_proj.g_idx",
         "I32",
         {k},
         bytes_from_vector(gidx)},
    };
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

float dequantize_reference(const std::vector<uint32_t>& packed,
                           const std::vector<half>& scales,
                           const std::vector<half>& zeros,
                           int k,
                           int n,
                           int group_size,
                           int row,
                           int col) {
    const uint32_t word =
        packed[static_cast<size_t>(row) * static_cast<size_t>(n / 8) +
               static_cast<size_t>(col / 8)];
    const uint32_t quantized = (word >> (4 * (col & 7))) & 0x0FU;
    const int group = row / group_size;
    const size_t metadata_index =
        static_cast<size_t>(group) * static_cast<size_t>(n) + static_cast<size_t>(col);
    return (static_cast<float>(quantized) - __half2float(zeros[metadata_index])) *
           __half2float(scales[metadata_index]);
}

std::vector<half> reference_gemm(const std::vector<half>& x,
                                 const std::vector<uint32_t>& packed,
                                 const std::vector<half>& scales,
                                 const std::vector<half>& zeros,
                                 const spoolstream::core::FusedGemmConfig& config) {
    std::vector<half> output(static_cast<size_t>(config.m) * static_cast<size_t>(config.n));
    for (int row = 0; row < config.m; ++row) {
        for (int col = 0; col < config.n; ++col) {
            float accumulator = 0.0f;
            for (int kk = 0; kk < config.k; ++kk) {
                const float lhs =
                    __half2float(x[static_cast<size_t>(row) * static_cast<size_t>(config.k) +
                                   static_cast<size_t>(kk)]);
                const float rhs = dequantize_reference(packed,
                                                       scales,
                                                       zeros,
                                                       config.k,
                                                       config.n,
                                                       config.group_size,
                                                       kk,
                                                       col);
                accumulator += lhs * rhs;
            }
            output[static_cast<size_t>(row) * static_cast<size_t>(config.n) +
                   static_cast<size_t>(col)] = __float2half(accumulator);
        }
    }
    return output;
}

float dequantize_exllama_reference(const std::vector<uint32_t>& packed,
                                   const std::vector<half>& scales,
                                   const std::vector<half>& zeros,
                                   const std::vector<int32_t>& gidx,
                                   int n,
                                   int kk,
                                   int col) {
    const uint32_t word =
        packed[static_cast<size_t>(kk / 8) * static_cast<size_t>(n) +
               static_cast<size_t>(col)];
    const uint32_t quantized = (word >> (4 * (kk & 7))) & 0x0FU;
    const int group = gidx[static_cast<size_t>(kk)];
    const size_t metadata_index =
        static_cast<size_t>(group) * static_cast<size_t>(n) + static_cast<size_t>(col);
    return (static_cast<float>(quantized) - __half2float(zeros[metadata_index])) *
           __half2float(scales[metadata_index]);
}

std::vector<half> reference_exllama_gemm(const std::vector<half>& x,
                                         const std::vector<uint32_t>& packed,
                                         const std::vector<half>& scales,
                                         const std::vector<half>& zeros,
                                         const std::vector<int32_t>& gidx,
                                         const spoolstream::core::FusedGemmConfig& config) {
    std::vector<half> output(static_cast<size_t>(config.m) * static_cast<size_t>(config.n));
    for (int row = 0; row < config.m; ++row) {
        for (int col = 0; col < config.n; ++col) {
            float accumulator = 0.0f;
            for (int kk = 0; kk < config.k; ++kk) {
                const float lhs =
                    __half2float(x[static_cast<size_t>(row) * static_cast<size_t>(config.k) +
                                   static_cast<size_t>(kk)]);
                accumulator += lhs * dequantize_exllama_reference(packed,
                                                                  scales,
                                                                  zeros,
                                                                  gidx,
                                                                  config.n,
                                                                  kk,
                                                                  col);
            }
            output[static_cast<size_t>(row) * static_cast<size_t>(config.n) +
                   static_cast<size_t>(col)] = __float2half(accumulator);
        }
    }
    return output;
}

void assert_close(const std::vector<half>& actual,
                  const std::vector<half>& expected,
                  const std::string& case_name) {
    require_true(actual.size() == expected.size(), case_name + ": size mismatch");
    for (size_t i = 0; i < actual.size(); ++i) {
        const float a = __half2float(actual[i]);
        const float e = __half2float(expected[i]);
        const float diff = std::fabs(a - e);
        if (diff > 0.02f) {
            throw std::runtime_error(case_name + ": mismatch at " + std::to_string(i) +
                                     " actual=" + std::to_string(a) +
                                     " expected=" + std::to_string(e));
        }
    }
}

void test_packed_qzeros_projection_execution() {
    constexpr int m = 16;
    constexpr int k = 16;
    constexpr int n = 16;
    constexpr int groups = 2;
    auto manifest = make_manifest(spoolstream::core::ModelQuantization::GPTQ_INT4);
    add_quant_family(manifest, "model.layers.0.self_attn.q_proj", 0, k, n, groups, true);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    const auto& projection =
        require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    const auto config = spoolstream::core::build_quantized_projection_gemm_config(
        projection,
        m,
        spoolstream::core::ActivationKind::NONE);

    const auto x = make_input(m, k);
    const auto packed_weights = make_packed_weights(k, n);
    const auto scales = make_scales(groups, n);
    const auto packed_qzeros = make_packed_qzeros(groups, n);
    const auto expanded_zeros =
        spoolstream::core::expand_packed_qzeros_to_half(packed_qzeros.data(), groups, n);
    const auto expected = reference_gemm(x, packed_weights, scales, expanded_zeros, config);

    auto workspace = spoolstream::core::create_quantized_projection_metadata_workspace(projection);
    spoolstream::core::upload_projection_zeros_to_workspace(workspace,
                                                            projection,
                                                            packed_qzeros.data(),
                                                            packed_qzeros.size() *
                                                                sizeof(uint32_t));

    DeviceBuffer<half> d_x(x.size());
    DeviceBuffer<uint32_t> d_packed(packed_weights.size());
    DeviceBuffer<half> d_scales(scales.size());
    DeviceBuffer<half> d_output(expected.size());
    d_x.copy_from_host(x);
    d_packed.copy_from_host(packed_weights);
    d_scales.copy_from_host(scales);
    spoolstream::core::launch_fused_dequant_gemm(d_x.get(),
                                                 d_packed.get(),
                                                 d_scales.get(),
                                                 workspace.device_zeros,
                                                 nullptr,
                                                 d_output.get(),
                                                 config);
    assert_close(d_output.copy_to_host(), expected, "packed qzeros projection");

    spoolstream::core::destroy_quantized_projection_metadata_workspace(workspace);
    require_true(workspace.device_zeros == nullptr, "workspace zeros not nulled");
}

void test_gptq_exllama_projection_execution() {
    constexpr int m = 3;
    constexpr int k = 16;
    constexpr int n = 16;
    constexpr int groups = 2;
    auto manifest = make_manifest(spoolstream::core::ModelQuantization::GPTQ_INT4);
    add_gptq_exllama_family(manifest, "model.layers.0.self_attn.q_proj", 0, k, n, groups);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "GPTQ ExLlama execution manifest should be supported");
    const auto& projection =
        require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    const auto config = spoolstream::core::build_quantized_projection_gemm_config(
        projection,
        m,
        spoolstream::core::ActivationKind::NONE);
    require_true(config.quant_format == spoolstream::core::QuantFormat::GPTQ_EXLLAMA_INT4,
                 "GPTQ ExLlama GEMM config quant format mismatch");

    const auto x = make_input(m, k);
    const auto packed_weights = make_exllama_packed_weights(k, n);
    const auto scales = make_scales(groups, n);
    const auto packed_qzeros = make_packed_qzeros(groups, n);
    const auto gidx = make_gidx(k, groups);
    const auto expanded_zeros = add_qzero_offset(
        spoolstream::core::expand_packed_qzeros_to_half(packed_qzeros.data(), groups, n),
        1.0f);
    const auto expected =
        reference_exllama_gemm(x, packed_weights, scales, expanded_zeros, gidx, config);

    auto workspace = spoolstream::core::create_quantized_projection_metadata_workspace(projection);
    spoolstream::core::upload_projection_zeros_to_workspace(workspace,
                                                            projection,
                                                            packed_qzeros.data(),
                                                            packed_qzeros.size() *
                                                                sizeof(uint32_t));
    spoolstream::core::upload_projection_gidx_to_workspace(workspace,
                                                           projection,
                                                           gidx.data(),
                                                           gidx.size() * sizeof(int32_t));

    DeviceBuffer<half> d_x(x.size());
    DeviceBuffer<uint32_t> d_packed(packed_weights.size());
    DeviceBuffer<half> d_scales(scales.size());
    DeviceBuffer<half> d_output(expected.size());
    d_x.copy_from_host(x);
    d_packed.copy_from_host(packed_weights);
    d_scales.copy_from_host(scales);

    const auto view = spoolstream::core::bind_quantized_projection_device_view(
        projection,
        d_packed.get(),
        d_scales.get(),
        workspace,
        m,
        spoolstream::core::ActivationKind::NONE);
    spoolstream::core::launch_quantized_projection(d_x.get(),
                                                   d_output.get(),
                                                   view);
    assert_close(d_output.copy_to_host(), expected, "GPTQ ExLlama projection");

    std::vector<int32_t> bad_gidx = gidx;
    bad_gidx[3] = groups;
    require_throw([&]() {
        spoolstream::core::upload_projection_gidx_to_workspace(workspace,
                                                               projection,
                                                               bad_gidx.data(),
                                                               bad_gidx.size() *
                                                                   sizeof(int32_t));
    }, "bad g_idx range should be rejected");
    spoolstream::core::destroy_quantized_projection_metadata_workspace(workspace);
}

void test_streamed_slot_quantized_projection_execution() {
    constexpr int m = 16;
    constexpr int k = 16;
    constexpr int n = 16;
    constexpr int groups = 2;
    constexpr size_t staging_capacity = 512;
    constexpr size_t slot_capacity = 512;

    const auto x = make_input(m, k);
    const auto packed_weights = make_packed_weights(k, n);
    const auto scales = make_scales(groups, n);
    const auto packed_qzeros = make_packed_qzeros(groups, n);
    const auto checkpoint = make_streamed_quant_checkpoint(packed_weights,
                                                           scales,
                                                           packed_qzeros,
                                                           k,
                                                           n,
                                                           groups);

    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 4096);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "streamed quantized manifest should be supported");
    const auto& projection =
        require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    require_true(projection.materializable, "streamed projection should be materializable");

    const auto plans = spoolstream::core::build_layer_execution_plans(manifest,
                                                                      slot_capacity,
                                                                      16);
    const auto& layer_plan = spoolstream::core::require_layer_plan(plans, 0);
    auto store = spoolstream::core::create_streaming_tensor_store(checkpoint,
                                                                  staging_capacity);
    DeviceBuffer<uint8_t> slot(slot_capacity);
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot.get(), 0, slot_capacity));

    auto transfer = spoolstream::core::schedule_layer_prefetch(store,
                                                               layer_plan,
                                                               slot.get());
    spoolstream::core::wait_for_layer_transfer(transfer);
    require_true(transfer.byte_count == layer_plan.total_bytes,
                 "scheduled transfer byte count mismatch");

    const auto staged_qzeros =
        spoolstream::core::stage_tensor_bytes(store, *projection.zeros);
    auto workspace = spoolstream::core::create_quantized_projection_metadata_workspace(
        projection);
    spoolstream::core::upload_projection_zeros_to_workspace(workspace,
                                                            projection,
                                                            staged_qzeros.host_ptr,
                                                            staged_qzeros.byte_size);

    const auto view = spoolstream::core::bind_quantized_projection_runtime_view(
        projection,
        layer_plan,
        slot.get(),
        workspace,
        m,
        spoolstream::core::ActivationKind::NONE);

    const auto expanded_zeros =
        spoolstream::core::expand_packed_qzeros_to_half(packed_qzeros.data(), groups, n);
    const auto expected = reference_gemm(x,
                                         packed_weights,
                                         scales,
                                         expanded_zeros,
                                         view.gemm_config);

    DeviceBuffer<half> d_x(x.size());
    DeviceBuffer<half> d_output(expected.size());
    d_x.copy_from_host(x);
    spoolstream::core::launch_quantized_projection(d_x.get(),
                                                   d_output.get(),
                                                   view);
    assert_close(d_output.copy_to_host(), expected, "streamed slot projection");

    spoolstream::core::destroy_quantized_projection_metadata_workspace(workspace);
    spoolstream::core::destroy_scheduled_layer_transfer(transfer);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

void test_streamed_gptq_exllama_projection_execution() {
    constexpr int m = 2;
    constexpr int k = 16;
    constexpr int n = 16;
    constexpr int groups = 2;
    constexpr size_t staging_capacity = 512;
    constexpr size_t slot_capacity = 512;

    const auto x = make_input(m, k);
    const auto packed_weights = make_exllama_packed_weights(k, n);
    const auto scales = make_scales(groups, n);
    const auto packed_qzeros = make_packed_qzeros(groups, n);
    const auto gidx = make_gidx(k, groups);
    const auto checkpoint = make_streamed_gptq_exllama_checkpoint(packed_weights,
                                                                  scales,
                                                                  packed_qzeros,
                                                                  gidx,
                                                                  k,
                                                                  n,
                                                                  groups);

    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 4096);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "streamed GPTQ ExLlama manifest should be supported");
    const auto& projection =
        require_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    require_true(projection.weight_layout ==
                     spoolstream::core::QuantizedWeightLayout::GPTQ_EXLLAMA_INT4,
                 "streamed GPTQ ExLlama layout mismatch");

    const auto plans = spoolstream::core::build_layer_execution_plans(manifest,
                                                                      slot_capacity,
                                                                      16);
    const auto& layer_plan = spoolstream::core::require_layer_plan(plans, 0);
    auto store = spoolstream::core::create_streaming_tensor_store(checkpoint,
                                                                  staging_capacity);
    DeviceBuffer<uint8_t> slot(slot_capacity);
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot.get(), 0, slot_capacity));

    auto transfer = spoolstream::core::schedule_layer_prefetch(store,
                                                               layer_plan,
                                                               slot.get());
    spoolstream::core::wait_for_layer_transfer(transfer);

    auto workspace = spoolstream::core::create_quantized_projection_metadata_workspace(
        projection);
    const auto staged_qzeros =
        spoolstream::core::stage_tensor_bytes(store, *projection.zeros);
    spoolstream::core::upload_projection_zeros_to_workspace(workspace,
                                                            projection,
                                                            staged_qzeros.host_ptr,
                                                            staged_qzeros.byte_size);
    const auto staged_gidx =
        spoolstream::core::stage_tensor_bytes(store, *projection.g_idx);
    spoolstream::core::upload_projection_gidx_to_workspace(workspace,
                                                           projection,
                                                           staged_gidx.host_ptr,
                                                           staged_gidx.byte_size);

    const auto view = spoolstream::core::bind_quantized_projection_runtime_view(
        projection,
        layer_plan,
        slot.get(),
        workspace,
        m,
        spoolstream::core::ActivationKind::NONE);
    const auto expanded_zeros = add_qzero_offset(
        spoolstream::core::expand_packed_qzeros_to_half(packed_qzeros.data(), groups, n),
        1.0f);
    const auto expected =
        reference_exllama_gemm(x, packed_weights, scales, expanded_zeros, gidx, view.gemm_config);

    DeviceBuffer<half> d_x(x.size());
    DeviceBuffer<half> d_output(expected.size());
    d_x.copy_from_host(x);
    spoolstream::core::launch_quantized_projection(d_x.get(),
                                                   d_output.get(),
                                                   view);
    assert_close(d_output.copy_to_host(), expected, "streamed GPTQ ExLlama projection");

    spoolstream::core::destroy_quantized_projection_metadata_workspace(workspace);
    spoolstream::core::destroy_scheduled_layer_transfer(transfer);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_direct_kernel_compatible_awq();
        test_packed_qzeros_real_checkpoint_layout();
        test_missing_scales_rejected();
        test_malformed_gidx_rejected();
        test_qwen2_full_awq_projection_family();
        test_gptq_exllama_layout_detection();
        test_gptq_exllama_bad_shapes_rejected();
        test_qzeros_expansion();
        test_packed_qzeros_projection_execution();
        test_gptq_exllama_projection_execution();
        test_streamed_slot_quantized_projection_execution();
        test_streamed_gptq_exllama_projection_execution();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream quantized adapter tests passed\n";
    return 0;
}
