#include "spoolstream/parser.h"

#include <chrono>
#include <cstdint>
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
    size_t bytes;
};

std::filesystem::path make_case_dir(const std::string& name) {
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    std::filesystem::path root =
        std::filesystem::temp_directory_path() /
        ("spoolstream_" + name + "_" + std::to_string(stamp));
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
                 const std::vector<TensorFixture>& tensors,
                 bool corrupt_first_span = false) {
    std::string header = "{";
    size_t offset = 0;
    for (size_t i = 0; i < tensors.size(); ++i) {
        const TensorFixture& tensor = tensors[i];
        if (i != 0) {
            header += ",";
        }
        const size_t span_end = offset + tensor.bytes + ((corrupt_first_span && i == 0) ? 1 : 0);
        header += "\"" + tensor.name + "\":{\"dtype\":\"" + tensor.dtype +
                  "\",\"shape\":" + shape_json(tensor.shape) + ",\"data_offsets\":[" +
                  std::to_string(offset) + "," + std::to_string(span_end) + "]}";
        offset += tensor.bytes;
    }
    header += "}";

    std::ofstream out(path, std::ios::binary);
    if (!out) {
        throw std::runtime_error("unable to create shard fixture: " + path.string());
    }
    write_u64_le(out, static_cast<uint64_t>(header.size()));
    out.write(header.data(), static_cast<std::streamsize>(header.size()));
    std::vector<char> payload(offset, '\0');
    out.write(payload.data(), static_cast<std::streamsize>(payload.size()));
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

void test_multi_shard_strict_and_adaptive_success() {
    const std::filesystem::path dir = make_case_dir("success");
    write_shard(dir / "model-00001-of-00002.safetensors",
                {{"model.layers.0.self_attn.q_proj.weight", "F16", {2, 4}, 16},
                 {"model.embed_tokens.weight", "F32", {50}, 200}});
    write_shard(dir / "model-00002-of-00002.safetensors",
                {{"model.layers.1.mlp.down_proj.weight", "F16", {2, 4}, 16}});
    write_index(dir,
                {{"model.layers.0.self_attn.q_proj.weight", "model-00001-of-00002.safetensors"},
                 {"model.embed_tokens.weight", "model-00001-of-00002.safetensors"},
                 {"model.layers.1.mlp.down_proj.weight", "model-00002-of-00002.safetensors"}});

    const auto strict =
        spoolstream::core::parse_model_topology(dir, "STRICT", 32);
    require_true(strict.total_model_bytes == 232, "strict total_model_bytes mismatch");
    require_true(strict.w_max_bytes == 16, "strict w_max_bytes mismatch");
    require_true(strict.total_layers == 2, "strict total_layers mismatch");
    require_true(strict.layers[0].layer_id == 0, "layer 0 id mismatch");
    require_true(strict.layers[1].layer_id == 1, "layer 1 id mismatch");
    require_true(strict.layers[0].total_layer_bytes == 16, "layer 0 bytes mismatch");
    require_true(strict.layers[0].tensors[0].start_offset < strict.layers[0].tensors[0].end_offset,
                 "physical offsets were not populated");

    const auto adaptive =
        spoolstream::core::parse_model_topology(dir, "ADAPTIVE");
    require_true(adaptive.total_model_bytes == 232, "adaptive total_model_bytes mismatch");
    require_true(adaptive.memory_strategy == "ADAPTIVE", "adaptive strategy mismatch");

    std::filesystem::remove_all(dir);
}

void test_single_shard_without_index_success() {
    const std::filesystem::path dir = make_case_dir("single_shard_no_index");
    write_shard(dir / "model.safetensors",
                {{"model.layers.0.self_attn.q_proj.weight", "BF16", {2, 4}, 16},
                 {"model.layers.1.mlp.down_proj.weight", "F16", {2, 4}, 16},
                 {"model.embed_tokens.weight", "F16", {8, 4}, 64}});

    const auto topology = spoolstream::core::parse_model_topology(dir, "STRICT", 64);
    require_true(topology.total_model_bytes == 96, "single shard total_model_bytes mismatch");
    require_true(topology.w_max_bytes == 16, "single shard w_max_bytes mismatch");
    require_true(topology.total_layers == 2, "single shard layer count mismatch");
    require_true(topology.tensors.size() == 3, "single shard tensor count mismatch");
    require_true(topology.layers[0].tensors[0].shard_file == "model.safetensors",
                 "single shard file mapping mismatch");

    std::filesystem::remove_all(dir);
}

void test_adaptive_guardrail_failure() {
    const std::filesystem::path dir = make_case_dir("adaptive_fail");
    write_shard(dir / "model.safetensors",
                {{"model.layers.0.weight", "F16", {2, 4}, 16},
                 {"model.layers.1.weight", "F16", {2, 4}, 16}});
    write_index(dir,
                {{"model.layers.0.weight", "model.safetensors"},
                 {"model.layers.1.weight", "model.safetensors"}});

    require_throw([&]() { spoolstream::core::parse_model_topology(dir, "ADAPTIVE"); },
                  "adaptive 20 percent guardrail");
    std::filesystem::remove_all(dir);
}

void test_shape_offset_mismatch_failure() {
    const std::filesystem::path dir = make_case_dir("shape_mismatch");
    write_shard(dir / "model.safetensors",
                {{"model.layers.0.weight", "F16", {2, 4}, 16}},
                true);
    write_index(dir, {{"model.layers.0.weight", "model.safetensors"}});

    require_throw([&]() { spoolstream::core::parse_model_topology(dir, "STRICT", 64); },
                  "shape and offset mismatch");
    std::filesystem::remove_all(dir);
}

void test_missing_tensor_failure() {
    const std::filesystem::path dir = make_case_dir("missing_tensor");
    write_shard(dir / "model.safetensors",
                {{"model.layers.0.weight", "F16", {2, 4}, 16}});
    write_index(dir,
                {{"model.layers.0.weight", "model.safetensors"},
                 {"model.layers.1.weight", "model.safetensors"}});

    require_throw([&]() { spoolstream::core::parse_model_topology(dir, "STRICT", 64); },
                  "tensor absent from shard");
    std::filesystem::remove_all(dir);
}

void test_non_contiguous_layers_failure() {
    const std::filesystem::path dir = make_case_dir("non_contiguous");
    write_shard(dir / "model.safetensors",
                {{"model.layers.0.weight", "F16", {2, 4}, 16},
                 {"model.layers.2.weight", "F16", {2, 4}, 16}});
    write_index(dir,
                {{"model.layers.0.weight", "model.safetensors"},
                 {"model.layers.2.weight", "model.safetensors"}});

    require_throw([&]() { spoolstream::core::parse_model_topology(dir, "STRICT", 64); },
                  "non-contiguous layer ids");
    std::filesystem::remove_all(dir);
}

} // namespace

int main() {
    try {
        test_multi_shard_strict_and_adaptive_success();
        test_single_shard_without_index_success();
        test_adaptive_guardrail_failure();
        test_shape_offset_mismatch_failure();
        test_missing_tensor_failure();
        test_non_contiguous_layers_failure();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream parser tests passed\n";
    return 0;
}
