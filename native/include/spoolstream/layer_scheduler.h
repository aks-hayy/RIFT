#pragma once

#include "spoolstream/model.h"
#include "spoolstream/streaming_store.h"

#include <cstddef>
#include <vector>

#include <cuda_runtime_api.h>

namespace spoolstream::core {

struct TensorPlacement {
    const ManifestTensor* tensor;
    size_t slot_offset;
    size_t byte_size;
    TensorRole role;
    int layer_id;
};

struct LayerExecutionPlan {
    int layer_id;
    size_t total_bytes;
    std::vector<TensorPlacement> placements;
};

struct LayerPlanSet {
    size_t slot_capacity;
    size_t alignment;
    std::vector<LayerExecutionPlan> layers;
};

struct ScheduledLayerTransfer {
    int layer_id;
    void* device_slot;
    size_t byte_count;
    cudaEvent_t ready_event;
};

LayerPlanSet build_layer_execution_plans(const ModelManifest& manifest,
                                         size_t slot_capacity,
                                         size_t alignment = 256);

const LayerExecutionPlan& require_layer_plan(const LayerPlanSet& plans,
                                             int layer_id);

ScheduledLayerTransfer schedule_layer_prefetch(StreamingTensorStore& store,
                                               const LayerExecutionPlan& plan,
                                               void* device_slot,
                                               cudaStream_t stream_copy = nullptr);

void wait_for_layer_transfer(const ScheduledLayerTransfer& transfer);

void destroy_scheduled_layer_transfer(ScheduledLayerTransfer& transfer) noexcept;

} // namespace spoolstream::core
