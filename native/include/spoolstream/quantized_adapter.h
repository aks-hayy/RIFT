#pragma once

#include "spoolstream/kernels.h"
#include "spoolstream/layer_scheduler.h"
#include "spoolstream/model.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

namespace spoolstream::core {

enum class QuantizedProjectionRole {
    UNKNOWN,
    ATTN_Q,
    ATTN_K,
    ATTN_V,
    ATTN_O,
    MLP_GATE,
    MLP_UP,
    MLP_DOWN,
    LM_HEAD
};

enum class QuantizedWeightLayout {
    UNKNOWN,
    PACKED_ROW_INT4,
    GPTQ_EXLLAMA_INT4
};

enum class QuantizedZeroEncoding {
    NONE,
    FP16_EXPANDED,
    INT32_PACKED
};

struct QuantizedProjection {
    QuantizedProjectionRole role;
    int layer_id;
    std::string base_name;
    ModelQuantization quantization;
    QuantizedWeightLayout weight_layout;
    QuantizedZeroEncoding zero_encoding;
    const ManifestTensor* qweight;
    const ManifestTensor* scales;
    const ManifestTensor* zeros;
    const ManifestTensor* g_idx;
    const ManifestTensor* bias;
    int input_features;
    int output_features;
    int qweight_rows;
    int qweight_columns;
    int packed_output_columns;
    int group_count;
    int group_size;
    bool kernel_compatible;
    bool materializable;
    std::string compatibility_notes;
};

struct QuantizedAdapterReport {
    bool supported;
    std::vector<std::string> issues;
    std::vector<QuantizedProjection> projections;
    size_t kernel_compatible_projection_count;
    size_t materializable_projection_count;
};

struct QuantizedProjectionMetadataWorkspace {
    half* device_zeros;
    int* device_g_idx;
    size_t zero_count;
    size_t g_idx_count;
    int group_count;
    int output_features;
    int group_size;
    QuantizedZeroEncoding source_zero_encoding;
};

struct QuantizedProjectionRuntimeView {
    const QuantizedProjection* projection;
    const uint32_t* device_qweight;
    const half* device_scales;
    const half* device_zeros;
    const int* device_g_idx;
    int input_features;
    int output_features;
    int group_size;
    FusedGemmConfig gemm_config;
};

QuantizedAdapterReport build_quantized_adapter_report(const ModelManifest& manifest);

std::vector<half> expand_packed_qzeros_to_half(const uint32_t* packed_qzeros,
                                               int group_count,
                                               int output_features);

QuantizedProjectionMetadataWorkspace create_quantized_projection_metadata_workspace(
    const QuantizedProjection& projection);

void destroy_quantized_projection_metadata_workspace(
    QuantizedProjectionMetadataWorkspace& workspace) noexcept;

void upload_projection_zeros_to_workspace(QuantizedProjectionMetadataWorkspace& workspace,
                                          const QuantizedProjection& projection,
                                          const void* host_zero_bytes,
                                          size_t byte_count,
                                          cudaStream_t stream = nullptr);

void upload_projection_gidx_to_workspace(QuantizedProjectionMetadataWorkspace& workspace,
                                         const QuantizedProjection& projection,
                                         const void* host_gidx_bytes,
                                         size_t byte_count,
                                         cudaStream_t stream = nullptr);

FusedGemmConfig build_quantized_projection_gemm_config(
    const QuantizedProjection& projection,
    int batch_tokens,
    ActivationKind activation = ActivationKind::NONE);

QuantizedProjectionRuntimeView bind_quantized_projection_runtime_view(
    const QuantizedProjection& projection,
    const LayerExecutionPlan& plan,
    const void* device_layer_slot,
    const QuantizedProjectionMetadataWorkspace& metadata_workspace,
    int batch_tokens,
    ActivationKind activation = ActivationKind::NONE);

QuantizedProjectionRuntimeView bind_quantized_projection_device_view(
    const QuantizedProjection& projection,
    const uint32_t* device_qweight,
    const half* device_scales,
    const QuantizedProjectionMetadataWorkspace& metadata_workspace,
    int batch_tokens,
    ActivationKind activation = ActivationKind::NONE);

void launch_quantized_projection(const half* input,
                                 half* output,
                                 const QuantizedProjectionRuntimeView& view,
                                 const half* bias = nullptr,
                                 cudaStream_t stream = nullptr);

const char* quantized_projection_role_name(QuantizedProjectionRole role) noexcept;

const char* quantized_zero_encoding_name(QuantizedZeroEncoding encoding) noexcept;

const char* quantized_weight_layout_name(QuantizedWeightLayout layout) noexcept;

} // namespace spoolstream::core
