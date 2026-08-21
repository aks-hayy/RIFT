#include "spoolstream/execution_policy.h"

#include "spoolstream/memory_manager.h"

#include <cuda_runtime_api.h>

#include <algorithm>
#include <sstream>
#include <stdexcept>

#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream execution policy validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

size_t host_total_bytes() {
#if defined(_WIN32)
    MEMORYSTATUSEX status{};
    status.dwLength = sizeof(status);
    require_condition(GlobalMemoryStatusEx(&status) != 0, "GlobalMemoryStatusEx failed");
    return static_cast<size_t>(status.ullTotalPhys);
#else
    const long pages = sysconf(_SC_PHYS_PAGES);
    const long page_size = sysconf(_SC_PAGESIZE);
    require_condition(pages > 0 && page_size > 0, "sysconf host memory query failed");
    return static_cast<size_t>(pages) * static_cast<size_t>(page_size);
#endif
}

size_t host_free_bytes() {
#if defined(_WIN32)
    MEMORYSTATUSEX status{};
    status.dwLength = sizeof(status);
    require_condition(GlobalMemoryStatusEx(&status) != 0, "GlobalMemoryStatusEx failed");
    return static_cast<size_t>(status.ullAvailPhys);
#else
    const long pages = sysconf(_SC_AVPHYS_PAGES);
    const long page_size = sysconf(_SC_PAGESIZE);
    require_condition(pages > 0 && page_size > 0, "sysconf host memory query failed");
    return static_cast<size_t>(pages) * static_cast<size_t>(page_size);
#endif
}

double conservative_h2d_bandwidth_gbps(const cudaDeviceProp& props) {
    if (props.major >= 8) {
        return 16.0;
    }
    if (props.major >= 7) {
        return 12.0;
    }
    return 8.0;
}

std::string join_issues(const std::vector<std::string>& issues) {
    std::ostringstream out;
    for (size_t i = 0; i < issues.size(); ++i) {
        if (i != 0) {
            out << "; ";
        }
        out << issues[i];
    }
    return out.str();
}

} // namespace

HardwareProfile build_hardware_profile(int cuda_device_id) {
    require_condition(cuda_device_id >= 0, "cuda_device_id must be non-negative");
    int device_count = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    require_condition(cuda_device_id < device_count, "cuda_device_id is out of range");
    SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(cuda_device_id));

    cudaDeviceProp props{};
    SPOOLSTREAM_CUDA_CHECK(cudaGetDeviceProperties(&props, cuda_device_id));

    size_t free_vram = 0;
    size_t total_vram = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaMemGetInfo(&free_vram, &total_vram));

    HardwareProfile profile{};
    profile.cuda_device_id = cuda_device_id;
    profile.cuda_available = true;
    profile.device_name = props.name;
    profile.compute_capability_major = props.major;
    profile.compute_capability_minor = props.minor;
    profile.multiprocessor_count = props.multiProcessorCount;
    profile.total_vram_bytes = total_vram;
    profile.free_vram_bytes = free_vram;
    profile.total_host_ram_bytes = host_total_bytes();
    profile.free_host_ram_bytes = host_free_bytes();
    profile.estimated_h2d_bandwidth_gbps = conservative_h2d_bandwidth_gbps(props);
    return profile;
}

ExecutionPolicy plan_execution_policy(const ModelManifest& manifest,
                                      const HardwareProfile& hardware,
                                      const MemoryBudget& budget) {
    require_condition(manifest.config.num_hidden_layers > 0,
                      "manifest must describe at least one transformer layer");
    require_condition(hardware.cuda_available, "CUDA hardware profile is not available");
    require_condition(budget.max_vram_bytes > 0, "max_vram_bytes must be positive");
    require_condition(budget.max_host_staging_bytes > 0,
                      "max_host_staging_bytes must be positive");

    ExecutionPolicy policy{};
    if (manifest.config.family == ModelFamily::LLAMA) {
        policy.architecture_backend = "LLAMA";
    } else if (manifest.config.family == ModelFamily::QWEN2) {
        policy.architecture_backend = "QWEN2";
    } else {
        policy.architecture_backend = "UNKNOWN";
    }
    policy.streaming_required =
        manifest.total_streamable_bytes > budget.max_host_resident_bytes;
    policy.use_quantized_weights =
        manifest.config.quantization == ModelQuantization::AWQ_INT4 ||
        manifest.config.quantization == ModelQuantization::GPTQ_INT4;
    policy.use_paged_kv_cache = budget.kv_cache_bytes > 0;
    policy.use_speculative = false;
    policy.scratchpad_slot_bytes = manifest.topology.w_max_bytes;
    policy.host_staging_bytes =
        std::min(budget.max_host_staging_bytes,
                 std::max(manifest.max_tensor_bytes, static_cast<size_t>(1)));
    policy.host_resident_cap_bytes = budget.max_host_resident_bytes;
    policy.kv_cache_bytes = budget.kv_cache_bytes;

    std::vector<std::string> issues;
    if (policy.architecture_backend == "UNKNOWN") {
        issues.push_back("model architecture has no registered execution adapter");
    }
    if (hardware.compute_capability_major < 7) {
        issues.push_back("CUDA device compute capability is below the minimum runtime target");
    }
    if (manifest.topology.w_max_bytes == 0) {
        issues.push_back("manifest reports zero scratchpad slot size");
    }
    if (manifest.topology.w_max_bytes * 2U + budget.kv_cache_bytes > budget.max_vram_bytes) {
        issues.push_back("double-buffer scratchpad plus KV budget exceeds configured VRAM budget");
    }
    if (manifest.topology.w_max_bytes * 2U + budget.kv_cache_bytes > hardware.total_vram_bytes) {
        issues.push_back("double-buffer scratchpad plus KV budget exceeds physical VRAM");
    }
    if (manifest.max_tensor_bytes > budget.max_host_staging_bytes) {
        issues.push_back("largest tensor exceeds configured host staging window");
    }
    if (policy.streaming_required && budget.max_host_staging_bytes > hardware.free_host_ram_bytes) {
        issues.push_back("host staging budget exceeds currently available host RAM");
    }
    if (manifest.config.quantization == ModelQuantization::UNKNOWN) {
        issues.push_back("model quantization is unknown; execution will need an explicit adapter");
    }

    policy.supported = issues.empty();
    policy.reason = policy.supported
                        ? (policy.streaming_required ? "streaming execution policy selected"
                                                     : "host-resident execution policy possible")
                        : join_issues(issues);
    return policy;
}

CompatibilityReport assess_model_compatibility(const ModelManifest& manifest,
                                               const HardwareProfile& hardware,
                                               const MemoryBudget& budget) {
    CompatibilityReport report{};
    report.policy = plan_execution_policy(manifest, hardware, budget);
    report.compatible = report.policy.supported;
    if (!report.compatible) {
        std::string reason = report.policy.reason;
        size_t pos = 0;
        while (pos < reason.size()) {
            const size_t next = reason.find("; ", pos);
            report.issues.push_back(reason.substr(pos, next == std::string::npos ? next : next - pos));
            if (next == std::string::npos) {
                break;
            }
            pos = next + 2;
        }
    }
    return report;
}

} // namespace spoolstream::core
