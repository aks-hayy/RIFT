#include "spoolstream/kernels.h"
#include "spoolstream/memory_manager.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
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

    const T* get() const {
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

float apply_activation_reference(float value, spoolstream::core::ActivationKind activation) {
    switch (activation) {
        case spoolstream::core::ActivationKind::NONE:
            return value;
        case spoolstream::core::ActivationKind::RELU:
            return std::max(value, 0.0f);
        case spoolstream::core::ActivationKind::GELU_TANH: {
            constexpr float kSqrtTwoOverPi = 0.7978845608028654f;
            constexpr float kCoeff = 0.044715f;
            const float inner = kSqrtTwoOverPi * (value + kCoeff * value * value * value);
            return 0.5f * value * (1.0f + std::tanh(inner));
        }
        case spoolstream::core::ActivationKind::GELU_ERF: {
            constexpr float kInvSqrtTwo = 0.7071067811865476f;
            return 0.5f * value * (1.0f + std::erf(value * kInvSqrtTwo));
        }
        case spoolstream::core::ActivationKind::SILU:
            return value / (1.0f + std::exp(-value));
        default:
            throw std::runtime_error("unsupported activation in reference");
    }
}

uint8_t quant_value_for(int k, int n) {
    return static_cast<uint8_t>((k * 3 + n * 5 + 7) & 0x0F);
}

std::vector<half> make_input(int m, int k) {
    std::vector<half> x(static_cast<size_t>(m) * static_cast<size_t>(k));
    for (int row = 0; row < m; ++row) {
        for (int col = 0; col < k; ++col) {
            const float value = static_cast<float>(((row * 7 + col * 3) % 11) - 5) * 0.03125f;
            x[static_cast<size_t>(row) * static_cast<size_t>(k) + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }
    return x;
}

std::vector<uint32_t> make_packed_weights(int k, int n) {
    require_true(n % 8 == 0, "test weight packing requires n divisible by 8");
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

std::vector<half> make_scales(int k, int n, int group_size) {
    const int groups = (k + group_size - 1) / group_size;
    std::vector<half> scales(static_cast<size_t>(groups) * static_cast<size_t>(n));
    for (int group = 0; group < groups; ++group) {
        for (int col = 0; col < n; ++col) {
            const float value = 0.01875f + 0.00125f * static_cast<float>((group + col) % 5);
            scales[static_cast<size_t>(group) * static_cast<size_t>(n) + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }
    return scales;
}

std::vector<half> make_zeros(int k, int n, int group_size) {
    const int groups = (k + group_size - 1) / group_size;
    std::vector<half> zeros(static_cast<size_t>(groups) * static_cast<size_t>(n));
    for (int group = 0; group < groups; ++group) {
        for (int col = 0; col < n; ++col) {
            const float value = 7.0f + static_cast<float>((group + col) % 3) * 0.25f;
            zeros[static_cast<size_t>(group) * static_cast<size_t>(n) + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }
    return zeros;
}

std::vector<half> make_bias(int n) {
    std::vector<half> bias(static_cast<size_t>(n));
    for (int col = 0; col < n; ++col) {
        const float value = static_cast<float>((col % 9) - 4) * 0.015625f;
        bias[static_cast<size_t>(col)] = __float2half(value);
    }
    return bias;
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
                                 const std::vector<half>* bias,
                                 const spoolstream::core::FusedGemmConfig& config) {
    std::vector<half> output(static_cast<size_t>(config.m) * static_cast<size_t>(config.n));
    for (int row = 0; row < config.m; ++row) {
        for (int col = 0; col < config.n; ++col) {
            float accumulator = 0.0f;
            for (int kk = 0; kk < config.k; ++kk) {
                const float lhs =
                    __half2float(x[static_cast<size_t>(row) * static_cast<size_t>(config.k) +
                                   static_cast<size_t>(kk)]);
                const float rhs =
                    dequantize_reference(packed,
                                         scales,
                                         zeros,
                                         config.k,
                                         config.n,
                                         config.group_size,
                                         kk,
                                         col);
                accumulator += lhs * rhs;
            }
            if (bias != nullptr) {
                accumulator += __half2float((*bias)[static_cast<size_t>(col)]);
            }
            accumulator = apply_activation_reference(accumulator, config.activation);
            output[static_cast<size_t>(row) * static_cast<size_t>(config.n) +
                   static_cast<size_t>(col)] = __float2half(accumulator);
        }
    }
    return output;
}

void assert_close(const std::vector<half>& actual,
                  const std::vector<half>& expected,
                  const std::string& case_name) {
    require_true(actual.size() == expected.size(), case_name + ": output size mismatch");
    for (size_t i = 0; i < actual.size(); ++i) {
        const float actual_f = __half2float(actual[i]);
        const float expected_f = __half2float(expected[i]);
        const float diff = std::fabs(actual_f - expected_f);
        if (diff > 0.02f) {
            throw std::runtime_error(case_name + ": mismatch at index " + std::to_string(i) +
                                     " actual=" + std::to_string(actual_f) +
                                     " expected=" + std::to_string(expected_f) +
                                     " diff=" + std::to_string(diff));
        }
    }
}

void run_kernel_case(const std::string& case_name,
                     int m,
                     int n,
                     int k,
                     int group_size,
                     bool use_bias,
                     spoolstream::core::ActivationKind activation) {
    spoolstream::core::FusedGemmConfig config;
    config.m = m;
    config.n = n;
    config.k = k;
    config.group_size = group_size;
    config.quant_format = spoolstream::core::QuantFormat::AWQ_INT4;
    config.activation = activation;

    const std::vector<half> x = make_input(m, k);
    const std::vector<uint32_t> packed = make_packed_weights(k, n);
    const std::vector<half> scales = make_scales(k, n, group_size);
    const std::vector<half> zeros = make_zeros(k, n, group_size);
    const std::vector<half> bias = make_bias(n);
    const std::vector<half> expected =
        reference_gemm(x, packed, scales, zeros, use_bias ? &bias : nullptr, config);

    DeviceBuffer<half> d_x(x.size());
    DeviceBuffer<uint32_t> d_packed(packed.size());
    DeviceBuffer<half> d_scales(scales.size());
    DeviceBuffer<half> d_zeros(zeros.size());
    DeviceBuffer<half> d_bias(use_bias ? bias.size() : 0);
    DeviceBuffer<half> d_output(expected.size());

    d_x.copy_from_host(x);
    d_packed.copy_from_host(packed);
    d_scales.copy_from_host(scales);
    d_zeros.copy_from_host(zeros);
    if (use_bias) {
        d_bias.copy_from_host(bias);
    }
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(d_output.get(), 0, sizeof(half) * expected.size()));

    spoolstream::core::launch_fused_dequant_gemm(d_x.get(),
                                                 d_packed.get(),
                                                 d_scales.get(),
                                                 d_zeros.get(),
                                                 use_bias ? d_bias.get() : nullptr,
                                                 d_output.get(),
                                                 config);

    const std::vector<half> actual = d_output.copy_to_host();
    assert_close(actual, expected, case_name);
}

void test_activation_coverage() {
    run_kernel_case("none", 16, 16, 16, 8, false, spoolstream::core::ActivationKind::NONE);
    run_kernel_case("relu", 16, 16, 16, 8, true, spoolstream::core::ActivationKind::RELU);
    run_kernel_case("gelu_tanh", 16, 16, 16, 8, true, spoolstream::core::ActivationKind::GELU_TANH);
    run_kernel_case("gelu_erf", 16, 16, 16, 8, true, spoolstream::core::ActivationKind::GELU_ERF);
    run_kernel_case("silu", 16, 16, 16, 8, true, spoolstream::core::ActivationKind::SILU);
}

void test_boundary_tiles() {
    run_kernel_case("boundary_tiles", 17, 24, 19, 7, true,
                    spoolstream::core::ActivationKind::GELU_TANH);
}

void test_invalid_configs() {
    spoolstream::core::FusedGemmConfig config;
    config.m = 16;
    config.n = 16;
    config.k = 16;
    config.group_size = 8;
    config.quant_format = spoolstream::core::QuantFormat::AWQ_INT4;
    config.activation = spoolstream::core::ActivationKind::NONE;

    std::vector<half> x = make_input(config.m, config.k);
    std::vector<uint32_t> packed = make_packed_weights(config.k, config.n);
    std::vector<half> scales = make_scales(config.k, config.n, config.group_size);
    std::vector<half> zeros = make_zeros(config.k, config.n, config.group_size);
    std::vector<half> output(static_cast<size_t>(config.m) * static_cast<size_t>(config.n));

    require_throw([&]() {
        spoolstream::core::launch_fused_dequant_gemm(nullptr,
                                                     packed.data(),
                                                     scales.data(),
                                                     zeros.data(),
                                                     nullptr,
                                                     output.data(),
                                                     config);
    }, "null x");

    config.n = 18;
    require_throw([&]() {
        spoolstream::core::launch_fused_dequant_gemm(x.data(),
                                                     packed.data(),
                                                     scales.data(),
                                                     zeros.data(),
                                                     nullptr,
                                                     output.data(),
                                                     config);
    }, "n not divisible by 8");

    config.n = 16;
    config.group_size = 0;
    require_throw([&]() {
        spoolstream::core::launch_fused_dequant_gemm(x.data(),
                                                     packed.data(),
                                                     scales.data(),
                                                     zeros.data(),
                                                     nullptr,
                                                     output.data(),
                                                     config);
    }, "invalid group size");
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_activation_coverage();
        test_boundary_tiles();
        test_invalid_configs();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream kernel tests passed\n";
    return 0;
}
