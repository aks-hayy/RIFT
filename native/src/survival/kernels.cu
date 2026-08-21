#include "spoolstream/kernels.h"

#include "spoolstream/memory_manager.h"

#include <cuda_fp16.h>
#include <mma.h>

#include <cmath>
#include <sstream>
#include <stdexcept>
#include <string>

namespace spoolstream::core {
namespace {

constexpr int kWmmaTileM = 16;
constexpr int kWmmaTileN = 16;
constexpr int kWmmaTileK = 16;
constexpr int kPackedValuesPerWord = 8;
constexpr int kThreadsPerBlock = 32;

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream fused GEMM validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

__device__ __forceinline__ float gelu_tanh(float x) {
    constexpr float kSqrtTwoOverPi = 0.7978845608028654f;
    constexpr float kCoeff = 0.044715f;
    const float inner = kSqrtTwoOverPi * (x + kCoeff * x * x * x);
    return 0.5f * x * (1.0f + tanhf(inner));
}

__device__ __forceinline__ float gelu_erf(float x) {
    constexpr float kInvSqrtTwo = 0.7071067811865476f;
    return 0.5f * x * (1.0f + erff(x * kInvSqrtTwo));
}

__device__ __forceinline__ float silu(float x) {
    return x / (1.0f + expf(-x));
}

__device__ __forceinline__ float apply_activation(float value, ActivationKind activation) {
    switch (activation) {
        case ActivationKind::NONE:
            return value;
        case ActivationKind::RELU:
            return value > 0.0f ? value : 0.0f;
        case ActivationKind::GELU_TANH:
            return gelu_tanh(value);
        case ActivationKind::GELU_ERF:
            return gelu_erf(value);
        case ActivationKind::SILU:
            return silu(value);
        default:
            return value;
    }
}

__device__ inline void dequantize_pack_4bit(uint32_t packed_val,
                                            half* target_reg_array,
                                            half scale,
                                            half zero) {
    const float scale_f = __half2float(scale);
    const float zero_f = __half2float(zero);
    #pragma unroll
    for (int i = 0; i < kPackedValuesPerWord; ++i) {
        const uint32_t quantized = (packed_val >> (4 * i)) & 0x0FU;
        const float dequantized = (static_cast<float>(quantized) - zero_f) * scale_f;
        target_reg_array[i] = __float2half(dequantized);
    }
}

__device__ __forceinline__ half dequantize_weight_at(const uint32_t* packed_w,
                                                     const half* scales,
                                                     const half* zeros,
                                                     int k_index,
                                                     int n_index,
                                                     int n,
                                                     int group_size) {
    const int packed_cols = n / kPackedValuesPerWord;
    const int packed_index = k_index * packed_cols + (n_index / kPackedValuesPerWord);
    const int nibble_index = n_index & 7;
    const int group_index = k_index / group_size;
    const int metadata_index = group_index * n + n_index;

    half unpacked[kPackedValuesPerWord];
    dequantize_pack_4bit(packed_w[packed_index],
                         unpacked,
                         scales[metadata_index],
                         zeros[metadata_index]);
    return unpacked[nibble_index];
}

__global__ void fused_dequant_gemm_kernel(const half* __restrict__ x,
                                          const uint32_t* __restrict__ packed_w,
                                          const half* __restrict__ scales,
                                          const half* __restrict__ zeros,
                                          const half* __restrict__ bias,
                                          half* __restrict__ output,
                                          FusedGemmConfig config) {
    __shared__ __align__(128) half shared_a[kWmmaTileM * kWmmaTileK];
    __shared__ __align__(128) half shared_b[kWmmaTileK * kWmmaTileN];
    __shared__ __align__(128) float shared_c[kWmmaTileM * kWmmaTileN];

    const int tile_m = blockIdx.y * kWmmaTileM;
    const int tile_n = blockIdx.x * kWmmaTileN;
    const int lane = threadIdx.x;

    nvcuda::wmma::fragment<nvcuda::wmma::matrix_a,
                           kWmmaTileM,
                           kWmmaTileN,
                           kWmmaTileK,
                           half,
                           nvcuda::wmma::row_major>
        a_fragment;
    nvcuda::wmma::fragment<nvcuda::wmma::matrix_b,
                           kWmmaTileM,
                           kWmmaTileN,
                           kWmmaTileK,
                           half,
                           nvcuda::wmma::row_major>
        b_fragment;
    nvcuda::wmma::fragment<nvcuda::wmma::accumulator,
                           kWmmaTileM,
                           kWmmaTileN,
                           kWmmaTileK,
                           float>
        accumulator;

    nvcuda::wmma::fill_fragment(accumulator, 0.0f);

    for (int k_tile = 0; k_tile < config.k; k_tile += kWmmaTileK) {
        for (int index = lane; index < kWmmaTileM * kWmmaTileK; index += kThreadsPerBlock) {
            const int local_m = index / kWmmaTileK;
            const int local_k = index % kWmmaTileK;
            const int global_m = tile_m + local_m;
            const int global_k = k_tile + local_k;
            if (global_m < config.m && global_k < config.k) {
                shared_a[index] = x[global_m * config.k + global_k];
            } else {
                shared_a[index] = __float2half(0.0f);
            }
        }

        for (int index = lane; index < kWmmaTileK * kWmmaTileN; index += kThreadsPerBlock) {
            const int local_k = index / kWmmaTileN;
            const int local_n = index % kWmmaTileN;
            const int global_k = k_tile + local_k;
            const int global_n = tile_n + local_n;
            if (global_k < config.k && global_n < config.n) {
                shared_b[index] = dequantize_weight_at(packed_w,
                                                       scales,
                                                       zeros,
                                                       global_k,
                                                       global_n,
                                                       config.n,
                                                       config.group_size);
            } else {
                shared_b[index] = __float2half(0.0f);
            }
        }

        __syncwarp();
        nvcuda::wmma::load_matrix_sync(a_fragment, shared_a, kWmmaTileK);
        nvcuda::wmma::load_matrix_sync(b_fragment, shared_b, kWmmaTileN);
        nvcuda::wmma::mma_sync(accumulator, a_fragment, b_fragment, accumulator);
        __syncwarp();
    }

    nvcuda::wmma::store_matrix_sync(shared_c,
                                    accumulator,
                                    kWmmaTileN,
                                    nvcuda::wmma::mem_row_major);
    __syncwarp();

    for (int index = lane; index < kWmmaTileM * kWmmaTileN; index += kThreadsPerBlock) {
        const int local_m = index / kWmmaTileN;
        const int local_n = index % kWmmaTileN;
        const int global_m = tile_m + local_m;
        const int global_n = tile_n + local_n;
        if (global_m < config.m && global_n < config.n) {
            float value = shared_c[index];
            if (bias != nullptr) {
                value += __half2float(bias[global_n]);
            }
            value = apply_activation(value, config.activation);
            output[global_m * config.n + global_n] = __float2half(value);
        }
    }
}

__global__ void gptq_exllama_dequant_gemm_kernel(const half* __restrict__ x,
                                                 const uint32_t* __restrict__ qweight,
                                                 const half* __restrict__ scales,
                                                 const half* __restrict__ zeros,
                                                 const int* __restrict__ g_idx,
                                                 const half* __restrict__ bias,
                                                 half* __restrict__ output,
                                                 FusedGemmConfig config) {
    const int n_index = blockIdx.x * blockDim.x + threadIdx.x;
    const int m_index = blockIdx.y * blockDim.y + threadIdx.y;
    if (m_index >= config.m || n_index >= config.n) {
        return;
    }

    float accumulator = 0.0f;
    for (int k_index = 0; k_index < config.k; ++k_index) {
        const int packed_row = k_index / kPackedValuesPerWord;
        const int nibble_index = k_index & 7;
        const uint32_t packed = qweight[packed_row * config.n + n_index];
        const uint32_t quantized = (packed >> (4 * nibble_index)) & 0x0FU;
        const int group_index =
            g_idx != nullptr ? g_idx[k_index] : (k_index / config.group_size);
        const int metadata_index = group_index * config.n + n_index;
        const float scale = __half2float(scales[metadata_index]);
        const float zero = __half2float(zeros[metadata_index]);
        const float weight = (static_cast<float>(quantized) - zero) * scale;
        accumulator += __half2float(x[m_index * config.k + k_index]) * weight;
    }

    if (bias != nullptr) {
        accumulator += __half2float(bias[n_index]);
    }
    accumulator = apply_activation(accumulator, config.activation);
    output[m_index * config.n + n_index] = __float2half(accumulator);
}

void validate_config(const half* x,
                     const uint32_t* packed_w,
                     const half* scales,
                     const half* zeros,
                     half* output,
                     const FusedGemmConfig& config) {
    require_condition(x != nullptr, "x pointer cannot be null");
    require_condition(packed_w != nullptr, "packed_w pointer cannot be null");
    require_condition(scales != nullptr, "scales pointer cannot be null");
    require_condition(zeros != nullptr, "zeros pointer cannot be null");
    require_condition(output != nullptr, "output pointer cannot be null");
    require_condition(config.quant_format == QuantFormat::AWQ_INT4,
                      "unsupported quantization format");
    require_condition(config.m > 0, "m must be positive");
    require_condition(config.n > 0, "n must be positive");
    require_condition(config.k > 0, "k must be positive");
    require_condition(config.group_size > 0, "group_size must be positive");
    require_condition(config.n % kPackedValuesPerWord == 0,
                      "n must be divisible by 8 for AWQ int4 packed row storage");
    require_condition(config.activation == ActivationKind::NONE ||
                          config.activation == ActivationKind::RELU ||
                          config.activation == ActivationKind::GELU_TANH ||
                          config.activation == ActivationKind::GELU_ERF ||
                          config.activation == ActivationKind::SILU,
                      "unsupported activation kind");
}

void validate_gptq_exllama_config(const half* x,
                                  const uint32_t* qweight,
                                  const half* scales,
                                  const half* zeros,
                                  half* output,
                                  const FusedGemmConfig& config) {
    require_condition(x != nullptr, "x pointer cannot be null");
    require_condition(qweight != nullptr, "qweight pointer cannot be null");
    require_condition(scales != nullptr, "scales pointer cannot be null");
    require_condition(zeros != nullptr, "zeros pointer cannot be null");
    require_condition(output != nullptr, "output pointer cannot be null");
    require_condition(config.quant_format == QuantFormat::GPTQ_EXLLAMA_INT4,
                      "unsupported quantization format for GPTQ ExLlama kernel");
    require_condition(config.m > 0, "m must be positive");
    require_condition(config.n > 0, "n must be positive");
    require_condition(config.k > 0, "k must be positive");
    require_condition(config.group_size > 0, "group_size must be positive");
    require_condition(config.k % kPackedValuesPerWord == 0,
                      "k must be divisible by 8 for GPTQ ExLlama qweight storage");
    require_condition(config.n % kPackedValuesPerWord == 0,
                      "n must be divisible by 8 for GPTQ ExLlama qzeros storage");
    require_condition(config.activation == ActivationKind::NONE ||
                          config.activation == ActivationKind::RELU ||
                          config.activation == ActivationKind::GELU_TANH ||
                          config.activation == ActivationKind::GELU_ERF ||
                          config.activation == ActivationKind::SILU,
                      "unsupported activation kind");
}

} // namespace

void launch_fused_dequant_gemm(const half* x,
                               const uint32_t* packed_w,
                               const half* scales,
                               const half* zeros,
                               const half* bias,
                               half* output,
                               const FusedGemmConfig& config,
                               cudaStream_t stream) {
    validate_config(x, packed_w, scales, zeros, output, config);

    const dim3 block(kThreadsPerBlock, 1, 1);
    const dim3 grid((config.n + kWmmaTileN - 1) / kWmmaTileN,
                    (config.m + kWmmaTileM - 1) / kWmmaTileM,
                    1);

    fused_dequant_gemm_kernel<<<grid, block, 0, stream>>>(
        x, packed_w, scales, zeros, bias, output, config);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

void launch_gptq_exllama_dequant_gemm(const half* x,
                                      const uint32_t* qweight,
                                      const half* scales,
                                      const half* zeros,
                                      const int* g_idx,
                                      const half* bias,
                                      half* output,
                                      const FusedGemmConfig& config,
                                      cudaStream_t stream) {
    validate_gptq_exllama_config(x, qweight, scales, zeros, output, config);

    const dim3 block(16, 16, 1);
    const dim3 grid((config.n + block.x - 1) / block.x,
                    (config.m + block.y - 1) / block.y,
                    1);
    gptq_exllama_dequant_gemm_kernel<<<grid, block, 0, stream>>>(
        x, qweight, scales, zeros, g_idx, bias, output, config);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

} // namespace spoolstream::core
