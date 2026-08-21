#include "spoolstream/kv_cache.h"

#include "spoolstream/memory_manager.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstring>
#include <sstream>
#include <stdexcept>
#include <string>

namespace spoolstream::core {
namespace {

__constant__ PageDescriptorTable c_layer_page_tables[kMaxConstantLayerPageTables];

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream KV cache validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

void validate_device(int cuda_device_id) {
    int device_count = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    require_condition(device_count > 0, "no CUDA-capable devices are visible");
    require_condition(cuda_device_id >= 0 && cuda_device_id < device_count,
                      "invalid CUDA device id " + std::to_string(cuda_device_id));
    SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(cuda_device_id));
}

void validate_config(const KVCacheConfig& config) {
    require_condition(config.page_size_bytes > 0, "page_size_bytes must be positive");
    require_condition(config.max_pages > 0, "max_pages must be positive");
    require_condition(config.max_sequences > 0, "max_sequences must be positive");
    require_condition(config.max_pages_per_sequence > 0,
                      "max_pages_per_sequence must be positive");
    require_condition(std::isfinite(config.eviction_threshold) &&
                          config.eviction_threshold > 0.0F &&
                          config.eviction_threshold <= 1.0F,
                      "eviction_threshold must be in (0, 1]");
    require_condition(std::isfinite(config.feedback_alpha) &&
                          config.feedback_alpha > 0.0F &&
                          config.feedback_alpha <= 1.0F,
                      "feedback_alpha must be in (0, 1]");
    require_condition(std::isfinite(config.verification_floor) &&
                          config.verification_floor >= 0.0F &&
                          config.verification_floor <= 1.0F,
                      "verification_floor must be in [0, 1]");
    require_condition(config.initial_lookahead_depth > 0,
                      "initial_lookahead_depth must be positive");

    const size_t max_pages = static_cast<size_t>(config.max_pages);
    require_condition(config.page_size_bytes <=
                          static_cast<size_t>(-1) / std::max<size_t>(1, max_pages),
                      "KV cache window size overflows size_t");
}

void validate_runtime(const KVCacheRuntime& runtime) {
    require_condition(runtime.device_window != nullptr, "device_window is null");
    require_condition(runtime.host_eviction_buffer != nullptr, "host_eviction_buffer is null");
    require_condition(runtime.stream_kv != nullptr, "stream_kv is null");
    require_condition(runtime.device_page_residency != nullptr, "device_page_residency is null");
    require_condition(runtime.device_sequence_page_table != nullptr,
                      "device_sequence_page_table is null");
    require_condition(runtime.device_page_last_access != nullptr,
                      "device_page_last_access is null");
    require_condition(runtime.device_eviction_marker != nullptr,
                      "device_eviction_marker is null");
    require_condition(runtime.page_size_bytes > 0, "page_size_bytes must be positive");
    require_condition(runtime.max_pages > 0, "max_pages must be positive");
}

void validate_page_id(const KVCacheRuntime& runtime, int physical_page_id) {
    require_condition(physical_page_id >= 0 && physical_page_id < runtime.max_pages,
                      "physical_page_id is out of range");
}

void validate_table(const PageDescriptorTable& table) {
    require_condition(table.page_count >= 0 &&
                          table.page_count <= kMaxPagesPerConstantLayer,
                      "constant page table page_count is out of range");
    for (int page = 0; page < table.page_count; ++page) {
        const PageDescriptor& descriptor = table.pages[page];
        require_condition(descriptor.byte_size > 0, "page descriptor byte_size must be positive");
        require_condition(descriptor.layer_id == table.layer_id,
                          "page descriptor layer_id must match table layer_id");
        require_condition(descriptor.logical_page_id >= 0,
                          "logical_page_id must be non-negative");
        require_condition(descriptor.physical_page_id >= 0,
                          "physical_page_id must be non-negative");
    }
}

__global__ void initialize_kv_tracking_kernel(int* page_residency,
                                              int* sequence_page_table,
                                              uint64_t* page_last_access,
                                              uint32_t* eviction_marker,
                                              int max_pages,
                                              int sequence_entries) {
    const int linear = blockIdx.x * blockDim.x + threadIdx.x;
    if (linear < max_pages) {
        page_residency[linear] = 0;
        page_last_access[linear] = 0;
    }
    if (linear < sequence_entries) {
        sequence_page_table[linear] = -1;
    }
    if (linear == 0) {
        *eviction_marker = 0U;
    }
}

__global__ void map_sequence_page_kernel(int* page_residency,
                                         int* sequence_page_table,
                                         int sequence_entries,
                                         int sequence_entry,
                                         int physical_page_id) {
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        if (sequence_entry >= 0 && sequence_entry < sequence_entries) {
            sequence_page_table[sequence_entry] = physical_page_id;
            page_residency[physical_page_id] = 1;
        }
    }
}

