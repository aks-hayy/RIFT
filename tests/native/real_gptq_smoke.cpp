#include "spoolstream/model.h"
#include "spoolstream/memory_manager.h"
#include "spoolstream/quantized_adapter.h"
#include "spoolstream/streaming_store.h"
#include "spoolstream/transformer_executor.h"

#include <cuda_fp16.h>
#include <cuda_runtime_api.h>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
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

template <typename T>
std::vector<T> copy_stage_as(const spoolstream::core::StagedTensor& staged) {
    require_true(staged.byte_size % sizeof(T) == 0, "staged tensor byte size is misaligned");
    std::vector<T> values(staged.byte_size / sizeof(T));
    if (!values.empty()) {
        std::memcpy(values.data(), staged.host_ptr, staged.byte_size);
    }
    return values;
}

const spoolstream::core::QuantizedProjection& find_projection(
    const spoolstream::core::QuantizedAdapterReport& report,
    const std::string& base_name) {
    for (const auto& projection : report.projections) {
        if (projection.base_name == base_name) {
            return projection;
        }
    }
    throw std::runtime_error("projection not found: " + base_name);
}

const spoolstream::core::ManifestTensor& find_manifest_tensor(
    const spoolstream::core::ModelManifest& manifest,
    spoolstream::core::TensorRole role) {
    for (const auto& tensor : manifest.tensors) {
        if (tensor.role == role) {
            return tensor;
        }
    }
    throw std::runtime_error("manifest tensor not found");
}

std::vector<half> make_input(int m, int k) {
    std::vector<half> x(static_cast<size_t>(m) * static_cast<size_t>(k));
    for (int row = 0; row < m; ++row) {
        for (int col = 0; col < k; ++col) {
            const float value = static_cast<float>(((row * 13 + col * 7) % 17) - 8) *
                                0.0025f;
            x[static_cast<size_t>(row) * static_cast<size_t>(k) + static_cast<size_t>(col)] =
                __float2half(value);
        }
    }
    return x;
}

std::vector<half> reference_exllama_projection(const std::vector<half>& x,
                                               const std::vector<uint32_t>& qweight,
                                               const std::vector<half>& scales,
                                               const std::vector<half>& zeros,
                                               const std::vector<int32_t>& gidx,
                                               int m,
                                               int k,
                                               int n) {
    std::vector<half> output(static_cast<size_t>(m) * static_cast<size_t>(n));
    for (int row = 0; row < m; ++row) {
        for (int col = 0; col < n; ++col) {
            float accumulator = 0.0f;
            for (int kk = 0; kk < k; ++kk) {
                const uint32_t word =
                    qweight[static_cast<size_t>(kk / 8) * static_cast<size_t>(n) +
                            static_cast<size_t>(col)];
                const uint32_t quantized = (word >> (4 * (kk & 7))) & 0x0FU;
                const int group = gidx[static_cast<size_t>(kk)];
                const size_t metadata_index =
                    static_cast<size_t>(group) * static_cast<size_t>(n) +
                    static_cast<size_t>(col);
                const float weight =
                    (static_cast<float>(quantized) - __half2float(zeros[metadata_index])) *
                    __half2float(scales[metadata_index]);
                accumulator += __half2float(
                                   x[static_cast<size_t>(row) * static_cast<size_t>(k) +
                                     static_cast<size_t>(kk)]) *
                               weight;
            }
            output[static_cast<size_t>(row) * static_cast<size_t>(n) +
                   static_cast<size_t>(col)] = __float2half(accumulator);
        }
    }
    return output;
}

float max_abs_error(const std::vector<half>& actual, const std::vector<half>& expected) {
    require_true(actual.size() == expected.size(), "output sizes differ");
    float max_error = 0.0f;
    for (size_t i = 0; i < actual.size(); ++i) {
        max_error = std::max(max_error,
                             std::fabs(__half2float(actual[i]) -
                                       __half2float(expected[i])));
    }
    return max_error;
}

} // namespace

