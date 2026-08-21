#include "spoolstream/quantized_adapter.h"

#include "spoolstream/memory_manager.h"

#include <algorithm>
#include <climits>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <map>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace spoolstream::core {
namespace {

bool contains_token(const std::string& haystack, const std::string& needle) {
    return haystack.find(needle) != std::string::npos;
}

bool is_int32_dtype(const std::string& dtype) {
    return dtype == "I32" || dtype == "U32" || dtype == "INT32" || dtype == "UINT32";
}

bool is_half_dtype(const std::string& dtype) {
    return dtype == "F16" || dtype == "FLOAT16" || dtype == "float16";
}

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream quantized adapter validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

size_t byte_size(const ManifestTensor& tensor) {
    return tensor.metadata.end_offset - tensor.metadata.start_offset;
}

bool tensor_byte_size_matches_shape(const ManifestTensor& tensor, size_t element_size) {
    size_t element_count = 1;
    for (int64_t dim : tensor.metadata.shape) {
        if (dim <= 0 ||
            element_count > std::numeric_limits<size_t>::max() / static_cast<size_t>(dim)) {
            return false;
        }
        element_count *= static_cast<size_t>(dim);
    }
    return byte_size(tensor) == element_count * element_size;
}

bool is_all_zero_half_tensor_on_disk(const ModelManifest& manifest,
                                     const ManifestTensor& tensor,
                                     std::string& error) {
    if (manifest.checkpoint_directory.empty()) {
        return true;
    }
    const std::filesystem::path path =
        manifest.checkpoint_directory / tensor.metadata.shard_file;
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        error = "unable to open bias shard " + path.string();
        return false;
    }
    const size_t bytes = byte_size(tensor);
    if ((bytes % sizeof(uint16_t)) != 0) {
        error = "bias byte size is not aligned to FP16 elements";
        return false;
    }
    file.seekg(static_cast<std::streamoff>(tensor.metadata.start_offset), std::ios::beg);
    if (!file) {
        error = "unable to seek to bias tensor offset";
        return false;
    }
    std::vector<uint16_t> words(bytes / sizeof(uint16_t));
    file.read(reinterpret_cast<char*>(words.data()), static_cast<std::streamsize>(bytes));
    if (file.gcount() != static_cast<std::streamsize>(bytes)) {
        error = "unable to read complete bias tensor";
        return false;
    }
    for (uint16_t word : words) {
        if ((word & 0x7FFFU) != 0U) {
            error = "nonzero projection bias is not supported yet";
            return false;
        }
    }
    return true;
}

std::string shape_string(const ManifestTensor& tensor) {
    std::ostringstream out;
    out << "[";
    for (size_t i = 0; i < tensor.metadata.shape.size(); ++i) {
        if (i != 0) {
            out << ",";
        }
        out << tensor.metadata.shape[i];
    }
    out << "]";
    return out.str();
}

QuantizedProjectionRole role_from_base_name(const std::string& base_name) {
    if (contains_token(base_name, "q_proj") || contains_token(base_name, "query_proj")) {
        return QuantizedProjectionRole::ATTN_Q;
    }
    if (contains_token(base_name, "k_proj") || contains_token(base_name, "key_proj")) {
        return QuantizedProjectionRole::ATTN_K;
    }
    if (contains_token(base_name, "v_proj") || contains_token(base_name, "value_proj")) {
        return QuantizedProjectionRole::ATTN_V;
    }
    if (contains_token(base_name, "o_proj") || contains_token(base_name, "out_proj")) {
        return QuantizedProjectionRole::ATTN_O;
    }
    if (contains_token(base_name, "gate_proj")) {
        return QuantizedProjectionRole::MLP_GATE;
    }
    if (contains_token(base_name, "up_proj")) {
        return QuantizedProjectionRole::MLP_UP;
    }
    if (contains_token(base_name, "down_proj")) {
        return QuantizedProjectionRole::MLP_DOWN;
    }
    if (contains_token(base_name, "lm_head")) {
        return QuantizedProjectionRole::LM_HEAD;
    }
    return QuantizedProjectionRole::UNKNOWN;
}

void add_issue(QuantizedAdapterReport& report, const std::string& issue) {
    report.issues.push_back(issue);
}

