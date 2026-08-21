#include "spoolstream/pipeline.h"

#include "spoolstream/memory_manager.h"

#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream pipeline validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

__global__ void throttle_delay_kernel(uint64_t delay_cycles, uint32_t* marker, uint32_t value) {
    const uint64_t start = clock64();
    while ((clock64() - start) < delay_cycles) {
    }
    if (threadIdx.x == 0 && blockIdx.x == 0 && marker != nullptr) {
        atomicAdd(marker, value);
    }
}

__global__ void pipeline_marker_kernel(uint32_t* marker, uint32_t value) {
    if (threadIdx.x == 0 && blockIdx.x == 0 && marker != nullptr) {
        *marker = value;
    }
}

void validate_bandwidth(double bandwidth_gbps) {
    require_condition(std::isfinite(bandwidth_gbps) && bandwidth_gbps > 0.0,
                      "H2D bandwidth limit must be positive and finite");
    require_condition(bandwidth_gbps <= kPcieGen5X16UnidirectionalH2DGBps,
                      "H2D bandwidth limit must not exceed the PCIe Gen 5 x16 unidirectional cap");
}

void validate_stage_config(const PipelineStageConfig& config) {
    require_condition(config.host_src != nullptr, "host_src cannot be null");
    require_condition(config.device_dst != nullptr, "device_dst cannot be null");
    require_condition(config.byte_count > 0, "byte_count must be positive");
    require_condition(config.device_marker != nullptr, "device_marker cannot be null");
    require_condition(config.target_exec_ns > 0, "target_exec_ns must be positive");
    validate_bandwidth(config.h2d_bandwidth_limit_gbps);
}

void validate_device(int cuda_device_id) {
    int device_count = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    require_condition(device_count > 0, "no CUDA-capable devices are visible");
    require_condition(cuda_device_id >= 0 && cuda_device_id < device_count,
                      "invalid CUDA device id " + std::to_string(cuda_device_id));
    SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(cuda_device_id));
}

uint64_t device_cycles_for_ns(uint64_t ns, int cuda_device_id) {
    validate_device(cuda_device_id);
    int clock_rate_khz = 0;
    SPOOLSTREAM_CUDA_CHECK(
        cudaDeviceGetAttribute(&clock_rate_khz, cudaDevAttrClockRate, cuda_device_id));
    require_condition(clock_rate_khz > 0, "selected CUDA device reports invalid clock rate");

    const long double cycles =
        static_cast<long double>(ns) * static_cast<long double>(clock_rate_khz) / 1000000.0L;
    require_condition(cycles <= static_cast<long double>(std::numeric_limits<uint64_t>::max()),
                      "throttle cycle count exceeds uint64_t range");
    return static_cast<uint64_t>(cycles);
}

void add_kernel_node(cudaGraph_t graph,
                     cudaGraphNode_t* node,
                     const cudaGraphNode_t* dependencies,
                     size_t dependency_count,
                     void* kernel,
                     dim3 grid,
                     dim3 block,
                     void** args) {
    cudaKernelNodeParams params{};
    params.func = kernel;
    params.gridDim = grid;
    params.blockDim = block;
    params.sharedMemBytes = 0;
    params.kernelParams = args;
    params.extra = nullptr;
    SPOOLSTREAM_CUDA_CHECK(
        cudaGraphAddKernelNode(node, graph, dependencies, dependency_count, &params));
}

bool try_add_conditional_node(cudaGraph_t graph) noexcept {
    cudaGraphConditionalHandle handle = 0;
    cudaError_t status = cudaGraphConditionalHandleCreate(
        &handle, graph, 0U, cudaGraphCondAssignDefault);
    if (status != cudaSuccess) {
        cudaGetLastError();
        return false;
    }

    cudaGraphNodeParams params{};
    params.type = cudaGraphNodeTypeConditional;
    params.conditional.handle = handle;
    params.conditional.type = cudaGraphCondTypeIf;
    params.conditional.size = 1U;
    params.conditional.phGraph_out = nullptr;
    params.conditional.ctx = nullptr;

    cudaGraphNode_t conditional_node = nullptr;
    status = cudaGraphAddNode(&conditional_node, graph, nullptr, nullptr, 0U, &params);
    if (status != cudaSuccess) {
        cudaGetLastError();
        return false;
    }
    return true;
}

} // namespace

