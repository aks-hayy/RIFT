#include "spoolstream/layer_scheduler.h"
#include "spoolstream/memory_manager.h"

#include <cuda_runtime_api.h>

#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct TensorFixture {
    std::string name;
    std::string dtype;
    std::vector<int64_t> shape;
    std::vector<uint8_t> payload;
};

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_),
                                             sizeof(T) * count_));
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

std::filesystem::path make_case_dir(const std::string& name) {
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path root =
        std::filesystem::temp_directory_path() /
        ("spoolstream_scheduler_" + name + "_" + std::to_string(stamp));
    std::filesystem::create_directories(root);
    return root;
}

void write_u64_le(std::ofstream& out, uint64_t value) {
    for (size_t i = 0; i < 8; ++i) {
        const char byte = static_cast<char>((value >> (i * 8)) & 0xFFU);
        out.write(&byte, 1);
    }
}

std::string shape_json(const std::vector<int64_t>& shape) {
    std::string out = "[";
    for (size_t i = 0; i < shape.size(); ++i) {
        if (i != 0) {
            out += ",";
        }
        out += std::to_string(shape[i]);
    }
    out += "]";
    return out;
}

std::vector<uint8_t> make_payload(size_t byte_count, uint8_t seed) {
    std::vector<uint8_t> payload(byte_count);
    for (size_t i = 0; i < byte_count; ++i) {
        payload[i] = static_cast<uint8_t>((seed + i * 19U) & 0xFFU);
    }
    return payload;
}

void write_shard(const std::filesystem::path& path,
                 const std::vector<TensorFixture>& tensors) {
    std::string header = "{";
    size_t offset = 0;
    for (size_t i = 0; i < tensors.size(); ++i) {
        const TensorFixture& tensor = tensors[i];
        if (i != 0) {
            header += ",";
        }
        header += "\"" + tensor.name + "\":{\"dtype\":\"" + tensor.dtype +
                  "\",\"shape\":" + shape_json(tensor.shape) + ",\"data_offsets\":[" +
                  std::to_string(offset) + "," +
                  std::to_string(offset + tensor.payload.size()) + "]}";
        offset += tensor.payload.size();
    }
    header += "}";

    std::ofstream out(path, std::ios::binary);
    write_u64_le(out, static_cast<uint64_t>(header.size()));
    out.write(header.data(), static_cast<std::streamsize>(header.size()));
    for (const TensorFixture& tensor : tensors) {
        out.write(reinterpret_cast<const char*>(tensor.payload.data()),
                  static_cast<std::streamsize>(tensor.payload.size()));
    }
}

