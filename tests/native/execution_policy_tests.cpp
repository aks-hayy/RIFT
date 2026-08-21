#include "spoolstream/execution_policy.h"
#include "spoolstream/memory_manager.h"

#include <cuda_runtime_api.h>

#include <iostream>
#include <stdexcept>
#include <string>

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

spoolstream::core::ModelManifest make_manifest(size_t total_bytes,
                                               size_t slot_bytes,
                                               size_t max_tensor_bytes,
                                               spoolstream::core::ModelQuantization quantization =
                                                   spoolstream::core::ModelQuantization::AWQ_INT4) {
    spoolstream::core::ModelManifest manifest{};
    manifest.config.family = spoolstream::core::ModelFamily::LLAMA;
    manifest.config.quantization = quantization;
    manifest.config.hidden_size = 4096;
    manifest.config.intermediate_size = 11008;
    manifest.config.num_hidden_layers = 32;
    manifest.config.num_attention_heads = 32;
    manifest.config.num_key_value_heads = 8;
    manifest.config.vocab_size = 32000;
    manifest.config.max_position_embeddings = 4096;
    manifest.config.rope_theta = 10000.0;
    manifest.config.rms_norm_eps = 1.0e-6;
    manifest.config.model_type = "llama";
    manifest.topology.total_model_bytes = total_bytes;
    manifest.topology.w_max_bytes = slot_bytes;
    manifest.topology.total_layers = 32;
    manifest.topology.memory_strategy = "ADAPTIVE";
    manifest.total_streamable_bytes = total_bytes;
    manifest.max_tensor_bytes = max_tensor_bytes;
    return manifest;
}

spoolstream::core::HardwareProfile synthetic_hardware(size_t total_vram,
                                                      size_t free_host_ram,
                                                      int major = 8) {
    spoolstream::core::HardwareProfile hardware{};
    hardware.cuda_device_id = 0;
    hardware.cuda_available = true;
    hardware.device_name = "Synthetic CUDA PC";
    hardware.compute_capability_major = major;
    hardware.compute_capability_minor = 9;
    hardware.multiprocessor_count = 24;
    hardware.total_vram_bytes = total_vram;
    hardware.free_vram_bytes = total_vram / 2U;
    hardware.total_host_ram_bytes = 16ULL * 1024ULL * 1024ULL * 1024ULL;
    hardware.free_host_ram_bytes = free_host_ram;
    hardware.estimated_h2d_bandwidth_gbps = 16.0;
    return hardware;
}

void test_real_hardware_profile() {
    const auto profile = spoolstream::core::build_hardware_profile(0);
    require_true(profile.cuda_available, "CUDA should be available");
    require_true(!profile.device_name.empty(), "device name should be populated");
    require_true(profile.total_vram_bytes > 0, "total VRAM should be positive");
    require_true(profile.total_host_ram_bytes > 0, "host RAM should be positive");
    require_true(profile.estimated_h2d_bandwidth_gbps > 0.0,
                 "bandwidth estimate should be positive");
}

void test_execution_policy_supported_streaming() {
    const auto manifest = make_manifest(20ULL * 1024ULL * 1024ULL * 1024ULL,
                                        512ULL * 1024ULL * 1024ULL,
                                        96ULL * 1024ULL * 1024ULL);
    const auto hardware = synthetic_hardware(8ULL * 1024ULL * 1024ULL * 1024ULL,
                                             6ULL * 1024ULL * 1024ULL * 1024ULL);
    spoolstream::core::MemoryBudget budget{};
    budget.max_vram_bytes = 6ULL * 1024ULL * 1024ULL * 1024ULL;
    budget.max_host_staging_bytes = 256ULL * 1024ULL * 1024ULL;
    budget.max_host_resident_bytes = 2ULL * 1024ULL * 1024ULL * 1024ULL;
    budget.kv_cache_bytes = 512ULL * 1024ULL * 1024ULL;

    const auto policy = spoolstream::core::plan_execution_policy(manifest, hardware, budget);
    require_true(policy.supported, "policy should be supported: " + policy.reason);
    require_true(policy.streaming_required, "streaming should be required");
    require_true(policy.use_quantized_weights, "quantized weights should be selected");
    require_true(policy.architecture_backend == "LLAMA", "backend should be LLAMA");
    require_true(policy.scratchpad_slot_bytes == manifest.topology.w_max_bytes,
                 "slot size mismatch");
}

void test_execution_policy_rejections() {
    auto manifest = make_manifest(20ULL * 1024ULL * 1024ULL * 1024ULL,
                                  4ULL * 1024ULL * 1024ULL * 1024ULL,
                                  96ULL * 1024ULL * 1024ULL);
    const auto low_vram = synthetic_hardware(6ULL * 1024ULL * 1024ULL * 1024ULL,
                                             4ULL * 1024ULL * 1024ULL * 1024ULL);
    spoolstream::core::MemoryBudget budget{};
    budget.max_vram_bytes = 6ULL * 1024ULL * 1024ULL * 1024ULL;
    budget.max_host_staging_bytes = 256ULL * 1024ULL * 1024ULL;
    budget.max_host_resident_bytes = 2ULL * 1024ULL * 1024ULL * 1024ULL;
    budget.kv_cache_bytes = 512ULL * 1024ULL * 1024ULL;

    auto report = spoolstream::core::assess_model_compatibility(manifest, low_vram, budget);
    require_true(!report.compatible, "oversized scratchpad should be incompatible");
    require_true(!report.issues.empty(), "incompatible report should include issues");

    manifest = make_manifest(20ULL * 1024ULL * 1024ULL * 1024ULL,
                             512ULL * 1024ULL * 1024ULL,
                             768ULL * 1024ULL * 1024ULL);
    report = spoolstream::core::assess_model_compatibility(manifest, low_vram, budget);
    require_true(!report.compatible, "oversized tensor should be incompatible");

    const auto old_gpu = synthetic_hardware(12ULL * 1024ULL * 1024ULL * 1024ULL,
                                            4ULL * 1024ULL * 1024ULL * 1024ULL,
                                            6);
    manifest = make_manifest(4ULL * 1024ULL * 1024ULL * 1024ULL,
                             256ULL * 1024ULL * 1024ULL,
                             64ULL * 1024ULL * 1024ULL);
    report = spoolstream::core::assess_model_compatibility(manifest, old_gpu, budget);
    require_true(!report.compatible, "old compute capability should be incompatible");

    require_throw([&]() {
        (void)spoolstream::core::build_hardware_profile(-1);
    }, "invalid device id");
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_real_hardware_profile();
        test_execution_policy_supported_streaming();
        test_execution_policy_rejections();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream execution policy tests passed\n";
    return 0;
}
