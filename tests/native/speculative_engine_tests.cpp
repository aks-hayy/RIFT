#include "spoolstream/memory_manager.h"
#include "spoolstream/speculative_engine.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

template <typename T>
class DeviceBuffer {
public:
    explicit DeviceBuffer(size_t count) : count_(count) {
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMalloc(reinterpret_cast<void**>(&ptr_), sizeof(T) * count_));
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

    const T* get() const {
        return ptr_;
    }

    void copy_from_host(const std::vector<T>& host) {
        if (!host.empty()) {
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(ptr_,
                                             host.data(),
                                             sizeof(T) * host.size(),
                                             cudaMemcpyHostToDevice));
        }
    }

    std::vector<T> copy_to_host() const {
        std::vector<T> host(count_);
        if (count_ > 0) {
            SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(host.data(),
                                             ptr_,
                                             sizeof(T) * count_,
                                             cudaMemcpyDeviceToHost));
        }
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

std::vector<half> to_half(const std::vector<float>& values) {
    std::vector<half> out(values.size());
    for (size_t i = 0; i < values.size(); ++i) {
        out[i] = __float2half(values[i]);
    }
    return out;
}

void set_logit(std::vector<half>& logits, int node, int vocab_size, int token, float value) {
    logits[static_cast<size_t>(node) * static_cast<size_t>(vocab_size) +
           static_cast<size_t>(token)] = __float2half(value);
}

bool is_negative_infinity(half value) {
    const float as_float = __half2float(value);
    return std::isinf(as_float) && as_float < 0.0f;
}

void test_eagle_prediction_top_k() {
    spoolstream::core::SpeculativeConfig config{};
    config.hidden_size = 3;
    config.vocab_size = 6;
    config.max_nodes = 4;
    config.top_k = 3;

    const int sequence_length = 2;
    const std::vector<half> hidden = to_half({
        1.0f, 0.0f, 0.0f,
        0.0f, 1.0f, 0.0f,
    });
    const std::vector<half> weights = to_half({
        0.10f, 0.70f, 0.20f, 0.90f, 0.90f, 0.30f,
        0.50f, 0.50f, 0.40f, 0.10f, 0.30f, 0.80f,
        0.00f, 0.00f, 0.00f, 0.00f, 0.00f, 0.00f,
    });
    const std::vector<half> bias = to_half({
        0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f,
    });

    DeviceBuffer<half> d_hidden(hidden.size());
    DeviceBuffer<half> d_weights(weights.size());
    DeviceBuffer<half> d_bias(bias.size());
    DeviceBuffer<half> d_logits(static_cast<size_t>(sequence_length) *
                                static_cast<size_t>(config.vocab_size));
    DeviceBuffer<int> d_tokens(static_cast<size_t>(sequence_length) *
                               static_cast<size_t>(config.top_k));

    d_hidden.copy_from_host(hidden);
    d_weights.copy_from_host(weights);
    d_bias.copy_from_host(bias);

    spoolstream::core::launch_eagle_predict_heads(d_hidden.get(),
                                                  d_weights.get(),
                                                  d_bias.get(),
                                                  d_logits.get(),
                                                  d_tokens.get(),
                                                  sequence_length,
                                                  config);

    const std::vector<int> tokens = d_tokens.copy_to_host();
    require_true(tokens[0] == 3, "row 0 rank 0 should choose lower tied top token 3");
    require_true(tokens[1] == 4, "row 0 rank 1 should choose token 4");
    require_true(tokens[2] == 1, "row 0 rank 2 should choose token 1");
    require_true(tokens[3] == 5, "row 1 rank 0 should choose token 5");
    require_true(tokens[4] == 0, "row 1 rank 1 should choose lower tied token 0");
    require_true(tokens[5] == 1, "row 1 rank 2 should choose token 1");

    const std::vector<half> logits = d_logits.copy_to_host();
    require_true(std::fabs(__half2float(logits[3]) - 0.90f) < 0.001f,
                 "row 0 token 3 logit mismatch");
    require_true(std::fabs(__half2float(logits[11]) - 0.80f) < 0.001f,
                 "row 1 token 5 logit mismatch");
}

