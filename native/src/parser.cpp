#include "spoolstream/parser.h"

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <limits>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string_view>

#if defined(_WIN32)
#define NOMINMAX
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace spoolstream::core {
namespace {

[[noreturn]] void fail(const std::string& message) {
    throw std::runtime_error("SpoolStream parser validation failed: " + message);
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

class MappedFile {
public:
    explicit MappedFile(const std::filesystem::path& path) : path_(path) {
#if defined(_WIN32)
        file_ = CreateFileW(path_.wstring().c_str(), GENERIC_READ, FILE_SHARE_READ,
                            nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
        require_condition(file_ != INVALID_HANDLE_VALUE,
                          "unable to open file: " + path_.string());

        LARGE_INTEGER file_size;
        require_condition(GetFileSizeEx(file_, &file_size) != 0,
                          "unable to query file size: " + path_.string());
        require_condition(file_size.QuadPart > 0,
                          "mapped file is empty: " + path_.string());
        require_condition(static_cast<unsigned long long>(file_size.QuadPart) <=
                              static_cast<unsigned long long>(std::numeric_limits<size_t>::max()),
                          "mapped file is too large for this process: " + path_.string());
        size_ = static_cast<size_t>(file_size.QuadPart);

        mapping_ = CreateFileMappingW(file_, nullptr, PAGE_READONLY, 0, 0, nullptr);
        require_condition(mapping_ != nullptr,
                          "unable to create read-only file mapping: " + path_.string());

        data_ = MapViewOfFile(mapping_, FILE_MAP_READ, 0, 0, 0);
        require_condition(data_ != nullptr,
                          "unable to map read-only file view: " + path_.string());
#else
        fd_ = open(path_.c_str(), O_RDONLY);
        require_condition(fd_ >= 0, "unable to open file: " + path_.string() +
                                      " errno=" + std::to_string(errno));

        struct stat st;
        require_condition(fstat(fd_, &st) == 0,
                          "unable to stat file: " + path_.string());
        require_condition(st.st_size > 0, "mapped file is empty: " + path_.string());
        require_condition(static_cast<unsigned long long>(st.st_size) <=
                              static_cast<unsigned long long>(std::numeric_limits<size_t>::max()),
                          "mapped file is too large for this process: " + path_.string());
        size_ = static_cast<size_t>(st.st_size);

        data_ = mmap(nullptr, size_, PROT_READ, MAP_SHARED, fd_, 0);
        require_condition(data_ != MAP_FAILED,
                          "unable to mmap file: " + path_.string());
#endif
    }

    MappedFile(const MappedFile&) = delete;
    MappedFile& operator=(const MappedFile&) = delete;

    MappedFile(MappedFile&& other) noexcept {
        move_from(other);
    }

    MappedFile& operator=(MappedFile&& other) noexcept {
        if (this != &other) {
            cleanup();
            move_from(other);
        }
        return *this;
    }

    ~MappedFile() {
        cleanup();
    }

    const uint8_t* bytes() const {
        return static_cast<const uint8_t*>(data_);
    }

    const char* chars() const {
        return static_cast<const char*>(data_);
    }

    size_t size() const {
        return size_;
    }

private:
    void move_from(MappedFile& other) noexcept {
        path_ = std::move(other.path_);
        data_ = other.data_;
        size_ = other.size_;
        other.data_ = nullptr;
        other.size_ = 0;
#if defined(_WIN32)
        file_ = other.file_;
        mapping_ = other.mapping_;
        other.file_ = INVALID_HANDLE_VALUE;
        other.mapping_ = nullptr;
#else
        fd_ = other.fd_;
        other.fd_ = -1;
#endif
    }

    void cleanup() noexcept {
#if defined(_WIN32)
        if (data_ != nullptr) {
            UnmapViewOfFile(data_);
            data_ = nullptr;
        }
        if (mapping_ != nullptr) {
            CloseHandle(mapping_);
            mapping_ = nullptr;
        }
        if (file_ != INVALID_HANDLE_VALUE) {
            CloseHandle(file_);
            file_ = INVALID_HANDLE_VALUE;
        }
#else
        if (data_ != nullptr && data_ != MAP_FAILED) {
            munmap(data_, size_);
            data_ = nullptr;
        }
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }
#endif
        size_ = 0;
    }

    std::filesystem::path path_;
    void* data_ = nullptr;
    size_t size_ = 0;
#if defined(_WIN32)
    HANDLE file_ = INVALID_HANDLE_VALUE;
    HANDLE mapping_ = nullptr;
#else
    int fd_ = -1;
#endif
};

enum class JsonType {
    Null,
    Bool,
    Number,
    String,
    Array,
    Object
};

struct JsonValue {
    JsonType type = JsonType::Null;
    bool boolean = false;
    std::string number;
    std::string string;
    std::vector<JsonValue> array;
    std::map<std::string, JsonValue> object;
};

class JsonParser {
public:
    JsonParser(std::string_view source, std::string source_name)
        : source_(source), source_name_(std::move(source_name)) {}

    JsonValue parse() {
        JsonValue value = parse_value(0);
        skip_ws();
        require_condition(pos_ == source_.size(),
                          source_name_ + ": trailing bytes after JSON document at offset " +
                              std::to_string(pos_));
        return value;
    }

private:
    JsonValue parse_value(size_t depth) {
        require_condition(depth < 128, source_name_ + ": JSON nesting exceeds 128 levels");
        skip_ws();
        require_condition(pos_ < source_.size(),
                          source_name_ + ": unexpected end of JSON document");
        const char c = source_[pos_];
        if (c == '{') {
            return parse_object(depth + 1);
        }
        if (c == '[') {
            return parse_array(depth + 1);
        }
        if (c == '"') {
            JsonValue value;
            value.type = JsonType::String;
            value.string = parse_string();
            return value;
        }
        if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) {
            JsonValue value;
            value.type = JsonType::Number;
            value.number = parse_number();
            return value;
        }
        if (consume_literal("true")) {
            JsonValue value;
            value.type = JsonType::Bool;
            value.boolean = true;
            return value;
        }
        if (consume_literal("false")) {
            JsonValue value;
            value.type = JsonType::Bool;
            value.boolean = false;
            return value;
        }
        if (consume_literal("null")) {
            JsonValue value;
            value.type = JsonType::Null;
            return value;
        }
        fail(source_name_ + ": unexpected JSON token at offset " + std::to_string(pos_));
    }

    JsonValue parse_object(size_t depth) {
        JsonValue value;
        value.type = JsonType::Object;
        expect('{');
        skip_ws();
        if (peek('}')) {
            ++pos_;
            return value;
        }
        while (true) {
            skip_ws();
            require_condition(peek('"'), source_name_ + ": object key must be a string at offset " +
                                           std::to_string(pos_));
            std::string key = parse_string();
            skip_ws();
            expect(':');
            JsonValue member = parse_value(depth);
            auto inserted = value.object.emplace(std::move(key), std::move(member));
            require_condition(inserted.second,
                              source_name_ + ": duplicate object key encountered");
            skip_ws();
            if (peek('}')) {
                ++pos_;
                return value;
            }
            expect(',');
        }
    }

    JsonValue parse_array(size_t depth) {
        JsonValue value;
        value.type = JsonType::Array;
        expect('[');
        skip_ws();
        if (peek(']')) {
            ++pos_;
            return value;
        }
        while (true) {
            value.array.push_back(parse_value(depth));
            skip_ws();
            if (peek(']')) {
                ++pos_;
                return value;
            }
            expect(',');
        }
    }

    std::string parse_string() {
        expect('"');
        std::string out;
        while (pos_ < source_.size()) {
            const unsigned char c = static_cast<unsigned char>(source_[pos_++]);
            if (c == '"') {
                return out;
            }
            if (c == '\\') {
                require_condition(pos_ < source_.size(),
                                  source_name_ + ": unterminated string escape");
                const char escaped = source_[pos_++];
                switch (escaped) {
                    case '"':
                    case '\\':
                    case '/':
                        out.push_back(escaped);
                        break;
                    case 'b':
                        out.push_back('\b');
                        break;
                    case 'f':
                        out.push_back('\f');
                        break;
                    case 'n':
                        out.push_back('\n');
                        break;
                    case 'r':
                        out.push_back('\r');
                        break;
                    case 't':
                        out.push_back('\t');
                        break;
                    case 'u':
                        append_utf8(parse_hex_quad(), out);
                        break;
                    default:
                        fail(source_name_ + ": invalid string escape at offset " +
                             std::to_string(pos_ - 1));
                }
            } else {
                require_condition(c >= 0x20,
                                  source_name_ + ": control byte inside JSON string");
                out.push_back(static_cast<char>(c));
            }
        }
        fail(source_name_ + ": unterminated JSON string");
    }

    std::string parse_number() {
        const size_t start = pos_;
        if (peek('-')) {
            ++pos_;
        }
        require_condition(pos_ < source_.size() &&
                              std::isdigit(static_cast<unsigned char>(source_[pos_])),
                          source_name_ + ": invalid number at offset " +
                              std::to_string(start));
        if (peek('0')) {
            ++pos_;
        } else {
            while (pos_ < source_.size() &&
                   std::isdigit(static_cast<unsigned char>(source_[pos_]))) {
                ++pos_;
            }
        }
        if (pos_ < source_.size() && source_[pos_] == '.') {
            ++pos_;
            require_condition(pos_ < source_.size() &&
                                  std::isdigit(static_cast<unsigned char>(source_[pos_])),
                              source_name_ + ": invalid fractional number");
            while (pos_ < source_.size() &&
                   std::isdigit(static_cast<unsigned char>(source_[pos_]))) {
                ++pos_;
            }
        }
        if (pos_ < source_.size() && (source_[pos_] == 'e' || source_[pos_] == 'E')) {
            ++pos_;
            if (pos_ < source_.size() && (source_[pos_] == '+' || source_[pos_] == '-')) {
                ++pos_;
            }
            require_condition(pos_ < source_.size() &&
                                  std::isdigit(static_cast<unsigned char>(source_[pos_])),
                              source_name_ + ": invalid exponent number");
            while (pos_ < source_.size() &&
                   std::isdigit(static_cast<unsigned char>(source_[pos_]))) {
                ++pos_;
            }
        }
        return std::string(source_.substr(start, pos_ - start));
    }

    uint32_t parse_hex_quad() {
        require_condition(pos_ + 4 <= source_.size(),
                          source_name_ + ": incomplete unicode escape");
        uint32_t value = 0;
        for (size_t i = 0; i < 4; ++i) {
            const char c = source_[pos_++];
            value <<= 4;
            if (c >= '0' && c <= '9') {
                value += static_cast<uint32_t>(c - '0');
            } else if (c >= 'a' && c <= 'f') {
                value += static_cast<uint32_t>(c - 'a' + 10);
            } else if (c >= 'A' && c <= 'F') {
                value += static_cast<uint32_t>(c - 'A' + 10);
            } else {
                fail(source_name_ + ": invalid unicode escape");
            }
        }
        return value;
    }

    static void append_utf8(uint32_t codepoint, std::string& out) {
        if (codepoint <= 0x7F) {
            out.push_back(static_cast<char>(codepoint));
        } else if (codepoint <= 0x7FF) {
            out.push_back(static_cast<char>(0xC0 | (codepoint >> 6)));
            out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        } else if (codepoint <= 0xFFFF) {
            out.push_back(static_cast<char>(0xE0 | (codepoint >> 12)));
            out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        } else {
            out.push_back(static_cast<char>(0xF0 | (codepoint >> 18)));
            out.push_back(static_cast<char>(0x80 | ((codepoint >> 12) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | ((codepoint >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (codepoint & 0x3F)));
        }
    }

    bool consume_literal(std::string_view literal) {
        if (source_.substr(pos_, literal.size()) == literal) {
            pos_ += literal.size();
            return true;
        }
        return false;
    }

    void skip_ws() {
        while (pos_ < source_.size()) {
            const char c = source_[pos_];
            if (c == ' ' || c == '\n' || c == '\r' || c == '\t') {
                ++pos_;
            } else {
                return;
            }
        }
    }

    bool peek(char expected) const {
        return pos_ < source_.size() && source_[pos_] == expected;
    }

    void expect(char expected) {
        require_condition(peek(expected), source_name_ + ": expected '" +
                                          std::string(1, expected) + "' at offset " +
                                          std::to_string(pos_));
        ++pos_;
    }

    std::string_view source_;
    std::string source_name_;
    size_t pos_ = 0;
};

const JsonValue& require_object_member(const JsonValue& value,
                                       const std::string& key,
                                       const std::string& context) {
    require_condition(value.type == JsonType::Object, context + " must be a JSON object");
    auto it = value.object.find(key);
    require_condition(it != value.object.end(), context + " is missing required key '" + key + "'");
    return it->second;
}

const std::map<std::string, JsonValue>& as_object(const JsonValue& value,
                                                  const std::string& context) {
    require_condition(value.type == JsonType::Object, context + " must be a JSON object");
    return value.object;
}

const std::vector<JsonValue>& as_array(const JsonValue& value,
                                       const std::string& context) {
    require_condition(value.type == JsonType::Array, context + " must be a JSON array");
    return value.array;
}

const std::string& as_string(const JsonValue& value,
                             const std::string& context) {
    require_condition(value.type == JsonType::String, context + " must be a JSON string");
    return value.string;
}

uint64_t as_u64(const JsonValue& value, const std::string& context) {
    require_condition(value.type == JsonType::Number, context + " must be a JSON integer");
    require_condition(!value.number.empty() && value.number[0] != '-',
                      context + " must be non-negative");
    require_condition(value.number.find_first_of(".eE") == std::string::npos,
                      context + " must be an integer, not a floating-point value");
    uint64_t result = 0;
    for (const char c : value.number) {
        require_condition(std::isdigit(static_cast<unsigned char>(c)),
                          context + " contains a non-digit byte");
        const uint64_t digit = static_cast<uint64_t>(c - '0');
        require_condition(result <=
                              (std::numeric_limits<uint64_t>::max() - digit) / 10ULL,
                          context + " exceeds uint64_t range");
        result = result * 10ULL + digit;
    }
    return result;
}

size_t u64_to_size(uint64_t value, const std::string& context) {
    require_condition(value <= static_cast<uint64_t>(std::numeric_limits<size_t>::max()),
                      context + " exceeds size_t range");
    return static_cast<size_t>(value);
}

size_t dtype_bytes(const std::string& dtype) {
    if (dtype == "F64" || dtype == "I64" || dtype == "U64") {
        return 8;
    }
    if (dtype == "F32" || dtype == "I32" || dtype == "U32") {
        return 4;
    }
    if (dtype == "F16" || dtype == "BF16" || dtype == "I16" || dtype == "U16") {
        return 2;
    }
    if (dtype == "I8" || dtype == "U8" || dtype == "BOOL" ||
        dtype == "F8_E4M3" || dtype == "F8_E5M2") {
        return 1;
    }
    fail("unsupported SafeTensors dtype '" + dtype + "'");
}

std::vector<int64_t> parse_shape(const JsonValue& shape_value,
                                 const std::string& context) {
    const auto& shape_array = as_array(shape_value, context + ".shape");
    require_condition(!shape_array.empty(), context + ".shape cannot be empty");
    std::vector<int64_t> shape;
    shape.reserve(shape_array.size());
    for (size_t i = 0; i < shape_array.size(); ++i) {
        const uint64_t dimension = as_u64(shape_array[i], context + ".shape[" + std::to_string(i) + "]");
        require_condition(dimension > 0, context + ".shape dimension must be positive");
        require_condition(dimension <= static_cast<uint64_t>(std::numeric_limits<int64_t>::max()),
                          context + ".shape dimension exceeds int64_t range");
        shape.push_back(static_cast<int64_t>(dimension));
    }
    return shape;
}

size_t tensor_element_count(const std::vector<int64_t>& shape,
                            const std::string& context) {
    size_t elements = 1;
    for (const int64_t dimension : shape) {
        elements = checked_mul(elements, static_cast<size_t>(dimension),
                               context + " shape product");
    }
    return elements;
}

uint64_t read_le_u64(const uint8_t* data) {
    uint64_t value = 0;
    for (size_t i = 0; i < 8; ++i) {
        value |= static_cast<uint64_t>(data[i]) << (i * 8);
    }
    return value;
}

struct TensorHeader {
    std::string dtype;
    std::vector<int64_t> shape;
    size_t physical_start = 0;
    size_t physical_end = 0;
    size_t logical_bytes = 0;
};

std::map<std::string, TensorHeader> parse_shard_header(const MappedFile& shard,
                                                       const std::string& shard_name) {
    require_condition(shard.size() >= 8,
                      "SafeTensors shard is too small to contain header length: " + shard_name);
    const uint64_t header_length_u64 = read_le_u64(shard.bytes());
    const size_t header_length = u64_to_size(header_length_u64,
                                            "SafeTensors header length for " + shard_name);
    require_condition(header_length <= shard.size() - 8,
                      "SafeTensors header length exceeds shard size: " + shard_name);
    const size_t data_region_start = checked_add(8, header_length,
                                                 "SafeTensors data region start");
    const std::string_view header_text(shard.chars() + 8, header_length);
    JsonValue header_json = JsonParser(header_text, shard_name + " header").parse();
    const auto& header_object = as_object(header_json, shard_name + " header");

    std::map<std::string, TensorHeader> tensors;
    for (const auto& entry : header_object) {
        const std::string& tensor_name = entry.first;
        if (tensor_name == "__metadata__") {
            continue;
        }
        const std::string context = shard_name + ":" + tensor_name;
        const auto& tensor_object = as_object(entry.second, context);
        (void)tensor_object;

        const std::string dtype = as_string(require_object_member(entry.second, "dtype", context),
                                            context + ".dtype");
        const std::vector<int64_t> shape =
            parse_shape(require_object_member(entry.second, "shape", context), context);
        const auto& offsets =
            as_array(require_object_member(entry.second, "data_offsets", context),
                     context + ".data_offsets");
        require_condition(offsets.size() == 2,
                          context + ".data_offsets must contain exactly two integers");
        const size_t relative_start =
            u64_to_size(as_u64(offsets[0], context + ".data_offsets[0]"),
                        context + ".data_offsets[0]");
        const size_t relative_end =
            u64_to_size(as_u64(offsets[1], context + ".data_offsets[1]"),
                        context + ".data_offsets[1]");
        require_condition(relative_start <= relative_end,
                          context + " has inverted data offsets");

        const size_t element_count = tensor_element_count(shape, context);
        const size_t logical_bytes =
            checked_mul(element_count, dtype_bytes(dtype), context + " byte size");
        require_condition(relative_end - relative_start == logical_bytes,
                          context + " data_offsets span does not match shape*dtype bytes");

        const size_t physical_start = checked_add(data_region_start, relative_start,
                                                  context + " physical start");
        const size_t physical_end = checked_add(data_region_start, relative_end,
                                                context + " physical end");
        require_condition(physical_end <= shard.size(),
                          context + " physical data range exceeds shard size");

        TensorHeader tensor_header;
        tensor_header.dtype = dtype;
        tensor_header.shape = shape;
        tensor_header.physical_start = physical_start;
        tensor_header.physical_end = physical_end;
        tensor_header.logical_bytes = logical_bytes;
        auto inserted = tensors.emplace(tensor_name, std::move(tensor_header));
        require_condition(inserted.second,
                          "duplicate tensor header in shard " + shard_name + ": " + tensor_name);
    }
    require_condition(!tensors.empty(), "SafeTensors shard contains no tensor headers: " + shard_name);
    return tensors;
}

std::optional<int> parse_layer_id(const std::string& tensor_name) {
    std::vector<std::string_view> segments;
    size_t start = 0;
    while (start <= tensor_name.size()) {
        const size_t dot = tensor_name.find('.', start);
        if (dot == std::string::npos) {
            segments.emplace_back(tensor_name.data() + start, tensor_name.size() - start);
            break;
        }
        segments.emplace_back(tensor_name.data() + start, dot - start);
        start = dot + 1;
    }

    for (size_t i = 0; i + 1 < segments.size(); ++i) {
        const std::string_view segment = segments[i];
        if (segment != "layers" && segment != "h" && segment != "blocks") {
            continue;
        }
        const std::string_view id_segment = segments[i + 1];
        require_condition(!id_segment.empty(),
                          "empty layer id segment in tensor name: " + tensor_name);
        int layer_id = 0;
        for (const char c : id_segment) {
            if (!std::isdigit(static_cast<unsigned char>(c))) {
                return std::nullopt;
            }
            const int digit = c - '0';
            require_condition(layer_id <= (std::numeric_limits<int>::max() - digit) / 10,
                              "layer id exceeds int range in tensor name: " + tensor_name);
            layer_id = layer_id * 10 + digit;
        }
        return layer_id;
    }
    return std::nullopt;
}

std::filesystem::path require_checkpoint_file(const std::filesystem::path& directory,
                                              const std::string& filename) {
    const std::filesystem::path file_path = directory / filename;
    require_condition(std::filesystem::exists(file_path),
                      "required checkpoint file does not exist: " + file_path.string());
    require_condition(std::filesystem::is_regular_file(file_path),
                      "checkpoint path is not a regular file: " + file_path.string());
    return file_path;
}

} // namespace

ModelTopology parse_model_topology(const std::filesystem::path& checkpoint_directory,
                                   const std::string& memory_strategy,
                                   size_t strict_scratchpad_bytes) {
    require_condition(std::filesystem::exists(checkpoint_directory),
                      "checkpoint directory does not exist: " + checkpoint_directory.string());
    require_condition(std::filesystem::is_directory(checkpoint_directory),
                      "checkpoint path is not a directory: " + checkpoint_directory.string());
    require_condition(memory_strategy == "STRICT" || memory_strategy == "ADAPTIVE",
                      "memory_strategy must be either STRICT or ADAPTIVE");

    std::map<std::string, std::string> weight_map_entries;
    std::set<std::string> unique_shards;
    const std::filesystem::path index_path =
        checkpoint_directory / "model.safetensors.index.json";
    if (std::filesystem::exists(index_path)) {
        require_condition(std::filesystem::is_regular_file(index_path),
                          "checkpoint index path is not a regular file: " +
                              index_path.string());
        MappedFile index_file(index_path);
        JsonValue index_json =
            JsonParser(std::string_view(index_file.chars(), index_file.size()),
                       index_path.string())
                .parse();
        const auto& weight_map_value =
            require_object_member(index_json, "weight_map", index_path.string());
        const auto& weight_map =
            as_object(weight_map_value, index_path.string() + ".weight_map");
        require_condition(!weight_map.empty(), "model.safetensors.index.json weight_map is empty");

        for (const auto& entry : weight_map) {
            const std::string& shard_name =
                as_string(entry.second, "weight_map entry for " + entry.first);
            require_condition(!shard_name.empty(),
                              "weight_map shard name is empty for tensor " + entry.first);
            require_condition(weight_map_entries.emplace(entry.first, shard_name).second,
                              "duplicate tensor in weight_map: " + entry.first);
            unique_shards.insert(shard_name);
        }
    } else {
        constexpr const char* kSingleShardName = "model.safetensors";
        const std::filesystem::path shard_path =
            require_checkpoint_file(checkpoint_directory, kSingleShardName);
        MappedFile single_shard(shard_path);
        const auto single_shard_headers =
            parse_shard_header(single_shard, kSingleShardName);
        for (const auto& entry : single_shard_headers) {
            require_condition(weight_map_entries.emplace(entry.first, kSingleShardName).second,
                              "duplicate tensor in single-shard SafeTensors header: " +
                                  entry.first);
        }
        unique_shards.insert(kSingleShardName);
    }
    require_condition(!weight_map_entries.empty(), "SafeTensors tensor map is empty");

    std::map<std::string, MappedFile> shard_files;
    std::map<std::string, std::map<std::string, TensorHeader>> shard_headers;
    for (const std::string& shard_name : unique_shards) {
        const std::filesystem::path shard_path =
            require_checkpoint_file(checkpoint_directory, shard_name);
        auto inserted = shard_files.emplace(shard_name, MappedFile(shard_path));
        require_condition(inserted.second, "duplicate shard mapping: " + shard_name);
        shard_headers.emplace(shard_name,
                              parse_shard_header(inserted.first->second, shard_name));
    }

    ModelTopology topology;
    topology.total_model_bytes = 0;
    topology.w_max_bytes = 0;
    topology.total_layers = 0;
    topology.memory_strategy = memory_strategy;

    std::map<int, LayerGrouping> layer_map;
    std::set<std::string> seen_tensors;
    for (const auto& entry : weight_map_entries) {
        const std::string& tensor_name = entry.first;
        const std::string& shard_name = entry.second;
        require_condition(seen_tensors.insert(tensor_name).second,
                          "duplicate tensor in weight_map: " + tensor_name);

        auto shard_it = shard_headers.find(shard_name);
        require_condition(shard_it != shard_headers.end(),
                          "tensor references unmapped shard: " + tensor_name);
        auto tensor_it = shard_it->second.find(tensor_name);
        require_condition(tensor_it != shard_it->second.end(),
                          "tensor listed in index is absent from shard header: " + tensor_name);
        const TensorHeader& header = tensor_it->second;

        topology.total_model_bytes =
            checked_add(topology.total_model_bytes, header.logical_bytes,
                        "total model byte mass");

        TensorMetaData tensor;
        tensor.name = tensor_name;
        tensor.shard_file = shard_name;
        tensor.start_offset = header.physical_start;
        tensor.end_offset = header.physical_end;
        tensor.shape = header.shape;
        tensor.data_type = header.dtype;
        topology.tensors.push_back(tensor);

        const std::optional<int> layer_id = parse_layer_id(tensor_name);
        if (!layer_id.has_value()) {
            continue;
        }

        auto layer_insert = layer_map.emplace(
            *layer_id, LayerGrouping{*layer_id, 0, std::vector<TensorMetaData>{}});
        LayerGrouping& layer = layer_insert.first->second;
        layer.total_layer_bytes =
            checked_add(layer.total_layer_bytes, header.logical_bytes,
                        "layer " + std::to_string(*layer_id) + " byte mass");
        layer.tensors.push_back(std::move(tensor));
    }

    require_condition(topology.total_model_bytes > 0,
                      "total model byte mass is zero");
    require_condition(!layer_map.empty(),
                      "no layer tensors were discovered from tensor namespaces");
    std::sort(topology.tensors.begin(), topology.tensors.end(),
              [](const TensorMetaData& lhs, const TensorMetaData& rhs) {
                  return lhs.name < rhs.name;
              });
    require_condition(layer_map.begin()->first == 0,
                      "layer ids must start at 0");

    int expected_layer = 0;
    topology.layers.reserve(layer_map.size());
    for (auto& entry : layer_map) {
        require_condition(entry.first == expected_layer,
                          "layer ids must be contiguous; missing layer " +
                              std::to_string(expected_layer));
        LayerGrouping& layer = entry.second;
        require_condition(!layer.tensors.empty(),
                          "layer " + std::to_string(layer.layer_id) + " contains no tensors");
        topology.w_max_bytes = std::max(topology.w_max_bytes, layer.total_layer_bytes);
        std::sort(layer.tensors.begin(), layer.tensors.end(),
                  [](const TensorMetaData& lhs, const TensorMetaData& rhs) {
                      return lhs.name < rhs.name;
                  });
        topology.layers.push_back(std::move(layer));
        ++expected_layer;
    }
    topology.total_layers = expected_layer;

    const size_t ring_bytes =
        checked_mul(2, topology.w_max_bytes, "double-buffered maximum layer footprint");
    if (memory_strategy == "STRICT") {
        require_condition(ring_bytes <= strict_scratchpad_bytes,
                          "STRICT strategy requires 2 * W_max <= vram_scratchpad_bytes");
    } else {
        const size_t five_x_ring =
            checked_mul(5, ring_bytes, "ADAPTIVE 20 percent safety rail");
        require_condition(five_x_ring <= topology.total_model_bytes,
                          "ADAPTIVE strategy requires 2 * W_max <= 0.20 * M_total");
    }

    return topology;
}

} // namespace spoolstream::core