int main(int argc, char** argv) {
    try {
        const std::filesystem::path model_path =
            argc > 1 ? std::filesystem::path(argv[1]) :
                       (std::filesystem::current_path() / "models" / "local" / "llama-gptq");
        const std::string projection_name = "model.layers.0.self_attn.q_proj";

        SPOOLSTREAM_CUDA_CHECK(cudaSetDevice(0));
        auto manifest = spoolstream::core::build_model_manifest(model_path, "STRICT");
        const auto report = spoolstream::core::build_quantized_adapter_report(manifest);
        require_true(report.supported, "quantized adapter report is not supported");
        require_true(report.projections.size() == 224,
                     "expected 224 quantized projections in models/local/llama-gptq");

        const auto& projection = find_projection(report, projection_name);
        require_true(projection.materializable, "target projection is not materializable");
        require_true(projection.weight_layout ==
                         spoolstream::core::QuantizedWeightLayout::GPTQ_EXLLAMA_INT4,
                     "target projection is not GPTQ ExLlama layout");
        require_true(projection.g_idx != nullptr, "target projection is missing g_idx");

        constexpr int lm_head_tile_rows = 1024;
        const size_t lm_head_tile_bytes =
            static_cast<size_t>(lm_head_tile_rows) *
            static_cast<size_t>(manifest.config.hidden_size) * sizeof(half);
        const size_t staging_capacity =
            std::max({projection.qweight != nullptr ? projection.qweight->metadata.end_offset -
                                                          projection.qweight->metadata.start_offset :
                                                      size_t{0},
                      projection.scales != nullptr ? projection.scales->metadata.end_offset -
                                                        projection.scales->metadata.start_offset :
                                                    size_t{0},
                      projection.zeros != nullptr ? projection.zeros->metadata.end_offset -
                                                       projection.zeros->metadata.start_offset :
                                                   size_t{0},
                      projection.g_idx != nullptr ? projection.g_idx->metadata.end_offset -
                                                       projection.g_idx->metadata.start_offset :
                                                   size_t{0},
                      lm_head_tile_bytes,
                      64ULL * 1024ULL * 1024ULL});
        auto store = spoolstream::core::create_streaming_tensor_store(model_path,
                                                                      staging_capacity);

        const auto qweight_stage =
            spoolstream::core::stage_tensor_bytes(store, *projection.qweight);
        const auto qweight = copy_stage_as<uint32_t>(qweight_stage);
        const auto scales_stage =
            spoolstream::core::stage_tensor_bytes(store, *projection.scales);
        const auto scales = copy_stage_as<half>(scales_stage);
        const auto zeros_stage =
            spoolstream::core::stage_tensor_bytes(store, *projection.zeros);
        const auto qzeros = copy_stage_as<uint32_t>(zeros_stage);
        const auto gidx_stage =
            spoolstream::core::stage_tensor_bytes(store, *projection.g_idx);
        const auto gidx = copy_stage_as<int32_t>(gidx_stage);

        auto metadata =
            spoolstream::core::create_quantized_projection_metadata_workspace(projection);
        spoolstream::core::upload_projection_zeros_to_workspace(metadata,
                                                                projection,
                                                                qzeros.data(),
                                                                qzeros.size() *
                                                                    sizeof(uint32_t));
        spoolstream::core::upload_projection_gidx_to_workspace(metadata,
                                                               projection,
                                                               gidx.data(),
                                                               gidx.size() * sizeof(int32_t));

        const int m = 1;
        const int k = projection.input_features;
        const int n = projection.output_features;
        const auto x = make_input(m, k);
        const auto expanded_zeros =
            spoolstream::core::expand_packed_qzeros_to_half(qzeros.data(),
                                                           projection.group_count,
                                                           projection.output_features);
        std::vector<half> adjusted_zeros = expanded_zeros;
        for (half& zero : adjusted_zeros) {
            zero = __float2half(__half2float(zero) + 1.0f);
        }
        const auto expected = reference_exllama_projection(x,
                                                           qweight,
                                                           scales,
                                                           adjusted_zeros,
                                                           gidx,
                                                           m,
                                                           k,
                                                           n);

        DeviceBuffer<half> d_x(x.size());
        DeviceBuffer<uint32_t> d_qweight(qweight.size());
        DeviceBuffer<half> d_scales(scales.size());
        DeviceBuffer<half> d_output(expected.size());
        d_x.copy_from_host(x);
        d_qweight.copy_from_host(qweight);
        d_scales.copy_from_host(scales);

        const auto view = spoolstream::core::bind_quantized_projection_device_view(
            projection,
            d_qweight.get(),
            d_scales.get(),
            metadata,
            m);
        spoolstream::core::launch_quantized_projection(d_x.get(),
                                                       d_output.get(),
                                                       view);
        const auto actual = d_output.copy_to_host();
        const float error = max_abs_error(actual, expected);
        require_true(error <= 0.125f, "real GPTQ projection error exceeded tolerance");

        spoolstream::core::destroy_quantized_projection_metadata_workspace(metadata);

        const auto& final_norm_tensor =
            find_manifest_tensor(manifest, spoolstream::core::TensorRole::FINAL_NORM);
        const auto& lm_head_tensor =
            find_manifest_tensor(manifest, spoolstream::core::TensorRole::LM_HEAD);
        DeviceBuffer<half> d_final_norm(static_cast<size_t>(manifest.config.hidden_size));
        const auto final_norm_stage =
            spoolstream::core::stage_tensor_bytes(store, final_norm_tensor);
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(d_final_norm.get(),
                                         final_norm_stage.host_ptr,
                                         final_norm_stage.byte_size,
                                         cudaMemcpyHostToDevice));
        auto activation_workspace = spoolstream::core::create_activation_workspace(
            1,
            manifest.config.hidden_size,
            manifest.config.intermediate_size);
        const auto dense_result =
            spoolstream::core::execute_dense_lm_head_greedy_streamed(
                store,
                lm_head_tensor,
                d_x.get(),
                d_final_norm.get(),
                activation_workspace,
                1,
                manifest.config.hidden_size,
                manifest.config.vocab_size,
                lm_head_tile_rows,
                static_cast<float>(manifest.config.rms_norm_eps));
        require_true(dense_result.token_id >= 0 &&
                         dense_result.token_id < manifest.config.vocab_size,
                     "dense lm_head greedy token is out of range");
        require_true(dense_result.bytes_streamed ==
                         lm_head_tensor.metadata.end_offset -
                             lm_head_tensor.metadata.start_offset,
                     "dense lm_head streamed byte count mismatch");

        auto tokenizer = spoolstream::core::load_tokenizer_json(model_path / "tokenizer.json");
        auto prompt_tokens = spoolstream::core::encode_tokenizer_text(tokenizer,
                                                                      "Hello from SpoolStream",
                                                                      true);
        require_true(!prompt_tokens.empty(), "prompt tokenizer produced no tokens");
        if (prompt_tokens.size() > 8) {
            prompt_tokens.resize(8);
        }
        const auto& embedding_tensor =
            find_manifest_tensor(manifest, spoolstream::core::TensorRole::TOKEN_EMBEDDING);
        DeviceBuffer<half> d_prompt_embeddings(prompt_tokens.size() *
                                               static_cast<size_t>(manifest.config.hidden_size));
        const auto embedding_result =
            spoolstream::core::execute_prompt_embedding_lookup_streamed(
                store,
                embedding_tensor,
                prompt_tokens.data(),
                static_cast<int>(prompt_tokens.size()),
                d_prompt_embeddings.get(),
                manifest.config.vocab_size,
                manifest.config.hidden_size);
        require_true(embedding_result.tokens_embedded ==
                         static_cast<int>(prompt_tokens.size()),
                     "real prompt embedding token count mismatch");
        require_true(embedding_result.bytes_streamed ==
                         prompt_tokens.size() *
                             static_cast<size_t>(manifest.config.hidden_size) * sizeof(half),
                     "real prompt embedding byte count mismatch");
        spoolstream::core::destroy_activation_workspace(activation_workspace);

        auto one_layer_manifest = manifest;
        one_layer_manifest.config.num_hidden_layers = 1;
        const auto one_layer_plans = spoolstream::core::build_layer_execution_plans(
            one_layer_manifest,
            one_layer_manifest.topology.w_max_bytes,
            256);
        const int layer_tokens = static_cast<int>(std::min<size_t>(prompt_tokens.size(), 2));
        DeviceBuffer<uint8_t> slot_a(one_layer_plans.slot_capacity);
        DeviceBuffer<uint8_t> slot_b(one_layer_plans.slot_capacity);
        DeviceBuffer<half> d_layer_output(static_cast<size_t>(layer_tokens) *
                                          static_cast<size_t>(manifest.config.hidden_size));
        auto layer_workspace = spoolstream::core::create_activation_workspace(
            layer_tokens,
            manifest.config.hidden_size,
            manifest.config.intermediate_size);
        spoolstream::core::LlamaDecoderLayerConfig layer_config{};
        layer_config.tokens = layer_tokens;
        layer_config.hidden_size = manifest.config.hidden_size;
        layer_config.intermediate_size = manifest.config.intermediate_size;
        layer_config.num_attention_heads = manifest.config.num_attention_heads;
        layer_config.num_key_value_heads = manifest.config.num_key_value_heads;
        layer_config.head_dim = manifest.config.hidden_size / manifest.config.num_attention_heads;
        layer_config.position_offset = 0;
        layer_config.rope_theta = static_cast<float>(manifest.config.rope_theta);
        layer_config.rms_norm_epsilon = static_cast<float>(manifest.config.rms_norm_eps);
        const auto layer_result = spoolstream::core::execute_streamed_llama_model_prefill(
            store,
            one_layer_manifest,
            one_layer_plans,
            report,
            slot_a.get(),
            slot_b.get(),
            d_prompt_embeddings.get(),
            d_layer_output.get(),
            layer_workspace,
            layer_config);
        require_true(layer_result.layers_executed == 1, "real layer smoke did not execute one layer");
        const auto layer_output = d_layer_output.copy_to_host();
        require_true(!layer_output.empty(), "real layer smoke output is empty");
        require_true(std::isfinite(__half2float(layer_output[0])),
                     "real layer smoke output contains a non-finite value");
        spoolstream::core::destroy_activation_workspace(layer_workspace);

        const auto full_plans = spoolstream::core::build_layer_execution_plans(
            manifest,
            manifest.topology.w_max_bytes,
            256);
        DeviceBuffer<half> d_full_output(static_cast<size_t>(manifest.config.hidden_size));
        auto full_workspace = spoolstream::core::create_activation_workspace(
            1,
            manifest.config.hidden_size,
            manifest.config.intermediate_size);
        spoolstream::core::LlamaDecoderLayerConfig full_config{};
        full_config.tokens = 1;
        full_config.hidden_size = manifest.config.hidden_size;
        full_config.intermediate_size = manifest.config.intermediate_size;
        full_config.num_attention_heads = manifest.config.num_attention_heads;
        full_config.num_key_value_heads = manifest.config.num_key_value_heads;
        full_config.head_dim = manifest.config.hidden_size / manifest.config.num_attention_heads;
        full_config.position_offset = 0;
        full_config.rope_theta = static_cast<float>(manifest.config.rope_theta);
        full_config.rms_norm_epsilon = static_cast<float>(manifest.config.rms_norm_eps);
        const auto full_result = spoolstream::core::execute_streamed_llama_model_prefill(
            store,
            manifest,
            full_plans,
            report,
            slot_a.get(),
            slot_b.get(),
            d_prompt_embeddings.get(),
            d_full_output.get(),
            full_workspace,
            full_config);
        require_true(full_result.layers_executed == manifest.config.num_hidden_layers,
                     "full prefill did not execute all layers");
        const auto full_output = d_full_output.copy_to_host();
        require_true(!full_output.empty(), "full prefill output is empty");
        require_true(std::isfinite(__half2float(full_output[0])),
                     "full prefill output contains a non-finite value");
        const auto full_dense_result =
            spoolstream::core::execute_dense_lm_head_greedy_streamed(
                store,
                lm_head_tensor,
                d_full_output.get(),
                d_final_norm.get(),
                full_workspace,
                1,
                manifest.config.hidden_size,
                manifest.config.vocab_size,
                lm_head_tile_rows,
                static_cast<float>(manifest.config.rms_norm_eps));
        require_true(full_dense_result.token_id >= 0 &&
                         full_dense_result.token_id < manifest.config.vocab_size,
                     "full prefill dense lm_head token is out of range");
        spoolstream::core::SamplingConfig sample_config{};
        sample_config.temperature = 0.7f;
        sample_config.top_k = 32;
        sample_config.top_p = 0.9f;
        sample_config.repetition_penalty = 1.05f;
        sample_config.seed = 424242;
        const auto full_sample_result =
            spoolstream::core::execute_dense_lm_head_sample_streamed(
                store,
                lm_head_tensor,
                d_full_output.get(),
                d_final_norm.get(),
                full_workspace,
                1,
                manifest.config.hidden_size,
                manifest.config.vocab_size,
                lm_head_tile_rows,
                static_cast<float>(manifest.config.rms_norm_eps),
                prompt_tokens.data(),
                static_cast<int>(prompt_tokens.size()),
                sample_config);
        require_true(full_sample_result.token_id >= 0 &&
                         full_sample_result.token_id < manifest.config.vocab_size,
                     "full prefill sampled token is out of range");
        spoolstream::core::destroy_activation_workspace(full_workspace);

        spoolstream::core::KVCacheConfig kv_config{};
        kv_config.page_size_bytes = 4096;
        kv_config.max_pages = 4;
        kv_config.max_sequences = 1;
        kv_config.max_pages_per_sequence = 4;
        kv_config.eviction_threshold = 1.0F;
        kv_config.feedback_alpha = 1.0F;
        kv_config.verification_floor = 0.45F;
        kv_config.initial_lookahead_depth = 1;
        kv_config.cuda_device_id = 0;
        auto kv_cache = spoolstream::core::create_paged_kv_cache(kv_config);
        std::vector<int> decode_context = {prompt_tokens.front()};
        std::vector<int> generated_tokens;
        constexpr int decode_steps = 2;
        for (int step = 0; step < decode_steps; ++step) {
            const int decode_token_count = static_cast<int>(decode_context.size());
            DeviceBuffer<half> d_decode_embeddings(static_cast<size_t>(decode_token_count) *
                                                   static_cast<size_t>(manifest.config.hidden_size));
            const auto decode_embedding_result =
                spoolstream::core::execute_prompt_embedding_lookup_streamed(
                    store,
                    embedding_tensor,
                    decode_context.data(),
                    decode_token_count,
                    d_decode_embeddings.get(),
                    manifest.config.vocab_size,
                    manifest.config.hidden_size);
            require_true(decode_embedding_result.tokens_embedded == decode_token_count,
                         "decode embedding count mismatch");
            DeviceBuffer<half> d_decode_output(static_cast<size_t>(decode_token_count) *
                                               static_cast<size_t>(manifest.config.hidden_size));
            auto decode_workspace = spoolstream::core::create_activation_workspace(
                decode_token_count,
                manifest.config.hidden_size,
                manifest.config.intermediate_size);
            spoolstream::core::LlamaDecoderLayerConfig decode_config{};
            decode_config.tokens = decode_token_count;
            decode_config.hidden_size = manifest.config.hidden_size;
            decode_config.intermediate_size = manifest.config.intermediate_size;
            decode_config.num_attention_heads = manifest.config.num_attention_heads;
            decode_config.num_key_value_heads = manifest.config.num_key_value_heads;
            decode_config.head_dim =
                manifest.config.hidden_size / manifest.config.num_attention_heads;
            decode_config.position_offset = 0;
            decode_config.rope_theta = static_cast<float>(manifest.config.rope_theta);
            decode_config.rms_norm_epsilon = static_cast<float>(manifest.config.rms_norm_eps);
            const auto decode_prefill = spoolstream::core::execute_streamed_llama_model_prefill(
                store,
                manifest,
                full_plans,
                report,
                slot_a.get(),
                slot_b.get(),
                d_decode_embeddings.get(),
                d_decode_output.get(),
                decode_workspace,
                decode_config);
            require_true(decode_prefill.layers_executed == manifest.config.num_hidden_layers,
                         "decode prefill did not execute all layers");
            const auto decode_greedy =
                spoolstream::core::execute_dense_lm_head_greedy_streamed(
                    store,
                    lm_head_tensor,
                    d_decode_output.get(),
                    d_final_norm.get(),
                    decode_workspace,
                    decode_token_count,
                    manifest.config.hidden_size,
                    manifest.config.vocab_size,
                    lm_head_tile_rows,
                    static_cast<float>(manifest.config.rms_norm_eps));
            generated_tokens.push_back(decode_greedy.token_id);
            decode_context.push_back(decode_greedy.token_id);
            spoolstream::core::record_decode_token_in_kv_cache(kv_cache,
                                                               0,
                                                               step,
                                                               decode_greedy.token_id);
            spoolstream::core::destroy_activation_workspace(decode_workspace);
        }
        std::vector<int> kv_records(generated_tokens.size(), -1);
        SPOOLSTREAM_CUDA_CHECK(cudaMemcpy(kv_records.data(),
                                         kv_cache.device_window,
                                         kv_records.size() * sizeof(int),
                                         cudaMemcpyDeviceToHost));
        require_true(kv_records == generated_tokens,
                     "real decode KV records do not match generated tokens");
        spoolstream::core::destroy_paged_kv_cache(kv_cache);
        spoolstream::core::destroy_streaming_tensor_store(store);

        std::cout << "LLAMA-GPT4Q q_proj smoke passed: projections="
                  << report.projections.size()
                  << " K=" << k
                  << " N=" << n
                  << " max_abs_error=" << error
                  << " dense_lm_head_token=" << dense_result.token_id
                  << " dense_lm_head_logit=" << dense_result.logit
                  << " dense_lm_head_tiles=" << dense_result.tiles_processed
                  << " prompt_tokens=" << prompt_tokens.size()
                  << " embedding_bytes=" << embedding_result.bytes_streamed
                  << " layer0_bytes=" << layer_result.bytes_streamed
                  << " layer0_first=" << __half2float(layer_output[0])
                  << " full_layers=" << full_result.layers_executed
                  << " full_bytes=" << full_result.bytes_streamed
                  << " full_token=" << full_dense_result.token_id
                  << " full_logit=" << full_dense_result.logit
                  << " sample_token=" << full_sample_result.token_id
                  << " decode_tokens=" << generated_tokens.size()
                  << " decode_last=" << generated_tokens.back()
                  << '\n';
        return 0;
    } catch (const std::exception& ex) {
        std::cerr << ex.what() << '\n';
        return 1;
    }
}
