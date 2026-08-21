#pragma once

#include "spoolstream/parser.h"

#include <cstddef>
#include <filesystem>
#include <string>
#include <vector>

#include <cuda_runtime_api.h>

namespace spoolstream::core {

struct RuntimeTensor {
    std::string name;
    void* host_ptr;
    void* device_uva_ptr;
    size_t byte_size;
};

struct RuntimeLayer {
    int layer_id;
    size_t byte_size;
    std::vector<RuntimeTensor> tensors;
};

struct ExecutionWorkspace {
    void* slot_A;
    void* slot_B;
    size_t slot_capacity;
    std::vector<RuntimeLayer> runtime_layers;
};

namespace detail {

void cuda_check(cudaError_t status,
                const char* expression,
                const char* file,
                int line);

} // namespace detail

#define SPOOLSTREAM_CUDA_CHECK(expr) \
    ::spoolstream::core::detail::cuda_check((expr), #expr, __FILE__, __LINE__)

ExecutionWorkspace provision_execution_workspace(
    const std::filesystem::path& checkpoint_dir,
    const ModelTopology& topology,
    int cuda_device_id = 0);

void destroy_execution_workspace(ExecutionWorkspace& workspace) noexcept;

} // namespace spoolstream::core