const ManifestTensor* find_by_role(const std::vector<const ManifestTensor*>& tensors,
                                   TensorRole role) {
    for (const ManifestTensor* tensor : tensors) {
        if (tensor->role == role) {
            return tensor;
        }
    }
    return nullptr;
}

const TensorPlacement* find_projection_placement(const LayerExecutionPlan& plan,
                                                 const QuantizedProjection& projection,
                                                 const ManifestTensor* tensor,
                                                 const char* label) {
    require_condition(tensor != nullptr,
                      std::string("projection is missing tensor for ") + label);
    for (const TensorPlacement& placement : plan.placements) {
        if (placement.tensor == tensor) {
            return &placement;
        }
        if (placement.tensor != nullptr &&
            placement.tensor->metadata.name == tensor->metadata.name &&
            placement.tensor->base_name == projection.base_name) {
            return &placement;
        }
    }
    fail(projection.base_name + ": layer plan does not contain placement for " + label);
}

QuantizedProjection validate_projection(const ModelManifest& manifest,
                                        const std::string& base_name,
                                        const std::vector<const ManifestTensor*>& tensors,
                                        std::vector<std::string>& issues) {
    QuantizedProjection projection{};
    projection.role = role_from_base_name(base_name);
    projection.layer_id = tensors.empty() ? -1 : tensors.front()->layer_id;
    projection.base_name = base_name;
    projection.quantization = manifest.config.quantization;
    projection.weight_layout = QuantizedWeightLayout::UNKNOWN;
    projection.zero_encoding = QuantizedZeroEncoding::NONE;
    projection.qweight = find_by_role(tensors, TensorRole::QUANT_QWEIGHT);
    projection.scales = find_by_role(tensors, TensorRole::QUANT_SCALE);
    projection.zeros = find_by_role(tensors, TensorRole::QUANT_ZERO);
    projection.g_idx = find_by_role(tensors, TensorRole::QUANT_GIDX);
    projection.bias = find_by_role(tensors, TensorRole::QUANT_BIAS);
    projection.input_features = 0;
    projection.output_features = 0;
    projection.qweight_rows = 0;
    projection.qweight_columns = 0;
    projection.packed_output_columns = 0;
    projection.group_count = 0;
    projection.group_size = 0;
    projection.kernel_compatible = false;
    projection.materializable = false;

    auto issue = [&](const std::string& message) {
        issues.push_back(base_name + ": " + message);
    };

    if (projection.role == QuantizedProjectionRole::UNKNOWN) {
        issue("unknown quantized projection role");
    }
    if (projection.qweight == nullptr) {
        issue("missing qweight tensor");
        return projection;
    }
    if (projection.scales == nullptr) {
        issue("missing scales tensor");
    }
    if (projection.zeros == nullptr) {
        issue("missing qzeros/zeros tensor");
    }
    if (manifest.config.quantization != ModelQuantization::AWQ_INT4 &&
        manifest.config.quantization != ModelQuantization::GPTQ_INT4) {
        issue("manifest quantization is not AWQ_INT4 or GPTQ_INT4");
    }
    if (!is_int32_dtype(projection.qweight->metadata.data_type)) {
        issue("qweight dtype must be I32/U32, got " + projection.qweight->metadata.data_type);
    }
    if (projection.qweight->metadata.shape.size() != 2) {
        issue("qweight shape must be rank-2, got " + shape_string(*projection.qweight));
        return projection;
    }

    const int64_t q_rows64 = projection.qweight->metadata.shape[0];
    const int64_t q_cols64 = projection.qweight->metadata.shape[1];
    if (q_rows64 <= 0 || q_cols64 <= 0 ||
        q_rows64 > INT_MAX || q_cols64 > INT_MAX ||
        q_cols64 > static_cast<int64_t>(INT_MAX / 8) ||
        q_rows64 > static_cast<int64_t>(INT_MAX / 8)) {
        issue("qweight dimensions are invalid");
        return projection;
    }
    const int q_rows = static_cast<int>(q_rows64);
    const int q_cols = static_cast<int>(q_cols64);
    projection.qweight_rows = q_rows;
    projection.qweight_columns = q_cols;

    const size_t expected_qweight_bytes = static_cast<size_t>(projection.qweight_rows) *
                                          static_cast<size_t>(projection.qweight_columns) *
                                          sizeof(uint32_t);
    if (byte_size(*projection.qweight) != expected_qweight_bytes) {
        issue("qweight byte size does not match rank-2 I32 shape");
    }

    int64_t scale_groups = 0;
    int64_t scale_cols = 0;
    if (projection.scales != nullptr) {
        if (!is_half_dtype(projection.scales->metadata.data_type)) {
            issue("scales dtype must be F16 for direct CUDA half metadata");
        }
        if (projection.scales->metadata.shape.size() != 2) {
            issue("scales shape must be rank-2, got " + shape_string(*projection.scales));
        } else {
            scale_groups = projection.scales->metadata.shape[0];
            scale_cols = projection.scales->metadata.shape[1];
            if (scale_groups <= 0 || scale_cols <= 0 || scale_groups > INT_MAX ||
                scale_cols > INT_MAX) {
                issue("scales dimensions are invalid");
            }
        }
    }

    int64_t zero_groups = 0;
    int64_t zero_cols = 0;
    if (projection.zeros != nullptr) {
        if (is_half_dtype(projection.zeros->metadata.data_type)) {
            projection.zero_encoding = QuantizedZeroEncoding::FP16_EXPANDED;
        } else if (is_int32_dtype(projection.zeros->metadata.data_type)) {
            projection.zero_encoding = QuantizedZeroEncoding::INT32_PACKED;
        } else {
            issue("zeros dtype must be F16 expanded or I32/U32 packed");
        }
        if (projection.zeros->metadata.shape.size() != 2) {
            issue("zeros shape must be rank-2, got " + shape_string(*projection.zeros));
        } else {
            zero_groups = projection.zeros->metadata.shape[0];
            zero_cols = projection.zeros->metadata.shape[1];
            if (zero_groups <= 0 || zero_cols <= 0 || zero_groups > INT_MAX ||
                zero_cols > INT_MAX) {
                issue("zeros dimensions are invalid");
            }
        }
    }

    const bool old_packed_row_candidate =
        scale_groups > 0 &&
        scale_cols == static_cast<int64_t>(q_cols) * 8 &&
        (projection.zero_encoding == QuantizedZeroEncoding::FP16_EXPANDED ||
         projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED);
    const bool exllama_candidate =
        scale_groups > 0 &&
        scale_cols == q_cols &&
        projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED;

    if (exllama_candidate) {
        projection.weight_layout = QuantizedWeightLayout::GPTQ_EXLLAMA_INT4;
        projection.input_features = q_rows * 8;
        projection.output_features = q_cols;
        projection.packed_output_columns = q_cols / 8;
    } else if (old_packed_row_candidate) {
        projection.weight_layout = QuantizedWeightLayout::PACKED_ROW_INT4;
        projection.input_features = q_rows;
        projection.output_features = q_cols * 8;
        projection.packed_output_columns = q_cols;
    } else if (projection.scales != nullptr) {
        issue("unable to infer supported int4 layout from qweight/scales shapes");
    }

    if (projection.weight_layout != QuantizedWeightLayout::UNKNOWN) {
        if (projection.output_features <= 0 || projection.input_features <= 0 ||
            (projection.output_features % 8) != 0) {
            issue("inferred projection dimensions are invalid for int4 metadata");
        }
        projection.group_count = static_cast<int>(scale_groups);
        if ((projection.input_features % projection.group_count) != 0) {
            issue("input_features must be divisible by group_count for deterministic group_size");
        } else {
            projection.group_size = projection.input_features / projection.group_count;
        }
    }

    if (projection.g_idx != nullptr) {
        if (!is_int32_dtype(projection.g_idx->metadata.data_type)) {
            issue("g_idx dtype must be I32/U32");
        }
        if (projection.g_idx->metadata.shape.size() != 1 ||
            projection.g_idx->metadata.shape[0] != projection.input_features) {
            issue("g_idx shape must be [input_features]");
        }
        if (projection.weight_layout == QuantizedWeightLayout::PACKED_ROW_INT4) {
            issue("g_idx is only supported for GPTQ_EXLLAMA_INT4 layout");
        }
    }

    if (projection.zeros != nullptr &&
        projection.weight_layout != QuantizedWeightLayout::UNKNOWN) {
        if (zero_groups != projection.group_count) {
            issue("zero metadata group count does not match scales");
        }
        if (projection.zero_encoding == QuantizedZeroEncoding::FP16_EXPANDED &&
            zero_cols != projection.output_features) {
            issue("expanded half zeros shape must be [groups, output_features]");
        }
        if (projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED &&
            zero_cols != projection.packed_output_columns) {
            issue("packed qzeros shape must be [groups, output_features / 8]");
        }
    }

    if (projection.bias != nullptr) {
        if (!is_half_dtype(projection.bias->metadata.data_type)) {
            issue("projection bias dtype must be F16");
        }
        if (projection.bias->metadata.shape.size() != 1 ||
            projection.bias->metadata.shape[0] != projection.output_features) {
            issue("projection bias shape must be [output_features]");
        }
        if (!tensor_byte_size_matches_shape(*projection.bias, sizeof(half))) {
            issue("projection bias byte size does not match FP16 shape");
        } else {
            std::string bias_error;
            if (!is_all_zero_half_tensor_on_disk(manifest, *projection.bias, bias_error)) {
                issue(bias_error);
            }
        }
    }

    const bool shape_ready = projection.group_count > 0 &&
                             projection.group_size > 0 &&
                             projection.qweight != nullptr &&
                             projection.scales != nullptr &&
                             projection.zeros != nullptr;
    projection.kernel_compatible =
        shape_ready &&
        projection.weight_layout == QuantizedWeightLayout::PACKED_ROW_INT4 &&
        projection.zero_encoding == QuantizedZeroEncoding::FP16_EXPANDED &&
        projection.g_idx == nullptr &&
        is_half_dtype(projection.scales->metadata.data_type);
    projection.materializable =
        shape_ready &&
        ((projection.weight_layout == QuantizedWeightLayout::PACKED_ROW_INT4 &&
          (projection.zero_encoding == QuantizedZeroEncoding::FP16_EXPANDED ||
           projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED) &&
          projection.g_idx == nullptr) ||
         (projection.weight_layout == QuantizedWeightLayout::GPTQ_EXLLAMA_INT4 &&
          projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED)) &&
        is_half_dtype(projection.scales->metadata.data_type);

    if (projection.kernel_compatible) {
        projection.compatibility_notes = "directly compatible with current fused AWQ int4 GEMM metadata contract";
    } else if (projection.materializable &&
               projection.weight_layout == QuantizedWeightLayout::GPTQ_EXLLAMA_INT4) {
        projection.compatibility_notes =
            "materializable GPTQ ExLlama int4 projection with optional g_idx grouping";
    } else if (projection.materializable &&
               projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED) {
        projection.compatibility_notes = "materializable after qzeros unpack to expanded half metadata";
    } else if (projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED) {
        projection.compatibility_notes = "requires qzeros unpack to expanded half metadata before current GEMM";
    } else if (projection.g_idx != nullptr) {
        projection.compatibility_notes = "requires g_idx-aware grouping path before current GEMM";
    } else {
        projection.compatibility_notes = "requires layout repair or unsupported metadata fixup";
    }

    return projection;
}

} // namespace