void write_index(const std::filesystem::path& dir,
                 const std::vector<std::pair<std::string, std::string>>& entries) {
    std::string json = "{\"metadata\":{\"total_size\":0},\"weight_map\":{";
    for (size_t i = 0; i < entries.size(); ++i) {
        if (i != 0) {
            json += ",";
        }
        json += "\"" + entries[i].first + "\":\"" + entries[i].second + "\"";
    }
    json += "}}";
    std::ofstream out(dir / "model.safetensors.index.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

void write_config(const std::filesystem::path& dir) {
    const std::string json =
        "{"
        "\"model_type\":\"llama\","
        "\"hidden_size\":8,"
        "\"intermediate_size\":16,"
        "\"num_hidden_layers\":2,"
        "\"num_attention_heads\":2,"
        "\"num_key_value_heads\":1,"
        "\"vocab_size\":16,"
        "\"quantization_config\":{\"quant_method\":\"gptq\"}"
        "}";
    std::ofstream out(dir / "config.json", std::ios::binary);
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

std::filesystem::path make_checkpoint() {
    const auto dir = make_case_dir("checkpoint");
    write_config(dir);
    const std::vector<TensorFixture> tensors = {
        {"model.layers.0.input_layernorm.weight", "F16", {8}, make_payload(16, 1)},
        {"model.layers.0.self_attn.q_proj.qweight", "I32", {4}, make_payload(16, 2)},
        {"model.layers.0.self_attn.q_proj.scales", "F16", {1, 8}, make_payload(16, 3)},
        {"model.layers.0.self_attn.q_proj.qzeros", "I32", {1}, make_payload(4, 4)},
        {"model.layers.1.post_attention_layernorm.weight", "F16", {8}, make_payload(16, 5)},
        {"model.layers.1.mlp.gate_proj.weight", "F16", {2, 8}, make_payload(32, 6)},
        {"model.layers.1.mlp.down_proj.weight", "F16", {2, 8}, make_payload(32, 7)},
    };
    write_shard(dir / "model.safetensors", tensors);
    std::vector<std::pair<std::string, std::string>> entries;
    for (const TensorFixture& tensor : tensors) {
        entries.emplace_back(tensor.name, "model.safetensors");
    }
    write_index(dir, entries);
    return dir;
}

std::vector<uint8_t> expected_payload_for_name(const std::string& name) {
    if (name.find("input_layernorm") != std::string::npos) {
        return make_payload(16, 1);
    }
    if (name.find("q_proj.qweight") != std::string::npos) {
        return make_payload(16, 2);
    }
    if (name.find("q_proj.scales") != std::string::npos) {
        return make_payload(16, 3);
    }
    if (name.find("q_proj.qzeros") != std::string::npos) {
        return make_payload(4, 4);
    }
    if (name.find("post_attention_layernorm") != std::string::npos) {
        return make_payload(16, 5);
    }
    if (name.find("gate_proj") != std::string::npos) {
        return make_payload(32, 6);
    }
    if (name.find("down_proj") != std::string::npos) {
        return make_payload(32, 7);
    }
    throw std::runtime_error("no expected payload for " + name);
}

void assert_slot_contains_plan(const std::vector<uint8_t>& slot,
                               const spoolstream::core::LayerExecutionPlan& plan) {
    for (const auto& placement : plan.placements) {
        const auto expected = expected_payload_for_name(placement.tensor->metadata.name);
        require_true(expected.size() == placement.byte_size, "expected payload size mismatch");
        require_true(placement.slot_offset + expected.size() <= slot.size(),
                     "placement exceeds host slot copy");
        require_true(std::memcmp(slot.data() + placement.slot_offset,
                                 expected.data(),
                                 expected.size()) == 0,
                     "slot payload mismatch for " + placement.tensor->metadata.name);
    }
}

void test_build_plans_and_prefetch_slots() {
    const auto dir = make_checkpoint();
    const auto manifest = spoolstream::core::build_model_manifest(dir, "STRICT", 512);
    const auto plans = spoolstream::core::build_layer_execution_plans(manifest, 128, 16);
    require_true(plans.layers.size() == 2, "expected two layer plans");
    const auto& layer0 = spoolstream::core::require_layer_plan(plans, 0);
    const auto& layer1 = spoolstream::core::require_layer_plan(plans, 1);
    require_true(layer0.placements.size() == 4, "layer0 placement count mismatch");
    require_true(layer1.placements.size() == 3, "layer1 placement count mismatch");
    require_true(layer0.placements[0].slot_offset == 0, "layer0 first offset mismatch");
    require_true(layer0.placements[1].slot_offset % 16 == 0, "layer0 alignment mismatch");
    require_true(layer0.total_bytes <= 128, "layer0 exceeds slot");

    auto store = spoolstream::core::create_streaming_tensor_store(dir, 64);
    DeviceBuffer<uint8_t> slot_a(128);
    DeviceBuffer<uint8_t> slot_b(128);
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot_a.get(), 0, 128));
    SPOOLSTREAM_CUDA_CHECK(cudaMemset(slot_b.get(), 0, 128));
    SPOOLSTREAM_CUDA_CHECK(cudaDeviceSynchronize());

    cudaStream_t stream = nullptr;
    SPOOLSTREAM_CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    auto transfer0 = spoolstream::core::schedule_layer_prefetch(store, layer0, slot_a.get(), stream);
    auto transfer1 = spoolstream::core::schedule_layer_prefetch(store, layer1, slot_b.get(), stream);
    spoolstream::core::wait_for_layer_transfer(transfer0);
    spoolstream::core::wait_for_layer_transfer(transfer1);
    require_true(transfer0.layer_id == 0 && transfer0.byte_count == layer0.total_bytes,
                 "layer0 transfer metadata mismatch");
    require_true(transfer1.layer_id == 1 && transfer1.byte_count == layer1.total_bytes,
                 "layer1 transfer metadata mismatch");

    const auto host_a = slot_a.copy_to_host();
    const auto host_b = slot_b.copy_to_host();
    assert_slot_contains_plan(host_a, layer0);
    assert_slot_contains_plan(host_b, layer1);

    spoolstream::core::destroy_scheduled_layer_transfer(transfer0);
    spoolstream::core::destroy_scheduled_layer_transfer(transfer1);
    SPOOLSTREAM_CUDA_CHECK(cudaStreamDestroy(stream));
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(dir);
}

void test_scheduler_rejections() {
    const auto dir = make_checkpoint();
    const auto manifest = spoolstream::core::build_model_manifest(dir, "STRICT", 512);
    require_throw([&]() {
        (void)spoolstream::core::build_layer_execution_plans(manifest, 16, 16);
    }, "slot too small");

    const auto plans = spoolstream::core::build_layer_execution_plans(manifest, 128, 16);
    require_throw([&]() {
        (void)spoolstream::core::require_layer_plan(plans, 99);
    }, "missing layer");

    auto store = spoolstream::core::create_streaming_tensor_store(dir, 8);
    DeviceBuffer<uint8_t> slot(128);
    const auto& layer0 = spoolstream::core::require_layer_plan(plans, 0);
    require_throw([&]() {
        auto transfer = spoolstream::core::schedule_layer_prefetch(store, layer0, slot.get());
        spoolstream::core::destroy_scheduled_layer_transfer(transfer);
    }, "staging too small");
    spoolstream::core::destroy_streaming_tensor_store(store);
    std::filesystem::remove_all(dir);
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_build_plans_and_prefetch_slots();
        test_scheduler_rejections();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream layer scheduler tests passed\n";
    return 0;
}
