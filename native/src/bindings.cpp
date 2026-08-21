#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include "spoolstream/execution_policy.h"
#include "spoolstream/kv_cache.h"
#include "spoolstream/layer_scheduler.h"
#include "spoolstream/memory_manager.h"
#include "spoolstream/model.h"
#include "spoolstream/parser.h"
#include "spoolstream/pipeline.h"
#include "spoolstream/quantized_adapter.h"
#include "spoolstream/streaming_store.h"
#include "spoolstream/transformer_executor.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using spoolstream::core::LayerGrouping;
using spoolstream::core::ModelTopology;
using spoolstream::core::TensorMetaData;

constexpr const char* kVersion = "1.3.0";

struct PyInferenceEngine {
    PyObject_HEAD
    int cuda_device_id;
    PyObject* loaded_model_info;
};

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        if (count_ != 0) {
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

    T* get() noexcept {
        return ptr_;
    }

private:
    T* ptr_ = nullptr;
    size_t count_ = 0;
};

PyObject* set_python_error_from_exception() {
    try {
        throw;
    } catch (const std::exception& ex) {
        PyErr_SetString(PyExc_RuntimeError, ex.what());
    } catch (...) {
        PyErr_SetString(PyExc_RuntimeError, "unknown native SpoolStream error");
    }
    return nullptr;
}

bool dict_set_steal(PyObject* dict, const char* key, PyObject* value) {
    if (value == nullptr) {
        return false;
    }
    const int status = PyDict_SetItemString(dict, key, value);
    Py_DECREF(value);
    return status == 0;
}

PyObject* py_size(size_t value) {
    return PyLong_FromUnsignedLongLong(static_cast<unsigned long long>(value));
}

PyObject* tensor_to_dict(const TensorMetaData& tensor) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }

    PyObject* shape = PyList_New(static_cast<Py_ssize_t>(tensor.shape.size()));
    if (shape == nullptr) {
        Py_DECREF(dict);
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(tensor.shape.size()); ++i) {
        PyObject* value = PyLong_FromLongLong(static_cast<long long>(tensor.shape[static_cast<size_t>(i)]));
        if (value == nullptr) {
            Py_DECREF(shape);
            Py_DECREF(dict);
            return nullptr;
        }
        PyList_SET_ITEM(shape, i, value);
    }

    if (!dict_set_steal(dict, "name", PyUnicode_FromString(tensor.name.c_str())) ||
        !dict_set_steal(dict, "shard_file", PyUnicode_FromString(tensor.shard_file.c_str())) ||
        !dict_set_steal(dict, "start_offset", py_size(tensor.start_offset)) ||
        !dict_set_steal(dict, "end_offset", py_size(tensor.end_offset)) ||
        !dict_set_steal(dict, "shape", shape) ||
        !dict_set_steal(dict, "data_type", PyUnicode_FromString(tensor.data_type.c_str()))) {
        Py_DECREF(dict);
        return nullptr;
    }

    return dict;
}

PyObject* layer_to_dict(const LayerGrouping& layer) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }

    PyObject* tensors = PyList_New(static_cast<Py_ssize_t>(layer.tensors.size()));
    if (tensors == nullptr) {
        Py_DECREF(dict);
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(layer.tensors.size()); ++i) {
        PyObject* tensor = tensor_to_dict(layer.tensors[static_cast<size_t>(i)]);
        if (tensor == nullptr) {
            Py_DECREF(tensors);
            Py_DECREF(dict);
            return nullptr;
        }
        PyList_SET_ITEM(tensors, i, tensor);
    }

    if (!dict_set_steal(dict, "layer_id", PyLong_FromLong(layer.layer_id)) ||
        !dict_set_steal(dict, "total_layer_bytes", py_size(layer.total_layer_bytes)) ||
        !dict_set_steal(dict, "tensors", tensors)) {
        Py_DECREF(dict);
        return nullptr;
    }

    return dict;
}

PyObject* topology_to_dict(const ModelTopology& topology) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }

    PyObject* layers = PyList_New(static_cast<Py_ssize_t>(topology.layers.size()));
    if (layers == nullptr) {
        Py_DECREF(dict);
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(topology.layers.size()); ++i) {
        PyObject* layer = layer_to_dict(topology.layers[static_cast<size_t>(i)]);
        if (layer == nullptr) {
            Py_DECREF(layers);
            Py_DECREF(dict);
            return nullptr;
        }
        PyList_SET_ITEM(layers, i, layer);
    }

    if (!dict_set_steal(dict, "total_model_bytes", py_size(topology.total_model_bytes)) ||
        !dict_set_steal(dict, "w_max_bytes", py_size(topology.w_max_bytes)) ||
        !dict_set_steal(dict, "total_layers", PyLong_FromLong(topology.total_layers)) ||
        !dict_set_steal(dict, "memory_strategy", PyUnicode_FromString(topology.memory_strategy.c_str())) ||
        !dict_set_steal(dict, "layers", layers)) {
        Py_DECREF(dict);
        return nullptr;
    }

    return dict;
}

