#include "spoolstream/kv_cache.h"
#include "spoolstream/memory_manager.h"

#include <cuda_runtime_api.h>

#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_), sizeof(T) * count_));
        }
    }

    DeviceBuffer(const DeviceBuffer&) = delete;
    DeviceBuffer& operator=(const DeviceBuffer&) = delete;

    ~DeviceBuffer() {
        if (ptr_ != nullptr) {
            cudaFree(ptr_);
        }
    }

    T* get() {
        return ptr_;
    }

    void copy_from_host(const std::vector<T>& host) {
        if (!host.empty()) {
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(ptr_,
                                             host.data(),
                                             sizeof(T) * host.size(),
                                             cudaMemcpyHostToDevice));
        }
    }

private:
    T* ptr_ = nullptr;
    size_t count_ = 0;
};

void require_true(bool condition, const std::string& message) {
    if (!condition) {
        throw std::runtime_error(message);
    }
}

template <typename Fn>
void require_throw(Fn&& fn, const std::string& message) {
    try {
        fn();
    } catch (const std::runtime_error&) {
        return;
    }
    throw std::runtime_error("expected runtime_error: " + message);
}

spoolstream::core::KVCacheConfig make_config() {
    spoolstream::core::KVCacheConfig config{};
    config.page_size_bytes = 256;
    config.max_pages = 4;
    config.max_sequences = 2;
    config.max_pages_per_sequence = 4;
    config.eviction_threshold = 0.75F;
    config.feedback_alpha = 1.0F;
    config.verification_floor = 0.45F;
    config.initial_lookahead_depth = 4;
    config.cuda_device_id = 0;
    return config;
}

std::vector<uint8_t> make_pattern(size_t byte_count) {
    std::vector<uint8_t> pattern(byte_count);
    for (size_t i = 0; i < byte_count; ++i) {
        pattern[i] = static_cast<uint8_t>((i * 31U + 17U) & 0xFFU);
    }
    return pattern;
}

std::vector<int> copy_ints(const int* device_ptr, size_t count) {
    std::vector<int> host(count);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                     device_ptr,
                                     sizeof(int) * count,
                                     cudaMemcpyDeviceToHost));
    return host;
}

std::vector<uint64_t> copy_u64(const uint64_t* device_ptr, size_t count) {
    std::vector<uint64_t> host(count);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                     device_ptr,
                                     sizeof(uint64_t) * count,
                                     cudaMemcpyDeviceToHost));
    return host;
}

std::vector<uint32_t> copy_u32(const uint32_t* device_ptr, size_t count) {
    std::vector<uint32_t> host(count);
    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                     device_ptr,
                                     sizeof(uint32_t) * count,
                                     cudaMemcpyDeviceToHost));
    return host;
}

void test_create_map_access_and_destroy() {
    auto runtime = spoolstream::core::create_paged_kv_cache(make_config());
    require_true(runtime.device_window != nullptr, "device_window is null");
    require_true(runtime.host_eviction_buffer != nullptr, "host_eviction_buffer is null");
    require_true(runtime.stream_kv != nullptr, "stream_kv is null");
    require_true(runtime.window_bytes == 1024, "window byte size mismatch");
    require_true(runtime.active_pages == 0, "initial active page count mismatch");
    require_true(runtime.lookahead_depth == 4, "initial lookahead depth mismatch");

    spoolstream::core::map_sequence_page(runtime, 1, 2, 3);
    require_true(runtime.active_pages == 1, "active page count after mapping mismatch");

    const std::vector<int> sequence_table =
        copy_ints(runtime.device_sequence_page_table, 8);
    require_true(sequence_table[1 * 4 + 2] == 3, "sequence page mapping mismatch");
    const std::vector<int> residency = copy_ints(runtime.device_page_residency, 4);
    require_true(residency[3] == 1, "page residency mismatch");

    spoolstream::core::mark_kv_page_access(runtime, 3, 42);
    const std::vector<uint64_t> access = copy_u64(runtime.device_page_last_access, 4);
    require_true(access[3] == 42, "page access step mismatch");

    spoolstream::core::destroy_paged_kv_cache(runtime);
    require_true(runtime.device_window == nullptr, "device_window was not nulled");
    require_true(runtime.host_eviction_buffer == nullptr, "host_eviction_buffer was not nulled");
    require_true(runtime.stream_kv == nullptr, "stream_kv was not nulled");
}