QuantizedAdapterReport build_quantized_adapter_report(const ModelManifest& manifest) {
    QuantizedAdapterReport report{};
    report.supported = false;
    report.kernel_compatible_projection_count = 0;
    report.materializable_projection_count = 0;

    std::map<std::string, std::vector<const ManifestTensor*>> grouped;
    for (const ManifestTensor& tensor : manifest.tensors) {
        if (tensor.role == TensorRole::QUANT_QWEIGHT ||
            tensor.role == TensorRole::QUANT_SCALE ||
            tensor.role == TensorRole::QUANT_ZERO ||
            tensor.role == TensorRole::QUANT_GIDX ||
            tensor.role == TensorRole::QUANT_BIAS) {
            grouped[tensor.base_name].push_back(&tensor);
        }
    }

    if (grouped.empty()) {
        report.issues.push_back("manifest contains no quantized tensor families");
        return report;
    }

    for (const auto& entry : grouped) {
        if (find_by_role(entry.second, TensorRole::QUANT_QWEIGHT) == nullptr) {
            continue;
        }
        std::vector<std::string> projection_issues;
        QuantizedProjection projection =
            validate_projection(manifest, entry.first, entry.second, projection_issues);
        if (projection.kernel_compatible) {
            ++report.kernel_compatible_projection_count;
        }
        if (projection.materializable) {
            ++report.materializable_projection_count;
        }
        for (const std::string& issue : projection_issues) {
            add_issue(report, issue);
        }
        report.projections.push_back(projection);
    }

    if (report.projections.empty()) {
        report.issues.push_back("manifest contains quant metadata but no qweight projections");
    }
    report.supported = !report.projections.empty() && report.issues.empty();
    std::sort(report.projections.begin(),
              report.projections.end(),
              [](const QuantizedProjection& lhs, const QuantizedProjection& rhs) {
                  if (lhs.layer_id != rhs.layer_id) {
                      return lhs.layer_id < rhs.layer_id;
                  }
                  return lhs.base_name < rhs.base_name;
              });
    return report;
}