__global__ void mark_access_kernel(uint64_t* page_last_access,
                                   int physical_page_id,
                                   uint64_t step) {
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        page_last_access[physical_page_id] = step;
    }
}

__global__ void mark_evicted_kernel(int* page_residency,
                                    uint32_t* eviction_marker,
                                    int physical_page_id) {
    if (threadIdx.x == 0 && blockIdx.x == 0) {
        page_residency[physical_page_id] = 0;
        atomicAdd(eviction_marker, 1U);
    }
}

} // namespace

KVCacheRuntime create_paged_kv_cache(const KVCacheConfig& config) {
    validate_config(config);
    validate_device(config.cuda_device_id);

    KVCacheRuntime runtime{};
    runtime.window_bytes =
        config.page_size_bytes * static_cast<size_t>(config.max_pages);
    runtime.page_size_bytes = config.page_size_bytes;
    runtime.max_pages = config.max_pages;
    runtime.max_sequences = config.max_sequences;
    runtime.max_pages_per_sequence = config.max_pages_per_sequence;
    runtime.active_pages = 0;
    runtime.lookahead_depth = config.initial_lookahead_depth;
    runtime.verification_moving_average = 1.0F;
    runtime.eviction_threshold = config.eviction_threshold;
    runtime.feedback_alpha = config.feedback_alpha;
    runtime.verification_floor = config.verification_floor;

    try {
        size_t free_bytes = 0;
        size_t total_bytes = 0;
        SPOOLSTREAM_CUDA_CHECK(cudaMemGetInfo(&free_bytes, &total_bytes));
        require_condition(free_bytes >= runtime.window_bytes,
                          "free VRAM cannot cover the requested KV cache window");

        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(&runtime.device_window, runtime.window_bytes));
        SPOOLSTREAM_CUDA_CHECK(cudaHostAlloc(&runtime.host_eviction_buffer,
                                             runtime.window_bytes,
                                             cudaHostAllocPortable));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamCreateWithFlags(&runtime.stream_kv,
                                                         cudaStreamNonBlocking));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&runtime.device_page_residency),
                                          sizeof(int) * static_cast<size_t>(runtime.max_pages)));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(
            reinterpret_cast<void**>(&runtime.device_sequence_page_table),
            sizeof(int) * static_cast<size_t>(runtime.max_sequences) *
                static_cast<size_t>(runtime.max_pages_per_sequence)));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(
            reinterpret_cast<void**>(&runtime.device_page_last_access),
            sizeof(uint64_t) * static_cast<size_t>(runtime.max_pages)));
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&runtime.device_eviction_marker),
                                          sizeof(uint32_t)));

        const int sequence_entries = runtime.max_sequences * runtime.max_pages_per_sequence;
        const int threads = 256;
        const int blocks =
            (std::max(runtime.max_pages, sequence_entries) + threads - 1) / threads;
        initialize_kv_tracking_kernel<<<blocks, threads>>>(runtime.device_page_residency,
                                                           runtime.device_sequence_page_table,
                                                           runtime.device_page_last_access,
                                                           runtime.device_eviction_marker,
                                                           runtime.max_pages,
                                                           sequence_entries);
        SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
        return runtime;
    } catch (...) {
        destroy_paged_kv_cache(runtime);
        throw;
    }
}

