#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace spoolstream::core {

struct TensorMetaData {
    std::string name;
    std::string shard_file;
    size_t start_offset;
    size_t end_offset;
    std::vector<int64_t> shape;
    std::string data_type;
};

struct LayerGrouping {
    int layer_id;
    size_t total_layer_bytes;
    std::vector<TensorMetaData> tensors;
};

struct ModelTopology {
    size_t total_model_bytes;
    size_t w_max_bytes;
    int total_layers;
    std::string memory_strategy; // "STRICT" or "ADAPTIVE"
    std::vector<TensorMetaData> tensors;
    std::vector<LayerGrouping> layers;
};

constexpr size_t kDefaultStrictScratchpadBytes =
    static_cast<size_t>(20) * 1024ULL * 1024ULL * 1024ULL;

ModelTopology parse_model_topology(
    const std::filesystem::path& checkpoint_directory,
    const std::string& memory_strategy,
    size_t strict_scratchpad_bytes = kDefaultStrictScratchpadBytes);

} // namespace spoolstream::core
