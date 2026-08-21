#pragma once

#include <cstdint>

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

namespace spoolstream::core {

enum class QuantFormat {
    AWQ_INT4,
    GPTQ_EXLLAMA_INT4
};

enum class ActivationKind {
    NONE,
    RELU,
    GELU_TANH,
    GELU_ERF,
    SILU
};

struct FusedGemmConfig {
    int m;
    int n;
    int k;
    int group_size;
    QuantFormat quant_format;
    ActivationKind activation;
};

void launch_fused_dequant_gemm(const half* x,
                               const uint32_t* packed_w,
                               const half* scales,
                               const half* zeros,
                               const half* bias,
                               half* output,
                               const FusedGemmConfig& config,
                               cudaStream_t stream = nullptr);

void launch_gptq_exllama_dequant_gemm(const half* x,
                                      const uint32_t* qweight,
                                      const half* scales,
                                      const half* zeros,
                                      const int* g_idx,
                                      const half* bias,
                                      half* output,
                                      const FusedGemmConfig& config,
                                      cudaStream_t stream = nullptr);

} // namespace spoolstream::core