void destroy_paged_kv_cache(KVCacheRuntime& runtime) noexcept {
    if (runtime.stream_kv != nullptr) {
        cudaStreamSynchronize(runtime.stream_kv);
    }
    if (runtime.device_eviction_marker != nullptr) {
        cudaFree(runtime.device_eviction_marker);
        runtime.device_eviction_marker = nullptr;
    }
    if (runtime.device_page_last_access != nullptr) {
        cudaFree(runtime.device_page_last_access);
        runtime.device_page_last_access = nullptr;
    }
    if (runtime.device_sequence_page_table != nullptr) {
        cudaFree(runtime.device_sequence_page_table);
        runtime.device_sequence_page_table = nullptr;
    }
    if (runtime.device_page_residency != nullptr) {
        cudaFree(runtime.device_page_residency);
        runtime.device_page_residency = nullptr;
    }
    if (runtime.host_eviction_buffer != nullptr) {
        cudaFreeHost(runtime.host_eviction_buffer);
        runtime.host_eviction_buffer = nullptr;
    }
    if (runtime.device_window != nullptr) {
        cudaFree(runtime.device_window);
        runtime.device_window = nullptr;
    }
    if (runtime.stream_kv != nullptr) {
        cudaStreamDestroy(runtime.stream_kv);
        runtime.stream_kv = nullptr;
    }
    runtime.window_bytes = 0;
    runtime.page_size_bytes = 0;
    runtime.max_pages = 0;
    runtime.max_sequences = 0;
    runtime.max_pages_per_sequence = 0;
    runtime.active_pages = 0;
    runtime.lookahead_depth = 0;
    runtime.verification_moving_average = 0.0F;
    runtime.eviction_threshold = 0.0F;
    runtime.feedback_alpha = 0.0F;
    runtime.verification_floor = 0.0F;
}

void upload_layer_page_tables_to_constant(const PageDescriptorTable* host_tables,
                                          int table_count,
                                          cudaStream_t stream) {
    require_condition(host_tables != nullptr, "host_tables is null");
    require_condition(table_count > 0, "table_count must be positive");
    require_condition(table_count <= kMaxConstantLayerPageTables,
                      "table_count exceeds constant descriptor capacity");
    for (int table = 0; table < table_count; ++table) {
        validate_table(host_tables[table]);
    }

    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyToSymbolAsync(c_layer_page_tables,
                                                   host_tables,
                                                   sizeof(PageDescriptorTable) *
                                                       static_cast<size_t>(table_count),
                                                   0,
                                                   cudaMemcpyHostToDevice,
                                                   stream));
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

PageDescriptorTable fetch_layer_page_table_from_constant(int table_index) {
    require_condition(table_index >= 0 && table_index < kMaxConstantLayerPageTables,
                      "table_index is out of range");
    PageDescriptorTable table{};
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyFromSymbol(&table,
                                                c_layer_page_tables,
                                                sizeof(PageDescriptorTable),
                                                sizeof(PageDescriptorTable) *
                                                    static_cast<size_t>(table_index),
                                                cudaMemcpyDeviceToHost));
    return table;
}

void map_sequence_page(KVCacheRuntime& runtime,
                       int sequence_id,
                       int sequence_page_index,
                       int physical_page_id,
                       cudaStream_t stream) {
    validate_runtime(runtime);
    validate_page_id(runtime, physical_page_id);
    require_condition(sequence_id >= 0 && sequence_id < runtime.max_sequences,
                      "sequence_id is out of range");
    require_condition(sequence_page_index >= 0 &&
                          sequence_page_index < runtime.max_pages_per_sequence,
                      "sequence_page_index is out of range");

    int residency = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(&residency,
                                      runtime.device_page_residency + physical_page_id,
                                      sizeof(int),
                                      cudaMemcpyDeviceToHost));
    if (residency == 0) {
        require_condition(runtime.active_pages < runtime.max_pages,
                          "all KV cache physical pages are active");
        ++runtime.active_pages;
    }

    const int sequence_entries = runtime.max_sequences * runtime.max_pages_per_sequence;
    const int sequence_entry =
        sequence_id * runtime.max_pages_per_sequence + sequence_page_index;
    map_sequence_page_kernel<<<1, 1, 0, stream>>>(runtime.device_page_residency,
                                                  runtime.device_sequence_page_table,
                                                  sequence_entries,
                                                  sequence_entry,
                                                  physical_page_id);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

