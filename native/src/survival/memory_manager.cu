#include "spoolstream/memory_manager.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#else
#include <sched.h>
#include <unistd.h>
#endif

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream memory manager validation failed: " + message);
}

void require_condition(bool condition, const std::string& message) {
    if (!condition) {
        fail(message);
    }
}

size_t checked_add(size_t lhs, size_t rhs, const std::string& context) {
    require_condition(lhs <= std::numeric_limits<size_t>::max() - rhs,
                      "size overflow while adding " + context);
    return lhs + rhs;
}

size_t checked_mul(size_t lhs, size_t rhs, const std::string& context) {
    if (lhs == 0 || rhs == 0) {
        return 0;
    }
    require_condition(lhs <= std::numeric_limits<size_t>::max() / rhs,
                      "size overflow while multiplying " + context);
    return lhs * rhs;
}

std::string cuda_error_message(cudaError_t status,
                               const char* expression,
                               const char* file,
                               int line) {
    std::ostringstream out;
    out << "CUDA call failed at " << file << ':' << line << " expression `" << expression
        << "` status=" << static_cast<int>(status) << " (" << cudaGetErrorString(status)
        << ')';
    return out.str();
}

#if defined(_WIN32)
class AffinityScope {
public:
    explicit AffinityScope(const std::string&) {
        ULONG highest_node = 0;
        if (!GetNumaHighestNodeNumber(&highest_node)) {
            return;
        }
        if (highest_node > 0) {
            return;
        }

        GROUP_AFFINITY node_affinity;
        std::memset(&node_affinity, 0, sizeof(node_affinity));
        if (!GetNumaNodeProcessorMaskEx(0, &node_affinity) || node_affinity.Mask == 0) {
            return;
        }

        if (SetThreadGroupAffinity(GetCurrentThread(), &node_affinity, &previous_affinity_)) {
            changed_ = true;
        }
    }

    AffinityScope(const AffinityScope&) = delete;
    AffinityScope& operator=(const AffinityScope&) = delete;

    ~AffinityScope() {
        if (changed_) {
            GROUP_AFFINITY ignored;
            std::memset(&ignored, 0, sizeof(ignored));
            SetThreadGroupAffinity(GetCurrentThread(), &previous_affinity_, &ignored);
        }
    }

private:
    GROUP_AFFINITY previous_affinity_{};
    bool changed_ = false;
};
#else
std::string normalize_linux_bus_id(const std::string& bus_id) {
    if (bus_id.size() == 12 && bus_id[4] == ':' && bus_id[7] == ':' && bus_id[10] == '.') {
        return bus_id;
    }
    if (bus_id.size() == 16 && bus_id[8] == ':' && bus_id[11] == ':' && bus_id[14] == '.') {
        return bus_id.substr(4);
    }
    return bus_id;
}

std::optional<int> read_linux_numa_node(const std::string& bus_id) {
    const std::filesystem::path numa_path =
        std::filesystem::path("/sys/bus/pci/devices") / normalize_linux_bus_id(bus_id) / "numa_node";
    std::ifstream in(numa_path);
    if (!in) {
        return std::nullopt;
    }
    int node = -1;
    in >> node;
    if (!in || node < 0) {
        return std::nullopt;
    }
    return node;
}

void add_cpu_range(cpu_set_t& set, int start_cpu, int end_cpu) {
    require_condition(start_cpu >= 0 && end_cpu >= start_cpu,
                      "invalid Linux NUMA CPU range");
    for (int cpu = start_cpu; cpu <= end_cpu; ++cpu) {
        CPU_SET(cpu, &set);
    }
}