PyObject* config_to_dict(const spoolstream::core::ModelConfig& config) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    if (!dict_set_steal(dict, "model_type", PyUnicode_FromString(config.model_type.c_str())) ||
        !dict_set_steal(dict,
                        "family",
                        PyUnicode_FromString(spoolstream::core::model_family_name(
                            config.family))) ||
        !dict_set_steal(dict,
                        "quantization",
                        PyUnicode_FromString(spoolstream::core::model_quantization_name(
                            config.quantization))) ||
        !dict_set_steal(dict, "hidden_size", PyLong_FromLong(config.hidden_size)) ||
        !dict_set_steal(dict, "intermediate_size", PyLong_FromLong(config.intermediate_size)) ||
        !dict_set_steal(dict, "num_hidden_layers", PyLong_FromLong(config.num_hidden_layers)) ||
        !dict_set_steal(dict, "num_attention_heads", PyLong_FromLong(config.num_attention_heads)) ||
        !dict_set_steal(dict, "num_key_value_heads", PyLong_FromLong(config.num_key_value_heads)) ||
        !dict_set_steal(dict, "vocab_size", PyLong_FromLong(config.vocab_size)) ||
        !dict_set_steal(dict,
                        "max_position_embeddings",
                        PyLong_FromLong(config.max_position_embeddings)) ||
        !dict_set_steal(dict, "rope_theta", PyFloat_FromDouble(config.rope_theta)) ||
        !dict_set_steal(dict, "rms_norm_eps", PyFloat_FromDouble(config.rms_norm_eps)) ||
        !dict_set_steal(dict,
                        "tie_word_embeddings",
                        PyBool_FromLong(config.tie_word_embeddings ? 1 : 0))) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* profile_to_dict(const spoolstream::core::ModelProfile& profile) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    if (!dict_set_steal(dict, "supported", PyBool_FromLong(profile.supported ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "streaming_required",
                        PyBool_FromLong(profile.streaming_required ? 1 : 0)) ||
        !dict_set_steal(dict, "reason", PyUnicode_FromString(profile.reason.c_str())) ||
        !dict_set_steal(dict, "total_model_bytes", py_size(profile.total_model_bytes)) ||
        !dict_set_steal(dict,
                        "required_scratchpad_bytes",
                        py_size(profile.required_scratchpad_bytes)) ||
        !dict_set_steal(dict,
                        "required_host_staging_bytes",
                        py_size(profile.required_host_staging_bytes)) ||
        !dict_set_steal(dict,
                        "estimated_peak_vram_bytes",
                        py_size(profile.estimated_peak_vram_bytes)) ||
        !dict_set_steal(dict,
                        "estimated_peak_host_bytes",
                        py_size(profile.estimated_peak_host_bytes))) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* hardware_profile_to_dict(const spoolstream::core::HardwareProfile& profile) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    if (!dict_set_steal(dict, "cuda_device_id", PyLong_FromLong(profile.cuda_device_id)) ||
        !dict_set_steal(dict, "cuda_available", PyBool_FromLong(profile.cuda_available ? 1 : 0)) ||
        !dict_set_steal(dict, "device_name", PyUnicode_FromString(profile.device_name.c_str())) ||
        !dict_set_steal(dict,
                        "compute_capability_major",
                        PyLong_FromLong(profile.compute_capability_major)) ||
        !dict_set_steal(dict,
                        "compute_capability_minor",
                        PyLong_FromLong(profile.compute_capability_minor)) ||
        !dict_set_steal(dict,
                        "multiprocessor_count",
                        PyLong_FromLong(profile.multiprocessor_count)) ||
        !dict_set_steal(dict, "total_vram_bytes", py_size(profile.total_vram_bytes)) ||
        !dict_set_steal(dict, "free_vram_bytes", py_size(profile.free_vram_bytes)) ||
        !dict_set_steal(dict, "total_host_ram_bytes", py_size(profile.total_host_ram_bytes)) ||
        !dict_set_steal(dict, "free_host_ram_bytes", py_size(profile.free_host_ram_bytes)) ||
        !dict_set_steal(dict,
                        "estimated_h2d_bandwidth_gbps",
                        PyFloat_FromDouble(profile.estimated_h2d_bandwidth_gbps))) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* execution_policy_to_dict(const spoolstream::core::ExecutionPolicy& policy) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    if (!dict_set_steal(dict, "supported", PyBool_FromLong(policy.supported ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "streaming_required",
                        PyBool_FromLong(policy.streaming_required ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "use_paged_kv_cache",
                        PyBool_FromLong(policy.use_paged_kv_cache ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "use_speculative",
                        PyBool_FromLong(policy.use_speculative ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "use_quantized_weights",
                        PyBool_FromLong(policy.use_quantized_weights ? 1 : 0)) ||
        !dict_set_steal(dict, "scratchpad_slot_bytes", py_size(policy.scratchpad_slot_bytes)) ||
        !dict_set_steal(dict, "host_staging_bytes", py_size(policy.host_staging_bytes)) ||
        !dict_set_steal(dict,
                        "host_resident_cap_bytes",
                        py_size(policy.host_resident_cap_bytes)) ||
        !dict_set_steal(dict, "kv_cache_bytes", py_size(policy.kv_cache_bytes)) ||
        !dict_set_steal(dict,
                        "architecture_backend",
                        PyUnicode_FromString(policy.architecture_backend.c_str())) ||
        !dict_set_steal(dict, "reason", PyUnicode_FromString(policy.reason.c_str()))) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* quant_projection_to_dict(const spoolstream::core::QuantizedProjection& projection) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    if (!dict_set_steal(dict,
                        "role",
                        PyUnicode_FromString(spoolstream::core::quantized_projection_role_name(
                            projection.role))) ||
        !dict_set_steal(dict, "layer_id", PyLong_FromLong(projection.layer_id)) ||
        !dict_set_steal(dict, "base_name", PyUnicode_FromString(projection.base_name.c_str())) ||
        !dict_set_steal(dict,
                        "quantization",
                        PyUnicode_FromString(spoolstream::core::model_quantization_name(
                            projection.quantization))) ||
        !dict_set_steal(dict,
                        "layout",
                        PyUnicode_FromString(spoolstream::core::quantized_weight_layout_name(
                            projection.weight_layout))) ||
        !dict_set_steal(dict,
                        "zero_encoding",
                        PyUnicode_FromString(spoolstream::core::quantized_zero_encoding_name(
                            projection.zero_encoding))) ||
        !dict_set_steal(dict, "input_features", PyLong_FromLong(projection.input_features)) ||
        !dict_set_steal(dict, "output_features", PyLong_FromLong(projection.output_features)) ||
        !dict_set_steal(dict, "qweight_rows", PyLong_FromLong(projection.qweight_rows)) ||
        !dict_set_steal(dict, "qweight_columns", PyLong_FromLong(projection.qweight_columns)) ||
        !dict_set_steal(dict,
                        "packed_output_columns",
                        PyLong_FromLong(projection.packed_output_columns)) ||
        !dict_set_steal(dict, "group_count", PyLong_FromLong(projection.group_count)) ||
        !dict_set_steal(dict, "group_size", PyLong_FromLong(projection.group_size)) ||
        !dict_set_steal(dict,
                        "has_g_idx",
                        PyBool_FromLong(projection.g_idx != nullptr ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "has_bias",
                        PyBool_FromLong(projection.bias != nullptr ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "kernel_compatible",
                        PyBool_FromLong(projection.kernel_compatible ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "materializable",
                        PyBool_FromLong(projection.materializable ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "compatibility_notes",
                        PyUnicode_FromString(projection.compatibility_notes.c_str()))) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* quant_report_to_dict(const spoolstream::core::QuantizedAdapterReport& report) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    PyObject* issues = PyList_New(static_cast<Py_ssize_t>(report.issues.size()));
    PyObject* projections = PyList_New(static_cast<Py_ssize_t>(report.projections.size()));
    if (issues == nullptr || projections == nullptr) {
        Py_XDECREF(issues);
        Py_XDECREF(projections);
        Py_DECREF(dict);
        return nullptr;
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(report.issues.size()); ++i) {
        PyObject* value = PyUnicode_FromString(report.issues[static_cast<size_t>(i)].c_str());
        if (value == nullptr) {
            Py_DECREF(issues);
            Py_DECREF(projections);
            Py_DECREF(dict);
            return nullptr;
        }
        PyList_SET_ITEM(issues, i, value);
    }
    for (Py_ssize_t i = 0; i < static_cast<Py_ssize_t>(report.projections.size()); ++i) {
        PyObject* value = quant_projection_to_dict(report.projections[static_cast<size_t>(i)]);
        if (value == nullptr) {
            Py_DECREF(issues);
            Py_DECREF(projections);
            Py_DECREF(dict);
            return nullptr;
        }
        PyList_SET_ITEM(projections, i, value);
    }
    if (!dict_set_steal(dict, "supported", PyBool_FromLong(report.supported ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "kernel_compatible_projection_count",
                        PyLong_FromSize_t(report.kernel_compatible_projection_count)) ||
        !dict_set_steal(dict,
                        "materializable_projection_count",
                        PyLong_FromSize_t(report.materializable_projection_count)) ||
        !dict_set_steal(dict,
                        "projection_count",
                        PyLong_FromSize_t(report.projections.size())) ||
        !dict_set_steal(dict, "issues", issues) ||
        !dict_set_steal(dict, "projections", projections)) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* role_counts_to_dict(const spoolstream::core::ModelManifest& manifest) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }
    for (const auto& tensor : manifest.tensors) {
        const char* role_name = spoolstream::core::tensor_role_name(tensor.role);
        PyObject* current = PyDict_GetItemString(dict, role_name);
        long count = current == nullptr ? 0 : PyLong_AsLong(current);
        if (PyErr_Occurred()) {
            Py_DECREF(dict);
            return nullptr;
        }
        if (!dict_set_steal(dict, role_name, PyLong_FromLong(count + 1))) {
            Py_DECREF(dict);
            return nullptr;
        }
    }
    return dict;
}

bool append_issue(PyObject* issues, const std::string& issue) {
    PyObject* value = PyUnicode_FromString(issue.c_str());
    if (value == nullptr) {
        return false;
    }
    const int status = PyList_Append(issues, value);
    Py_DECREF(value);
    return status == 0;
}

bool manifest_has_role(const spoolstream::core::ModelManifest& manifest,
                       spoolstream::core::TensorRole role) {
    for (const auto& tensor : manifest.tensors) {
        if (tensor.role == role) {
            return true;
        }
    }
    return false;
}

bool has_projection(const spoolstream::core::QuantizedAdapterReport& report,
                    int layer_id,
                    spoolstream::core::QuantizedProjectionRole role,
                    bool require_materializable,
                    bool* has_gidx) {
    for (const auto& projection : report.projections) {
        if (projection.layer_id == layer_id && projection.role == role) {
            if (has_gidx != nullptr && projection.g_idx != nullptr) {
                *has_gidx = true;
            }
            return !require_materializable || projection.materializable;
        }
    }
    return false;
}

const spoolstream::core::ManifestTensor& require_manifest_tensor(
    const spoolstream::core::ModelManifest& manifest,
    spoolstream::core::TensorRole role,
    const char* name) {
    for (const auto& tensor : manifest.tensors) {
        if (tensor.role == role) {
            return tensor;
        }
    }
    throw std::runtime_error(std::string("missing required tensor role: ") + name);
}

size_t phase28_staging_capacity(const spoolstream::core::ModelManifest& manifest,
                                int lm_head_tile_rows) {
    size_t largest_layer_tensor = 0;
    for (const auto& tensor : manifest.tensors) {
        if (tensor.role == spoolstream::core::TensorRole::LM_HEAD ||
            tensor.role == spoolstream::core::TensorRole::TOKEN_EMBEDDING) {
            continue;
        }
        largest_layer_tensor = std::max(largest_layer_tensor,
                                        tensor.metadata.end_offset -
                                            tensor.metadata.start_offset);
    }
    const size_t dense_tile_bytes =
        static_cast<size_t>(lm_head_tile_rows) *
        static_cast<size_t>(manifest.config.hidden_size) * sizeof(half);
    constexpr size_t kMinimumStagingBytes = 64ULL * 1024ULL * 1024ULL;
    return std::max({kMinimumStagingBytes, largest_layer_tensor, dense_tile_bytes});
}

PyObject* int_vector_to_pylist(const std::vector<int>& values) {
    PyObject* list = PyList_New(static_cast<Py_ssize_t>(values.size()));
    if (list == nullptr) {
        return nullptr;
    }
    for (Py_ssize_t index = 0; index < static_cast<Py_ssize_t>(values.size()); ++index) {
        PyObject* value = PyLong_FromLong(values[static_cast<size_t>(index)]);
        if (value == nullptr) {
            Py_DECREF(list);
            return nullptr;
        }
        PyList_SET_ITEM(list, index, value);
    }
    return list;
}

std::filesystem::path loaded_model_path_from_report(PyObject* report) {
    PyObject* path_value = PyDict_GetItemString(report, "model_path");
    if (path_value == nullptr || !PyUnicode_Check(path_value)) {
        throw std::runtime_error("loaded model report does not contain a model_path");
    }
    const char* path = PyUnicode_AsUTF8(path_value);
    if (path == nullptr) {
        throw std::runtime_error("loaded model_path is not valid UTF-8");
    }
    return std::filesystem::path(path);
}

size_t py_dict_size_or_default(PyObject* dict, const char* key, size_t fallback) {
    PyObject* value = PyDict_GetItemString(dict, key);
    if (value == nullptr) {
        return fallback;
    }
    const unsigned long long raw = PyLong_AsUnsignedLongLong(value);
    if (PyErr_Occurred()) {
        throw std::runtime_error(std::string("loaded model report has invalid ") + key);
    }
    return static_cast<size_t>(raw);
}

PyObject* generation_readiness_to_dict(
    const std::filesystem::path& model_path,
    const spoolstream::core::ModelManifest& manifest,
    const spoolstream::core::QuantizedAdapterReport& quant_report) {
    PyObject* dict = PyDict_New();
    PyObject* issues = PyList_New(0);
    if (dict == nullptr || issues == nullptr) {
        Py_XDECREF(dict);
        Py_XDECREF(issues);
        return nullptr;
    }

    bool ready = true;
    auto issue = [&](const std::string& message) {
        ready = false;
        return append_issue(issues, message);
    };

    if (!std::filesystem::exists(model_path / "tokenizer.json")) {
        if (!issue("missing tokenizer.json for prompt encode/decode")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    }
    if (!manifest_has_role(manifest, spoolstream::core::TensorRole::TOKEN_EMBEDDING)) {
        if (!issue("missing token embedding tensor")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    }
    if (!manifest_has_role(manifest, spoolstream::core::TensorRole::FINAL_NORM)) {
        if (!issue("missing final norm tensor")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    }
    if (manifest.config.quantization != spoolstream::core::ModelQuantization::AWQ_INT4 &&
        manifest.config.quantization != spoolstream::core::ModelQuantization::GPTQ_INT4) {
        if (!issue("model quantization is not AWQ_INT4 or GPTQ_INT4")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    }
    if (!quant_report.supported) {
        if (!issue("quantized adapter report is unsupported")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    }

    bool has_gidx = false;
    const spoolstream::core::QuantizedProjectionRole layer_roles[] = {
        spoolstream::core::QuantizedProjectionRole::ATTN_Q,
        spoolstream::core::QuantizedProjectionRole::ATTN_K,
        spoolstream::core::QuantizedProjectionRole::ATTN_V,
        spoolstream::core::QuantizedProjectionRole::ATTN_O,
        spoolstream::core::QuantizedProjectionRole::MLP_GATE,
        spoolstream::core::QuantizedProjectionRole::MLP_UP,
        spoolstream::core::QuantizedProjectionRole::MLP_DOWN,
    };
    for (int layer = 0; layer < manifest.config.num_hidden_layers; ++layer) {
        for (const auto role : layer_roles) {
            if (!has_projection(quant_report, layer, role, true, &has_gidx)) {
                if (!issue("missing or non-materializable projection for layer " +
                           std::to_string(layer) + " role " +
                           spoolstream::core::quantized_projection_role_name(role))) {
                    Py_DECREF(dict);
                    Py_DECREF(issues);
                    return nullptr;
                }
            }
        }
    }
    const bool has_quantized_lm_head =
        has_projection(quant_report,
                       -1,
                       spoolstream::core::QuantizedProjectionRole::LM_HEAD,
                       true,
                       &has_gidx);
    const bool tied_embedding_output_detected =
        manifest.config.tie_word_embeddings &&
        manifest_has_role(manifest, spoolstream::core::TensorRole::TOKEN_EMBEDDING);
    const bool has_dense_lm_head =
        manifest_has_role(manifest, spoolstream::core::TensorRole::LM_HEAD);
    std::string output_head_mode = "MISSING";
    if (has_quantized_lm_head) {
        output_head_mode = "QUANTIZED_LM_HEAD";
    } else if (has_dense_lm_head) {
        output_head_mode = "DENSE_FP16_LM_HEAD_STREAMING";
    } else if (tied_embedding_output_detected) {
        output_head_mode = "TIED_EMBEDDING_PENDING";
    }
    if (!has_quantized_lm_head && !has_dense_lm_head && tied_embedding_output_detected) {
        if (!issue("tied embedding output head detected; dense tied logits projection is not integrated yet")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    } else if (!has_quantized_lm_head && !has_dense_lm_head) {
        if (!issue("missing or non-materializable quantized lm_head")) {
            Py_DECREF(dict);
            Py_DECREF(issues);
            return nullptr;
        }
    }

    if (!dict_set_steal(dict, "ready", PyBool_FromLong(ready ? 1 : 0)) ||
        !dict_set_steal(dict, "issues", issues) ||
        !dict_set_steal(dict,
                        "required_layer_projection_count",
                        PyLong_FromLong(manifest.config.num_hidden_layers * 7)) ||
        !dict_set_steal(dict,
                        "materializable_projection_count",
                        PyLong_FromSize_t(quant_report.materializable_projection_count)) ||
        !dict_set_steal(dict,
                        "has_quantized_lm_head",
                        PyBool_FromLong(has_quantized_lm_head ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "has_dense_lm_head",
                        PyBool_FromLong(has_dense_lm_head ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "uses_gidx_projections",
                        PyBool_FromLong(has_gidx ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "tied_word_embeddings",
                        PyBool_FromLong(manifest.config.tie_word_embeddings ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "tied_embedding_output_detected",
                        PyBool_FromLong(tied_embedding_output_detected ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "output_head_mode",
                        PyUnicode_FromString(output_head_mode.c_str())) ||
        !dict_set_steal(dict,
                        "requires_tokenizer_json",
                        PyBool_FromLong(1)) ||
        !dict_set_steal(dict,
                        "requires_quantized_lm_head",
                        PyBool_FromLong((!has_quantized_lm_head &&
                                         !has_dense_lm_head &&
                                         !tied_embedding_output_detected) ? 1 : 0)) ||
        !dict_set_steal(dict,
                        "requires_dense_lm_head_logits",
                        PyBool_FromLong(0)) ||
        !dict_set_steal(dict,
                        "requires_tied_embedding_logits",
                        PyBool_FromLong((tied_embedding_output_detected &&
                                         !has_quantized_lm_head) ? 1 : 0))) {
        Py_DECREF(dict);
        return nullptr;
    }
    return dict;
}

PyObject* build_info_dict(int cuda_device_id) {
    PyObject* dict = PyDict_New();
    if (dict == nullptr) {
        return nullptr;
    }

    int runtime_version = 0;
    cudaError_t runtime_status = cudaRuntimeGetVersion(&runtime_version);
    if (runtime_status != cudaSuccess) {
        Py_DECREF(dict);
        PyErr_SetString(PyExc_RuntimeError, cudaGetErrorString(runtime_status));
        return nullptr;
    }

    int device_count = 0;
    cudaError_t count_status = cudaGetDeviceCount(&device_count);
    if (count_status != cudaSuccess) {
        Py_DECREF(dict);
        PyErr_SetString(PyExc_RuntimeError, cudaGetErrorString(count_status));
        return nullptr;
    }

    if (!dict_set_steal(dict, "version", PyUnicode_FromString(kVersion)) ||
        !dict_set_steal(dict, "cuda_runtime_version", PyLong_FromLong(runtime_version)) ||
        !dict_set_steal(dict, "cuda_device_count", PyLong_FromLong(device_count)) ||
        !dict_set_steal(dict, "default_cuda_device_id", PyLong_FromLong(cuda_device_id)) ||
        !dict_set_steal(dict, "phase", PyUnicode_FromString("Phase 28 + R10 primitives")) ||
        !dict_set_steal(dict,
                        "capability",
                        PyUnicode_FromString("real LLAMA GPTQ ExLlama streamed model execution, dense FP16 lm_head streaming, sampling controls, correctness-first Python generate path, and cached decode-attention primitives"))) {
        Py_DECREF(dict);
        return nullptr;
    }

    return dict;
}

int PyInferenceEngine_init(PyInferenceEngine* self, PyObject* args, PyObject* kwargs) {
    static const char* keywords[] = {"cuda_device_id", nullptr};
    int cuda_device_id = 0;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "|i",
                                     const_cast<char**>(keywords),
                                     &cuda_device_id)) {
        return -1;
    }

    int device_count = 0;
    cudaError_t status = cudaGetDeviceCount(&device_count);
    if (status != cudaSuccess) {
        PyErr_SetString(PyExc_RuntimeError, cudaGetErrorString(status));
        return -1;
    }
    if (cuda_device_id < 0 || cuda_device_id >= device_count) {
        PyErr_SetString(PyExc_ValueError, "invalid cuda_device_id");
        return -1;
    }
    status = cudaSetDevice(cuda_device_id);
    if (status != cudaSuccess) {
        PyErr_SetString(PyExc_RuntimeError, cudaGetErrorString(status));
        return -1;
    }

    self->cuda_device_id = cuda_device_id;
    self->loaded_model_info = nullptr;
    return 0;
}

void PyInferenceEngine_dealloc(PyInferenceEngine* self) {
    Py_XDECREF(self->loaded_model_info);
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject*>(self));
}

PyObject* PyInferenceEngine_build_info(PyInferenceEngine* self, PyObject*) {
    return build_info_dict(self->cuda_device_id);
}

PyObject* PyInferenceEngine_cuda_device_count(PyInferenceEngine*, PyObject*) {
    int device_count = 0;
    cudaError_t status = cudaGetDeviceCount(&device_count);
    if (status != cudaSuccess) {
        PyErr_SetString(PyExc_RuntimeError, cudaGetErrorString(status));
        return nullptr;
    }
    return PyLong_FromLong(device_count);
}

PyObject* PyInferenceEngine_hardware_profile(PyInferenceEngine* self, PyObject*) {
    try {
        return hardware_profile_to_dict(spoolstream::core::build_hardware_profile(
            self->cuda_device_id));
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_measure_h2d_bandwidth(PyInferenceEngine* self,
                                                  PyObject* args,
                                                  PyObject* kwargs) {
    static const char* keywords[] = {
        "sample_bytes",
        "iterations",
        "warmup_iterations",
        nullptr,
    };
    unsigned long long sample_bytes = 64ULL * 1024ULL * 1024ULL;
    int iterations = 8;
    int warmup_iterations = 2;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "|Kii",
                                     const_cast<char**>(keywords),
                                     &sample_bytes,
                                     &iterations,
                                     &warmup_iterations)) {
        return nullptr;
    }
    if (sample_bytes < 1024ULL * 1024ULL || sample_bytes > 512ULL * 1024ULL * 1024ULL ||
        iterations <= 0 || iterations > 1000 || warmup_iterations < 0 ||
        warmup_iterations > 100) {
        PyErr_SetString(PyExc_ValueError,
                        "sample_bytes must be 1-512 MiB, iterations 1-1000, and warmup_iterations 0-100");
        return nullptr;
    }

    void* host = nullptr;
    void* device = nullptr;
    cudaStream_t stream = nullptr;
    cudaEvent_t started = nullptr;
    cudaEvent_t finished = nullptr;
    try {
        const size_t bytes = static_cast<size_t>(sample_bytes);
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(self->cuda_device_id));
        SPOOLSTREAM_CUDA_CHECK(
            cudaHostAlloc(&host, bytes, cudaHostAllocPortable | cudaHostAllocMapped));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(&device, bytes));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
        SPOOLSTREAM_CUDA_CHECK(cudaEventCreateWithFlags(&started, cudaEventDefault));
        SPOOLSTREAM_CUDA_CHECK(cudaEventCreateWithFlags(&finished, cudaEventDefault));

        std::fill_n(static_cast<unsigned char*>(host), bytes, static_cast<unsigned char>(0x5a));
        for (int index = 0; index < warmup_iterations; ++index) {
            SPOOLSTREAM_CUDA_CHECK(
                cudaMemcpyAsync(device, host, bytes, cudaMemcpyHostToDevice, stream));
        }
        SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream));

        SPOOLSTREAM_CUDA_CHECK(cudaEventRecord(started, stream));
        for (int index = 0; index < iterations; ++index) {
            SPOOLSTREAM_CUDA_CHECK(
                cudaMemcpyAsync(device, host, bytes, cudaMemcpyHostToDevice, stream));
        }
        SPOOLSTREAM_CUDA_CHECK(cudaEventRecord(finished, stream));
        SPOOLSTREAM_CUDA_CHECK(cudaEventSynchronize(finished));
        float elapsed_ms = 0.0F;
        SPOOLSTREAM_CUDA_CHECK(cudaEventElapsedTime(&elapsed_ms, started, finished));
        if (!(elapsed_ms > 0.0F)) {
            throw std::runtime_error("CUDA H2D calibration returned a non-positive duration");
        }

        const double total_bytes = static_cast<double>(bytes) * static_cast<double>(iterations);
        const double elapsed_seconds = static_cast<double>(elapsed_ms) / 1000.0;
        const double gbps = total_bytes / elapsed_seconds / 1.0e9;
        const double gib_per_second = total_bytes / elapsed_seconds /
                                      static_cast<double>(1024ULL * 1024ULL * 1024ULL);

        SPOOLSTREAM_CUDA_CHECK(cudaEventDestroy(finished));
        finished = nullptr;
        SPOOLSTREAM_CUDA_CHECK(cudaEventDestroy(started));
        started = nullptr;
        SPOOLSTREAM_CUDA_CHECK(cudaStreamDestroy(stream));
        stream = nullptr;
        SPOOLSTREAM_CUDA_CHECK(cudaFree(device));
        device = nullptr;
        SPOOLSTREAM_CUDA_CHECK(cudaFreeHost(host));
        host = nullptr;

        return Py_BuildValue("{s:s,s:K,s:i,s:i,s:d,s:d,s:d}",
                             "measurement",
                             "measured_pinned_cuda_events",
                             "sample_bytes",
                             sample_bytes,
                             "iterations",
                             iterations,
                             "warmup_iterations",
                             warmup_iterations,
                             "elapsed_ms",
                             static_cast<double>(elapsed_ms),
                             "bandwidth_gb_s",
                             gbps,
                             "bandwidth_gib_s",
                             gib_per_second);
    } catch (...) {
        if (finished != nullptr) {
            cudaEventDestroy(finished);
        }
        if (started != nullptr) {
            cudaEventDestroy(started);
        }
        if (stream != nullptr) {
            cudaStreamDestroy(stream);
        }
        if (device != nullptr) {
            cudaFree(device);
        }
        if (host != nullptr) {
            cudaFreeHost(host);
        }
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_parse_model_topology(PyInferenceEngine*, PyObject* args, PyObject* kwargs) {
    static const char* keywords[] = {
        "checkpoint_directory",
        "memory_strategy",
        "strict_scratchpad_bytes",
        nullptr,
    };

    const char* checkpoint_directory = nullptr;
    const char* memory_strategy = "ADAPTIVE";
    unsigned long long strict_scratchpad_bytes =
        static_cast<unsigned long long>(spoolstream::core::kDefaultStrictScratchpadBytes);

    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "s|sK",
                                     const_cast<char**>(keywords),
                                     &checkpoint_directory,
                                     &memory_strategy,
                                     &strict_scratchpad_bytes)) {
        return nullptr;
    }

    try {
        const ModelTopology topology = spoolstream::core::parse_model_topology(
            std::filesystem::path(checkpoint_directory),
            memory_strategy,
            static_cast<size_t>(strict_scratchpad_bytes));
        return topology_to_dict(topology);
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_inspect_model(PyInferenceEngine* self, PyObject* args, PyObject* kwargs) {
    static const char* keywords[] = {
        "model_path",
        "quant_format",
        "max_vram_bytes",
        "max_host_staging_bytes",
        "max_host_resident_bytes",
        "kv_cache_bytes",
        nullptr,
    };
    const char* model_path = nullptr;
    const char* quant_format = "awq_int4";
    unsigned long long max_vram_bytes = 8ULL * 1024ULL * 1024ULL * 1024ULL;
    unsigned long long max_host_staging_bytes = 512ULL * 1024ULL * 1024ULL;
    unsigned long long max_host_resident_bytes = 2ULL * 1024ULL * 1024ULL * 1024ULL;
    unsigned long long kv_cache_bytes = 512ULL * 1024ULL * 1024ULL;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "s|sKKKK",
                                     const_cast<char**>(keywords),
                                     &model_path,
                                     &quant_format,
                                     &max_vram_bytes,
                                     &max_host_staging_bytes,
                                     &max_host_resident_bytes,
                                     &kv_cache_bytes)) {
        return nullptr;
    }

    try {
        const auto manifest = spoolstream::core::build_model_manifest(
            std::filesystem::path(model_path),
            "STRICT",
            static_cast<size_t>(max_vram_bytes));
        spoolstream::core::MemoryBudget budget{};
        budget.max_vram_bytes = static_cast<size_t>(max_vram_bytes);
        budget.max_host_staging_bytes = static_cast<size_t>(max_host_staging_bytes);
        budget.max_host_resident_bytes = static_cast<size_t>(max_host_resident_bytes);
        budget.kv_cache_bytes = static_cast<size_t>(kv_cache_bytes);
        const auto profile = spoolstream::core::plan_model_profile(manifest, budget);
        const int cuda_device_id = self == nullptr ? 0 : self->cuda_device_id;
        const auto hardware = spoolstream::core::build_hardware_profile(cuda_device_id);
        const auto policy = spoolstream::core::plan_execution_policy(manifest,
                                                                     hardware,
                                                                     budget);
        const auto quant_report = spoolstream::core::build_quantized_adapter_report(manifest);
        const auto layer_plans = spoolstream::core::build_layer_execution_plans(
            manifest,
            profile.required_scratchpad_bytes / 2U,
            256);

        PyObject* dict = PyDict_New();
        if (dict == nullptr) {
            return nullptr;
        }
        if (!dict_set_steal(dict, "model_path", PyUnicode_FromString(model_path)) ||
            !dict_set_steal(dict, "requested_quant_format", PyUnicode_FromString(quant_format)) ||
            !dict_set_steal(dict, "max_vram_bytes", py_size(static_cast<size_t>(max_vram_bytes))) ||
            !dict_set_steal(dict,
                            "max_host_staging_bytes",
                            py_size(static_cast<size_t>(max_host_staging_bytes))) ||
            !dict_set_steal(dict,
                            "max_host_resident_bytes",
                            py_size(static_cast<size_t>(max_host_resident_bytes))) ||
            !dict_set_steal(dict, "kv_cache_bytes", py_size(static_cast<size_t>(kv_cache_bytes))) ||
            !dict_set_steal(dict, "config", config_to_dict(manifest.config)) ||
            !dict_set_steal(dict, "topology", topology_to_dict(manifest.topology)) ||
            !dict_set_steal(dict, "profile", profile_to_dict(profile)) ||
            !dict_set_steal(dict, "hardware", hardware_profile_to_dict(hardware)) ||
            !dict_set_steal(dict, "execution_policy", execution_policy_to_dict(policy)) ||
            !dict_set_steal(dict, "quantized_adapter", quant_report_to_dict(quant_report)) ||
            !dict_set_steal(dict,
                            "generation_readiness",
                            generation_readiness_to_dict(std::filesystem::path(model_path),
                                                         manifest,
                                                         quant_report)) ||
            !dict_set_steal(dict, "tensor_count", PyLong_FromSize_t(manifest.tensors.size())) ||
            !dict_set_steal(dict, "role_counts", role_counts_to_dict(manifest)) ||
            !dict_set_steal(dict,
                            "layer_plan_count",
                            PyLong_FromSize_t(layer_plans.layers.size())) ||
            !dict_set_steal(dict,
                            "slot_capacity_bytes",
                            py_size(layer_plans.slot_capacity)) ||
            !dict_set_steal(dict, "max_tensor_bytes", py_size(manifest.max_tensor_bytes))) {
            Py_DECREF(dict);
            return nullptr;
        }
        return dict;
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_load_model(PyInferenceEngine* self, PyObject* args, PyObject* kwargs) {
    PyObject* report = PyInferenceEngine_inspect_model(self, args, kwargs);
    if (report == nullptr) {
        return nullptr;
    }
    if (!PyDict_Check(report)) {
        Py_DECREF(report);
        PyErr_SetString(PyExc_RuntimeError, "load_model expected an inspection dictionary");
        return nullptr;
    }
    int checkpoint_ready = 0;
    PyObject* readiness = PyDict_GetItemString(report, "generation_readiness");
    if (readiness != nullptr && PyDict_Check(readiness)) {
        PyObject* ready_value = PyDict_GetItemString(readiness, "ready");
        checkpoint_ready = ready_value == Py_True ? 1 : 0;
    }
    if (!dict_set_steal(report, "loaded", PyBool_FromLong(1)) ||
        !dict_set_steal(report, "checkpoint_generation_ready", PyBool_FromLong(checkpoint_ready)) ||
        !dict_set_steal(report, "generation_ready", PyBool_FromLong(checkpoint_ready)) ||
        !dict_set_steal(
            report,
            "generation_reason",
            PyUnicode_FromString(
                checkpoint_ready
                    ? "Phase 28 enables correctness-first tokenizer-backed generation using streamed real checkpoint weights."
                    : "Model inspection reported unresolved generation readiness issues."))) {
        Py_DECREF(report);
        return nullptr;
    }
    Py_INCREF(report);
    Py_XDECREF(self->loaded_model_info);
    self->loaded_model_info = report;
    return report;
}

PyObject* PyInferenceEngine_generate(PyInferenceEngine* self, PyObject* args, PyObject* kwargs) {
    static const char* keywords[] = {
        "prompt",
        "max_tokens",
        "temperature",
        "top_p",
        "top_k",
        "repetition_penalty",
        nullptr,
    };
    const char* prompt = nullptr;
    int max_tokens = 16;
    double temperature = 0.0;
    double top_p = 1.0;
    int top_k = 32;
    double repetition_penalty = 1.0;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "s|iddid",
                                     const_cast<char**>(keywords),
                                     &prompt,
                                     &max_tokens,
                                     &temperature,
                                     &top_p,
                                     &top_k,
                                     &repetition_penalty)) {
        return nullptr;
    }
    if (self->loaded_model_info == nullptr) {
        PyErr_SetString(PyExc_RuntimeError, "load_model must be called before generate");
        return nullptr;
    }
    if (max_tokens <= 0) {
        PyErr_SetString(PyExc_ValueError, "max_tokens must be positive");
        return nullptr;
    }
    if (temperature < 0.0 || top_p <= 0.0 || top_p > 1.0) {
        PyErr_SetString(PyExc_ValueError, "invalid sampling parameters");
        return nullptr;
    }
    if (top_k < 0 || repetition_penalty < 1.0) {
        PyErr_SetString(PyExc_ValueError, "invalid top_k or repetition_penalty");
        return nullptr;
    }

    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(self->cuda_device_id));
        constexpr int kPhase28MaxContextTokens = 32;
        constexpr int kLmHeadTileRows = 1024;
        const std::filesystem::path model_path =
            loaded_model_path_from_report(self->loaded_model_info);
        const size_t max_vram_bytes = py_dict_size_or_default(
            self->loaded_model_info,
            "max_vram_bytes",
            8ULL * 1024ULL * 1024ULL * 1024ULL);
        const auto manifest = spoolstream::core::build_model_manifest(model_path,
                                                                      "STRICT",
                                                                      max_vram_bytes);
        const auto quant_report =
            spoolstream::core::build_quantized_adapter_report(manifest);
        const auto readiness = generation_readiness_to_dict(model_path, manifest, quant_report);
        if (readiness == nullptr) {
            return nullptr;
        }
        PyObject* ready_value = PyDict_GetItemString(readiness, "ready");
        const bool ready = ready_value == Py_True;
        Py_DECREF(readiness);
        if (!ready) {
            throw std::runtime_error("loaded model is not generation-ready");
        }

        const auto tokenizer = spoolstream::core::load_tokenizer_json(
            model_path / "tokenizer.json");
        std::vector<int> context_tokens =
            spoolstream::core::encode_tokenizer_text(tokenizer, prompt, true);
        if (context_tokens.empty()) {
            throw std::runtime_error("tokenizer produced no prompt tokens");
        }
        if (static_cast<int>(context_tokens.size()) + max_tokens >
            kPhase28MaxContextTokens) {
            throw std::runtime_error(
                "Phase 28 generate supports prompt + max_tokens <= 32 tokens");
        }

        const auto& embedding_tensor =
            require_manifest_tensor(manifest,
                                    spoolstream::core::TensorRole::TOKEN_EMBEDDING,
                                    "TOKEN_EMBEDDING");
        const auto& final_norm_tensor =
            require_manifest_tensor(manifest,
                                    spoolstream::core::TensorRole::FINAL_NORM,
                                    "FINAL_NORM");
        const auto& lm_head_tensor =
            require_manifest_tensor(manifest,
                                    spoolstream::core::TensorRole::LM_HEAD,
                                    "LM_HEAD");
        const auto plans = spoolstream::core::build_layer_execution_plans(
            manifest,
            manifest.topology.w_max_bytes,
            256);
        const size_t staging_capacity = phase28_staging_capacity(manifest, kLmHeadTileRows);
        auto store = spoolstream::core::create_streaming_tensor_store(model_path,
                                                                      staging_capacity);

        std::vector<int> generated_tokens;
        size_t total_streamed_bytes = 0;
        int total_layers_executed = 0;
        try {
            DeviceBuffer<uint8_t> slot_a(plans.slot_capacity);
            DeviceBuffer<uint8_t> slot_b(plans.slot_capacity);
            DeviceBuffer<half> d_final_norm(static_cast<size_t>(manifest.config.hidden_size));
            const auto final_norm_stage =
                spoolstream::core::stage_tensor_bytes(store, final_norm_tensor);
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_final_norm.get(),
                                             final_norm_stage.host_ptr,
                                             final_norm_stage.byte_size,
                                             cudaMemcpyHostToDevice));

            for (int step = 0; step < max_tokens; ++step) {
                const int token_count = static_cast<int>(context_tokens.size());
                DeviceBuffer<half> d_embeddings(static_cast<size_t>(token_count) *
                                                static_cast<size_t>(manifest.config.hidden_size));
                const auto embedding_result =
                    spoolstream::core::execute_prompt_embedding_lookup_streamed(
                        store,
                        embedding_tensor,
                        context_tokens.data(),
                        token_count,
                        d_embeddings.get(),
                        manifest.config.vocab_size,
                        manifest.config.hidden_size);
                total_streamed_bytes += embedding_result.bytes_streamed;

                DeviceBuffer<half> d_model_output(static_cast<size_t>(token_count) *
                                                  static_cast<size_t>(manifest.config.hidden_size));
                auto workspace = spoolstream::core::create_activation_workspace(
                    token_count,
                    manifest.config.hidden_size,
                    manifest.config.intermediate_size);
                try {
                    spoolstream::core::LlamaDecoderLayerConfig layer_config{};
                    layer_config.tokens = token_count;
                    layer_config.hidden_size = manifest.config.hidden_size;
                    layer_config.intermediate_size = manifest.config.intermediate_size;
                    layer_config.num_attention_heads = manifest.config.num_attention_heads;
                    layer_config.num_key_value_heads = manifest.config.num_key_value_heads;
                    layer_config.head_dim =
                        manifest.config.hidden_size / manifest.config.num_attention_heads;
                    layer_config.position_offset = 0;
                    layer_config.rope_theta = static_cast<float>(manifest.config.rope_theta);
                    layer_config.rms_norm_epsilon =
                        static_cast<float>(manifest.config.rms_norm_eps);

                    const auto prefill =
                        spoolstream::core::execute_streamed_llama_model_prefill(
                            store,
                            manifest,
                            plans,
                            quant_report,
                            slot_a.get(),
                            slot_b.get(),
                            d_embeddings.get(),
                            d_model_output.get(),
                            workspace,
                            layer_config);
                    total_streamed_bytes += prefill.bytes_streamed;
                    total_layers_executed += prefill.layers_executed;

                    spoolstream::core::SamplingConfig sampling{};
                    sampling.temperature = static_cast<float>(temperature);
                    sampling.top_k = top_k;
                    sampling.top_p = static_cast<float>(top_p);
                    sampling.repetition_penalty = static_cast<float>(repetition_penalty);
                    sampling.seed = 0xA51CE5EEDULL + static_cast<uint64_t>(step);
                    const auto sampled =
                        spoolstream::core::execute_dense_lm_head_sample_streamed(
                            store,
                            lm_head_tensor,
                            d_model_output.get(),
                            d_final_norm.get(),
                            workspace,
                            token_count,
                            manifest.config.hidden_size,
                            manifest.config.vocab_size,
                            kLmHeadTileRows,
                            static_cast<float>(manifest.config.rms_norm_eps),
                            context_tokens.data(),
                            token_count,
                            sampling);
                    total_streamed_bytes += sampled.bytes_streamed;
                    generated_tokens.push_back(sampled.token_id);
                    context_tokens.push_back(sampled.token_id);
                    spoolstream::core::destroy_activation_workspace(workspace);

                    if (tokenizer.eos_token_id >= 0 &&
                        sampled.token_id == tokenizer.eos_token_id) {
                        break;
                    }
                } catch (...) {
                    spoolstream::core::destroy_activation_workspace(workspace);
                    throw;
                }
            }
            spoolstream::core::destroy_streaming_tensor_store(store);
        } catch (...) {
            spoolstream::core::destroy_streaming_tensor_store(store);
            throw;
        }

        const std::string generated_text =
            spoolstream::core::decode_tokenizer_tokens(tokenizer,
                                                       generated_tokens,
                                                       true);
        const std::string full_text =
            spoolstream::core::decode_tokenizer_tokens(tokenizer,
                                                       context_tokens,
                                                       true);
        PyObject* token_list = int_vector_to_pylist(generated_tokens);
        PyObject* prompt_token_list = int_vector_to_pylist(
            std::vector<int>(context_tokens.begin(),
                             context_tokens.begin() +
                                 static_cast<std::ptrdiff_t>(
                                     context_tokens.size() - generated_tokens.size())));
        if (token_list == nullptr || prompt_token_list == nullptr) {
            Py_XDECREF(token_list);
            Py_XDECREF(prompt_token_list);
            return nullptr;
        }

        PyObject* dict = PyDict_New();
        if (dict == nullptr) {
            Py_DECREF(token_list);
            Py_DECREF(prompt_token_list);
            return nullptr;
        }
        if (!dict_set_steal(dict, "status", PyUnicode_FromString("ok")) ||
            !dict_set_steal(dict,
                            "mode",
                            PyUnicode_FromString("phase28_correctness_first_repeated_prefill")) ||
            !dict_set_steal(dict, "prompt", PyUnicode_FromString(prompt)) ||
            !dict_set_steal(dict, "text", PyUnicode_FromString(generated_text.c_str())) ||
            !dict_set_steal(dict, "full_text", PyUnicode_FromString(full_text.c_str())) ||
            !dict_set_steal(dict, "tokens", token_list) ||
            !dict_set_steal(dict, "prompt_tokens", prompt_token_list) ||
            !dict_set_steal(dict,
                            "generated_tokens",
                            PyLong_FromSize_t(generated_tokens.size())) ||
            !dict_set_steal(dict, "max_tokens", PyLong_FromLong(max_tokens)) ||
            !dict_set_steal(dict, "temperature", PyFloat_FromDouble(temperature)) ||
            !dict_set_steal(dict, "top_p", PyFloat_FromDouble(top_p)) ||
            !dict_set_steal(dict, "top_k", PyLong_FromLong(top_k)) ||
            !dict_set_steal(dict,
                            "repetition_penalty",
                            PyFloat_FromDouble(repetition_penalty)) ||
            !dict_set_steal(dict,
                            "total_streamed_bytes",
                            py_size(total_streamed_bytes)) ||
            !dict_set_steal(dict,
                            "layers_executed",
                            PyLong_FromLong(total_layers_executed)) ||
            !dict_set_steal(dict,
                            "context_limit_tokens",
                            PyLong_FromLong(kPhase28MaxContextTokens)) ||
            !dict_set_steal(dict,
                            "staging_capacity_bytes",
                            py_size(staging_capacity))) {
            Py_DECREF(dict);
            return nullptr;
        }
        return dict;
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_benchmark_model(PyInferenceEngine* self,
                                            PyObject* args,
                                            PyObject* kwargs) {
    static const char* keywords[] = {
        "model_path",
        "max_tokens",
        "h2d_bandwidth_limit_gbps",
        "max_vram_bytes",
        "max_host_staging_bytes",
        "max_host_resident_bytes",
        "kv_cache_bytes",
        nullptr,
    };
    const char* model_path = nullptr;
    int max_tokens = 16;
    double bandwidth = spoolstream::core::kPcieGen5X16UnidirectionalH2DGBps;
    unsigned long long max_vram_bytes = 8ULL * 1024ULL * 1024ULL * 1024ULL;
    unsigned long long max_host_staging_bytes = 512ULL * 1024ULL * 1024ULL;
    unsigned long long max_host_resident_bytes = 2ULL * 1024ULL * 1024ULL * 1024ULL;
    unsigned long long kv_cache_bytes = 512ULL * 1024ULL * 1024ULL;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "s|idKKKK",
                                     const_cast<char**>(keywords),
                                     &model_path,
                                     &max_tokens,
                                     &bandwidth,
                                     &max_vram_bytes,
                                     &max_host_staging_bytes,
                                     &max_host_resident_bytes,
                                     &kv_cache_bytes)) {
        return nullptr;
    }
    if (max_tokens <= 0) {
        PyErr_SetString(PyExc_ValueError, "max_tokens must be positive");
        return nullptr;
    }

    try {
        const auto manifest = spoolstream::core::build_model_manifest(
            std::filesystem::path(model_path),
            "STRICT",
            static_cast<size_t>(max_vram_bytes));
        spoolstream::core::MemoryBudget budget{};
        budget.max_vram_bytes = static_cast<size_t>(max_vram_bytes);
        budget.max_host_staging_bytes = static_cast<size_t>(max_host_staging_bytes);
        budget.max_host_resident_bytes = static_cast<size_t>(max_host_resident_bytes);
        budget.kv_cache_bytes = static_cast<size_t>(kv_cache_bytes);
        const auto profile = spoolstream::core::plan_model_profile(manifest, budget);
        const auto hardware = spoolstream::core::build_hardware_profile(self->cuda_device_id);
        const auto policy = spoolstream::core::plan_execution_policy(manifest,
                                                                     hardware,
                                                                     budget);
        const auto quant_report = spoolstream::core::build_quantized_adapter_report(manifest);
        const auto plans = spoolstream::core::build_layer_execution_plans(
            manifest,
            profile.required_scratchpad_bytes / 2U,
            256);

        size_t scheduled_layer_bytes = 0;
        for (const auto& layer : plans.layers) {
            scheduled_layer_bytes += layer.total_bytes;
        }
        const uint64_t model_body_transfer_ns =
            spoolstream::core::estimate_h2d_transfer_ns(scheduled_layer_bytes, bandwidth);
        const uint64_t decode_transfer_ns =
            model_body_transfer_ns * static_cast<uint64_t>(max_tokens);

        PyObject* readiness = generation_readiness_to_dict(std::filesystem::path(model_path),
                                                           manifest,
                                                           quant_report);
        if (readiness == nullptr) {
            return nullptr;
        }
        int ready = 0;
        PyObject* ready_value = PyDict_GetItemString(readiness, "ready");
        ready = ready_value == Py_True ? 1 : 0;
        const int first_attempt_ready = ready && profile.supported && policy.supported;

        PyObject* dict = PyDict_New();
        if (dict == nullptr) {
            Py_DECREF(readiness);
            return nullptr;
        }
        if (!dict_set_steal(dict, "dry_run", PyBool_FromLong(1)) ||
            !dict_set_steal(dict,
                            "ready_for_first_attempt",
                            PyBool_FromLong(first_attempt_ready ? 1 : 0)) ||
            !dict_set_steal(dict, "generation_readiness", readiness) ||
            !dict_set_steal(dict, "profile", profile_to_dict(profile)) ||
            !dict_set_steal(dict, "execution_policy", execution_policy_to_dict(policy)) ||
            !dict_set_steal(dict,
                            "scheduled_layer_bytes_per_pass",
                            py_size(scheduled_layer_bytes)) ||
            !dict_set_steal(dict,
                            "estimated_model_body_h2d_ns_per_token",
                            PyLong_FromUnsignedLongLong(
                                static_cast<unsigned long long>(model_body_transfer_ns))) ||
            !dict_set_steal(dict,
                            "estimated_decode_h2d_ns",
                            PyLong_FromUnsignedLongLong(
                                static_cast<unsigned long long>(decode_transfer_ns))) ||
            !dict_set_steal(dict, "max_tokens", PyLong_FromLong(max_tokens)) ||
            !dict_set_steal(dict,
                            "h2d_bandwidth_limit_gbps",
                            PyFloat_FromDouble(bandwidth)) ||
            !dict_set_steal(dict, "layer_plan_count", PyLong_FromSize_t(plans.layers.size())) ||
            !dict_set_steal(dict, "total_streamable_bytes", py_size(manifest.total_streamable_bytes)) ||
            !dict_set_steal(dict, "max_tensor_bytes", py_size(manifest.max_tensor_bytes))) {
            Py_DECREF(dict);
            return nullptr;
        }
        return dict;
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_estimate_h2d_transfer_ns(PyInferenceEngine*,
                                                     PyObject* args,
                                                     PyObject* kwargs) {
    static const char* keywords[] = {"byte_count", "h2d_bandwidth_limit_gbps", nullptr};
    unsigned long long byte_count = 0;
    double bandwidth = spoolstream::core::kPcieGen5X16UnidirectionalH2DGBps;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "K|d",
                                     const_cast<char**>(keywords),
                                     &byte_count,
                                     &bandwidth)) {
        return nullptr;
    }

    try {
        const uint64_t ns = spoolstream::core::estimate_h2d_transfer_ns(
            static_cast<size_t>(byte_count),
            bandwidth);
        return PyLong_FromUnsignedLongLong(static_cast<unsigned long long>(ns));
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_compute_throttle_cycles(PyInferenceEngine* self,
                                                    PyObject* args,
                                                    PyObject* kwargs) {
    static const char* keywords[] = {
        "byte_count",
        "target_exec_ns",
        "h2d_bandwidth_limit_gbps",
        nullptr,
    };
    unsigned long long byte_count = 0;
    unsigned long long target_exec_ns = 0;
    double bandwidth = spoolstream::core::kPcieGen5X16UnidirectionalH2DGBps;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "KK|d",
                                     const_cast<char**>(keywords),
                                     &byte_count,
                                     &target_exec_ns,
                                     &bandwidth)) {
        return nullptr;
    }

    try {
        const uint64_t cycles = spoolstream::core::compute_throttle_cycles(
            static_cast<size_t>(byte_count),
            static_cast<uint64_t>(target_exec_ns),
            bandwidth,
            self->cuda_device_id);
        return PyLong_FromUnsignedLongLong(static_cast<unsigned long long>(cycles));
    } catch (...) {
        return set_python_error_from_exception();
    }
}

PyObject* PyInferenceEngine_conditional_graph_nodes_available(PyInferenceEngine* self, PyObject*) {
    const bool available =
        spoolstream::core::cuda_conditional_graph_nodes_available(self->cuda_device_id);
    if (available) {
        Py_RETURN_TRUE;
    }
    Py_RETURN_FALSE;
}

PyObject* PyInferenceEngine_kv_feedback(PyInferenceEngine*,
                                        PyObject* args,
                                        PyObject* kwargs) {
    static const char* keywords[] = {
        "current_moving_average",
        "current_lookahead_depth",
        "accepted_tokens",
        "proposed_tokens",
        "feedback_alpha",
        "verification_floor",
        nullptr,
    };
    double moving_average = 1.0;
    int current_depth = 1;
    int accepted_tokens = 0;
    int proposed_tokens = 1;
    double feedback_alpha = 0.25;
    double verification_floor = 0.45;
    if (!PyArg_ParseTupleAndKeywords(args,
                                     kwargs,
                                     "diii|dd",
                                     const_cast<char**>(keywords),
                                     &moving_average,
                                     &current_depth,
                                     &accepted_tokens,
                                     &proposed_tokens,
                                     &feedback_alpha,
                                     &verification_floor)) {
        return nullptr;
    }
    if (proposed_tokens <= 0 || accepted_tokens < 0 || accepted_tokens > proposed_tokens ||
        current_depth <= 0 || feedback_alpha <= 0.0 || feedback_alpha > 1.0 ||
        verification_floor < 0.0 || verification_floor > 1.0) {
        PyErr_SetString(PyExc_ValueError, "invalid KV feedback arguments");
        return nullptr;
    }

    const double ratio =
        static_cast<double>(accepted_tokens) / static_cast<double>(proposed_tokens);
    const double next_average = feedback_alpha * ratio + (1.0 - feedback_alpha) * moving_average;
    const int next_depth = next_average < verification_floor ? 1 : current_depth;
    return Py_BuildValue("{s:d,s:i}", "verification_moving_average", next_average,
                         "lookahead_depth", next_depth);
}

PyMethodDef PyInferenceEngine_methods[] = {
    {"build_info",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_build_info),
     METH_NOARGS,
     "Return native SpoolStream build and CUDA runtime information."},
    {"cuda_device_count",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_cuda_device_count),
     METH_NOARGS,
     "Return the number of visible CUDA devices."},
    {"hardware_profile",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_hardware_profile),
     METH_NOARGS,
     "Return the selected CUDA device and host memory execution profile."},
    {"measure_h2d_bandwidth",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_measure_h2d_bandwidth),
     METH_VARARGS | METH_KEYWORDS,
     "Measure pinned host-to-device copy bandwidth with CUDA events."},
    {"parse_model_topology",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_parse_model_topology),
     METH_VARARGS | METH_KEYWORDS,
     "Parse a SafeTensors checkpoint directory into a topology dictionary."},
    {"inspect_model",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_inspect_model),
     METH_VARARGS | METH_KEYWORDS,
     "Build a streaming manifest and memory profile for a local model."},
    {"load_model",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_load_model),
     METH_VARARGS | METH_KEYWORDS,
     "Inspect and store a local model readiness report on this engine."},
    {"generate",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_generate),
     METH_VARARGS | METH_KEYWORDS,
     "Run guarded generation entry point for a previously loaded model."},
    {"benchmark_model",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_benchmark_model),
     METH_VARARGS | METH_KEYWORDS,
     "Return a dry-run model compatibility and H2D transfer benchmark report."},
    {"estimate_h2d_transfer_ns",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_estimate_h2d_transfer_ns),
     METH_VARARGS | METH_KEYWORDS,
     "Estimate unidirectional H2D transfer duration in nanoseconds."},
    {"compute_throttle_cycles",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_compute_throttle_cycles),
     METH_VARARGS | METH_KEYWORDS,
     "Compute CUDA clock64 throttle cycles for a paced H2D copy."},
    {"conditional_graph_nodes_available",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_conditional_graph_nodes_available),
     METH_NOARGS,
     "Return whether CUDA conditional graph nodes are usable on the selected device."},
    {"kv_feedback",
     reinterpret_cast<PyCFunction>(PyInferenceEngine_kv_feedback),
     METH_VARARGS | METH_KEYWORDS,
     "Apply the KV-cache speculative feedback rule without allocating a cache."},
    {nullptr, nullptr, 0, nullptr},
};

