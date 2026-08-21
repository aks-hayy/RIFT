#pragma once

#include "spoolstream/model.h"

#include <cstddef>
#include <string>
#include <vector>

namespace spoolstream::core {

struct HardwareProfile {
    int cuda_device_id;
    bool cuda_available;
    std::string device_name;
    int compute_capability_major;
    int compute_capability_minor;
    int multiprocessor_count;
    size_t total_vram_bytes;
    size_t free_vram_bytes;
    size_t total_host_ram_bytes;
    size_t free_host_ram_bytes;
    double estimated_h2d_bandwidth_gbps;
};

struct ExecutionPolicy {
    bool supported;
    bool streaming_required;
    bool use_paged_kv_cache;
    bool use_speculative;
    bool use_quantized_weights;
    size_t scratchpad_slot_bytes;
    size_t host_staging_bytes;
    size_t host_resident_cap_bytes;
    size_t kv_cache_bytes;
    std::string architecture_backend;
    std::string reason;
};

struct CompatibilityReport {
    bool compatible;
    std::vector<std::string> issues;
    ExecutionPolicy policy;
};

HardwareProfile build_hardware_profile(int cuda_device_id = 0);

ExecutionPolicy plan_execution_policy(const ModelManifest& manifest,
                                      const HardwareProfile& hardware,
                                      const MemoryBudget& budget);

CompatibilityReport assess_model_compatibility(const ModelManifest& manifest,
                                               const HardwareProfile& hardware,
                                               const MemoryBudget& budget);

} // namespace spoolstream::core