PipelineQueues create_pipeline_queues(int cuda_device_id) {
    validate_device(cuda_device_id);

    int least_priority = 0;
    int greatest_priority = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaDeviceGetStreamPriorityRange(&least_priority, &greatest_priority));

    PipelineQueues queues{};
    queues.compute_priority = greatest_priority;
    queues.copy_priority = least_priority;

    try {
        SPOOLSTREAM_CUDA_CHECK(cudaStreamCreateWithPriority(&queues.stream_compute,
                                                           cudaStreamNonBlocking,
                                                           queues.compute_priority));
        SPOOLSTREAM_CUDA_CHECK(cudaStreamCreateWithPriority(&queues.stream_copy,
                                                           cudaStreamNonBlocking,
                                                           queues.copy_priority));
        return queues;
    } catch (...) {
        destroy_pipeline_queues(queues);
        throw;
    }
}

void destroy_pipeline_queues(PipelineQueues& queues) noexcept {
    if (queues.stream_compute != nullptr) {
        cudaStreamDestroy(queues.stream_compute);
        queues.stream_compute = nullptr;
    }
    if (queues.stream_copy != nullptr) {
        cudaStreamDestroy(queues.stream_copy);
        queues.stream_copy = nullptr;
    }
    queues.compute_priority = 0;
    queues.copy_priority = 0;
}

uint64_t estimate_h2d_transfer_ns(size_t byte_count, double h2d_bandwidth_limit_gbps) {
    validate_bandwidth(h2d_bandwidth_limit_gbps);
    require_condition(byte_count > 0, "byte_count must be positive");

    const long double bytes_per_second =
        static_cast<long double>(h2d_bandwidth_limit_gbps) * 1000000000.0L;
    const long double ns =
        static_cast<long double>(byte_count) * 1000000000.0L / bytes_per_second;
    require_condition(ns <= static_cast<long double>(std::numeric_limits<uint64_t>::max()),
                      "estimated H2D transfer duration exceeds uint64_t range");
    return std::max<uint64_t>(1U, static_cast<uint64_t>(std::ceil(ns)));
}

uint64_t compute_throttle_cycles(size_t byte_count,
                                 uint64_t target_exec_ns,
                                 double h2d_bandwidth_limit_gbps,
                                 int cuda_device_id) {
    require_condition(target_exec_ns > 0, "target_exec_ns must be positive");
    const uint64_t physical_transfer_ns =
        estimate_h2d_transfer_ns(byte_count, h2d_bandwidth_limit_gbps);
    if (physical_transfer_ns >= target_exec_ns) {
        return 0;
    }
    return device_cycles_for_ns(target_exec_ns - physical_transfer_ns, cuda_device_id);
}

bool cuda_conditional_graph_nodes_available(int cuda_device_id) {
    try {
        validate_device(cuda_device_id);
        cudaGraph_t graph = nullptr;
        SPOOLSTREAM_CUDA_CHECK(cudaGraphCreate(&graph, 0));
        const bool added = try_add_conditional_node(graph);
        cudaGraphExec_t executable = nullptr;
        bool instantiated = false;
        if (added) {
            cudaError_t status = cudaGraphInstantiate(&executable, graph, 0);
            if (status == cudaSuccess) {
                instantiated = true;
            } else {
                cudaGetLastError();
            }
        }
        if (executable != nullptr) {
            cudaGraphExecDestroy(executable);
        }
        if (graph != nullptr) {
            cudaGraphDestroy(graph);
        }
        return added && instantiated;
    } catch (...) {
        return false;
    }
}

void schedule_throttle_paced_h2d(const PipelineQueues& queues,
                                 void* device_dst,
                                 const void* host_src,
                                 size_t byte_count,
                                 uint64_t target_exec_ns,
                                 cudaEvent_t completion_event,
                                 double h2d_bandwidth_limit_gbps,
                                 int cuda_device_id) {
    require_condition(queues.stream_copy != nullptr, "stream_copy cannot be null");
    require_condition(device_dst != nullptr, "device_dst cannot be null");
    require_condition(host_src != nullptr, "host_src cannot be null");
    require_condition(byte_count > 0, "byte_count must be positive");

    const uint64_t throttle_cycles =
        compute_throttle_cycles(byte_count, target_exec_ns, h2d_bandwidth_limit_gbps, cuda_device_id);

    SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(device_dst,
                                           host_src,
                                           byte_count,
                                           cudaMemcpyHostToDevice,
                                           queues.stream_copy));
    throttle_delay_kernel<<<1, 32, 0, queues.stream_copy>>>(throttle_cycles, nullptr, 0U);
    SPOOLSTREAM_CUDA_CHECK(cudaGetLastError());
    if (completion_event != nullptr) {
        SPOOLSTREAM_CUDA_CHECK(cudaEventRecord(completion_event, queues.stream_copy));
    }
}

