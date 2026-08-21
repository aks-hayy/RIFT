#include "spoolstream/memory_manager.h"
#include "spoolstream/pipeline.h"

#include <cuda_runtime_api.h>

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

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

class PinnedHostBuffer {
public:
    explicit PinnedHostBuffer(size_t byte_count) : byte_count_(byte_count) {
        SPOOLSTREAM_CUDA_CHECK(cudaHostAlloc(&ptr_, byte_count_, cudaHostAllocPortable));
    }

    PinnedHostBuffer(const PinnedHostBuffer&) = delete;
    PinnedHostBuffer& operator=(const PinnedHostBuffer&) = delete;

    ~PinnedHostBuffer() {
        if (ptr_ != nullptr) {
            cudaFreeHost(ptr_);
        }
    }

    uint8_t* bytes() {
        return static_cast<uint8_t*>(ptr_);
    }

    const uint8_t* bytes() const {
        return static_cast<const uint8_t*>(ptr_);
    }

    void* ptr() {
        return ptr_;
    }

private:
    void* ptr_ = nullptr;
    size_t byte_count_ = 0;
};

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_), sizeof(T) * count_));
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

    std::vector<T> copy_to_host() const {
        std::vector<T> host(count_);
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                         ptr_,
                                         sizeof(T) * count_,
                                         cudaMemcpyDeviceToHost));
        return host;
    }

private:
    T* ptr_ = nullptr;
    size_t count_ = 0;
};

std::vector<uint8_t> make_pattern(size_t byte_count) {
    std::vector<uint8_t> pattern(byte_count);
    for (size_t i = 0; i < byte_count; ++i) {
        pattern[i] = static_cast<uint8_t>((i * 17U + 29U) & 0xFFU);
    }
    return pattern;
}

void test_transfer_estimation_and_throttle_math() {
    const uint64_t one_gb_at_64_gbps =
        spoolstream::core::estimate_h2d_transfer_ns(1000000000ULL, 64.0);
    require_true(one_gb_at_64_gbps >= 15625000ULL && one_gb_at_64_gbps <= 15625001ULL,
                 "64 GB/s transfer estimate mismatch");

    const uint64_t cycles =
        spoolstream::core::compute_throttle_cycles(1024, 2000000ULL, 64.0, 0);
    require_true(cycles > 0, "expected positive throttle cycles");

    const uint64_t no_delay =
        spoolstream::core::compute_throttle_cycles(1024ULL * 1024ULL * 1024ULL,
                                                   1ULL,
                                                   64.0,
                                                   0);
    require_true(no_delay == 0, "expected zero throttle when physical transfer exceeds target");
}

void test_pipeline_queues_and_scheduled_copy() {
    constexpr size_t kBytes = 4096;
    const std::vector<uint8_t> pattern = make_pattern(kBytes);
    PinnedHostBuffer host(kBytes);
    std::memcpy(host.ptr(), pattern.data(), kBytes);
    DeviceBuffer<uint8_t> device(kBytes);

    auto queues = spoolstream::core::create_pipeline_queues(0);
    require_true(queues.stream_compute != nullptr, "compute stream is null");
    require_true(queues.stream_copy != nullptr, "copy stream is null");
    require_true(queues.compute_priority <= queues.copy_priority,
                 "compute stream priority should be higher or equal priority");

    cudaEvent_t completion = nullptr;
    SPOOLSTREAM_CUDA_CHECK(cudaEventCreateWithFlags(&completion, cudaEventDisableTiming));
    spoolstream::core::schedule_throttle_paced_h2d(queues,
                                                   device.get(),
                                                   host.ptr(),
                                                   kBytes,
                                                   1000000ULL,
                                                   completion,
                                                   64.0,
                                                   0);
    SPOOLSTREAM_CUDA_CHECK(cudaEventSynchronize(completion));
    SPOOLSTREAM_CUDA_CHECK(cudaEventDestroy(completion));

    const std::vector<uint8_t> actual = device.copy_to_host();
    require_true(actual == pattern, "scheduled throttled copy bytes mismatch");

    spoolstream::core::destroy_pipeline_queues(queues);
    require_true(queues.stream_compute == nullptr, "compute stream was not nulled");
    require_true(queues.stream_copy == nullptr, "copy stream was not nulled");
}

void test_compiled_pipeline_graph() {
    constexpr size_t kBytes = 8192;
    const std::vector<uint8_t> pattern = make_pattern(kBytes);
    PinnedHostBuffer host(kBytes);
    std::memcpy(host.ptr(), pattern.data(), kBytes);
    DeviceBuffer<uint8_t> device(kBytes);
    DeviceBuffer<uint32_t> marker(1);
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(marker.get(), 0, sizeof(uint32_t)));

    spoolstream::core::PipelineStageConfig config{};
    config.host_src = host.ptr();
    config.device_dst = device.get();
    config.byte_count = kBytes;
    config.target_exec_ns = 1000000ULL;
    config.device_marker = marker.get();
    config.marker_value = 0xC0DEFACEU;
    config.cuda_device_id = 0;
    config.h2d_bandwidth_limit_gbps = 64.0;

    auto graph = spoolstream::core::compile_streaming_pipeline_graph(config);
    require_true(graph.graph != nullptr, "graph handle is null");
    require_true(graph.executable != nullptr, "graph executable is null");
    require_true(graph.estimated_physical_transfer_ns > 0,
                 "estimated transfer duration should be positive");

    spoolstream::core::launch_streaming_pipeline_graph(graph);

    const std::vector<uint8_t> actual = device.copy_to_host();
    require_true(actual == pattern, "graph H2D copy bytes mismatch");
    const std::vector<uint32_t> marker_value = marker.copy_to_host();
    require_true(marker_value[0] == 0xC0DEFACEU, "graph marker kernel did not execute");

    const bool capability_probe = spoolstream::core::cuda_conditional_graph_nodes_available(0);
    if (graph.conditional_node_created) {
        require_true(capability_probe, "conditional node created despite negative capability probe");
    }

    spoolstream::core::destroy_pipeline_graph(graph);
    require_true(graph.graph == nullptr, "graph handle was not nulled");
    require_true(graph.executable == nullptr, "graph executable was not nulled");
}

void test_invalid_pipeline_inputs() {
    require_throw([&]() {
        spoolstream::core::estimate_h2d_transfer_ns(1024, 128.0);
    }, "bandwidth above unidirectional physical limit");

    spoolstream::core::PipelineStageConfig config{};
    config.host_src = nullptr;
    config.device_dst = reinterpret_cast<void*>(0x1);
    config.byte_count = 1024;
    config.target_exec_ns = 1;
    config.device_marker = reinterpret_cast<uint32_t*>(0x1);
    config.marker_value = 1;
    config.cuda_device_id = 0;
    config.h2d_bandwidth_limit_gbps = 64.0;
    require_throw([&]() {
        spoolstream::core::compile_streaming_pipeline_graph(config);
    }, "null host source");
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_transfer_estimation_and_throttle_math();
        test_pipeline_queues_and_scheduled_copy();
        test_compiled_pipeline_graph();
        test_invalid_pipeline_inputs();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream pipeline tests passed\n";
    return 0;
}