PyType_Slot PyInferenceEngine_slots[] = {
    {Py_tp_dealloc, reinterpret_cast<void*>(PyInferenceEngine_dealloc)},
    {Py_tp_init, reinterpret_cast<void*>(PyInferenceEngine_init)},
    {Py_tp_new, reinterpret_cast<void*>(PyType_GenericNew)},
    {Py_tp_methods, reinterpret_cast<void*>(PyInferenceEngine_methods)},
    {0, nullptr},
};

PyType_Spec PyInferenceEngine_spec = {
    "spoolstream._core.InferenceEngine",
    static_cast<int>(sizeof(PyInferenceEngine)),
    0,
    Py_TPFLAGS_DEFAULT,
    PyInferenceEngine_slots,
};

PyObject* module_build_info(PyObject*, PyObject*) {
    return build_info_dict(0);
}

PyObject* module_cuda_device_count(PyObject*, PyObject*) {
    return PyInferenceEngine_cuda_device_count(nullptr, nullptr);
}

PyObject* module_parse_model_topology(PyObject*, PyObject* args, PyObject* kwargs) {
    return PyInferenceEngine_parse_model_topology(nullptr, args, kwargs);
}

PyObject* module_inspect_model(PyObject*, PyObject* args, PyObject* kwargs) {
    return PyInferenceEngine_inspect_model(nullptr, args, kwargs);
}