PipelineGraph compile_streaming_pipeline_graph(const PipelineStageConfig& config) {
    validate_stage_config(config);
    validate_device(config.cuda_device_id);

    PipelineGraph pipeline_graph{};
    pipeline_graph.graph = nullptr;
    pipeline_graph.executable = nullptr;
    pipeline_graph.estimated_physical_transfer_ns =
        estimate_h2d_transfer_ns(config.byte_count, config.h2d_bandwidth_limit_gbps);
    pipeline_graph.throttle_cycles =
        compute_throttle_cycles(config.byte_count,
                                config.target_exec_ns,
                                config.h2d_bandwidth_limit_gbps,
                                config.cuda_device_id);
    pipeline_graph.conditional_nodes_supported =
        cuda_conditional_graph_nodes_available(config.cuda_device_id);
    pipeline_graph.conditional_node_created = false;

    try {
        SPOOLSTREAM_CUDA_CHECK(cudaGraphCreate(&pipeline_graph.graph, 0));

        if (pipeline_graph.conditional_nodes_supported) {
            pipeline_graph.conditional_node_created = try_add_conditional_node(pipeline_graph.graph);
        }

        cudaGraphNode_t copy_node = nullptr;
        SPOOLSTREAM_CUDA_CHECK(cudaGraphAddMemcpyNode1D(&copy_node,
                                                        pipeline_graph.graph,
                                                        nullptr,
                                                        0,
                                                        config.device_dst,
                                                        config.host_src,
                                                        config.byte_count,
                                                        cudaMemcpyHostToDevice));

        cudaGraphNode_t throttle_node = nullptr;
        uint64_t throttle_cycles = pipeline_graph.throttle_cycles;
        uint32_t* marker_for_throttle = nullptr;
        uint32_t throttle_marker_value = 0U;
        void* throttle_args[] = {&throttle_cycles, &marker_for_throttle, &throttle_marker_value};
        add_kernel_node(pipeline_graph.graph,
                        &throttle_node,
                        &copy_node,
                        1,
                        reinterpret_cast<void*>(throttle_delay_kernel),
                        dim3(1),
                        dim3(32),
                        throttle_args);

        cudaGraphNode_t marker_node = nullptr;
        uint32_t* device_marker = config.device_marker;
        uint32_t marker_value = config.marker_value;
        void* marker_args[] = {&device_marker, &marker_value};
        add_kernel_node(pipeline_graph.graph,
                        &marker_node,
                        &throttle_node,
                        1,
                        reinterpret_cast<void*>(pipeline_marker_kernel),
                        dim3(1),
                        dim3(1),
                        marker_args);

        SPOOLSTREAM_CUDA_CHECK(cudaGraphInstantiate(&pipeline_graph.executable,
                                                    pipeline_graph.graph,
                                                    0));
        return pipeline_graph;
    } catch (...) {
        destroy_pipeline_graph(pipeline_graph);
        throw;
    }
}

void launch_streaming_pipeline_graph(const PipelineGraph& pipeline_graph, cudaStream_t launch_stream) {
    require_condition(pipeline_graph.executable != nullptr,
                      "pipeline graph executable cannot be null");
    SPOOLSTREAM_CUDA_CHECK(cudaGraphLaunch(pipeline_graph.executable, launch_stream));
    SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(launch_stream));
}

void destroy_pipeline_graph(PipelineGraph& pipeline_graph) noexcept {
    if (pipeline_graph.executable != nullptr) {
        cudaGraphExecDestroy(pipeline_graph.executable);
        pipeline_graph.executable = nullptr;
    }
    if (pipeline_graph.graph != nullptr) {
        cudaGraphDestroy(pipeline_graph.graph);
        pipeline_graph.graph = nullptr;
    }
    pipeline_graph.throttle_cycles = 0;
    pipeline_graph.estimated_physical_transfer_ns = 0;
    pipeline_graph.conditional_nodes_supported = false;
    pipeline_graph.conditional_node_created = false;
}

} // namespace spoolstream::core
