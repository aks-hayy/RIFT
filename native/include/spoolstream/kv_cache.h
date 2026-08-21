#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

namespace spoolstream::core {

constexpr int kMaxConstantLayerPageTables = 128;
constexpr int kMaxPagesPerConstantLayer = 8;

struct PageDescriptor {
    int layer_id;
    int logical_page_id;
    int physical_page_id;
    size_t byte_offset;
    size_t byte_size;
};

struct PageDescriptorTable {
    int layer_id;
    int page_count;
    PageDescriptor pages[kMaxPagesPerConstantLayer];
};

struct KVCacheConfig {
    size_t page_size_bytes;
    int max_pages;
    int max_sequences;
    int max_pages_per_sequence;
    float eviction_threshold;
    float feedback_alpha;
    float verification_floor;
    int initial_lookahead_depth;
    int cuda_device_id;
};

struct KVCacheRuntime {
    void* device_window;
    void* host_eviction_buffer;
    size_t window_bytes;
    size_t page_size_bytes;
    int max_pages;
    int max_sequences;
    int max_pages_per_sequence;
    int active_pages;
    int lookahead_depth;
    float verification_moving_average;
    float eviction_threshold;
    float feedback_alpha;
    float verification_floor;
    cudaStream_t stream_kv;
    int* device_page_residency;
    int* device_sequence_page_table;
    uint64_t* device_page_last_access;
    uint32_t* device_eviction_marker;
};

KVCacheRuntime create_paged_kv_cache(const KVCacheConfig& config);

void destroy_paged_kv_cache(KVCacheRuntime& runtime) noexcept;

void upload_layer_page_tables_to_constant(const PageDescriptorTable* host_tables,
                                          int table_count,
                                          cudaStream_t stream = nullptr);

PageDescriptorTable fetch_layer_page_table_from_constant(int table_index);

void map_sequence_page(KVCacheRuntime& runtime,
                       int sequence_id,
                       int sequence_page_index,
                       int physical_page_id,
                       cudaStream_t stream = nullptr);

void mark_kv_page_access(const KVCacheRuntime& runtime,
                         int physical_page_id,
                         uint64_t step,
                         cudaStream_t stream = nullptr);

bool kv_cache_should_evict(const KVCacheRuntime& runtime);

void schedule_kv_eviction(KVCacheRuntime& runtime,
                          int physical_page_id,
                          size_t byte_count,
                          cudaEvent_t quiet_window_event = nullptr);

void record_decode_token_in_kv_cache(KVCacheRuntime& runtime,
                                     int sequence_id,
                                     int token_index,
                                     int token_id,
                                     cudaStream_t stream = nullptr);

int update_kv_cache_feedback(KVCacheRuntime& runtime,
                             int accepted_tokens,
                             int proposed_tokens);

} // namespace spoolstream::core