std::vector<half> expand_packed_qzeros_to_half(const uint32_t* packed_qzeros,
                                               int group_count,
                                               int output_features) {
    require_condition(packed_qzeros != nullptr, "packed_qzeros pointer cannot be null");
    require_condition(group_count > 0, "group_count must be positive");
    require_condition(output_features > 0, "output_features must be positive");
    require_condition((output_features % 8) == 0,
                      "output_features must be divisible by 8 for packed qzeros");

    const int packed_cols = output_features / 8;
    const size_t total = static_cast<size_t>(group_count) *
                         static_cast<size_t>(output_features);
    std::vector<half> expanded(total);
    for (int group = 0; group < group_count; ++group) {
        for (int pack = 0; pack < packed_cols; ++pack) {
            const uint32_t word = packed_qzeros[static_cast<size_t>(group) *
                                                static_cast<size_t>(packed_cols) +
                                                static_cast<size_t>(pack)];
            for (int nibble = 0; nibble < 8; ++nibble) {
                const uint32_t value = (word >> (4 * nibble)) & 0x0FU;
                const int col = pack * 8 + nibble;
                expanded[static_cast<size_t>(group) * static_cast<size_t>(output_features) +
                         static_cast<size_t>(col)] =
                    __float2half(static_cast<float>(value));
            }
        }
    }
    return expanded;
}

