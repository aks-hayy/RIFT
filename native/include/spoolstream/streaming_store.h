#pragma once

#include "spoolstream/model.h"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <vector>

#include <cuda_runtime_api.h>

namespace spoolstream::core {

struct StagedTensor {
    const ManifestTensor* tensor;
    void* host_ptr;
    void* device_uva_ptr;
    size_t byte_size;
};

struct StreamingTensorStore {
    std::filesystem::path checkpoint_directory;
    size_t staging_capacity;
    void* host_staging_ptr;
    void* device_uva_ptr;
};

StreamingTensorStore create_streaming_tensor_store(
    const std::filesystem::path& checkpoint_directory,
    size_t staging_capacity);

void destroy_streaming_tensor_store(StreamingTensorStore& store) noexcept;

StagedTensor stage_tensor_bytes(StreamingTensorStore& store,
                                const ManifestTensor& tensor);

StagedTensor stage_tensor_slice(StreamingTensorStore& store,
                                const ManifestTensor& tensor,
                                size_t tensor_relative_offset,
                                size_t byte_size);

void copy_staged_tensor_to_device(const StreamingTensorStore& store,
                                  void* device_dst,
                                  const StagedTensor& staged,
                                  cudaStream_t stream = nullptr);

} // namespace spoolstream::core