void test_constant_descriptor_upload() {
    spoolstream::core::PageDescriptorTable table{};
    table.layer_id = 7;
    table.page_count = 2;
    table.pages[0].layer_id = 7;
    table.pages[0].logical_page_id = 0;
    table.pages[0].physical_page_id = 3;
    table.pages[0].byte_offset = 768;
    table.pages[0].byte_size = 256;
    table.pages[1].layer_id = 7;
    table.pages[1].logical_page_id = 1;
    table.pages[1].physical_page_id = 2;
    table.pages[1].byte_offset = 512;
    table.pages[1].byte_size = 256;

    spoolstream::core::upload_layer_page_tables_to_constant(&table, 1);
    const auto fetched = spoolstream::core::fetch_layer_page_table_from_constant(0);
    require_true(fetched.layer_id == 7, "fetched layer id mismatch");
    require_true(fetched.page_count == 2, "fetched page count mismatch");
    require_true(fetched.pages[1].physical_page_id == 2,
                 "fetched physical page mismatch");
    require_true(fetched.pages[0].byte_offset == 768,
                 "fetched byte offset mismatch");
}

void test_eviction_stream_copy_and_feedback() {
    auto runtime = spoolstream::core::create_paged_kv_cache(make_config());
    const std::vector<uint8_t> pattern = make_pattern(runtime.page_size_bytes);
    constexpr int kPhysicalPage = 2;
    const size_t offset = static_cast<size_t>(kPhysicalPage) * runtime.page_size_bytes;

    SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(static_cast<uint8_t*>(runtime.device_window) + offset,
                                     pattern.data(),
                                     pattern.size(),
                                     cudaMemcpyHostToDevice));
    spoolstream::core::map_sequence_page(runtime, 0, 0, kPhysicalPage);
    spoolstream::core::map_sequence_page(runtime, 0, 1, 1);
    spoolstream::core::map_sequence_page(runtime, 0, 2, 3);
    require_true(spoolstream::core::kv_cache_should_evict(runtime),
                 "cache should evict at threshold");

    cudaEvent_t quiet_event = nullptr;
    SPOOLSTREAM_CUDA_CHECK(cudaEventCreateWithFlags(&quiet_event, cudaEventDisableTiming));
    SPOOLSTREAM_CUDA_CHECK(cudaEventRecord(quiet_event, nullptr));
    spoolstream::core::schedule_kv_eviction(runtime,
                                            kPhysicalPage,
                                            runtime.page_size_bytes,
                                            quiet_event);
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(runtime.stream_kv));
    SPOOLSTREAM_CUDA_CHECK(cudaEventDestroy(quiet_event));

    const auto* evicted =
        static_cast<const uint8_t*>(runtime.host_eviction_buffer) + offset;
    require_true(std::memcmp(evicted, pattern.data(), pattern.size()) == 0,
                 "evicted bytes mismatch");
    const std::vector<int> residency = copy_ints(runtime.device_page_residency, 4);
    require_true(residency[kPhysicalPage] == 0, "evicted page residency mismatch");
    const std::vector<uint32_t> marker = copy_u32(runtime.device_eviction_marker, 1);
    require_true(marker[0] == 1U, "eviction marker mismatch");

    const int reduced_depth = spoolstream::core::update_kv_cache_feedback(runtime, 1, 4);
    require_true(reduced_depth == 1, "lookahead depth should reduce to 1");
    require_true(runtime.lookahead_depth == 1, "runtime lookahead depth mismatch");

    spoolstream::core::destroy_paged_kv_cache(runtime);
}

void test_validation_failures() {
    auto config = make_config();
    config.page_size_bytes = 0;
    require_throw([&]() {
        auto runtime = spoolstream::core::create_paged_kv_cache(config);
        spoolstream::core::destroy_paged_kv_cache(runtime);
    }, "invalid page size");

    config = make_config();
    auto runtime = spoolstream::core::create_paged_kv_cache(config);
    require_throw([&]() {
        spoolstream::core::map_sequence_page(runtime, 0, 0, 99);
    }, "invalid physical page");

    require_throw([&]() {
        spoolstream::core::schedule_kv_eviction(runtime, 0, runtime.page_size_bytes + 1);
    }, "oversized eviction");

    require_throw([&]() {
        spoolstream::core::update_kv_cache_feedback(runtime, 5, 4);
    }, "invalid feedback counts");

    spoolstream::core::PageDescriptorTable invalid_table{};
    invalid_table.layer_id = 1;
    invalid_table.page_count = 1;
    invalid_table.pages[0].layer_id = 2;
    invalid_table.pages[0].logical_page_id = 0;
    invalid_table.pages[0].physical_page_id = 0;
    invalid_table.pages[0].byte_size = 1;
    require_throw([&]() {
        spoolstream::core::upload_layer_page_tables_to_constant(&invalid_table, 1);
    }, "invalid constant descriptor");

    spoolstream::core::destroy_paged_kv_cache(runtime);
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_create_map_access_and_destroy();
        test_constant_descriptor_upload();
        test_eviction_stream_copy_and_feedback();
        test_validation_failures();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream KV cache tests passed\n";
    return 0;
}