std::vector<half> expand_packed_qzeros_to_half_with_offset(const uint32_t* packed_qzeros,
                                                           int group_count,
                                                           int output_features,
                                                           int zero_offset) {
    std::vector<half> expanded =
        expand_packed_qzeros_to_half(packed_qzeros, group_count, output_features);
    if (zero_offset != 0) {
        for (half& value : expanded) {
            value = __float2half(__half2float(value) + static_cast<float>(zero_offset));
        }
    }
    return expanded;
}

QuantizedProjectionMetadataWorkspace create_quantized_projection_metadata_workspace(
    const QuantizedProjection& projection) {
    require_condition(projection.materializable,
                      "projection is not materializable for current GEMM metadata path");
    require_condition(projection.group_count > 0, "projection group_count must be positive");
    require_condition(projection.output_features > 0, "projection output_features must be positive");
    const size_t zero_count = static_cast<size_t>(projection.group_count) *
                              static_cast<size_t>(projection.output_features);
    require_condition(zero_count <= std::numeric_limits<size_t>::max() / sizeof(half),
                      "projection zero metadata allocation overflows size_t");

    QuantizedProjectionMetadataWorkspace workspace{};
    workspace.zero_count = zero_count;
    workspace.g_idx_count = projection.g_idx != nullptr ?
                                 static_cast<size_t>(projection.input_features) :
                                 0;
    workspace.group_count = projection.group_count;
    workspace.output_features = projection.output_features;
    workspace.group_size = projection.group_size;
    workspace.source_zero_encoding = projection.zero_encoding;
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.device_zeros),
                                          zero_count * sizeof(half)));
        if (workspace.g_idx_count > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&workspace.device_g_idx),
                                              workspace.g_idx_count * sizeof(int)));
        }
    } catch (...) {
        destroy_quantized_projection_metadata_workspace(workspace);
        throw;
    }
    return workspace;
}

