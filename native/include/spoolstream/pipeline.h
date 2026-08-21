#pragma once

#include <cstddef>
#include <cstdint>

#include <cuda_runtime_api.h>

namespace spoolstream::core {

constexpr double kPcieGen5X16UnidirectionalH2DGBps = 64.0;

struct PipelineQueues {
    cudaStream_t stream_compute;
    cudaStream_t stream_copy;
    int compute_priority;
    int copy_priority;
};

struct PipelineStageConfig {
    const void* host_src;
    void* device_dst;
    size_t byte_count;
    uint64_t target_exec_ns;
    uint32_t* device_marker;
    uint32_t marker_value;
    int cuda_device_id;
    double h2d_bandwidth_limit_gbps;
};

struct PipelineGraph {
    cudaGraph_t graph;
    cudaGraphExec_t executable;
    uint64_t throttle_cycles;
    uint64_t estimated_physical_transfer_ns;
    bool conditional_nodes_supported;
    bool conditional_node_created;
};

PipelineQueues create_pipeline_queues(int cuda_device_id = 0);

void destroy_pipeline_queues(PipelineQueues& queues) noexcept;

uint64_t estimate_h2d_transfer_ns(size_t byte_count,
                                  double h2d_bandwidth_limit_gbps =
                                      kPcieGen5X16UnidirectionalH2DGBps);

uint64_t compute_throttle_cycles(size_t byte_count,
                                 uint64_t target_exec_ns,
                                 double h2d_bandwidth_limit_gbps =
                                     kPcieGen5X16UnidirectionalH2DGBps,
                                 int cuda_device_id = 0);

bool cuda_conditional_graph_nodes_available(int cuda_device_id = 0);

void schedule_throttle_paced_h2d(const PipelineQueues& queues,
                                 void* device_dst,
                                 const void* host_src,
                                 size_t byte_count,
                                 uint64_t target_exec_ns,
                                 cudaEvent_t completion_event = nullptr,
                                 double h2d_bandwidth_limit_gbps =
                                     kPcieGen5X16UnidirectionalH2DGBps,
                                 int cuda_device_id = 0);

PipelineGraph compile_streaming_pipeline_graph(const PipelineStageConfig& config);

void launch_streaming_pipeline_graph(const PipelineGraph& pipeline_graph,
                                     cudaStream_t launch_stream = nullptr);

void destroy_pipeline_graph(PipelineGraph& pipeline_graph) noexcept;

} // namespace spoolstream::core