bool parse_linux_cpu_list(const std::string& text, cpu_set_t& set) {
    CPU_ZERO(&set);
    size_t pos = 0;
    bool any = false;
    while (pos < text.size()) {
        while (pos < text.size() && (text[pos] == ',' || text[pos] == '\n' ||
                                     text[pos] == '\r' || text[pos] == ' ' ||
                                     text[pos] == '\t')) {
            ++pos;
        }
        if (pos >= text.size()) {
            break;
        }
        require_condition(std::isdigit(static_cast<unsigned char>(text[pos])),
                          "invalid Linux NUMA CPU list");
        int start_cpu = 0;
        while (pos < text.size() && std::isdigit(static_cast<unsigned char>(text[pos]))) {
            start_cpu = start_cpu * 10 + (text[pos] - '0');
            ++pos;
        }
        int end_cpu = start_cpu;
        if (pos < text.size() && text[pos] == '-') {
            ++pos;
            require_condition(pos < text.size() &&
                                  std::isdigit(static_cast<unsigned char>(text[pos])),
                              "invalid Linux NUMA CPU range");
            end_cpu = 0;
            while (pos < text.size() && std::isdigit(static_cast<unsigned char>(text[pos]))) {
                end_cpu = end_cpu * 10 + (text[pos] - '0');
                ++pos;
            }
        }
        add_cpu_range(set, start_cpu, end_cpu);
        any = true;
        while (pos < text.size() && text[pos] != ',') {
            if (text[pos] == '\n' || text[pos] == '\r' || text[pos] == ' ' || text[pos] == '\t') {
                ++pos;
            } else {
                break;
            }
        }
    }
    return any;
}

class AffinityScope {
public:
    explicit AffinityScope(const std::string& bus_id) {
        const std::optional<int> numa_node = read_linux_numa_node(bus_id);
        if (!numa_node.has_value()) {
            return;
        }

        const std::filesystem::path cpu_list_path =
            std::filesystem::path("/sys/devices/system/node") /
            ("node" + std::to_string(*numa_node)) / "cpulist";
        std::ifstream in(cpu_list_path);
        if (!in) {
            return;
        }
        std::string cpu_list;
        std::getline(in, cpu_list);

        cpu_set_t target_set;
        if (!parse_linux_cpu_list(cpu_list, target_set)) {
            return;
        }
        if (sched_getaffinity(0, sizeof(previous_set_), &previous_set_) != 0) {
            return;
        }
        if (sched_setaffinity(0, sizeof(target_set), &target_set) == 0) {
            changed_ = true;
        }
    }

    AffinityScope(const AffinityScope&) = delete;
    AffinityScope& operator=(const AffinityScope&) = delete;

    ~AffinityScope() {
        if (changed_) {
            sched_setaffinity(0, sizeof(previous_set_), &previous_set_);
        }
    }

private:
    cpu_set_t previous_set_{};
    bool changed_ = false;
};
#endif

std::vector<uint8_t> read_file_range(const std::filesystem::path& file_path,
                                     size_t start_offset,
                                     size_t end_offset) {
    require_condition(start_offset <= end_offset,
                      "tensor file range has inverted offsets: " + file_path.string());
    const size_t byte_size = end_offset - start_offset;
    require_condition(std::filesystem::exists(file_path),
                      "tensor shard does not exist: " + file_path.string());
    require_condition(std::filesystem::is_regular_file(file_path),
                      "tensor shard path is not a regular file: " + file_path.string());

    const uintmax_t file_size_u64 = std::filesystem::file_size(file_path);
    require_condition(file_size_u64 <= static_cast<uintmax_t>(std::numeric_limits<size_t>::max()),
                      "tensor shard is too large for this process: " + file_path.string());
    const size_t file_size = static_cast<size_t>(file_size_u64);
    require_condition(end_offset <= file_size,
                      "tensor file range exceeds shard size: " + file_path.string());

    std::vector<uint8_t> bytes(byte_size);
    if (byte_size == 0) {
        return bytes;
    }

    std::ifstream in(file_path, std::ios::binary);
    require_condition(static_cast<bool>(in),
                      "unable to open tensor shard: " + file_path.string());
    in.seekg(static_cast<std::streamoff>(start_offset), std::ios::beg);
    require_condition(static_cast<bool>(in),
                      "unable to seek tensor shard: " + file_path.string());
    in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(byte_size));
    require_condition(in.gcount() == static_cast<std::streamsize>(byte_size),
                      "short read while materializing tensor: " + file_path.string());
    return bytes;
}