void destroy_quantized_projection_metadata_workspace(
    QuantizedProjectionMetadataWorkspace& workspace) noexcept {
    if (workspace.device_zeros != nullptr) {
        cudaFree(workspace.device_zeros);
        workspace.device_zeros = nullptr;
    }
    if (workspace.device_g_idx != nullptr) {
        cudaFree(workspace.device_g_idx);
        workspace.device_g_idx = nullptr;
    }
    workspace.zero_count = 0;
    workspace.g_idx_count = 0;
    workspace.group_count = 0;
    workspace.output_features = 0;
    workspace.group_size = 0;
    workspace.source_zero_encoding = QuantizedZeroEncoding::NONE;
}

void upload_projection_zeros_to_workspace(QuantizedProjectionMetadataWorkspace& workspace,
                                          const QuantizedProjection& projection,
                                          const void* host_zero_bytes,
                                          size_t byte_count,
                                          cudaStream_t stream) {
    require_condition(workspace.device_zeros != nullptr, "workspace device_zeros is null");
    require_condition(host_zero_bytes != nullptr, "host_zero_bytes pointer cannot be null");
    require_condition(workspace.group_count == projection.group_count,
                      "workspace group_count does not match projection");
    require_condition(workspace.output_features == projection.output_features,
                      "workspace output_features does not match projection");
    require_condition(workspace.zero_count == static_cast<size_t>(projection.group_count) *
                                                  static_cast<size_t>(projection.output_features),
                      "workspace zero_count does not match projection");

    if (projection.zero_encoding == QuantizedZeroEncoding::FP16_EXPANDED) {
        const size_t expected_bytes = workspace.zero_count * sizeof(half);
        require_condition(byte_count == expected_bytes,
                          "expanded zero byte count does not match projection metadata");
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(workspace.device_zeros,
                                               host_zero_bytes,
                                               expected_bytes,
                                               cudaMemcpyHostToDevice,
                                               stream));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
        return;
    }

    if (projection.zero_encoding == QuantizedZeroEncoding::INT32_PACKED) {
        require_condition((projection.output_features % 8) == 0,
                          "projection output_features must be divisible by 8");
        const size_t packed_count = static_cast<size_t>(projection.group_count) *
                                    static_cast<size_t>(projection.output_features / 8);
        const size_t expected_bytes = packed_count * sizeof(uint32_t);
        require_condition(byte_count == expected_bytes,
                          "packed qzeros byte count does not match projection metadata");
        const auto* packed = static_cast<const uint32_t*>(host_zero_bytes);
        const int zero_offset =
            projection.weight_layout == QuantizedWeightLayout::GPTQ_EXLLAMA_INT4 ? 1 : 0;
        const std::vector<half> expanded =
            expand_packed_qzeros_to_half_with_offset(packed,
                                                     projection.group_count,
                                                     projection.output_features,
                                                     zero_offset);
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(workspace.device_zeros,
                                               expanded.data(),
                                               expanded.size() * sizeof(half),
                                               cudaMemcpyHostToDevice,
                                               stream));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
        return;
    }

    fail("unsupported projection zero encoding");
}

void upload_projection_gidx_to_workspace(QuantizedProjectionMetadataWorkspace& workspace,
                                         const QuantizedProjection& projection,
                                         const void* host_gidx_bytes,
                                         size_t byte_count,
                                         cudaStream_t stream) {
    if (projection.g_idx == nullptr) {
        require_condition(workspace.device_g_idx == nullptr,
                          "workspace has g_idx allocation for projection without g_idx");
        return;
    }
    require_condition(workspace.device_g_idx != nullptr, "workspace device_g_idx is null");
    require_condition(host_gidx_bytes != nullptr, "host_gidx_bytes pointer cannot be null");
    require_condition(workspace.g_idx_count == static_cast<size_t>(projection.input_features),
                      "workspace g_idx_count does not match projection input_features");
    const size_t expected_bytes = static_cast<size_t>(projection.input_features) * sizeof(int32_t);
    require_condition(byte_count == expected_bytes,
                      "g_idx byte count does not match projection metadata");

    const auto* host = static_cast<const int32_t*>(host_gidx_bytes);
    for (int index = 0; index < projection.input_features; ++index) {
        if (host[index] < 0 || host[index] >= projection.group_count) {
            std::ostringstream out;
            out << "g_idx value at " << index << " is outside [0,"
                << projection.group_count << ")";
            fail(out.str());
        }
    }
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(workspace.device_g_idx,
                                           host_gidx_bytes,
                                           expected_bytes,
                                           cudaMemcpyHostToDevice,
                                           stream));
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));
}