void mark_kv_page_access(const KVCacheRuntime& runtime,
                         int physical_page_id,
                         uint64_t step,
                         cudaStream_t stream) {
    validate_runtime(runtime);
    validate_page_id(runtime, physical_page_id);
    mark_access_kernel<<<1, 1, 0, stream>>>(runtime.device_page_last_access,
                                            physical_page_id,
                                            step);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

bool kv_cache_should_evict(const KVCacheRuntime& runtime) {
    validate_runtime(runtime);
    const float utilization =
        static_cast<float>(runtime.active_pages) / static_cast<float>(runtime.max_pages);
    return utilization >= 0.0F && utilization >= runtime.eviction_threshold;
}

void schedule_kv_eviction(KVCacheRuntime& runtime,
                          int physical_page_id,
                          size_t byte_count,
                          cudaEvent_t quiet_window_event) {
    validate_runtime(runtime);
    validate_page_id(runtime, physical_page_id);
    require_condition(byte_count > 0, "byte_count must be positive");
    require_condition(byte_count <= runtime.page_size_bytes,
                      "byte_count cannot exceed one KV cache page");

    if (quiet_window_event != nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaStreamWaitEvent(runtime.stream_kv, quiet_window_event, 0));
    }

    const size_t offset =
        static_cast<size_t>(physical_page_id) * runtime.page_size_bytes;
    auto* device_src = static_cast<unsigned char*>(runtime.device_window) + offset;
    auto* host_dst = static_cast<unsigned char*>(runtime.host_eviction_buffer) + offset;
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(host_dst,
                                           device_src,
                                           byte_count,
                                           cudaMemcpyDeviceToHost,
                                           runtime.stream_kv));
    mark_evicted_kernel<<<1, 1, 0, runtime.stream_kv>>>(runtime.device_page_residency,
                                                        runtime.device_eviction_marker,
                                                        physical_page_id);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    if (runtime.active_pages > 0) {
        --runtime.active_pages;
    }
}

void record_decode_token_in_kv_cache(KVCacheRuntime& runtime,
                                     int sequence_id,
                                     int token_index,
                                     int token_id,
                                     cudaStream_t stream) {
    validate_runtime(runtime);
    require_condition(sequence_id >= 0 && sequence_id < runtime.max_sequences,
                      "sequence_id is out of range");
    require_condition(token_index >= 0, "token_index must be non-negative");
    require_condition(token_id >= 0, "token_id must be non-negative");
    const size_t records_per_page =
        std::max<size_t>(1, runtime.page_size_bytes / sizeof(int));
    const int sequence_page_index =
        static_cast<int>(static_cast<size_t>(token_index) / records_per_page);
    require_condition(sequence_page_index < runtime.max_pages_per_sequence,
                      "token_index exceeds sequence page table capacity");
    require_condition(sequence_page_index < runtime.max_pages,
                      "token_index exceeds physical page capacity");
    const int physical_page_id = sequence_page_index;
    const size_t in_page_index = static_cast<size_t>(token_index) % records_per_page;
    const size_t byte_offset = static_cast<size_t>(physical_page_id) *
                                   runtime.page_size_bytes +
                               in_page_index * sizeof(int);
    require_condition(byte_offset + sizeof(int) <= runtime.window_bytes,
                      "decode token record exceeds KV cache window");

    map_sequence_page(runtime, sequence_id, sequence_page_index, physical_page_id, stream);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(static_cast<unsigned char*>(runtime.device_window) +
                                               byte_offset,
                                           &token_id,
                                           sizeof(int),
                                           cudaMemcpyHostToDevice,
                                           stream));
    mark_kv_page_access(runtime,
                        physical_page_id,
                        static_cast<uint64_t>(token_index + 1),
                        stream);
    if (stream == nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());
    }
}

int update_kv_cache_feedback(KVCacheRuntime& runtime,
                             int accepted_tokens,
                             int proposed_tokens) {
    validate_runtime(runtime);
    require_condition(accepted_tokens >= 0, "accepted_tokens must be non-negative");
    require_condition(proposed_tokens > 0, "proposed_tokens must be positive");
    require_condition(accepted_tokens <= proposed_tokens,
                      "accepted_tokens cannot exceed proposed_tokens");

    const float ratio =
        static_cast<float>(accepted_tokens) / static_cast<float>(proposed_tokens);
    const float alpha = runtime.feedback_alpha;
    runtime.verification_moving_average =
        alpha * ratio + (1.0F - alpha) * runtime.verification_moving_average;

    if (runtime.verification_moving_average < runtime.verification_floor) {
        runtime.lookahead_depth = 1;
    }
    return runtime.lookahead_depth;
}

} // namespace spoolstream::core