void assert_mask_value(const std::vector<half>& mask,
                       int node_count,
                       int row,
                       int col,
                       bool expected_allowed) {
    const half value =
        mask[static_cast<size_t>(row) * static_cast<size_t>(node_count) +
             static_cast<size_t>(col)];
    if (expected_allowed) {
        require_true(__half2float(value) == 0.0f, "expected allowed mask value");
    } else {
        require_true(is_negative_infinity(value), "expected -inf mask value");
    }
}

void test_chain_tree_mask() {
    const std::vector<int> parents = {-1, 0, 1, 2};
    DeviceBuffer<int> d_parents(parents.size());
    DeviceBuffer<half> d_mask(parents.size() * parents.size());
    d_parents.copy_from_host(parents);

    spoolstream::core::generate_tree_attention_mask(d_parents.get(),
                                                    d_mask.get(),
                                                    static_cast<int>(parents.size()));

    const std::vector<half> mask = d_mask.copy_to_host();
    assert_mask_value(mask, 4, 0, 0, true);
    assert_mask_value(mask, 4, 0, 3, true);
    assert_mask_value(mask, 4, 1, 0, false);
    assert_mask_value(mask, 4, 1, 3, true);
    assert_mask_value(mask, 4, 2, 1, false);
    assert_mask_value(mask, 4, 3, 3, true);
}

void test_branching_tree_mask() {
    const std::vector<int> parents = {-1, 0, 0, 1, 1};
    DeviceBuffer<int> d_parents(parents.size());
    DeviceBuffer<half> d_mask(parents.size() * parents.size());
    d_parents.copy_from_host(parents);

    spoolstream::core::generate_tree_attention_mask(d_parents.get(),
                                                    d_mask.get(),
                                                    static_cast<int>(parents.size()));

    const std::vector<half> mask = d_mask.copy_to_host();
    assert_mask_value(mask, 5, 0, 4, true);
    assert_mask_value(mask, 5, 1, 3, true);
    assert_mask_value(mask, 5, 1, 2, false);
    assert_mask_value(mask, 5, 2, 4, false);
    assert_mask_value(mask, 5, 4, 4, true);
}

void test_invalid_parent_rejected() {
    const std::vector<int> parents = {-1, 0, 2};
    DeviceBuffer<int> d_parents(parents.size());
    DeviceBuffer<half> d_mask(parents.size() * parents.size());
    d_parents.copy_from_host(parents);

    require_throw([&]() {
        spoolstream::core::generate_tree_attention_mask(d_parents.get(),
                                                        d_mask.get(),
                                                        static_cast<int>(parents.size()));
    }, "invalid parent");
}

void test_greedy_verification_full_path() {
    constexpr int kNodes = 4;
    constexpr int kVocab = 12;
    const std::vector<int> parents = {-1, 0, 1, 2};
    const std::vector<int> tokens = {-1, 5, 7, 9};
    std::vector<half> logits(static_cast<size_t>(kNodes) * static_cast<size_t>(kVocab),
                             __float2half(-1.0f));
    set_logit(logits, 1, kVocab, 5, 3.0f);
    set_logit(logits, 2, kVocab, 7, 4.0f);
    set_logit(logits, 3, kVocab, 9, 5.0f);

    DeviceBuffer<int> d_parents(parents.size());
    DeviceBuffer<int> d_tokens(tokens.size());
    DeviceBuffer<half> d_logits(logits.size());
    d_parents.copy_from_host(parents);
    d_tokens.copy_from_host(tokens);
    d_logits.copy_from_host(logits);

    spoolstream::core::SpeculativeTree tree{};
    tree.device_tokens = d_tokens.get();
    tree.device_parents = d_parents.get();
    tree.node_count = kNodes;

    const auto result =
        spoolstream::core::verify_speculative_tree_greedy(d_logits.get(), tree, kVocab);
    require_true(result.accepted_count == 3, "expected full path acceptance");
    require_true(result.terminal_node == 3, "expected terminal node 3");
}