FusedGemmConfig build_quantized_projection_gemm_config(
    const QuantizedProjection& projection,
    int batch_tokens,
    ActivationKind activation) {
    require_condition(projection.materializable,
                      "projection is not materializable for current GEMM metadata path");
    require_condition(batch_tokens > 0, "batch_tokens must be positive");
    require_condition(projection.input_features > 0, "projection input_features must be positive");
    require_condition(projection.output_features > 0, "projection output_features must be positive");
    require_condition(projection.group_size > 0, "projection group_size must be positive");

    FusedGemmConfig config{};
    config.m = batch_tokens;
    config.n = projection.output_features;
    config.k = projection.input_features;
    config.group_size = projection.group_size;
    config.quant_format =
        projection.weight_layout == QuantizedWeightLayout::GPTQ_EXLLAMA_INT4 ?
            QuantFormat::GPTQ_EXLLAMA_INT4 :
            QuantFormat::AWQ_INT4;
    config.activation = activation;
    return config;
}

QuantizedProjectionRuntimeView bind_quantized_projection_runtime_view(
    const QuantizedProjection& projection,
    const LayerExecutionPlan& plan,
    const void* device_layer_slot,
    const QuantizedProjectionMetadataWorkspace& metadata_workspace,
    int batch_tokens,
    ActivationKind activation) {
    require_condition(device_layer_slot != nullptr, "device_layer_slot pointer cannot be null");
    require_condition(plan.layer_id == projection.layer_id,
                      "layer plan does not match projection layer_id");
    require_condition(metadata_workspace.device_zeros != nullptr,
                      "metadata workspace device_zeros is null");
    require_condition(metadata_workspace.group_count == projection.group_count,
                      "metadata workspace group_count mismatch");
    require_condition(metadata_workspace.output_features == projection.output_features,
                      "metadata workspace output_features mismatch");
    if (projection.g_idx != nullptr) {
        require_condition(metadata_workspace.device_g_idx != nullptr,
                          "metadata workspace device_g_idx is null");
        require_condition(metadata_workspace.g_idx_count ==
                              static_cast<size_t>(projection.input_features),
                          "metadata workspace g_idx_count mismatch");
    }

    const TensorPlacement* qweight =
        find_projection_placement(plan, projection, projection.qweight, "qweight");
    const TensorPlacement* scales =
        find_projection_placement(plan, projection, projection.scales, "scales");
    require_condition(qweight->byte_size ==
                          static_cast<size_t>(projection.qweight_rows) *
                              static_cast<size_t>(projection.qweight_columns) *
                              sizeof(uint32_t),
                      "qweight placement byte size does not match projection");
    require_condition(scales->byte_size ==
                          static_cast<size_t>(projection.group_count) *
                              static_cast<size_t>(projection.output_features) * sizeof(half),
                      "scales placement byte size does not match projection");

    const auto* base = static_cast<const unsigned char*>(device_layer_slot);
    QuantizedProjectionRuntimeView view{};
    view.projection = &projection;
    view.device_qweight =
        reinterpret_cast<const uint32_t*>(base + qweight->slot_offset);
    view.device_scales = reinterpret_cast<const half*>(base + scales->slot_offset);
    view.device_zeros = metadata_workspace.device_zeros;
    view.device_g_idx = metadata_workspace.device_g_idx;
    view.input_features = projection.input_features;
    view.output_features = projection.output_features;
    view.group_size = projection.group_size;
    view.gemm_config =
        build_quantized_projection_gemm_config(projection, batch_tokens, activation);
    return view;
}

