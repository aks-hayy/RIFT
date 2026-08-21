#include "spoolstream/memory_manager.h"
#include "spoolstream/layer_scheduler.h"
#include "spoolstream/quantized_adapter.h"
#include "spoolstream/streaming_store.h"
#include "spoolstream/transformer_executor.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_), sizeof(T) * count_));
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

struct QuantProjectionFixture {
    std::string base_name;
    int input_features;
    int output_features;
    int group_count;
    int group_size;
    std::vector<uint32_t> qweight;
    std::vector<half> scales;
    std::vector<uint32_t> qzeros;
    std::vector<half> expanded_zeros;
};

std::filesystem::path make_case_dir(const std::string& name) {
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path root =
        std::filesystem::temp_directory_path() /
        ("spoolstream_transformer_" + name + "_" + std::to_string(stamp));
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

void write_quant_layer_config(const std::filesystem::path& dir, int num_layers = 1) {
    const std::string json =
        "{"
        "\"model_type\":\"llama\","
        "\"hidden_size\":16,"
        "\"intermediate_size\":32,"
        "\"num_hidden_layers\":" + std::to_string(num_layers) + "," +
        "\"num_attention_heads\":2,"
        "\"num_key_value_heads\":1,"
        "\"vocab_size\":64,"
        "\"rope_theta\":10000.0,"
        "\"rms_norm_eps\":0.00001,"
        "\"quantization_config\":{\"quant_method\":\"gptq\"}"
        "}";
    std::ofstream out(dir / "config.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

std::vector<half> to_half(const std::vector<float>& values) {
    std::vector<half> out(values.size());
    for (size_t i = 0; i < values.size(); ++i) {
        out[i] = __float2half(values[i]);
    }
    return out;
}

std::vector<float> to_float(const std::vector<half>& values) {
    std::vector<float> out(values.size());
    for (size_t i = 0; i < values.size(); ++i) {
        out[i] = __half2float(values[i]);
    }
    return out;
}

void assert_close(const std::vector<half>& actual,
                  const std::vector<float>& expected,
                  float tolerance,
                  const std::string& name) {
    require_true(actual.size() == expected.size(), name + " size mismatch");
    for (size_t i = 0; i < actual.size(); ++i) {
        const float a = __half2float(actual[i]);
        const float e = expected[i];
        const float diff = std::fabs(a - e);
        if (diff > tolerance) {
            throw std::runtime_error(name + " mismatch at " + std::to_string(i) +
                                     " actual=" + std::to_string(a) +
                                     " expected=" + std::to_string(e) +
                                     " diff=" + std::to_string(diff));
        }
    }
}

std::vector<float> reference_rmsnorm(const std::vector<float>& input,
                                     const std::vector<float>& weight,
                                     int rows,
                                     int hidden_size,
                                     float epsilon) {
    std::vector<float> out(input.size());
    for (int row = 0; row < rows; ++row) {
        float sum = 0.0f;
        for (int col = 0; col < hidden_size; ++col) {
            const float value = input[static_cast<size_t>(row) * hidden_size + col];
            sum += value * value;
        }
        const float inv_rms = 1.0f / std::sqrt(sum / static_cast<float>(hidden_size) + epsilon);
        for (int col = 0; col < hidden_size; ++col) {
            const size_t index = static_cast<size_t>(row) * hidden_size + col;
            out[index] = input[index] * inv_rms * weight[static_cast<size_t>(col)];
        }
    }
    return out;
}

std::vector<float> reference_dense(const std::vector<float>& lhs,
                                   const std::vector<float>& rhs,
                                   const std::vector<float>* bias,
                                   int m,
                                   int n,
                                   int k) {
    std::vector<float> out(static_cast<size_t>(m) * n);
    for (int row = 0; row < m; ++row) {
        for (int col = 0; col < n; ++col) {
            float sum = bias == nullptr ? 0.0f : (*bias)[static_cast<size_t>(col)];
            for (int kk = 0; kk < k; ++kk) {
                sum += lhs[static_cast<size_t>(row) * k + kk] *
                       rhs[static_cast<size_t>(kk) * n + col];
            }
            out[static_cast<size_t>(row) * n + col] = sum;
        }
    }
    return out;
}

void apply_rope_reference(std::vector<float>& tensor,
                          int tokens,
                          int heads,
                          int head_dim,
                          int position_offset,
                          float rope_theta) {
    for (int token = 0; token < tokens; ++token) {
        for (int head = 0; head < heads; ++head) {
            for (int pair = 0; pair < head_dim / 2; ++pair) {
                const int base = (token * heads + head) * head_dim + pair * 2;
                const float exponent = static_cast<float>(pair * 2) / static_cast<float>(head_dim);
                const float frequency = std::pow(rope_theta, -exponent);
                const float angle = static_cast<float>(position_offset + token) * frequency;
                const float c = std::cos(angle);
                const float s = std::sin(angle);
                const float x0 = tensor[static_cast<size_t>(base)];
                const float x1 = tensor[static_cast<size_t>(base + 1)];
                tensor[static_cast<size_t>(base)] = x0 * c - x1 * s;
                tensor[static_cast<size_t>(base + 1)] = x0 * s + x1 * c;
            }
        }
    }
}

std::vector<float> reference_attention(const std::vector<float>& q,
                                       const std::vector<float>& k,
                                       const std::vector<float>& v,
                                       int tokens,
                                       int q_heads,
                                       int kv_heads,
                                       int head_dim) {
    std::vector<float> out(static_cast<size_t>(tokens) * q_heads * head_dim);
    const int group = q_heads / kv_heads;
    const float scale = 1.0f / std::sqrt(static_cast<float>(head_dim));
    for (int token = 0; token < tokens; ++token) {
        for (int head = 0; head < q_heads; ++head) {
            const int kv_head = head / group;
            std::vector<float> logits(static_cast<size_t>(token + 1));
            float max_logit = -std::numeric_limits<float>::infinity();
            for (int source = 0; source <= token; ++source) {
                float dot = 0.0f;
                for (int dim = 0; dim < head_dim; ++dim) {
                    const int q_index = (token * q_heads + head) * head_dim + dim;
                    const int k_index = (source * kv_heads + kv_head) * head_dim + dim;
                    dot += q[static_cast<size_t>(q_index)] * k[static_cast<size_t>(k_index)];
                }
                logits[static_cast<size_t>(source)] = dot * scale;
                max_logit = std::max(max_logit, logits[static_cast<size_t>(source)]);
            }
            float denom = 0.0f;
            for (float& logit : logits) {
                logit = std::exp(logit - max_logit);
                denom += logit;
            }
            for (int dim = 0; dim < head_dim; ++dim) {
                float value = 0.0f;
                for (int source = 0; source <= token; ++source) {
                    const int v_index = (source * kv_heads + kv_head) * head_dim + dim;
                    value += logits[static_cast<size_t>(source)] / denom *
                             v[static_cast<size_t>(v_index)];
                }
                const int out_index = (token * q_heads + head) * head_dim + dim;
                out[static_cast<size_t>(out_index)] = value;
            }
        }
    }
    return out;
}

void test_activation_workspace() {
    auto workspace = spoolstream::core::create_activation_workspace(2, 8, 16);
    require_true(workspace.hidden != nullptr, "workspace hidden null");
    require_true(workspace.residual != nullptr, "workspace residual null");
    require_true(workspace.normalized != nullptr, "workspace normalized null");
    require_true(workspace.mlp_gate != nullptr, "workspace mlp_gate null");
    require_true(workspace.tokens == 2, "workspace tokens mismatch");
    spoolstream::core::destroy_activation_workspace(workspace);
    require_true(workspace.hidden == nullptr, "workspace hidden not nulled");
    require_true(workspace.mlp_gate == nullptr, "workspace mlp_gate not nulled");
    require_true(workspace.tokens == 0, "workspace tokens not cleared");

    require_throw([&]() {
        auto invalid = spoolstream::core::create_activation_workspace(0, 8, 16);
        spoolstream::core::destroy_activation_workspace(invalid);
    }, "invalid workspace");
}

void test_rmsnorm() {
    constexpr int rows = 3;
    constexpr int hidden = 8;
    std::vector<float> input(static_cast<size_t>(rows) * hidden);
    for (size_t i = 0; i < input.size(); ++i) {
        input[i] = static_cast<float>(static_cast<int>(i % 11) - 5) * 0.125f;
    }
    std::vector<float> weight(static_cast<size_t>(hidden));
    for (int i = 0; i < hidden; ++i) {
        weight[static_cast<size_t>(i)] = 0.75f + static_cast<float>(i) * 0.03125f;
    }
    const auto expected = reference_rmsnorm(input, weight, rows, hidden, 1.0e-5f);

    DeviceBuffer<half> d_input(input.size());
    DeviceBuffer<half> d_weight(weight.size());
    DeviceBuffer<half> d_output(input.size());
    d_input.copy_from_host(to_half(input));
    d_weight.copy_from_host(to_half(weight));

    spoolstream::core::launch_rmsnorm(d_input.get(),
                                      d_weight.get(),
                                      d_output.get(),
                                      rows,
                                      hidden,
                                      1.0e-5f);
    assert_close(d_output.copy_to_host(), expected, 0.0025f, "rmsnorm");

    require_throw([&]() {
        spoolstream::core::launch_rmsnorm(nullptr,
                                          d_weight.get(),
                                          d_output.get(),
                                          rows,
                                          hidden,
                                          1.0e-5f);
    }, "null rmsnorm");
}

void test_rope() {
    constexpr int tokens = 3;
    constexpr int q_heads = 2;
    constexpr int kv_heads = 1;
    constexpr int head_dim = 4;
    std::vector<float> q(static_cast<size_t>(tokens) * q_heads * head_dim);
    std::vector<float> k(static_cast<size_t>(tokens) * kv_heads * head_dim);
    for (size_t i = 0; i < q.size(); ++i) {
        q[i] = static_cast<float>(i + 1) * 0.0625f;
    }
    for (size_t i = 0; i < k.size(); ++i) {
        k[i] = static_cast<float>(static_cast<int>(i) - 3) * 0.09375f;
    }
    std::vector<float> expected_q = q;
    std::vector<float> expected_k = k;
    apply_rope_reference(expected_q, tokens, q_heads, head_dim, 2, 10000.0f);
    apply_rope_reference(expected_k, tokens, kv_heads, head_dim, 2, 10000.0f);

    DeviceBuffer<half> d_q(q.size());
    DeviceBuffer<half> d_k(k.size());
    d_q.copy_from_host(to_half(q));
    d_k.copy_from_host(to_half(k));

    spoolstream::core::launch_rope(d_q.get(),
                                   d_k.get(),
                                   tokens,
                                   q_heads,
                                   kv_heads,
                                   head_dim,
                                   2,
                                   10000.0f);
    assert_close(d_q.copy_to_host(), expected_q, 0.003f, "rope q");
    assert_close(d_k.copy_to_host(), expected_k, 0.003f, "rope k");
}

void test_residual_swiglu_and_copy() {
    constexpr int count = 17;
    std::vector<float> lhs(count);
    std::vector<float> rhs(count);
    for (int i = 0; i < count; ++i) {
        lhs[static_cast<size_t>(i)] = static_cast<float>(i - 8) * 0.125f;
        rhs[static_cast<size_t>(i)] = static_cast<float>((i * 3) % 7 - 3) * 0.0625f;
    }

    std::vector<float> expected_add(count);
    std::vector<float> expected_swiglu(count);
    for (int i = 0; i < count; ++i) {
        const float gate = lhs[static_cast<size_t>(i)];
        const float up = rhs[static_cast<size_t>(i)];
        expected_add[static_cast<size_t>(i)] = gate + up;
        expected_swiglu[static_cast<size_t>(i)] = gate / (1.0f + std::exp(-gate)) * up;
    }

    DeviceBuffer<half> d_lhs(count);
    DeviceBuffer<half> d_rhs(count);
    DeviceBuffer<half> d_output(count);
    d_lhs.copy_from_host(to_half(lhs));
    d_rhs.copy_from_host(to_half(rhs));

    spoolstream::core::launch_residual_add(d_lhs.get(), d_rhs.get(), d_output.get(), count);
    assert_close(d_output.copy_to_host(), expected_add, 0.0015f, "residual add");

    spoolstream::core::launch_swiglu(d_lhs.get(), d_rhs.get(), d_output.get(), count);
    assert_close(d_output.copy_to_host(), expected_swiglu, 0.0015f, "swiglu");

    spoolstream::core::launch_copy_half(d_lhs.get(), d_output.get(), count);
    assert_close(d_output.copy_to_host(), lhs, 0.001f, "copy half");
}

void test_dense_matmul() {
    constexpr int m = 3;
    constexpr int n = 5;
    constexpr int k = 4;
    std::vector<float> lhs(static_cast<size_t>(m) * k);
    std::vector<float> rhs(static_cast<size_t>(k) * n);
    std::vector<float> bias(static_cast<size_t>(n));
    for (size_t i = 0; i < lhs.size(); ++i) {
        lhs[i] = static_cast<float>(static_cast<int>(i % 7) - 3) * 0.0625f;
    }
    for (size_t i = 0; i < rhs.size(); ++i) {
        rhs[i] = static_cast<float>(static_cast<int>((i * 5) % 11) - 5) * 0.03125f;
    }
    for (int i = 0; i < n; ++i) {
        bias[static_cast<size_t>(i)] = static_cast<float>(i - 2) * 0.015625f;
    }
    const auto expected = reference_dense(lhs, rhs, &bias, m, n, k);

    DeviceBuffer<half> d_lhs(lhs.size());
    DeviceBuffer<half> d_rhs(rhs.size());
    DeviceBuffer<half> d_bias(bias.size());
    DeviceBuffer<half> d_output(expected.size());
    d_lhs.copy_from_host(to_half(lhs));
    d_rhs.copy_from_host(to_half(rhs));
    d_bias.copy_from_host(to_half(bias));
    spoolstream::core::launch_dense_matmul_fp16(d_lhs.get(),
                                                d_rhs.get(),
                                                d_bias.get(),
                                                d_output.get(),
                                                m,
                                                n,
                                                k);
    assert_close(d_output.copy_to_host(), expected, 0.0015f, "dense matmul");
}

void test_causal_attention_prefill() {
    constexpr int tokens = 4;
    constexpr int q_heads = 4;
    constexpr int kv_heads = 2;
    constexpr int head_dim = 2;
    std::vector<float> q(static_cast<size_t>(tokens) * q_heads * head_dim);
    std::vector<float> k(static_cast<size_t>(tokens) * kv_heads * head_dim);
    std::vector<float> v(static_cast<size_t>(tokens) * kv_heads * head_dim);
    for (size_t i = 0; i < q.size(); ++i) {
        q[i] = static_cast<float>(static_cast<int>(i % 9) - 4) * 0.046875f;
    }
    for (size_t i = 0; i < k.size(); ++i) {
        k[i] = static_cast<float>(static_cast<int>((i * 3) % 7) - 3) * 0.0625f;
        v[i] = static_cast<float>(static_cast<int>((i * 5) % 13) - 6) * 0.03125f;
    }
    const auto expected = reference_attention(q, k, v, tokens, q_heads, kv_heads, head_dim);

    DeviceBuffer<half> d_q(q.size());
    DeviceBuffer<half> d_k(k.size());
    DeviceBuffer<half> d_v(v.size());
    DeviceBuffer<half> d_output(expected.size());
    d_q.copy_from_host(to_half(q));
    d_k.copy_from_host(to_half(k));
    d_v.copy_from_host(to_half(v));
    spoolstream::core::launch_causal_attention_prefill(d_q.get(),
                                                       d_k.get(),
                                                       d_v.get(),
                                                       d_output.get(),
                                                       tokens,
                                                       q_heads,
                                                       kv_heads,
                                                       head_dim);
    assert_close(d_output.copy_to_host(), expected, 0.0025f, "causal attention");
}

void test_causal_attention_decode_matches_prefill_tail() {
    constexpr int tokens = 5;
    constexpr int q_heads = 4;
    constexpr int kv_heads = 2;
    constexpr int head_dim = 4;
    const int q_values_per_token = q_heads * head_dim;
    const int kv_values_per_token = kv_heads * head_dim;
    std::vector<float> q(static_cast<size_t>(tokens) * q_values_per_token);
    std::vector<float> k(static_cast<size_t>(tokens) * kv_values_per_token);
    std::vector<float> v(static_cast<size_t>(tokens) * kv_values_per_token);
    for (size_t i = 0; i < q.size(); ++i) {
        q[i] = static_cast<float>(static_cast<int>((i * 7) % 17) - 8) * 0.03125f;
    }
    for (size_t i = 0; i < k.size(); ++i) {
        k[i] = static_cast<float>(static_cast<int>((i * 5) % 19) - 9) * 0.02734375f;
        v[i] = static_cast<float>(static_cast<int>((i * 11) % 23) - 11) * 0.0234375f;
    }
    const auto expected_prefill =
        reference_attention(q, k, v, tokens, q_heads, kv_heads, head_dim);
    std::vector<float> expected_tail(static_cast<size_t>(q_values_per_token));
    const size_t tail_offset = static_cast<size_t>(tokens - 1) *
                               static_cast<size_t>(q_values_per_token);
    std::copy(expected_prefill.begin() + static_cast<std::ptrdiff_t>(tail_offset),
              expected_prefill.begin() +
                  static_cast<std::ptrdiff_t>(tail_offset + q_values_per_token),
              expected_tail.begin());

    DeviceBuffer<half> d_q(q.size());
    DeviceBuffer<half> d_k(k.size());
    DeviceBuffer<half> d_v(v.size());
    DeviceBuffer<half> d_k_cache(k.size());
    DeviceBuffer<half> d_v_cache(v.size());
    DeviceBuffer<half> d_decode_output(static_cast<size_t>(q_values_per_token));
    d_q.copy_from_host(to_half(q));
    d_k.copy_from_host(to_half(k));
    d_v.copy_from_host(to_half(v));

    for (int token = 0; token < tokens; ++token) {
        spoolstream::core::launch_store_kv_cache_token(
            d_k.get() + static_cast<size_t>(token) * kv_values_per_token,
            d_v.get() + static_cast<size_t>(token) * kv_values_per_token,
            d_k_cache.get(),
            d_v_cache.get(),
            token,
            tokens,
            kv_heads,
            head_dim);
    }

    spoolstream::core::launch_causal_attention_decode(
        d_q.get() + static_cast<size_t>(tokens - 1) * q_values_per_token,
        d_k_cache.get(),
        d_v_cache.get(),
        d_decode_output.get(),
        tokens,
        q_heads,
        kv_heads,
        head_dim);
    assert_close(d_decode_output.copy_to_host(),
                 expected_tail,
                 0.0025f,
                 "decode attention cached tail");

    assert_close(d_k_cache.copy_to_host(), k, 0.001f, "stored k cache");
    assert_close(d_v_cache.copy_to_host(), v, 0.001f, "stored v cache");

    require_throw(
        [&] {
            spoolstream::core::launch_causal_attention_decode(d_q.get(),
                                                              d_k_cache.get(),
                                                              d_v_cache.get(),
                                                              d_decode_output.get(),
                                                              0,
                                                              q_heads,
                                                              kv_heads,
                                                              head_dim);
        },
        "decode attention rejects zero cached tokens");
}

std::vector<float> make_weight(size_t count, int modulus, float scale) {
    std::vector<float> values(count);
    for (size_t i = 0; i < count; ++i) {
        values[i] = static_cast<float>(static_cast<int>((i * 7) % static_cast<size_t>(modulus)) -
                                       modulus / 2) *
                    scale;
    }
    return values;
}

uint8_t quant_value_for(int row, int col, int seed) {
    return static_cast<uint8_t>((row * 3 + col * 5 + seed) & 0x0F);
}

QuantProjectionFixture make_quant_projection_fixture(const std::string& base_name,
                                                     int input_features,
                                                     int output_features,
                                                     int group_count,
                                                     int seed) {
    require_true(output_features % 8 == 0, "quant fixture output must be divisible by 8");
    require_true(input_features > 0 && output_features > 0 && group_count > 0,
                 "quant fixture dimensions must be positive");
    QuantProjectionFixture fixture{};
    fixture.base_name = base_name;
    fixture.input_features = input_features;
    fixture.output_features = output_features;
    fixture.group_count = group_count;
    fixture.group_size = (input_features + group_count - 1) / group_count;
    const int packed_cols = output_features / 8;

    fixture.qweight.resize(static_cast<size_t>(input_features) *
                           static_cast<size_t>(packed_cols));
    for (int row = 0; row < input_features; ++row) {
        for (int pack = 0; pack < packed_cols; ++pack) {
            uint32_t word = 0;
            for (int nibble = 0; nibble < 8; ++nibble) {
                const int col = pack * 8 + nibble;
                word |= static_cast<uint32_t>(quant_value_for(row, col, seed))
                        << (4 * nibble);
            }
            fixture.qweight[static_cast<size_t>(row) * static_cast<size_t>(packed_cols) +
                            static_cast<size_t>(pack)] = word;
        }
    }

    fixture.scales.resize(static_cast<size_t>(group_count) *
                          static_cast<size_t>(output_features));
    fixture.qzeros.resize(static_cast<size_t>(group_count) *
                          static_cast<size_t>(packed_cols));
    fixture.expanded_zeros.resize(static_cast<size_t>(group_count) *
                                  static_cast<size_t>(output_features));
    for (int group = 0; group < group_count; ++group) {
        for (int col = 0; col < output_features; ++col) {
            const float scale = 0.00625f + 0.00075f *
                                static_cast<float>((seed + group + col) % 5);
            const uint32_t zero = static_cast<uint32_t>((seed + group * 3 + col) & 0x0F);
            fixture.scales[static_cast<size_t>(group) *
                               static_cast<size_t>(output_features) +
                           static_cast<size_t>(col)] = __float2half(scale);
            fixture.expanded_zeros[static_cast<size_t>(group) *
                                       static_cast<size_t>(output_features) +
                                   static_cast<size_t>(col)] =
                __float2half(static_cast<float>(zero));
        }
        for (int pack = 0; pack < packed_cols; ++pack) {
            uint32_t word = 0;
            for (int nibble = 0; nibble < 8; ++nibble) {
                const int col = pack * 8 + nibble;
                const uint32_t zero =
                    static_cast<uint32_t>((seed + group * 3 + col) & 0x0F);
                word |= zero << (4 * nibble);
            }
            fixture.qzeros[static_cast<size_t>(group) * static_cast<size_t>(packed_cols) +
                           static_cast<size_t>(pack)] = word;
        }
    }
    return fixture;
}

std::vector<float> reference_quant_projection(const std::vector<float>& lhs,
                                              const QuantProjectionFixture& projection,
                                              int rows) {
    std::vector<float> out(static_cast<size_t>(rows) *
                           static_cast<size_t>(projection.output_features));
    const int packed_cols = projection.output_features / 8;
    for (int row = 0; row < rows; ++row) {
        for (int col = 0; col < projection.output_features; ++col) {
            float sum = 0.0f;
            for (int kk = 0; kk < projection.input_features; ++kk) {
                const uint32_t word =
                    projection.qweight[static_cast<size_t>(kk) *
                                           static_cast<size_t>(packed_cols) +
                                       static_cast<size_t>(col / 8)];
                const uint32_t q = (word >> (4 * (col & 7))) & 0x0FU;
                const int group = kk / projection.group_size;
                const size_t metadata_index =
                    static_cast<size_t>(group) *
                        static_cast<size_t>(projection.output_features) +
                    static_cast<size_t>(col);
                const float rhs =
                    (static_cast<float>(q) -
                     __half2float(projection.expanded_zeros[metadata_index])) *
                    __half2float(projection.scales[metadata_index]);
                sum += lhs[static_cast<size_t>(row) *
                               static_cast<size_t>(projection.input_features) +
                           static_cast<size_t>(kk)] *
                       rhs;
            }
            out[static_cast<size_t>(row) *
                    static_cast<size_t>(projection.output_features) +
                static_cast<size_t>(col)] = sum;
        }
    }
    return out;
}

void append_quant_projection_tensors(std::vector<TensorFixture>& tensors,
                                     const QuantProjectionFixture& projection) {
    const int packed_cols = projection.output_features / 8;
    tensors.push_back({projection.base_name + ".qweight",
                       "I32",
                       {projection.input_features, packed_cols},
                       bytes_from_vector(projection.qweight)});
    tensors.push_back({projection.base_name + ".scales",
                       "F16",
                       {projection.group_count, projection.output_features},
                       bytes_from_vector(projection.scales)});
    tensors.push_back({projection.base_name + ".qzeros",
                       "I32",
                       {projection.group_count, packed_cols},
                       bytes_from_vector(projection.qzeros)});
}

std::filesystem::path write_quantized_layer_checkpoint(
    const std::vector<half>& attn_norm,
    const std::vector<half>& mlp_norm,
    const std::vector<QuantProjectionFixture>& projections) {
    const auto dir = make_case_dir("quant_layer");
    write_quant_layer_config(dir);
    std::vector<TensorFixture> tensors = {
        {"model.layers.0.input_layernorm.weight", "F16", {16}, bytes_from_vector(attn_norm)},
        {"model.layers.0.post_attention_layernorm.weight", "F16", {16}, bytes_from_vector(mlp_norm)},
    };
    for (const QuantProjectionFixture& projection : projections) {
        append_quant_projection_tensors(tensors, projection);
    }
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

std::filesystem::path write_quantized_model_checkpoint(
    int num_layers,
    const std::vector<std::vector<half>>& attn_norms,
    const std::vector<std::vector<half>>& mlp_norms,
    const std::vector<QuantProjectionFixture>& projections) {
    const auto dir = make_case_dir("quant_model");
    write_quant_layer_config(dir, num_layers);
    std::vector<TensorFixture> tensors;
    for (int layer = 0; layer < num_layers; ++layer) {
        tensors.push_back({"model.layers." + std::to_string(layer) + ".input_layernorm.weight",
                           "F16",
                           {16},
                           bytes_from_vector(attn_norms[static_cast<size_t>(layer)])});
        tensors.push_back({"model.layers." + std::to_string(layer) +
                               ".post_attention_layernorm.weight",
                           "F16",
                           {16},
                           bytes_from_vector(mlp_norms[static_cast<size_t>(layer)])});
    }
    for (const QuantProjectionFixture& projection : projections) {
        append_quant_projection_tensors(tensors, projection);
    }
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

std::filesystem::path write_quantized_model_with_head_checkpoint(
    int num_layers,
    const std::vector<std::vector<half>>& attn_norms,
    const std::vector<std::vector<half>>& mlp_norms,
    const std::vector<half>& final_norm,
    const std::vector<QuantProjectionFixture>& layer_projections,
    const QuantProjectionFixture& lm_head) {
    const auto dir = make_case_dir("quant_model_head");
    write_quant_layer_config(dir, num_layers);
    std::vector<TensorFixture> tensors;
    for (int layer = 0; layer < num_layers; ++layer) {
        tensors.push_back({"model.layers." + std::to_string(layer) + ".input_layernorm.weight",
                           "F16",
                           {16},
                           bytes_from_vector(attn_norms[static_cast<size_t>(layer)])});
        tensors.push_back({"model.layers." + std::to_string(layer) +
                               ".post_attention_layernorm.weight",
                           "F16",
                           {16},
                           bytes_from_vector(mlp_norms[static_cast<size_t>(layer)])});
    }
    tensors.push_back({"model.norm.weight", "F16", {16}, bytes_from_vector(final_norm)});
    for (const QuantProjectionFixture& projection : layer_projections) {
        append_quant_projection_tensors(tensors, projection);
    }
    append_quant_projection_tensors(tensors, lm_head);
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

std::filesystem::path write_dense_lm_head_checkpoint(const std::vector<half>& final_norm,
                                                     const std::vector<half>& lm_head,
                                                     int hidden,
                                                     int vocab) {
    const auto dir = make_case_dir("dense_lm_head");
    write_quant_layer_config(dir, 1);
    const std::vector<half> one_norm(static_cast<size_t>(hidden), __float2half(1.0f));
    std::vector<TensorFixture> tensors = {
        {"model.layers.0.input_layernorm.weight", "F16", {hidden}, bytes_from_vector(one_norm)},
        {"model.layers.0.post_attention_layernorm.weight", "F16", {hidden}, bytes_from_vector(one_norm)},
        {"model.norm.weight", "F16", {hidden}, bytes_from_vector(final_norm)},
        {"lm_head.weight", "F16", {vocab, hidden}, bytes_from_vector(lm_head)},
    };
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

std::filesystem::path write_embedding_checkpoint(const std::vector<half>& embeddings,
                                                 int hidden,
                                                 int vocab) {
    const auto dir = make_case_dir("embedding_rows");
    write_quant_layer_config(dir, 1);
    const std::vector<half> one_norm(static_cast<size_t>(hidden), __float2half(1.0f));
    std::vector<TensorFixture> tensors = {
        {"model.embed_tokens.weight", "F16", {vocab, hidden}, bytes_from_vector(embeddings)},
        {"model.layers.0.input_layernorm.weight", "F16", {hidden}, bytes_from_vector(one_norm)},
        {"model.layers.0.post_attention_layernorm.weight", "F16", {hidden}, bytes_from_vector(one_norm)},
    };
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

const spoolstream::core::QuantizedProjection& find_projection(
    const spoolstream::core::QuantizedAdapterReport& report,
    spoolstream::core::QuantizedProjectionRole role) {
    for (const auto& projection : report.projections) {
        if (projection.role == role) {
            return projection;
        }
    }
    throw std::runtime_error("missing quantized projection");
}

const spoolstream::core::ManifestTensor& find_manifest_tensor(
    const spoolstream::core::ModelManifest& manifest,
    spoolstream::core::TensorRole role) {
    for (const auto& tensor : manifest.tensors) {
        if (tensor.role == role) {
            return tensor;
        }
    }
    throw std::runtime_error("missing manifest tensor");
}

void upload_workspace_for_projection(
    spoolstream::core::StreamingTensorStore& store,
    const spoolstream::core::QuantizedProjection& projection,
    spoolstream::core::QuantizedProjectionMetadataWorkspace& workspace) {
    const auto staged = spoolstream::core::stage_tensor_bytes(store, *projection.zeros);
    spoolstream::core::upload_projection_zeros_to_workspace(workspace,
                                                            projection,
                                                            staged.host_ptr,
                                                            staged.byte_size);
    if (projection.g_idx != nullptr) {
        const auto gidx = spoolstream::core::stage_tensor_bytes(store, *projection.g_idx);
        spoolstream::core::upload_projection_gidx_to_workspace(workspace,
                                                               projection,
                                                               gidx.host_ptr,
                                                               gidx.byte_size);
    }
}

std::vector<float> reference_quantized_decoder_layer(
    const std::vector<float>& input,
    const std::vector<float>& attn_norm,
    const std::vector<float>& mlp_norm,
    const QuantProjectionFixture& q_proj,
    const QuantProjectionFixture& k_proj,
    const QuantProjectionFixture& v_proj,
    const QuantProjectionFixture& o_proj,
    const QuantProjectionFixture& gate_proj,
    const QuantProjectionFixture& up_proj,
    const QuantProjectionFixture& down_proj,
    int tokens,
    int hidden,
    int intermediate,
    int q_heads,
    int kv_heads,
    int head_dim,
    float eps) {
    auto residual = input;
    auto normalized = reference_rmsnorm(residual, attn_norm, tokens, hidden, eps);
    auto q = reference_quant_projection(normalized, q_proj, tokens);
    auto k = reference_quant_projection(normalized, k_proj, tokens);
    auto v = reference_quant_projection(normalized, v_proj, tokens);
    apply_rope_reference(q, tokens, q_heads, head_dim, 0, 10000.0f);
    apply_rope_reference(k, tokens, kv_heads, head_dim, 0, 10000.0f);
    auto attention = reference_attention(q, k, v, tokens, q_heads, kv_heads, head_dim);
    auto attn_out = reference_quant_projection(attention, o_proj, tokens);
    for (size_t i = 0; i < residual.size(); ++i) {
        residual[i] += attn_out[i];
    }
    normalized = reference_rmsnorm(residual, mlp_norm, tokens, hidden, eps);
    auto gate = reference_quant_projection(normalized, gate_proj, tokens);
    auto up = reference_quant_projection(normalized, up_proj, tokens);
    for (size_t i = 0; i < gate.size(); ++i) {
        gate[i] = gate[i] / (1.0f + std::exp(-gate[i])) * up[i];
    }
    auto down = reference_quant_projection(gate, down_proj, tokens);
    std::vector<float> output(residual.size());
    for (size_t i = 0; i < output.size(); ++i) {
        output[i] = residual[i] + down[i];
    }
    (void)intermediate;
    return output;
}

void test_complete_llama_decoder_layer_prefill() {
    constexpr int tokens = 3;
    constexpr int hidden = 4;
    constexpr int intermediate = 6;
    constexpr int q_heads = 2;
    constexpr int kv_heads = 1;
    constexpr int head_dim = 2;
    constexpr float eps = 1.0e-5f;
    std::vector<float> input = {
        0.10f, -0.20f, 0.05f, 0.30f,
        -0.15f, 0.25f, 0.12f, -0.08f,
        0.18f, -0.04f, 0.22f, -0.11f,
    };
    const std::vector<float> attn_norm(hidden, 1.0f);
    const std::vector<float> mlp_norm(hidden, 0.875f);
    const auto q_proj = make_weight(hidden * hidden, 9, 0.025f);
    const auto k_proj = make_weight(hidden * kv_heads * head_dim, 7, 0.03125f);
    const auto v_proj = make_weight(hidden * kv_heads * head_dim, 11, 0.0275f);
    const auto o_proj = make_weight(hidden * hidden, 13, 0.01875f);
    const auto gate_proj = make_weight(hidden * intermediate, 17, 0.021f);
    const auto up_proj = make_weight(hidden * intermediate, 19, 0.019f);
    const auto down_proj = make_weight(intermediate * hidden, 23, 0.017f);

    auto residual = input;
    auto normalized = reference_rmsnorm(residual, attn_norm, tokens, hidden, eps);
    auto q = reference_dense(normalized, q_proj, nullptr, tokens, hidden, hidden);
    auto k = reference_dense(normalized, k_proj, nullptr, tokens, kv_heads * head_dim, hidden);
    auto v = reference_dense(normalized, v_proj, nullptr, tokens, kv_heads * head_dim, hidden);
    apply_rope_reference(q, tokens, q_heads, head_dim, 0, 10000.0f);
    apply_rope_reference(k, tokens, kv_heads, head_dim, 0, 10000.0f);
    auto attention = reference_attention(q, k, v, tokens, q_heads, kv_heads, head_dim);
    auto attn_out = reference_dense(attention, o_proj, nullptr, tokens, hidden, hidden);
    for (size_t i = 0; i < residual.size(); ++i) {
        residual[i] += attn_out[i];
    }
    normalized = reference_rmsnorm(residual, mlp_norm, tokens, hidden, eps);
    auto gate = reference_dense(normalized, gate_proj, nullptr, tokens, intermediate, hidden);
    auto up = reference_dense(normalized, up_proj, nullptr, tokens, intermediate, hidden);
    for (size_t i = 0; i < gate.size(); ++i) {
        gate[i] = gate[i] / (1.0f + std::exp(-gate[i])) * up[i];
    }
    auto down = reference_dense(gate, down_proj, nullptr, tokens, hidden, intermediate);
    std::vector<float> expected(residual.size());
    for (size_t i = 0; i < expected.size(); ++i) {
        expected[i] = residual[i] + down[i];
    }

    DeviceBuffer<half> d_input(input.size());
    DeviceBuffer<half> d_output(expected.size());
    DeviceBuffer<half> d_attn_norm(attn_norm.size());
    DeviceBuffer<half> d_q_proj(q_proj.size());
    DeviceBuffer<half> d_k_proj(k_proj.size());
    DeviceBuffer<half> d_v_proj(v_proj.size());
    DeviceBuffer<half> d_o_proj(o_proj.size());
    DeviceBuffer<half> d_mlp_norm(mlp_norm.size());
    DeviceBuffer<half> d_gate_proj(gate_proj.size());
    DeviceBuffer<half> d_up_proj(up_proj.size());
    DeviceBuffer<half> d_down_proj(down_proj.size());
    d_input.copy_from_host(to_half(input));
    d_attn_norm.copy_from_host(to_half(attn_norm));
    d_q_proj.copy_from_host(to_half(q_proj));
    d_k_proj.copy_from_host(to_half(k_proj));
    d_v_proj.copy_from_host(to_half(v_proj));
    d_o_proj.copy_from_host(to_half(o_proj));
    d_mlp_norm.copy_from_host(to_half(mlp_norm));
    d_gate_proj.copy_from_host(to_half(gate_proj));
    d_up_proj.copy_from_host(to_half(up_proj));
    d_down_proj.copy_from_host(to_half(down_proj));

    auto workspace = spoolstream::core::create_activation_workspace(tokens, hidden, intermediate);
    spoolstream::core::LlamaDecoderLayerWeights weights{};
    weights.attn_norm = d_attn_norm.get();
    weights.q_proj = d_q_proj.get();
    weights.k_proj = d_k_proj.get();
    weights.v_proj = d_v_proj.get();
    weights.o_proj = d_o_proj.get();
    weights.mlp_norm = d_mlp_norm.get();
    weights.gate_proj = d_gate_proj.get();
    weights.up_proj = d_up_proj.get();
    weights.down_proj = d_down_proj.get();
    spoolstream::core::LlamaDecoderLayerConfig config{};
    config.tokens = tokens;
    config.hidden_size = hidden;
    config.intermediate_size = intermediate;
    config.num_attention_heads = q_heads;
    config.num_key_value_heads = kv_heads;
    config.head_dim = head_dim;
    config.position_offset = 0;
    config.rope_theta = 10000.0f;
    config.rms_norm_epsilon = eps;
    spoolstream::core::execute_llama_decoder_layer_prefill(d_input.get(),
                                                           d_output.get(),
                                                           weights,
                                                           workspace,
                                                           config);
    assert_close(d_output.copy_to_host(), expected, 0.01f, "complete decoder layer");
    spoolstream::core::destroy_activation_workspace(workspace);
}

void test_streamed_quantized_llama_decoder_layer_prefill() {
    constexpr int tokens = 16;
    constexpr int hidden = 16;
    constexpr int intermediate = 32;
    constexpr int q_heads = 2;
    constexpr int kv_heads = 1;
    constexpr int head_dim = 8;
    constexpr int kv_hidden = kv_heads * head_dim;
    constexpr float eps = 1.0e-5f;

    std::vector<float> input(static_cast<size_t>(tokens) * hidden);
    for (size_t i = 0; i < input.size(); ++i) {
        input[i] = static_cast<float>(static_cast<int>((i * 5) % 17) - 8) * 0.01875f;
    }
    const std::vector<float> attn_norm_f(hidden, 1.0f);
    std::vector<float> mlp_norm_f(hidden);
    for (int i = 0; i < hidden; ++i) {
        mlp_norm_f[static_cast<size_t>(i)] = 0.875f + static_cast<float>(i % 3) * 0.03125f;
    }
    const auto attn_norm = to_half(attn_norm_f);
    const auto mlp_norm = to_half(mlp_norm_f);

    const auto q_proj = make_quant_projection_fixture("model.layers.0.self_attn.q_proj",
                                                      hidden,
                                                      hidden,
                                                      2,
                                                      3);
    const auto k_proj = make_quant_projection_fixture("model.layers.0.self_attn.k_proj",
                                                      hidden,
                                                      kv_hidden,
                                                      2,
                                                      5);
    const auto v_proj = make_quant_projection_fixture("model.layers.0.self_attn.v_proj",
                                                      hidden,
                                                      kv_hidden,
                                                      2,
                                                      7);
    const auto o_proj = make_quant_projection_fixture("model.layers.0.self_attn.o_proj",
                                                      hidden,
                                                      hidden,
                                                      2,
                                                      9);
    const auto gate_proj = make_quant_projection_fixture("model.layers.0.mlp.gate_proj",
                                                         hidden,
                                                         intermediate,
                                                         2,
                                                         11);
    const auto up_proj = make_quant_projection_fixture("model.layers.0.mlp.up_proj",
                                                       hidden,
                                                       intermediate,
                                                       2,
                                                       13);
    const auto down_proj = make_quant_projection_fixture("model.layers.0.mlp.down_proj",
                                                         intermediate,
                                                         hidden,
                                                         4,
                                                         15);

    auto residual = input;
    auto normalized = reference_rmsnorm(residual, attn_norm_f, tokens, hidden, eps);
    auto q = reference_quant_projection(normalized, q_proj, tokens);
    auto k = reference_quant_projection(normalized, k_proj, tokens);
    auto v = reference_quant_projection(normalized, v_proj, tokens);
    apply_rope_reference(q, tokens, q_heads, head_dim, 0, 10000.0f);
    apply_rope_reference(k, tokens, kv_heads, head_dim, 0, 10000.0f);
    auto attention = reference_attention(q, k, v, tokens, q_heads, kv_heads, head_dim);
    auto attn_out = reference_quant_projection(attention, o_proj, tokens);
    for (size_t i = 0; i < residual.size(); ++i) {
        residual[i] += attn_out[i];
    }
    normalized = reference_rmsnorm(residual, mlp_norm_f, tokens, hidden, eps);
    auto gate = reference_quant_projection(normalized, gate_proj, tokens);
    auto up = reference_quant_projection(normalized, up_proj, tokens);
    for (size_t i = 0; i < gate.size(); ++i) {
        gate[i] = gate[i] / (1.0f + std::exp(-gate[i])) * up[i];
    }
    auto down = reference_quant_projection(gate, down_proj, tokens);
    std::vector<float> expected(residual.size());
    for (size_t i = 0; i < expected.size(); ++i) {
        expected[i] = residual[i] + down[i];
    }

    const std::vector<QuantProjectionFixture> projection_fixtures = {
        q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj,
    };
    const auto checkpoint = write_quantized_layer_checkpoint(attn_norm,
                                                             mlp_norm,
                                                             projection_fixtures);
    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 8192);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "streamed quantized layer adapter report unsupported");
    const auto& q_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_Q);
    const auto& k_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_K);
    const auto& v_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_V);
    const auto& o_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::ATTN_O);
    const auto& gate_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::MLP_GATE);
    const auto& up_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::MLP_UP);
    const auto& down_desc = find_projection(report, spoolstream::core::QuantizedProjectionRole::MLP_DOWN);

    const auto plans = spoolstream::core::build_layer_execution_plans(manifest, 4096, 16);
    const auto& layer_plan = spoolstream::core::require_layer_plan(plans, 0);
    auto store = spoolstream::core::create_streaming_tensor_store(checkpoint, 512);
    DeviceBuffer<uint8_t> slot(4096);
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot.get(), 0, 4096));
    auto transfer = spoolstream::core::schedule_layer_prefetch(store, layer_plan, slot.get());
    spoolstream::core::wait_for_layer_transfer(transfer);

    auto q_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(q_desc);
    auto k_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(k_desc);
    auto v_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(v_desc);
    auto o_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(o_desc);
    auto gate_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(gate_desc);
    auto up_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(up_desc);
    auto down_workspace = spoolstream::core::create_quantized_projection_metadata_workspace(down_desc);
    upload_workspace_for_projection(store, q_desc, q_workspace);
    upload_workspace_for_projection(store, k_desc, k_workspace);
    upload_workspace_for_projection(store, v_desc, v_workspace);
    upload_workspace_for_projection(store, o_desc, o_workspace);
    upload_workspace_for_projection(store, gate_desc, gate_workspace);
    upload_workspace_for_projection(store, up_desc, up_workspace);
    upload_workspace_for_projection(store, down_desc, down_workspace);

    auto weights = spoolstream::core::bind_quantized_llama_decoder_layer_weights(slot.get(),
                                                                                 layer_plan,
                                                                                 q_desc,
                                                                                 q_workspace,
                                                                                 k_desc,
                                                                                 k_workspace,
                                                                                 v_desc,
                                                                                 v_workspace,
                                                                                 o_desc,
                                                                                 o_workspace,
                                                                                 gate_desc,
                                                                                 gate_workspace,
                                                                                 up_desc,
                                                                                 up_workspace,
                                                                                 down_desc,
                                                                                 down_workspace,
                                                                                 tokens);

    DeviceBuffer<half> d_input(input.size());
    DeviceBuffer<half> d_output(expected.size());
    d_input.copy_from_host(to_half(input));
    auto workspace = spoolstream::core::create_activation_workspace(tokens, hidden, intermediate);
    spoolstream::core::LlamaDecoderLayerConfig config{};
    config.tokens = tokens;
    config.hidden_size = hidden;
    config.intermediate_size = intermediate;
    config.num_attention_heads = q_heads;
    config.num_key_value_heads = kv_heads;
    config.head_dim = head_dim;
    config.position_offset = 0;
    config.rope_theta = 10000.0f;
    config.rms_norm_epsilon = eps;
    spoolstream::core::execute_quantized_llama_decoder_layer_prefill(d_input.get(),
                                                                     d_output.get(),
                                                                     weights,
                                                                     workspace,
                                                                     config);
    assert_close(d_output.copy_to_host(), expected, 0.08f, "streamed quantized decoder layer");

    spoolstream::core::destroy_activation_workspace(workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(q_workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(k_workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(v_workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(o_workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(gate_workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(up_workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(down_workspace);
    spoolstream::core::destroy_scheduled_layer_transfer(transfer);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

void test_streamed_quantized_multilayer_prefill() {
    constexpr int layers = 2;
    constexpr int tokens = 16;
    constexpr int hidden = 16;
    constexpr int intermediate = 32;
    constexpr int q_heads = 2;
    constexpr int kv_heads = 1;
    constexpr int head_dim = 8;
    constexpr int kv_hidden = kv_heads * head_dim;
    constexpr float eps = 1.0e-5f;

    std::vector<float> input(static_cast<size_t>(tokens) * hidden);
    for (size_t i = 0; i < input.size(); ++i) {
        input[i] = static_cast<float>(static_cast<int>((i * 7) % 19) - 9) * 0.015625f;
    }

    std::vector<std::vector<float>> attn_norm_f(layers);
    std::vector<std::vector<float>> mlp_norm_f(layers);
    std::vector<std::vector<half>> attn_norms(layers);
    std::vector<std::vector<half>> mlp_norms(layers);
    std::vector<std::vector<QuantProjectionFixture>> layer_projections(layers);
    std::vector<QuantProjectionFixture> all_projections;
    for (int layer = 0; layer < layers; ++layer) {
        attn_norm_f[static_cast<size_t>(layer)].resize(hidden);
        mlp_norm_f[static_cast<size_t>(layer)].resize(hidden);
        for (int i = 0; i < hidden; ++i) {
            attn_norm_f[static_cast<size_t>(layer)][static_cast<size_t>(i)] =
                0.9375f + static_cast<float>((layer + i) % 4) * 0.015625f;
            mlp_norm_f[static_cast<size_t>(layer)][static_cast<size_t>(i)] =
                0.8125f + static_cast<float>((layer * 2 + i) % 5) * 0.01875f;
        }
        attn_norms[static_cast<size_t>(layer)] =
            to_half(attn_norm_f[static_cast<size_t>(layer)]);
        mlp_norms[static_cast<size_t>(layer)] =
            to_half(mlp_norm_f[static_cast<size_t>(layer)]);

        const std::string prefix = "model.layers." + std::to_string(layer);
        const int seed_base = 3 + layer * 17;
        layer_projections[static_cast<size_t>(layer)] = {
            make_quant_projection_fixture(prefix + ".self_attn.q_proj", hidden, hidden, 2, seed_base),
            make_quant_projection_fixture(prefix + ".self_attn.k_proj", hidden, kv_hidden, 2, seed_base + 2),
            make_quant_projection_fixture(prefix + ".self_attn.v_proj", hidden, kv_hidden, 2, seed_base + 4),
            make_quant_projection_fixture(prefix + ".self_attn.o_proj", hidden, hidden, 2, seed_base + 6),
            make_quant_projection_fixture(prefix + ".mlp.gate_proj", hidden, intermediate, 2, seed_base + 8),
            make_quant_projection_fixture(prefix + ".mlp.up_proj", hidden, intermediate, 2, seed_base + 10),
            make_quant_projection_fixture(prefix + ".mlp.down_proj", intermediate, hidden, 4, seed_base + 12),
        };
        for (const auto& projection : layer_projections[static_cast<size_t>(layer)]) {
            all_projections.push_back(projection);
        }
    }

    std::vector<float> expected = input;
    for (int layer = 0; layer < layers; ++layer) {
        const auto& projections = layer_projections[static_cast<size_t>(layer)];
        expected = reference_quantized_decoder_layer(
            expected,
            attn_norm_f[static_cast<size_t>(layer)],
            mlp_norm_f[static_cast<size_t>(layer)],
            projections[0],
            projections[1],
            projections[2],
            projections[3],
            projections[4],
            projections[5],
            projections[6],
            tokens,
            hidden,
            intermediate,
            q_heads,
            kv_heads,
            head_dim,
            eps);
    }

    const auto checkpoint = write_quantized_model_checkpoint(layers,
                                                             attn_norms,
                                                             mlp_norms,
                                                             all_projections);
    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 8192);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "multi-layer quantized adapter report unsupported");
    const auto plans = spoolstream::core::build_layer_execution_plans(manifest, 4096, 16);
    auto store = spoolstream::core::create_streaming_tensor_store(checkpoint, 512);
    DeviceBuffer<uint8_t> slot_a(4096);
    DeviceBuffer<uint8_t> slot_b(4096);
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot_a.get(), 0, 4096));
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot_b.get(), 0, 4096));

    DeviceBuffer<half> d_input(input.size());
    DeviceBuffer<half> d_output(expected.size());
    d_input.copy_from_host(to_half(input));
    auto workspace = spoolstream::core::create_activation_workspace(tokens, hidden, intermediate);
    spoolstream::core::LlamaDecoderLayerConfig config{};
    config.tokens = tokens;
    config.hidden_size = hidden;
    config.intermediate_size = intermediate;
    config.num_attention_heads = q_heads;
    config.num_key_value_heads = kv_heads;
    config.head_dim = head_dim;
    config.position_offset = 0;
    config.rope_theta = 10000.0f;
    config.rms_norm_epsilon = eps;
    const auto result = spoolstream::core::execute_streamed_llama_model_prefill(store,
                                                                               manifest,
                                                                               plans,
                                                                               report,
                                                                               slot_a.get(),
                                                                               slot_b.get(),
                                                                               d_input.get(),
                                                                               d_output.get(),
                                                                               workspace,
                                                                               config);
    require_true(result.layers_executed == layers, "multi-layer prefill layer count mismatch");
    require_true(result.bytes_streamed > 0, "multi-layer prefill streamed no bytes");
    assert_close(d_output.copy_to_host(), expected, 0.14f, "streamed multi-layer prefill");

    spoolstream::core::destroy_activation_workspace(workspace);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

void test_quantized_final_logits_greedy() {
    constexpr int tokens = 16;
    constexpr int hidden = 16;
    constexpr int intermediate = 32;
    constexpr int vocab = 64;
    constexpr float eps = 1.0e-5f;

    std::vector<float> hidden_states(static_cast<size_t>(tokens) * hidden);
    for (size_t i = 0; i < hidden_states.size(); ++i) {
        hidden_states[i] =
            static_cast<float>(static_cast<int>((i * 11) % 23) - 11) * 0.0125f;
    }
    std::vector<float> final_norm_f(hidden);
    for (int i = 0; i < hidden; ++i) {
        final_norm_f[static_cast<size_t>(i)] =
            0.75f + static_cast<float>((i * 3) % 7) * 0.025f;
    }
    const auto final_norm = to_half(final_norm_f);
    const auto lm_head = make_quant_projection_fixture("lm_head", hidden, vocab, 2, 29);

    const auto normalized =
        reference_rmsnorm(hidden_states, final_norm_f, tokens, hidden, eps);
    const auto expected_logits = reference_quant_projection(normalized, lm_head, tokens);
    int expected_token = 0;
    float expected_logit =
        expected_logits[static_cast<size_t>(tokens - 1) * static_cast<size_t>(vocab)];
    for (int col = 1; col < vocab; ++col) {
        const float value =
            expected_logits[static_cast<size_t>(tokens - 1) * static_cast<size_t>(vocab) +
                            static_cast<size_t>(col)];
        if (value > expected_logit) {
            expected_logit = value;
            expected_token = col;
        }
    }

    const std::vector<std::vector<float>> norm_float = {std::vector<float>(hidden, 1.0f)};
    const std::vector<std::vector<half>> attn_norms = {to_half(norm_float[0])};
    const std::vector<std::vector<half>> mlp_norms = {to_half(norm_float[0])};
    const std::vector<QuantProjectionFixture> layer_projections = {
        make_quant_projection_fixture("model.layers.0.self_attn.q_proj", hidden, hidden, 2, 3),
        make_quant_projection_fixture("model.layers.0.self_attn.k_proj", hidden, 8, 2, 5),
        make_quant_projection_fixture("model.layers.0.self_attn.v_proj", hidden, 8, 2, 7),
        make_quant_projection_fixture("model.layers.0.self_attn.o_proj", hidden, hidden, 2, 9),
        make_quant_projection_fixture("model.layers.0.mlp.gate_proj", hidden, intermediate, 2, 11),
        make_quant_projection_fixture("model.layers.0.mlp.up_proj", hidden, intermediate, 2, 13),
        make_quant_projection_fixture("model.layers.0.mlp.down_proj", intermediate, hidden, 4, 15),
    };
    const auto checkpoint = write_quantized_model_with_head_checkpoint(1,
                                                                       attn_norms,
                                                                       mlp_norms,
                                                                       final_norm,
                                                                       layer_projections,
                                                                       lm_head);
    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 8192);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "lm_head quantized adapter report unsupported");
    const auto& lm_desc =
        find_projection(report, spoolstream::core::QuantizedProjectionRole::LM_HEAD);
    const auto& final_norm_tensor =
        find_manifest_tensor(manifest, spoolstream::core::TensorRole::FINAL_NORM);
    auto store = spoolstream::core::create_streaming_tensor_store(checkpoint, 1024);

    DeviceBuffer<half> d_hidden(hidden_states.size());
    DeviceBuffer<half> d_final_norm(hidden);
    DeviceBuffer<uint32_t> d_lm_qweight(static_cast<size_t>(lm_desc.input_features) *
                                        static_cast<size_t>(lm_desc.packed_output_columns));
    DeviceBuffer<half> d_lm_scales(static_cast<size_t>(lm_desc.group_count) *
                                   static_cast<size_t>(lm_desc.output_features));
    DeviceBuffer<half> d_logits(static_cast<size_t>(tokens) * vocab);
    d_hidden.copy_from_host(to_half(hidden_states));

    auto staged = spoolstream::core::stage_tensor_bytes(store, final_norm_tensor);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_final_norm.get(),
                                     staged.host_ptr,
                                     staged.byte_size,
                                     cudaMemcpyHostToDevice));
    staged = spoolstream::core::stage_tensor_bytes(store, *lm_desc.qweight);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_lm_qweight.get(),
                                     staged.host_ptr,
                                     staged.byte_size,
                                     cudaMemcpyHostToDevice));
    staged = spoolstream::core::stage_tensor_bytes(store, *lm_desc.scales);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_lm_scales.get(),
                                     staged.host_ptr,
                                     staged.byte_size,
                                     cudaMemcpyHostToDevice));

    auto lm_workspace =
        spoolstream::core::create_quantized_projection_metadata_workspace(lm_desc);
    upload_workspace_for_projection(store, lm_desc, lm_workspace);
    const auto lm_view = spoolstream::core::bind_quantized_projection_device_view(
        lm_desc,
        d_lm_qweight.get(),
        d_lm_scales.get(),
        lm_workspace,
        tokens);

    auto workspace = spoolstream::core::create_activation_workspace(tokens, hidden, intermediate);
    const auto result = spoolstream::core::execute_quantized_final_logits_greedy(d_hidden.get(),
                                                                                d_final_norm.get(),
                                                                                lm_view,
                                                                                workspace,
                                                                                d_logits.get(),
                                                                                tokens,
                                                                                hidden,
                                                                                vocab,
                                                                                eps);
    require_true(result.token_id == expected_token, "greedy token mismatch");
    require_true(std::fabs(result.logit - expected_logit) < 0.025f,
                 "greedy logit mismatch");

    spoolstream::core::destroy_activation_workspace(workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(lm_workspace);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

void test_dense_lm_head_streamed_greedy() {
    constexpr int tokens = 2;
    constexpr int hidden = 16;
    constexpr int vocab = 64;
    constexpr int tile_rows = 7;
    constexpr float eps = 0.00001f;

    std::vector<float> hidden_states(static_cast<size_t>(tokens) * hidden);
    for (int row = 0; row < tokens; ++row) {
        for (int col = 0; col < hidden; ++col) {
            hidden_states[static_cast<size_t>(row) * hidden + col] =
                static_cast<float>(((row + 2) * (col + 5)) % 19 - 9) * 0.0175f;
        }
    }
    std::vector<float> final_norm_f(hidden);
    for (int col = 0; col < hidden; ++col) {
        final_norm_f[static_cast<size_t>(col)] = 0.75f + 0.01f * static_cast<float>(col % 5);
    }
    std::vector<float> lm_head_f(static_cast<size_t>(vocab) * hidden);
    for (int token = 0; token < vocab; ++token) {
        for (int col = 0; col < hidden; ++col) {
            lm_head_f[static_cast<size_t>(token) * hidden + col] =
                static_cast<float>(((token + 3) * (col + 7)) % 23 - 11) * 0.02125f;
        }
    }

    const auto normalized = reference_rmsnorm(hidden_states, final_norm_f, tokens, hidden, eps);
    int expected_token = 0;
    float expected_logit = -std::numeric_limits<float>::infinity();
    for (int token = 0; token < vocab; ++token) {
        float logit = 0.0f;
        for (int col = 0; col < hidden; ++col) {
            logit += normalized[static_cast<size_t>(tokens - 1) * hidden + col] *
                     lm_head_f[static_cast<size_t>(token) * hidden + col];
        }
        if (logit > expected_logit ||
            (logit == expected_logit && token < expected_token)) {
            expected_logit = logit;
            expected_token = token;
        }
    }

    const auto checkpoint = write_dense_lm_head_checkpoint(to_half(final_norm_f),
                                                           to_half(lm_head_f),
                                                           hidden,
                                                           vocab);
    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 8192);
    const auto& final_norm_tensor =
        find_manifest_tensor(manifest, spoolstream::core::TensorRole::FINAL_NORM);
    const auto& lm_head_tensor =
        find_manifest_tensor(manifest, spoolstream::core::TensorRole::LM_HEAD);
    auto store = spoolstream::core::create_streaming_tensor_store(
        checkpoint,
        static_cast<size_t>(tile_rows) * hidden * sizeof(half));

    DeviceBuffer<half> d_hidden(hidden_states.size());
    DeviceBuffer<half> d_final_norm(hidden);
    d_hidden.copy_from_host(to_half(hidden_states));
    const auto staged_final_norm =
        spoolstream::core::stage_tensor_bytes(store, final_norm_tensor);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_final_norm.get(),
                                     staged_final_norm.host_ptr,
                                     staged_final_norm.byte_size,
                                     cudaMemcpyHostToDevice));
    auto workspace = spoolstream::core::create_activation_workspace(tokens, hidden, 32);
    const auto result = spoolstream::core::execute_dense_lm_head_greedy_streamed(
        store,
        lm_head_tensor,
        d_hidden.get(),
        d_final_norm.get(),
        workspace,
        tokens,
        hidden,
        vocab,
        tile_rows,
        eps);

    require_true(result.token_id == expected_token, "dense lm_head greedy token mismatch");
    require_true(std::fabs(result.logit - expected_logit) < 0.025f,
                 "dense lm_head greedy logit mismatch");
    require_true(result.bytes_streamed == static_cast<size_t>(vocab) * hidden * sizeof(half),
                 "dense lm_head streamed byte count mismatch");
    require_true(result.tiles_processed == (vocab + tile_rows - 1) / tile_rows,
                 "dense lm_head tile count mismatch");

    spoolstream::core::SamplingConfig sampling{};
    sampling.temperature = 0.8f;
    sampling.top_k = 1;
    sampling.top_p = 1.0f;
    sampling.repetition_penalty = 1.0f;
    sampling.seed = 12345;
    const auto sampled = spoolstream::core::execute_dense_lm_head_sample_streamed(
        store,
        lm_head_tensor,
        d_hidden.get(),
        d_final_norm.get(),
        workspace,
        tokens,
        hidden,
        vocab,
        tile_rows,
        eps,
        nullptr,
        0,
        sampling);
    require_true(sampled.token_id == expected_token,
                 "dense lm_head top-k sampling token mismatch");
    require_true(std::fabs(sampled.logit - expected_logit) < 0.025f,
                 "dense lm_head top-k sampling logit mismatch");
    require_true(sampled.bytes_streamed == static_cast<size_t>(vocab) * hidden * sizeof(half),
                 "dense lm_head sampled byte count mismatch");

    const int recent_tokens[] = {expected_token};
    sampling.temperature = 0.0f;
    sampling.top_k = 0;
    sampling.repetition_penalty = 1.25f;
    const auto penalized = spoolstream::core::execute_dense_lm_head_sample_streamed(
        store,
        lm_head_tensor,
        d_hidden.get(),
        d_final_norm.get(),
        workspace,
        tokens,
        hidden,
        vocab,
        tile_rows,
        eps,
        recent_tokens,
        1,
        sampling);
    require_true(penalized.token_id >= 0 && penalized.token_id < vocab,
                 "dense lm_head penalized sampling token out of range");

    sampling.temperature = -0.1f;
    require_throw([&]() {
        (void)spoolstream::core::execute_dense_lm_head_sample_streamed(store,
                                                                       lm_head_tensor,
                                                                       d_hidden.get(),
                                                                       d_final_norm.get(),
                                                                       workspace,
                                                                       tokens,
                                                                       hidden,
                                                                       vocab,
                                                                       tile_rows,
                                                                       eps,
                                                                       nullptr,
                                                                       0,
                                                                       sampling);
    }, "invalid dense lm_head sampling config");

    spoolstream::core::destroy_activation_workspace(workspace);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