void test_greedy_verification_stops_on_mismatch() {
    constexpr int kNodes = 4;
    constexpr int kVocab = 12;
    const std::vector<int> parents = {-1, 0, 1, 2};
    const std::vector<int> tokens = {-1, 5, 7, 9};
    std::vector<half> logits(static_cast<size_t>(kNodes) * static_cast<size_t>(kVocab),
                             __float2half(-1.0f));
    set_logit(logits, 1, kVocab, 5, 3.0f);
    set_logit(logits, 2, kVocab, 8, 4.0f);
    set_logit(logits, 3, kVocab, 9, 5.0f);

    DeviceBuffer<int> d_parents(parents.size());
    DeviceBuffer<int> d_tokens(tokens.size());
    DeviceBuffer<half> d_logits(logits.size());
    d_parents.copy_from_host(parents);
    d_tokens.copy_from_host(tokens);
    d_logits.copy_from_host(logits);

    spoolstream::core::SpeculativeTree tree{};
    tree.device_tokens = d_tokens.get();
    tree.device_parents = d_parents.get();
    tree.node_count = kNodes;

    const auto result =
        spoolstream::core::verify_speculative_tree_greedy(d_logits.get(), tree, kVocab);
    require_true(result.accepted_count == 1, "expected acceptance to stop at first mismatch");
    require_true(result.terminal_node == 1, "expected terminal node 1 after mismatch");
}

void test_validation_failures() {
    spoolstream::core::SpeculativeConfig config{};
    config.hidden_size = 2;
    config.vocab_size = 4;
    config.max_nodes = 2;
    config.top_k = 2;

    std::vector<half> hidden = to_half({1.0f, 0.0f});
    std::vector<half> weights = to_half({
        1.0f, 0.0f, 0.0f, 0.0f,
        0.0f, 1.0f, 0.0f, 0.0f,
    });
    DeviceBuffer<half> d_hidden(hidden.size());
    DeviceBuffer<half> d_weights(weights.size());
    DeviceBuffer<half> d_logits(config.vocab_size);
    DeviceBuffer<int> d_tokens(config.top_k);
    d_hidden.copy_from_host(hidden);
    d_weights.copy_from_host(weights);

    require_throw([&]() {
        spoolstream::core::launch_eagle_predict_heads(nullptr,
                                                      d_weights.get(),
                                                      nullptr,
                                                      d_logits.get(),
                                                      d_tokens.get(),
                                                      1,
                                                      config);
    }, "null hidden");

    config.top_k = 5;
    require_throw([&]() {
        spoolstream::core::launch_eagle_predict_heads(d_hidden.get(),
                                                      d_weights.get(),
                                                      nullptr,
                                                      d_logits.get(),
                                                      d_tokens.get(),
                                                      1,
                                                      config);
    }, "top_k greater than vocab");

    spoolstream::core::SpeculativeTree tree{};
    tree.device_tokens = nullptr;
    tree.device_parents = nullptr;
    tree.node_count = 1;
    require_throw([&]() {
        spoolstream::core::verify_speculative_tree_greedy(d_logits.get(), tree, 4);
    }, "null speculative tree");
}

} // namespace

int main() {
    try {
        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        test_eagle_prediction_top_k();
        test_chain_tree_mask();
        test_branching_tree_mask();
        test_invalid_parent_rejected();
        test_greedy_verification_full_path();
        test_greedy_verification_stops_on_mismatch();
        test_validation_failures();
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }

    std::cout << "spoolstream speculative tests passed\n";
    return 0;
}