void validate_topology_for_workspace(const ModelTopology& topology) {
    require_condition(topology.w_max_bytes > 0,
                      "topology.w_max_bytes must be non-zero");
    require_condition(topology.total_layers > 0,
                      "topology.total_layers must be positive");
    require_condition(static_cast<size_t>(topology.total_layers) == topology.layers.size(),
                      "topology.total_layers does not match layers.size()");
    for (const LayerGrouping& layer : topology.layers) {
        require_condition(layer.total_layer_bytes > 0,
                          "runtime layer byte size must be non-zero");
        size_t accumulated = 0;
        for (const TensorMetaData& tensor : layer.tensors) {
            require_condition(!tensor.name.empty(), "runtime tensor name cannot be empty");
            require_condition(!tensor.shard_file.empty(),
                              "runtime tensor shard file cannot be empty");
            require_condition(tensor.start_offset < tensor.end_offset,
                              "runtime tensor offsets must describe a non-empty span");
            accumulated = checked_add(accumulated, tensor.end_offset - tensor.start_offset,
                                      "runtime layer tensor byte total");
        }
        require_condition(accumulated == layer.total_layer_bytes,
                          "runtime layer byte size does not match tensor byte spans");
        require_condition(layer.total_layer_bytes <= topology.w_max_bytes,
                          "runtime layer exceeds topology.w_max_bytes");
    }
}

void check_cuda_device(int cuda_device_id, std::string& pci_bus_id_out) {
    int device_count = 0;
    SPOOLSTREAM_CUDA_CHECK(cudaGetDeviceCount(&device_count));
    require_condition(device_count > 0, "no CUDA-capable devices are visible");
    require_condition(cuda_device_id >= 0 && cuda_device_id < device_count,
                      "invalid CUDA device id " + std::to_string(cuda_device_id) +
                          "; visible device count is " + std::to_string(device_count));

    SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(cuda_device_id));

    cudaDeviceProp properties{};
    SPOOLSTREAM_CUDA_CHECK(cudaGetDeviceProperties(&properties, cuda_device_id));
    require_condition(properties.canMapHostMemory != 0,
                      "selected CUDA device does not support mapped host memory");
    require_condition(properties.unifiedAddressing != 0,
                      "selected CUDA device does not support unified virtual addressing");

    char bus_id[64] = {};
    SPOOLSTREAM_CUDA_CHECK(cudaDeviceGetPCIBusId(bus_id, sizeof(bus_id), cuda_device_id));
    require_condition(bus_id[0] != '\0',
                      "cudaDeviceGetPCIBusId returned an empty PCI bus identifier");
    pci_bus_id_out = bus_id;
}

RuntimeTensor materialize_tensor(const std::filesystem::path& checkpoint_dir,
                                 const TensorMetaData& tensor) {
    const size_t byte_size = tensor.end_offset - tensor.start_offset;
    const std::filesystem::path shard_path = checkpoint_dir / tensor.shard_file;
    const std::vector<uint8_t> bytes =
        read_file_range(shard_path, tensor.start_offset, tensor.end_offset);
    require_condition(bytes.size() == byte_size,
                      "materialized tensor byte count mismatch for " + tensor.name);

    RuntimeTensor runtime_tensor;
    runtime_tensor.name = tensor.name;
    runtime_tensor.host_ptr = nullptr;
    runtime_tensor.device_uva_ptr = nullptr;
    runtime_tensor.byte_size = byte_size;

    SPOOLSTREAM_CUDA_CHECK(cudaHostAlloc(&runtime_tensor.host_ptr,
                                         runtime_tensor.byte_size,
                                         cudaHostAllocPortable | cudaHostAllocMapped));
    require_condition(runtime_tensor.host_ptr != nullptr,
                      "cudaHostAlloc returned null for tensor " + tensor.name);

    std::memcpy(runtime_tensor.host_ptr, bytes.data(), runtime_tensor.byte_size);

    SPOOLSTREAM_CUDA_CHECK(cudaHostGetDevicePointer(&runtime_tensor.device_uva_ptr,
                                                    runtime_tensor.host_ptr,
                                                    0));
    require_condition(runtime_tensor.device_uva_ptr != nullptr,
                      "cudaHostGetDevicePointer returned null for tensor " + tensor.name);
    return runtime_tensor;
}

} // namespace