PyMethodDef module_methods[] = {
    {"build_info", module_build_info, METH_NOARGS, "Return native build information."},
    {"cuda_device_count", module_cuda_device_count, METH_NOARGS, "Return visible CUDA device count."},
    {"parse_model_topology",
     reinterpret_cast<PyCFunction>(module_parse_model_topology),
     METH_VARARGS | METH_KEYWORDS,
     "Parse a SafeTensors checkpoint directory."},
    {"inspect_model",
     reinterpret_cast<PyCFunction>(module_inspect_model),
     METH_VARARGS | METH_KEYWORDS,
     "Build a streaming manifest and memory profile for a local model."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module_def = {
    PyModuleDef_HEAD_INIT,
    "_core",
    "Native SpoolStream CUDA runtime extension.",
    -1,
    module_methods,
    nullptr,
    nullptr,
    nullptr,
    nullptr,
};

} // namespace

PyMODINIT_FUNC PyInit__core() {
    PyObject* module = PyModule_Create(&module_def);
    if (module == nullptr) {
        return nullptr;
    }

    PyObject* engine_type = PyType_FromSpec(&PyInferenceEngine_spec);
    if (engine_type == nullptr) {
        Py_DECREF(module);
        return nullptr;
    }
    if (PyModule_AddObject(module, "InferenceEngine", engine_type) != 0) {
        Py_DECREF(engine_type);
        Py_DECREF(module);
        return nullptr;
    }

    if (PyModule_AddStringConstant(module, "__version__", kVersion) != 0) {
        Py_DECREF(module);
        return nullptr;
    }
    if (PyModule_AddIntConstant(module,
                                "PCIE_GEN5_X16_H2D_GBPS",
                                static_cast<long>(spoolstream::core::kPcieGen5X16UnidirectionalH2DGBps)) != 0) {
        Py_DECREF(module);
        return nullptr;
    }

    return module;
}
