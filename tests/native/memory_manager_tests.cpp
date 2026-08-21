#include "spoolstream/memory_manager.h"
#include "spoolstream/parser.h"

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

std::filesystem::path make_case_dir(const std::string& name) {
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path root =
        std::filesystem::temp_directory_path() /
        ("spoolstream_cuda_" + name + "_" + std::to_string(stamp));
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

void write_shard(const std::filesystem::path& path,
                 const std::vector<TensorFixture>& tensors) {
    std::string header = "{";
    size_t offset = 0;
    for (size_t i = 0; i < tensors.size(); ++i) {
        const TensorFixture& tensor = tensors[i];
        if (i != 0) {
            header += ",";
        }
        const size_t end = offset + tensor.payload.size();
        header += "\"" + tensor.name + "\":{\"dtype\":\"" + tensor.dtype +
                  "\",\"shape\":" + shape_json(tensor.shape) + ",\"data_offsets\":[" +
                  std::to_string(offset) + "," + std::to_string(end) + "]}";
        offset = end;
    }
    header += "}";

    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("unable to create shard fixture: " + path.string());
    }
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
    if (!out) {
        throw std::runtime_error("unable to create index fixture");
    }
    out.write(json.data(), static_cast<std::streamsize>(json.size()));
}

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

std::filesystem::path write_workspace_fixture() {
    const std::filesystem::path dir = make_case_dir("workspace");
    write_shard(dir / "model-00001-of-00002.safetensors",
                {{"model.layers.0.attn.q.weight", "U8", {16},
                  {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15}},
                 {"model.embed_tokens.weight", "U8", {16},
                  {90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105}}});
    write_shard(dir / "model-00002-of-00002.safetensors",
                {{"model.layers.1.mlp.down.weight", "U8", {16},
                  {30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45}}});
    write_index(dir,
                {{"model.layers.0.attn.q.weight", "model-00001-of-00002.safetensors"},
                 {"model.embed_tokens.weight", "model-00001-of-00002.safetensors"},
                 {"model.layers.1.mlp.down.weight", "model-00002-of-00002.safetensors"}});
    return dir;
}

void test_workspace_provision_and_destroy() {
    const std::filesystem::path dir = write_workspace_fixture();
    const auto topology = spoolstream::core::parse_model_topology(dir, "STRICT", 32);
    auto workspace = spoolstream::core::provision_execution_workspace(dir, topology, 0);

    require_true(workspace.slot_A != nullptr, "slot_A was not allocated");
    require_true(workspace.slot_B != nullptr, "slot_B was not allocated");
    require_true(workspace.slot_capacity == topology.w_max_bytes, "slot capacity mismatch");
    require_true(workspace.runtime_layers.size() == topology.layers.size(),
                 "runtime layer count mismatch");
    require_true(workspace.runtime_layers[0].tensors.size() == 1,
                 "runtime tensor count mismatch");
    require_true(workspace.runtime_layers[0].tensors[0].host_ptr != nullptr,
                 "host pinned pointer is null");
    require_true(workspace.runtime_layers[0].tensors[0].device_uva_ptr != nullptr,
                 "device UVA pointer is null");
    require_true(workspace.runtime_layers[0].tensors[0].byte_size == 16,
                 "runtime tensor byte size mismatch");

    const uint8_t expected_layer0[] =
        {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
    require_true(std::memcmp(workspace.runtime_layers[0].tensors[0].host_ptr,
                             expected_layer0,
                             sizeof(expected_layer0)) == 0,
                 "pinned host bytes do not match shard payload");

    spoolstream::core::destroy_execution_workspace(workspace);
    require_true(workspace.slot_A == nullptr, "slot_A was not nulled");
    require_true(workspace.slot_B == nullptr, "slot_B was not nulled");
    require_true(workspace.slot_capacity == 0, "slot_capacity was not cleared");
    require_true(workspace.runtime_layers.empty(), "runtime_layers was not cleared");
    spoolstream::core::destroy_execution_workspace(workspace);

    std::filesystem::remove_all(dir);
}

void test_invalid_device_failure() {
    const std::filesystem::path dir = write_workspace_fixture();
    const auto topology = spoolstream::core::parse_model_topology(dir, "STRICT", 32);

    int device_count = 0;
    spoolstream::core::detail::cuda_check(cudaGetDeviceCount(&device_count),
                                          "cudaGetDeviceCount(&device_count)",
                                          __FILE__,
                                          __LINE__);
    require_throw([&]() {
        spoolstream::core::provision_execution_workspace(dir, topology, device_count);
    }, "invalid CUDA device id");

    std::filesystem::remove_all(dir);
}

void test_tensor_offset_failure_during_materialization() {
    const std::filesystem::path dir = write_workspace_fixture();
    auto topology = spoolstream::core::parse_model_topology(dir, "STRICT", 32);
    topology.layers[0].tensors[0].end_offset =
        static_cast<size_t>(std::filesystem::file_size(dir / topology.layers[0].tensors[0].shard_file)) +
        1U;
    topology.layers[0].total_layer_bytes =
        topology.layers[0].tensors[0].end_offset - topology.layers[0].tensors[0].start_offset;
    topology.w_max_bytes = std::max(topology.w_max_bytes, topology.layers[0].total_layer_bytes);

    require_throw([&]() {
        spoolstream::core::provision_execution_workspace(dir, topology, 0);
    }, "tensor offset range mismatch");

    std::filesystem::remove_all(dir);
}

void test_insufficient_vram_failure() {
    const std::filesystem::path dir = make_case_dir("oversized");

    size_t free_bytes = 0;
    size_t total_bytes = 0;
    spoolstream::core::detail::cuda_check(cudaSetDevice(0), "cudaSetDevice(0)", __FILE__, __LINE__);
    spoolstream::core::detail::cuda_check(cudaMemGetInfo(&free_bytes, &total_bytes),
                                          "cudaMemGetInfo(&free_bytes, &total_bytes)",
                                          __FILE__,
                                          __LINE__);

    const size_t oversized_w_max = (free_bytes / 2U) + (1024U * 1024U);
    spoolstream::core::ModelTopology topology;
    topology.total_model_bytes = oversized_w_max;
    topology.w_max_bytes = oversized_w_max;
    topology.total_layers = 1;
    topology.memory_strategy = "STRICT";

    spoolstream::core::TensorMetaData tensor;
    tensor.name = "model.layers.0.synthetic.weight";
    tensor.shard_file = "missing.safetensors";
    tensor.start_offset = 0;
    tensor.end_offset = oversized_w_max;
    tensor.shape = {static_cast<int64_t>(oversized_w_max)};
    tensor.data_type = "U8";

    spoolstream::core::LayerGrouping layer;
    layer.layer_id = 0;
    layer.total_layer_bytes = oversized_w_max;
    layer.tensors.push_back(tensor);
    topology.layers.push_back(layer);

    require_throw([&]() {
        spoolstream::core::provision_execution_workspace(dir, topology, 0);
    }, "insufficient VRAM");

    std::filesystem::remove_all(dir);
}

} // namespace

int main() {
    try {
        test_workspace_provision_and_destroy();
        test_invalid_device_failure();
        test_tensor_offset_failure_during_materialization();
        test_insufficient_vram_failure();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream memory manager tests passed\n";
    return 0;
}