void test_streamed_prompt_embedding_lookup() {
    constexpr int hidden = 16;
    constexpr int vocab = 64;
    const std::vector<int> token_ids = {5, 2, 63, 5};
    std::vector<half> embeddings(static_cast<size_t>(vocab) * hidden);
    for (int token = 0; token < vocab; ++token) {
        for (int col = 0; col < hidden; ++col) {
            const float value =
                static_cast<float>(((token + 11) * (col + 3)) % 29 - 14) * 0.009375f;
            embeddings[static_cast<size_t>(token) * hidden + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }

    const auto checkpoint = write_embedding_checkpoint(embeddings, hidden, vocab);
    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 8192);
    const auto& embedding_tensor =
        find_manifest_tensor(manifest, spoolstream::core::TensorRole::TOKEN_EMBEDDING);
    auto store = spoolstream::core::create_streaming_tensor_store(
        checkpoint,
        static_cast<size_t>(hidden) * sizeof(half));

    DeviceBuffer<half> d_output(static_cast<size_t>(token_ids.size()) * hidden);
    const auto result = spoolstream::core::execute_prompt_embedding_lookup_streamed(
        store,
        embedding_tensor,
        token_ids.data(),
        static_cast<int>(token_ids.size()),
        d_output.get(),
        vocab,
        hidden);
    const auto actual = d_output.copy_to_host();
    require_true(result.tokens_embedded == static_cast<int>(token_ids.size()),
                 "streamed embedding token count mismatch");
    require_true(result.bytes_streamed ==
                     token_ids.size() * static_cast<size_t>(hidden) * sizeof(half),
                 "streamed embedding byte count mismatch");
    for (size_t row = 0; row < token_ids.size(); ++row) {
        const int token_id = token_ids[row];
        for (int col = 0; col < hidden; ++col) {
            const size_t actual_index = row * static_cast<size_t>(hidden) +
                                        static_cast<size_t>(col);
            const size_t expected_index = static_cast<size_t>(token_id) *
                                              static_cast<size_t>(hidden) +
                                          static_cast<size_t>(col);
            require_true(__half2float(actual[actual_index]) ==
                             __half2float(embeddings[expected_index]),
                         "streamed embedding row mismatch");
        }
    }

    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

void test_greedy_decode_loop_with_kv_records() {
    constexpr int tokens = 1;
    constexpr int hidden = 16;
    constexpr int intermediate = 32;
    constexpr int vocab = 64;

    const std::vector<std::vector<float>> norm_float = {std::vector<float>(hidden, 1.0f)};
    const std::vector<std::vector<half>> attn_norms = {to_half(norm_float[0])};
    const std::vector<std::vector<half>> mlp_norms = {to_half(norm_float[0])};
    std::vector<float> final_norm_f(hidden, 0.875f);
    const auto final_norm = to_half(final_norm_f);
    const std::vector<QuantProjectionFixture> layer_projections = {
        make_quant_projection_fixture("model.layers.0.self_attn.q_proj", hidden, hidden, 2, 3),
        make_quant_projection_fixture("model.layers.0.self_attn.k_proj", hidden, 8, 2, 5),
        make_quant_projection_fixture("model.layers.0.self_attn.v_proj", hidden, 8, 2, 7),
        make_quant_projection_fixture("model.layers.0.self_attn.o_proj", hidden, hidden, 2, 9),
        make_quant_projection_fixture("model.layers.0.mlp.gate_proj", hidden, intermediate, 2, 11),
        make_quant_projection_fixture("model.layers.0.mlp.up_proj", hidden, intermediate, 2, 13),
        make_quant_projection_fixture("model.layers.0.mlp.down_proj", intermediate, hidden, 4, 15),
    };
    const auto lm_head = make_quant_projection_fixture("lm_head", hidden, vocab, 2, 31);
    const auto checkpoint = write_quantized_model_with_head_checkpoint(1,
                                                                       attn_norms,
                                                                       mlp_norms,
                                                                       final_norm,
                                                                       layer_projections,
                                                                       lm_head);
    auto manifest = spoolstream::core::build_model_manifest(checkpoint, "STRICT", 8192);
    const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
    require_true(report.supported, "decode quantized adapter report unsupported");
    const auto& lm_desc =
        find_projection(report, spoolstream::core::QuantizedProjectionRole::LM_HEAD);
    const auto& final_norm_tensor =
        find_manifest_tensor(manifest, spoolstream::core::TensorRole::FINAL_NORM);
    const auto plans = spoolstream::core::build_layer_execution_plans(manifest, 4096, 16);
    auto store = spoolstream::core::create_streaming_tensor_store(checkpoint, 1024);

    DeviceBuffer<uint8_t> slot_a(4096);
    DeviceBuffer<uint8_t> slot_b(4096);
    DeviceBuffer<half> d_final_norm(hidden);
    DeviceBuffer<uint32_t> d_lm_qweight(static_cast<size_t>(lm_desc.input_features) *
                                        static_cast<size_t>(lm_desc.packed_output_columns));
    DeviceBuffer<half> d_lm_scales(static_cast<size_t>(lm_desc.group_count) *
                                   static_cast<size_t>(lm_desc.output_features));
    auto staged = spoolstream::core::stage_tensor_bytes(store, final_norm_tensor);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_final_norm.get(),
                                     staged.host_ptr,
                                     staged.byte_size,
                                     cudaMemcpyHostToDevice));
    staged = spoolstream::core::stage_tensor_bytes(store, *lm_desc.qweight);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_lm_qweight.get(),
                                     staged.host_ptr,
                                     staged.byte_size,
                                     cudaMemcpyHostToDevice));
    staged = spoolstream::core::stage_tensor_bytes(store, *lm_desc.scales);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_lm_scales.get(),
                                     staged.host_ptr,
                                     staged.byte_size,
                                     cudaMemcpyHostToDevice));
    auto lm_workspace =
        spoolstream::core::create_quantized_projection_metadata_workspace(lm_desc);
    upload_workspace_for_projection(store, lm_desc, lm_workspace);
    const auto lm_view = spoolstream::core::bind_quantized_projection_device_view(
        lm_desc,
        d_lm_qweight.get(),
        d_lm_scales.get(),
        lm_workspace,
        tokens);

    std::vector<half> embeddings(static_cast<size_t>(vocab) * hidden);
    for (int token = 0; token < vocab; ++token) {
        for (int col = 0; col < hidden; ++col) {
            const float value =
                static_cast<float>(((token + 1) * (col + 3)) % 17 - 8) * 0.0125f;
            embeddings[static_cast<size_t>(token) * hidden + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }
    DeviceBuffer<half> d_embeddings(embeddings.size());
    DeviceBuffer<half> d_current_hidden(hidden);
    DeviceBuffer<half> d_model_hidden(hidden);
    DeviceBuffer<half> d_logits(vocab);
    d_embeddings.copy_from_host(embeddings);
    auto workspace = spoolstream::core::create_activation_workspace(tokens, hidden, intermediate);

    spoolstream::core::KVCacheConfig kv_config{};
    kv_config.page_size_bytes = 256;
    kv_config.max_pages = 2;
    kv_config.max_sequences = 1;
    kv_config.max_pages_per_sequence = 2;
    kv_config.eviction_threshold = 1.0F;
    kv_config.feedback_alpha = 1.0F;
    kv_config.verification_floor = 0.45F;
    kv_config.initial_lookahead_depth = 1;
    kv_config.cuda_device_id = 0;
    auto kv_cache = spoolstream::core::create_paged_kv_cache(kv_config);

    std::vector<int> output_tokens(2, -1);
    spoolstream::core::GreedyDecodeConfig decode_config{};
    decode_config.max_new_tokens = 2;
    decode_config.eos_token_id = -1;
    decode_config.sequence_id = 0;
    const auto result = spoolstream::core::execute_greedy_decode_loop(store,
                                                                      manifest,
                                                                      plans,
                                                                      report,
                                                                      slot_a.get(),
                                                                      slot_b.get(),
                                                                      d_embeddings.get(),
                                                                      vocab,
                                                                      d_final_norm.get(),
                                                                      lm_view,
                                                                      3,
                                                                      output_tokens.data(),
                                                                      static_cast<int>(output_tokens.size()),
                                                                      decode_config,
                                                                      workspace,
                                                                      d_current_hidden.get(),
                                                                      d_model_hidden.get(),
                                                                      d_logits.get(),
                                                                      &kv_cache);
    require_true(result.tokens_generated == 2, "decode generated token count mismatch");
    require_true(output_tokens[0] >= 0 && output_tokens[0] < vocab, "decode token 0 out of range");
    require_true(output_tokens[1] >= 0 && output_tokens[1] < vocab, "decode token 1 out of range");
    require_true(kv_cache.active_pages == 1, "decode KV active page count mismatch");
    std::vector<int> kv_records(2);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(kv_records.data(),
                                     kv_cache.device_window,
                                     sizeof(int) * kv_records.size(),
                                     cudaMemcpyDeviceToHost));
    require_true(kv_records[0] == output_tokens[0], "KV token record 0 mismatch");
    require_true(kv_records[1] == output_tokens[1], "KV token record 1 mismatch");

    spoolstream::core::destroy_paged_kv_cache(kv_cache);
    spoolstream::core::destroy_activation_workspace(workspace);
    spoolstream::core::destroy_quantized_projection_metadata_workspace(lm_workspace);
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(checkpoint);
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_activation_workspace();
        test_rmsnorm();
        test_rope();
        test_residual_swiglu_and_copy();
        test_dense_matmul();
        test_causal_attention_prefill();
        test_causal_attention_decode_matches_prefill_tail();
        test_complete_llama_decoder_layer_prefill();
        test_streamed_quantized_llama_decoder_layer_prefill();
        test_streamed_quantized_multilayer_prefill();
        test_quantized_final_logits_greedy();
        test_dense_lm_head_streamed_greedy();
        test_streamed_prompt_embedding_lookup();
        test_greedy_decode_loop_with_kv_records();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream transformer executor tests passed\n";
    return 0;
}