namespace detail {

void cuda_check(cudaError_t status,
                const char* expression,
                const char* file,
                int line) {
    if (status != cudaSuccess) {
        throw std::runtime_error(cuda_error_message(status, expression, file, line));
    }
}

} // namespace detail

ExecutionWorkspace provision_execution_workspace(const std::filesystem::path& checkpoint_dir,
                                                 const ModelTopology& topology,
                                                 int cuda_device_id) {
    require_condition(std::filesystem::exists(checkpoint_dir),
                      "checkpoint directory does not exist: " + checkpoint_dir.string());
    require_condition(std::filesystem::is_directory(checkpoint_dir),
                      "checkpoint path is not a directory: " + checkpoint_dir.string());
    validate_topology_for_workspace(topology);

    ExecutionWorkspace workspace;
    workspace.slot_A = nullptr;
    workspace.slot_B = nullptr;
    workspace.slot_capacity = 0;

    try {
        std::string pci_bus_id;
        check_cuda_device(cuda_device_id, pci_bus_id);
        AffinityScope affinity_scope(pci_bus_id);

        size_t free_bytes = 0;
        size_t total_bytes = 0;
        SPOOLSTREAM_CUDA_CHECK(cudaMemGetInfo(&free_bytes, &total_bytes));
        const size_t required_scratch_bytes =
            checked_mul(2, topology.w_max_bytes, "double scratchpad capacity");
        require_condition(free_bytes >= required_scratch_bytes,
                          "insufficient free VRAM for execution workspace: required " +
                              std::to_string(required_scratch_bytes) + " bytes, free " +
                              std::to_string(free_bytes) + " bytes");

        workspace.slot_capacity = topology.w_max_bytes;
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(&workspace.slot_A, workspace.slot_capacity));
        require_condition(workspace.slot_A != nullptr,
                          "cudaMalloc returned null for scratchpad slot_A");
        SPOOLSTREAM_CUDA_CHECK(cudaMalloc(&workspace.slot_B, workspace.slot_capacity));
        require_condition(workspace.slot_B != nullptr,
                          "cudaMalloc returned null for scratchpad slot_B");

        workspace.runtime_layers.reserve(topology.layers.size());
        for (const LayerGrouping& layer : topology.layers) {
            RuntimeLayer runtime_layer;
            runtime_layer.layer_id = layer.layer_id;
            runtime_layer.byte_size = layer.total_layer_bytes;
            runtime_layer.tensors.reserve(layer.tensors.size());

            for (const TensorMetaData& tensor : layer.tensors) {
                runtime_layer.tensors.push_back(materialize_tensor(checkpoint_dir, tensor));
            }

            workspace.runtime_layers.push_back(std::move(runtime_layer));
        }

        return workspace;
    } catch (...) {
        destroy_execution_workspace(workspace);
        throw;
    }
}

void destroy_execution_workspace(ExecutionWorkspace& workspace) noexcept {
    for (RuntimeLayer& layer : workspace.runtime_layers) {
        for (RuntimeTensor& tensor : layer.tensors) {
            if (tensor.host_ptr != nullptr) {
                cudaFreeHost(tensor.host_ptr);
            }
            tensor.host_ptr = nullptr;
            tensor.device_uva_ptr = nullptr;
            tensor.byte_size = 0;
            tensor.name.clear();
        }
        layer.tensors.clear();
        layer.layer_id = 0;
        layer.byte_size = 0;
    }
    workspace.runtime_layers.clear();

    if (workspace.slot_A != nullptr) {
        cudaFree(workspace.slot_A);
        workspace.slot_A = nullptr;
    }
    if (workspace.slot_B != nullptr) {
        cudaFree(workspace.slot_B);
        workspace.slot_B = nullptr;
    }
    workspace.slot_capacity = 0;
}

} // namespace spoolstream::core
