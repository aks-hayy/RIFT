#include "spoolstream/streaming_store.h"

#include "spoolstream/memory_manager.h"

#include <cuda_runtime_api.h>

#include <fstream>
#include <stdexcept>
#include <string>

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream streaming store validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

} // namespace

StreamingTensorStore create_streaming_tensor_store(
    const std::filesystem::path& checkpoint_directory,
    size_t staging_capacity) {
    require_condition(staging_capacity > 0, "staging_capacity must be positive");
    require_condition(std::filesystem::is_directory(checkpoint_directory),
                      "checkpoint_directory is not a directory");

    StreamingTensorStore store{};
    store.checkpoint_directory = checkpoint_directory;
    store.staging_capacity = staging_capacity;
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaHostAlloc(&store.host_staging_ptr,
                                             staging_capacity,
                                             cudaHostAllocPortable | cudaHostAllocMapped));
        SPOOLSTREAM_CUDA_CHECK(cudaHostGetDevicePointer(&store.device_uva_ptr,
                                                        store.host_staging_ptr,
                                                        0));
        return store;
    } catch (...) {
        destroy_streaming_tensor_store(store);
        throw;
    }
}

void destroy_streaming_tensor_store(StreamingTensorStore& store) noexcept {
    if (store.host_staging_ptr != nullptr) {
        cudaFreeHost(store.host_staging_ptr);
        store.host_staging_ptr = nullptr;
    }
    store.device_uva_ptr = nullptr;
    store.staging_capacity = 0;
    store.checkpoint_directory.clear();
}

StagedTensor stage_tensor_bytes(StreamingTensorStore& store,
                                const ManifestTensor& tensor) {
    require_condition(tensor.metadata.end_offset >= tensor.metadata.start_offset,
                      "tensor offsets are inverted");
    const size_t byte_size = tensor.metadata.end_offset - tensor.metadata.start_offset;
    return stage_tensor_slice(store, tensor, 0, byte_size);
}

StagedTensor stage_tensor_slice(StreamingTensorStore& store,
                                const ManifestTensor& tensor,
                                size_t tensor_relative_offset,
                                size_t byte_size) {
    require_condition(store.host_staging_ptr != nullptr, "host staging buffer is null");
    require_condition(tensor.metadata.end_offset >= tensor.metadata.start_offset,
                      "tensor offsets are inverted");
    const size_t tensor_byte_size = tensor.metadata.end_offset - tensor.metadata.start_offset;
    require_condition(tensor_relative_offset <= tensor_byte_size,
                      "tensor slice offset exceeds tensor byte size");
    require_condition(byte_size <= tensor_byte_size - tensor_relative_offset,
                      "tensor slice exceeds tensor byte range");
    require_condition(byte_size > 0, "tensor byte size must be positive");
    require_condition(byte_size <= store.staging_capacity,
                      "tensor exceeds pinned staging capacity");

    const std::filesystem::path shard_path =
        store.checkpoint_directory / tensor.metadata.shard_file;
    std::ifstream in(shard_path, std::ios::binary);
    require_condition(static_cast<bool>(in), "unable to open shard: " + shard_path.string());
    in.seekg(0, std::ios::end);
    const std::streamoff file_size = in.tellg();
    require_condition(file_size >= 0, "unable to query shard size");
    const size_t absolute_start = tensor.metadata.start_offset + tensor_relative_offset;
    const size_t absolute_end = absolute_start + byte_size;
    require_condition(static_cast<size_t>(file_size) >= absolute_end,
                      "tensor byte range exceeds shard size");
    in.seekg(static_cast<std::streamoff>(absolute_start), std::ios::beg);
    in.read(static_cast<char*>(store.host_staging_ptr),
            static_cast<std::streamsize>(byte_size));
    require_condition(in.gcount() == static_cast<std::streamsize>(byte_size),
                      "short read while staging tensor");

    StagedTensor staged{};
    staged.tensor = &tensor;
    staged.host_ptr = store.host_staging_ptr;
    staged.device_uva_ptr = store.device_uva_ptr;
    staged.byte_size = byte_size;
    return staged;
}

void copy_staged_tensor_to_device(const StreamingTensorStore& store,
                                  void* device_dst,
                                  const StagedTensor& staged,
                                  cudaStream_t stream) {
    require_condition(store.host_staging_ptr != nullptr, "host staging buffer is null");
    require_condition(device_dst != nullptr, "device_dst is null");
    require_condition(staged.host_ptr == store.host_staging_ptr,
                      "staged tensor does not belong to this store");
    require_condition(staged.byte_size > 0, "staged byte_size must be positive");
    require_condition(staged.byte_size <= store.staging_capacity,
                      "staged byte_size exceeds staging capacity");
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(device_dst,
                                           staged.host_ptr,
                                           staged.byte_size,
                                           cudaMemcpyHostToDevice,
                                           stream));
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

} // namespace spoolstream::core