QuantizedProjectionRuntimeView bind_quantized_projection_device_view(
    const QuantizedProjection& projection,
    const uint32_t* device_qweight,
    const half* device_scales,
    const QuantizedProjectionMetadataWorkspace& metadata_workspace,
    int batch_tokens,
    ActivationKind activation) {
    require_condition(device_qweight != nullptr, "device_qweight pointer cannot be null");
    require_condition(device_scales != nullptr, "device_scales pointer cannot be null");
    require_condition(metadata_workspace.device_zeros != nullptr,
                      "metadata workspace device_zeros is null");
    require_condition(metadata_workspace.group_count == projection.group_count,
                      "metadata workspace group_count mismatch");
    require_condition(metadata_workspace.output_features == projection.output_features,
                      "metadata workspace output_features mismatch");
    if (projection.g_idx != nullptr) {
        require_condition(metadata_workspace.device_g_idx != nullptr,
                          "metadata workspace device_g_idx is null");
        require_condition(metadata_workspace.g_idx_count ==
                              static_cast<size_t>(projection.input_features),
                          "metadata workspace g_idx_count mismatch");
    }

    QuantizedProjectionRuntimeView view{};
    view.projection = &projection;
    view.device_qweight = device_qweight;
    view.device_scales = device_scales;
    view.device_zeros = metadata_workspace.device_zeros;
    view.device_g_idx = metadata_workspace.device_g_idx;
    view.input_features = projection.input_features;
    view.output_features = projection.output_features;
    view.group_size = projection.group_size;
    view.gemm_config =
        build_quantized_projection_gemm_config(projection, batch_tokens, activation);
    return view;
}

void launch_quantized_projection(const half* input,
                                 half* output,
                                 const QuantizedProjectionRuntimeView& view,
                                 const half* bias,
                                 cudaStream_t stream) {
    require_condition(input != nullptr, "input pointer cannot be null");
    require_condition(output != nullptr, "output pointer cannot be null");
    require_condition(view.projection != nullptr, "runtime view projection is null");
    require_condition(view.device_qweight != nullptr, "runtime view qweight pointer is null");
    require_condition(view.device_scales != nullptr, "runtime view scales pointer is null");
    require_condition(view.device_zeros != nullptr, "runtime view zeros pointer is null");
    require_condition(view.input_features == view.gemm_config.k,
                      "runtime view input_features does not match GEMM config");
    require_condition(view.output_features == view.gemm_config.n,
                      "runtime view output_features does not match GEMM config");
    if (view.projection->weight_layout == QuantizedWeightLayout::GPTQ_EXLLAMA_INT4) {
        if (view.projection->g_idx != nullptr) {
            require_condition(view.device_g_idx != nullptr,
                              "runtime view g_idx pointer is null");
        }
        launch_gptq_exllama_dequant_gemm(input,
                                          view.device_qweight,
                                          view.device_scales,
                                          view.device_zeros,
                                          view.device_g_idx,
                                          bias,
                                          output,
                                          view.gemm_config,
                                          stream);
        return;
    }
    launch_fused_dequant_gemm(input,
                              view.device_qweight,
                              view.device_scales,
                              view.device_zeros,
                              bias,
                              output,
                              view.gemm_config,
                              stream);
}

const char* quantized_projection_role_name(QuantizedProjectionRole role) noexcept {
    switch (role) {
        case QuantizedProjectionRole::ATTN_Q:
            return "ATTN_Q";
        case QuantizedProjectionRole::ATTN_K:
            return "ATTN_K";
        case QuantizedProjectionRole::ATTN_V:
            return "ATTN_V";
        case QuantizedProjectionRole::ATTN_O:
            return "ATTN_O";
        case QuantizedProjectionRole::MLP_GATE:
            return "MLP_GATE";
        case QuantizedProjectionRole::MLP_UP:
            return "MLP_UP";
        case QuantizedProjectionRole::MLP_DOWN:
            return "MLP_DOWN";
        case QuantizedProjectionRole::LM_HEAD:
            return "LM_HEAD";
        default:
            return "UNKNOWN";
    }
}

const char* quantized_zero_encoding_name(QuantizedZeroEncoding encoding) noexcept {
    switch (encoding) {
        case QuantizedZeroEncoding::FP16_EXPANDED:
            return "FP16_EXPANDED";
        case QuantizedZeroEncoding::INT32_PACKED:
            return "INT32_PACKED";
        default:
            return "NONE";
    }
}

const char* quantized_weight_layout_name(QuantizedWeightLayout layout) noexcept {
    switch (layout) {
        case QuantizedWeightLayout::PACKED_ROW_INT4:
            return "PACKED_ROW_INT4";
        case QuantizedWeightLayout::GPTQ_EXLLAMA_INT4:
            return "GPTQ_EXLLAMA_INT4";
        default:
            return "UNKNOWN";
    }
}

} // namespace spoolstream::core
