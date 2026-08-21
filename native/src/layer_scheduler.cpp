#include "spoolstream/layer_scheduler.h"

#include "spoolstream/memory_manager.h"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream layer scheduler validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

size_t align_up(size_t value, size_t alignment) {
    require_condition(alignment > 0, "alignment must be positive");
    const size_t remainder = value % alignment;
    if (remainder == 0) {
        return value;
    }
    require_condition(value <= std::numeric_limits<size_t>::max() - (alignment - remainder),
                      "aligned size overflows size_t");
    return value + alignment - remainder;
}

int role_order(TensorRole role) {
    switch (role) {
        case TensorRole::ATTN_NORM:
            return 0;
        case TensorRole::ATTN_Q:
        case TensorRole::ATTN_K:
        case TensorRole::ATTN_V:
        case TensorRole::ATTN_O:
        case TensorRole::QUANT_QWEIGHT:
        case TensorRole::QUANT_SCALE:
        case TensorRole::QUANT_ZERO:
        case TensorRole::QUANT_GIDX:
        case TensorRole::QUANT_BIAS:
            return 1;
        case TensorRole::MLP_NORM:
            return 2;
        case TensorRole::MLP_GATE:
        case TensorRole::MLP_UP:
        case TensorRole::MLP_DOWN:
            return 3;
        default:
            return 4;
    }
}

size_t tensor_byte_size(const ManifestTensor& tensor) {
    require_condition(tensor.metadata.end_offset >= tensor.metadata.start_offset,
                      "tensor has inverted offsets: " + tensor.metadata.name);
    const size_t bytes = tensor.metadata.end_offset - tensor.metadata.start_offset;
    require_condition(bytes > 0, "tensor has zero bytes: " + tensor.metadata.name);
    return bytes;
}

} // namespace

LayerPlanSet build_layer_execution_plans(const ModelManifest& manifest,
                                         size_t slot_capacity,
                                         size_t alignment) {
    require_condition(slot_capacity > 0, "slot_capacity must be positive");
    require_condition(alignment > 0, "alignment must be positive");
    require_condition(manifest.config.num_hidden_layers > 0,
                      "manifest config has no transformer layers");

    LayerPlanSet plan_set{};
    plan_set.slot_capacity = slot_capacity;
    plan_set.alignment = alignment;
    plan_set.layers.reserve(static_cast<size_t>(manifest.config.num_hidden_layers));

    for (int layer_id = 0; layer_id < manifest.config.num_hidden_layers; ++layer_id) {
        std::vector<const ManifestTensor*> tensors;
        for (const ManifestTensor& tensor : manifest.tensors) {
            if (tensor.layer_id == layer_id) {
                tensors.push_back(&tensor);
            }
        }
        require_condition(!tensors.empty(),
                          "no manifest tensors found for layer " + std::to_string(layer_id));
        std::sort(tensors.begin(),
                  tensors.end(),
                  [](const ManifestTensor* lhs, const ManifestTensor* rhs) {
                      const int lhs_order = role_order(lhs->role);
                      const int rhs_order = role_order(rhs->role);
                      if (lhs_order != rhs_order) {
                          return lhs_order < rhs_order;
                      }
                      return lhs->metadata.name < rhs->metadata.name;
                  });

        LayerExecutionPlan plan{};
        plan.layer_id = layer_id;
        size_t cursor = 0;
        for (const ManifestTensor* tensor : tensors) {
            cursor = align_up(cursor, alignment);
            const size_t bytes = tensor_byte_size(*tensor);
            require_condition(bytes <= slot_capacity,
                              "single tensor exceeds slot capacity: " + tensor->metadata.name);
            require_condition(cursor <= slot_capacity && bytes <= slot_capacity - cursor,
                              "layer " + std::to_string(layer_id) +
                                  " exceeds scratchpad slot capacity");
            TensorPlacement placement{};
            placement.tensor = tensor;
            placement.slot_offset = cursor;
            placement.byte_size = bytes;
            placement.role = tensor->role;
            placement.layer_id = layer_id;
            plan.placements.push_back(placement);
            cursor += bytes;
        }
        plan.total_bytes = cursor;
        plan_set.layers.push_back(std::move(plan));
    }

    return plan_set;
}

const LayerExecutionPlan& require_layer_plan(const LayerPlanSet& plans,
                                             int layer_id) {
    require_condition(layer_id >= 0, "layer_id must be non-negative");
    for (const LayerExecutionPlan& plan : plans.layers) {
        if (plan.layer_id == layer_id) {
            return plan;
        }
    }
    fail("missing layer execution plan for layer " + std::to_string(layer_id));
}

ScheduledLayerTransfer schedule_layer_prefetch(StreamingTensorStore& store,
                                               const LayerExecutionPlan& plan,
                                               void* device_slot,
                                               cudaStream_t stream_copy) {
    require_condition(device_slot != nullptr, "device_slot is null");
    require_condition(!plan.placements.empty(), "layer plan has no placements");

    ScheduledLayerTransfer transfer{};
    transfer.layer_id = plan.layer_id;
    transfer.device_slot = device_slot;
    transfer.byte_count = plan.total_bytes;
    transfer.ready_event = nullptr;

    try {
        SPOOLSTREAM_CUDA_CHECK(cudaEventCreateWithFlags(&transfer.ready_event,
                                                        cudaEventDisableTiming));
        auto* slot_bytes = static_cast<unsigned char*>(device_slot);
        for (const TensorPlacement& placement : plan.placements) {
            const StagedTensor staged = stage_tensor_bytes(store, *placement.tensor);
            require_condition(staged.byte_size == placement.byte_size,
                              "staged tensor byte size does not match placement");
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpyAsync(slot_bytes + placement.slot_offset,
                                                   staged.host_ptr,
                                                   staged.byte_size,
                                                   cudaMemcpyHostToDevice,
                                                   stream_copy));
            SPOOLSTREAM_CUDA_CHECK(cudaStreamSynchronize(stream_copy));
        }
        SPOOLSTREAM_CUDA_CHECK(cudaEventRecord(transfer.ready_event, stream_copy));
        return transfer;
    } catch (...) {
        destroy_scheduled_layer_transfer(transfer);
        throw;
    }
}

void wait_for_layer_transfer(const ScheduledLayerTransfer& transfer) {
    require_condition(transfer.ready_event != nullptr, "ready_event is null");
    SPOOLSTREAM_CUDA_CHECK(cudaEventSynchronize(transfer.ready_event));
}

void destroy_scheduled_layer_transfer(ScheduledLayerTransfer& transfer) noexcept {
    if (transfer.ready_event != nullptr) {
        cudaEventDestroy(transfer.ready_event);
        transfer.ready_event = nullptr;
    }
    transfer.layer_id = -1;
    transfer.device_slot = nullptr;
    transfer.byte_count = 0;
}

} // namespace spoolstream::core
