# RIFT Version History

## RIFT Control Plane 1.3.0 Release-Hardening Increment

### Verified Changes

- Added SQLite WAL-backed authoritative controller state with revisioned writes,
  JSON compatibility mirrors, validated backup/restore commands, and
  cluster-state persistence.
- Replaced duplicate top-level aliases with the canonical lifecycle commands:
  `rift init`, `start`, `discover`, `plan`, `apply`, `status`, `doctor`, and
  `stop`, plus grouped expert operations.
- Added a permission-gated mTLS node inference proxy for bounded,
  non-streaming OpenAI-compatible requests routed only through RIFT-managed
  service state.
- Added diagnostic state-store revision metadata without archiving SQLite
  contents or credentials.
- Bundled a live-data dashboard in the Python wheel. Node.js is only needed to
  rebuild the contributor UI; an installed user does not run npm.
- Added platform-aware `RIFT_HOME` paths and previewed, backup-first migration
  of checkout-local `.rift` state and model data.
- Added bounded controller reconciliation with opt-in automatic recovery.
- Added local-artifact recommendation and config generation through
  `rift model recommend --source local --models-dir PATH`.

### Verification

```text
Python tests:                  active suite passed in isolated RIFT_HOME dirs
State store tests:             passed
Cluster state persistence:     passed with 50-node placement/recovery suite
CLI surface tests:             passed (canonical grouped commands)
Node inference proxy tests:    passed (policy, managed-route, bounded response)
Frontend lint/typecheck/build: passed during dependency-installed verification
Native CUDA CMake/CTest:       blocked by missing MSVC C++ compiler (`cl.exe`)
```

The direct data-plane proxy remains implementation-verified only. Physical
multi-node mTLS, streaming, route leases, and failover are still required
before production fleet claims.

## Phase 1: Ingestion, Topology Parsing & Low-Level Memory Virtualization

### Status

Complete and build-verified.

Phase 1 establishes the native pre-inference foundation for SpoolStream Core. It can inspect a local SafeTensors checkpoint, compute validated model topology and memory guardrails, then provision a CUDA-visible execution workspace made of pinned host tensor buffers and dual VRAM scratchpad slots.

### Phase 1 Summary

This phase does not generate tokens yet. Its job is to prove that SpoolStream can understand where model weights live, how large each transformer layer is, and how to materialize those weights into low-level CUDA-accessible memory without relying on PyTorch, Hugging Face, Accelerate, or other high-level inference frameworks.

End-to-end Phase 1 flow:

1. Parse `model.safetensors.index.json`.
2. Map and inspect all referenced SafeTensors shards.
3. Build tensor metadata with physical shard offsets, shapes, dtypes, and byte sizes.
4. Group tensors into contiguous transformer layers.
5. Compute `M_total`, per-layer byte mass, `W_max`, and memory strategy guardrails.
6. Allocate pinned mapped host buffers for runtime tensors.
7. Register CUDA UVA aliases for those pinned buffers.
8. Allocate `slot_A` and `slot_B` VRAM scratchpads, each exactly `W_max` bytes.
9. Cleanly destroy all pinned host and device allocations.

### Current Capabilities

- Native C++17/CUDA implementation.
- CMake/Ninja build.
- SafeTensors multi-shard checkpoint ingestion.
- Cross-platform read-only file mapping:
  - POSIX `mmap()` on POSIX platforms.
  - Windows file mapping APIs on Windows.
- Strict internal JSON parsing for checkpoint metadata and shard headers.
- Tensor metadata extraction:
  - tensor name
  - shard file
  - physical byte offsets
  - shape
  - dtype
- Transformer layer grouping from common namespaces:
  - `layers.<id>`
  - `model.layers.<id>`
  - `h.<id>`
  - `blocks.<id>`
- Model topology computation:
  - total model byte mass
  - per-layer byte mass
  - maximum single-layer footprint, `W_max`
  - total contiguous layer count
- Memory guardrail enforcement:
  - `STRICT`: `2 * W_max <= vram_scratchpad_bytes`
  - `ADAPTIVE`: `2 * W_max <= 0.20 * total_model_bytes`
- CUDA GPU validation:
  - visible device count
  - selected device ID
  - mapped host memory support
  - unified virtual addressing support
  - PCI bus identifier
- Best-effort NUMA locality:
  - Linux reads GPU NUMA information from sysfs and binds allocation work when available.
  - Windows uses best-effort processor affinity and continues on single-node or unknown-node systems.
- Runtime tensor memory provisioning:
  - `cudaHostAllocPortable`
  - `cudaHostAllocMapped`
  - tensor byte materialization from validated SafeTensors offsets
  - `cudaHostGetDevicePointer()` UVA registration
- Dual VRAM scratchpad provisioning:
  - `slot_A`
  - `slot_B`
  - each slot sized exactly to `ModelTopology::w_max_bytes`
  - preflight `cudaMemGetInfo()` free-VRAM check
- Defensive cleanup:
  - `cudaFreeHost()` for pinned tensor buffers
  - `cudaFree()` for scratchpad slots
  - idempotent pointer nulling and vector clearing
- CUDA error tracking through `SPOOLSTREAM_CUDA_CHECK`, including expression, file, line, status code, and CUDA error string.

### Public API Surface

Phase 1 exposes:

- `ModelTopology parse_model_topology(const std::filesystem::path& checkpoint_directory, const std::string& memory_strategy, size_t strict_scratchpad_bytes)`
- `ExecutionWorkspace provision_execution_workspace(const std::filesystem::path& checkpoint_dir, const ModelTopology& topology, int cuda_device_id)`
- `void destroy_execution_workspace(ExecutionWorkspace& workspace) noexcept`

Key descriptors:

- `TensorMetaData`
- `LayerGrouping`
- `ModelTopology`
- `RuntimeTensor`
- `RuntimeLayer`
- `ExecutionWorkspace`

### Validation Coverage

The current test suite covers:

- multi-shard SafeTensors parsing
- `STRICT` strategy success
- `ADAPTIVE` strategy success
- adaptive 20 percent guardrail failure
- malformed JSON/header-derived failures
- shape and offset byte-size mismatch
- tensors listed in index but missing from shard headers
- non-contiguous layer IDs
- successful CUDA workspace provisioning from real SafeTensors-style fixture shards
- non-null `slot_A` and `slot_B`
- exact `slot_capacity == w_max_bytes`
- runtime layer and tensor counts matching topology
- pinned host payload bytes matching source shard bytes
- non-null UVA device aliases
- idempotent cleanup with nulled pointers and cleared runtime vectors
- invalid CUDA device ID failure
- tensor offset range failure during materialization
- insufficient VRAM failure with a synthetic oversized topology

### Verified Workstation

Latest verification was run on:

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU
- PCI bus: `00000000:01:00.0`
- VRAM: `8188 MiB`
- NVIDIA driver: `581.04`
- MSVC: `19.44.35228`
- CMake: `4.3.4`
- Ninja: `1.13.2`
- CUDA Toolkit: `13.3`, `nvcc V13.3.33`

Latest test commands passed:

```text
ctest --test-dir build --output-on-failure --verbose
spoolstream_parser_tests.exe
spoolstream_memory_manager_tests.exe
```

Latest result:

```text
100% tests passed, 0 tests failed out of 3
```

### Not Yet Implemented

Phase 1 is complete, but SpoolStream is not yet an inference engine. The following remain for later phases:

- asynchronous DMA stream scheduling
- CUDA event choreography
- ring-buffer prefetch and overwrite logic
- transformer layer kernels
- activation/state buffers
- tokenizer and model config execution semantics
- Python `InferenceEngine`
- OpenAI-compatible API server
- command-line inference daemon
- token generation

## Phase 1 Part 1: SafeTensors Parser & Dynamic Topology Evaluator

Implemented the checkpoint ingestion layer:

- SafeTensors index parsing.
- shard header parsing.
- tensor offset, shape, dtype, and byte validation.
- layer grouping.
- `M_total`, `W_max`, and guardrail computation.
- malformed checkpoint rejection with explicit runtime errors.

## Phase 1 Part 2: CUDA Pinned Host Allocator & Workspace Provisioner

Implemented the CUDA memory workspace layer:

- CUDA device validation.
- best-effort NUMA affinity.
- pinned mapped host tensor allocation.
- tensor byte materialization from SafeTensors shards.
- UVA pointer registration.
- dual VRAM scratchpad allocation.
- full workspace cleanup.

## Phase 2: Core Compute & Parallel Execution Pipeline

### Status

Implemented and build-verified as a reusable AWQ int4 fused GEMM primitive plus a throttle-paced CUDA pipeline graph scheduler.

Phase 2 begins the performance-critical compute and orchestration layer. It does not yet execute a full transformer block, but it provides the first real Tensor Core computation primitive and the first low-overhead H2D scheduling primitive needed by later attention and MLP execution stages.

### Current Capability

This phase adds a CUDA WMMA GEMM launcher that consumes FP16 activations and AWQ-style packed int4 weights, dequantizes weights on the fly, accumulates through Tensor Cores, and writes fused bias/activation output. It also adds a throttle-paced H2D pipeline graph module for staging host-resident weights into device scratchpad slots without treating PCIe as full-duplex bandwidth.

Capabilities:

- Native CUDA kernel module:
  - `include/spoolstream/kernels.h`
  - `src/kernels.cu`
- Native CUDA pipeline module:
  - `include/spoolstream/pipeline.h`
  - `src/pipeline.cu`
- Public compute descriptors:
  - `QuantFormat`
  - `ActivationKind`
  - `FusedGemmConfig`
- Public launcher:
  - `launch_fused_dequant_gemm(...)`
- First supported quantization ABI:
  - `QuantFormat::AWQ_INT4`
- Future quantization extension point:
  - `QuantFormat` is intentionally structured so MXFP4 can be added later without replacing the public launcher model.
- Explicit tensor layout:
  - `x`: row-major `[M, K]` FP16
  - logical weight matrix: row-major `[K, N]`
  - packed weights: 8 adjacent 4-bit `N` values per `uint32_t`, low nibble first
  - `scales`: `[ceil(K / group_size), N]`
  - `zeros`: `[ceil(K / group_size), N]`
  - output: row-major `[M, N]` FP16
- Device-side AWQ dequantization utility:
  - decodes each nibble with `(packed_val >> (4 * i)) & 0x0F`
  - reconstructs FP16 weight values with `(W_int - zero) * scale`
- WMMA compute path:
  - `16x16x16` warp-level matrix tiles
  - activation tiles staged in 128-byte-aligned shared memory
  - dequantized weight tiles staged in 128-byte-aligned shared memory
  - `nvcuda::wmma::load_matrix_sync`
  - `nvcuda::wmma::mma_sync`
  - FP32 accumulation
- Fused output post-processing:
  - optional per-output-column FP16 bias
  - `NONE`
  - `RELU`
  - `GELU_TANH`
  - `GELU_ERF`
  - `SILU`
- Boundary handling:
  - supports non-multiple `M`
  - supports non-multiple `K`
  - supports non-multiple WMMA `N` tiles while requiring packed-storage `N % 8 == 0`
- Host-side validation:
  - rejects null required pointers
  - rejects unsupported quantization formats
  - rejects invalid dimensions
  - rejects invalid group size
  - rejects `N` values not divisible by 8
  - checks CUDA launch and stream completion through `SPOOLSTREAM_CUDA_CHECK`
- Pipeline queue architecture:
  - creates a high-priority non-blocking `stream_compute`
  - creates a non-blocking `stream_copy`
  - preserves stream priority metadata for verification and later scheduling policy
- Unidirectional H2D bandwidth model:
  - uses a default physical cap of `64 GB/s`
  - rejects limits above the PCIe Gen 5 x16 H2D ceiling
  - estimates transfer duration from bytes and physical H2D bandwidth only
- DMA throttle pacing:
  - computes throttle cycles from `target_exec_ns - estimated_physical_transfer_ns`
  - uses CUDA device clock-rate attributes to convert nanoseconds to cycles
  - launches a `clock64()` delay kernel into the copy queue after the H2D copy
- CUDA graph pipeline wrapper:
  - compiles H2D copy, throttle, and marker/compute-order nodes into a `cudaGraphExec_t`
  - supports graph launch and cleanup through public APIs
  - probes CUDA conditional graph-node availability at runtime
  - records whether conditional nodes are supported and whether a conditional node was created
- Defensive pipeline cleanup:
  - destroys CUDA streams
  - destroys graph executables
  - destroys graph handles
  - clears handles and accounting fields

### Validation Coverage

The Phase 2 kernel test suite compares GPU output against a CPU reference implementation that decodes the same packed AWQ int4 layout, applies scale/zero metadata, accumulates in FP32, applies bias/activation, and compares FP16 outputs.

The current tests cover:

- pure GEMM with no bias and no activation
- bias + `RELU`
- bias + `GELU_TANH`
- bias + `GELU_ERF`
- bias + `SILU`
- non-multiple `M/N/K` boundary tiles
- invalid null pointer failure
- invalid packed `N` failure
- invalid `group_size` failure
- all Phase 1 parser and workspace tests
- H2D transfer-duration estimation at the `64 GB/s` physical cap
- throttle-cycle computation
- pipeline stream creation and cleanup
- scheduled throttle-paced H2D copy byte correctness
- compiled CUDA graph H2D copy byte correctness
- graph marker node execution
- conditional graph-node capability probing
- invalid pipeline bandwidth failure
- invalid pipeline stage configuration failure

### Verified Build

The project configured, built, and passed tests with:

- GPU: NVIDIA GeForce RTX 4060 Laptop GPU
- PCI bus: `00000000:01:00.0`
- VRAM: `8188 MiB`
- NVIDIA driver: `581.04`
- MSVC: `19.44.35228`
- CMake: `4.3.4`
- Ninja: `1.13.2`
- CUDA Toolkit: `13.3`, `nvcc V13.3.33`
- CUDA architecture: `89-real`

The `89-real` setting emits native `sm_89` code for this workstation and avoids PTX JIT incompatibility between CUDA Toolkit `13.3` and the installed driver-reported CUDA runtime level.

Latest test commands passed:

```text
ctest --test-dir build --output-on-failure
spoolstream_parser_tests.exe
spoolstream_memory_manager_tests.exe
spoolstream_kernel_tests.exe
spoolstream_pipeline_tests.exe
```

Latest result:

```text
100% tests passed, 0 tests failed out of 4
```

### Not Yet Implemented

Phase 2 is a GEMM primitive, not yet a complete model executor. Remaining future work includes:

- MXFP4 decode path
- full multi-layer async DMA overlap and ring-buffer scheduler
- full attention projection orchestration
- MLP layer orchestration
- KV cache management
- activation/state buffer planner
- tokenizer and generation loop
- Python `InferenceEngine`
- OpenAI-compatible API server

## Phase 3: Algorithmic Acceleration & Context Virtualization

### Status

Implemented and build-verified as standalone CUDA speculative-decoding primitives.

Phase 3 adds the first algorithmic acceleration layer for future multi-token decoding. It does not yet run an integrated transformer decoder, but it can build fixed-size speculative candidate structures, generate causal tree-attention masks, and verify proposed token paths against logits produced by a future main-model executor.

### Current Capability

This phase adds:

- Native CUDA speculative engine module:
  - `include/spoolstream/speculative_engine.h`
  - `src/speculative_engine.cu`
- Public speculative descriptors:
  - `SpeculativeConfig`
  - `SpeculativeTree`
  - `VerificationResult`
- EAGLE-style predictive head primitive:
  - consumes FP16 hidden states shaped `[N, hidden_size]`
  - applies a FP16 linear projection with optional bias
  - writes candidate logits shaped `[N, vocab_size]`
  - selects deterministic top-`K` token candidates per source position
  - resolves ties by choosing the lower token ID
- Fixed-`K` tree layout support:
  - node `0` is the root/current-token context
  - every speculative node uses an explicit parent index
  - malformed parent arrays are rejected before CUDA mask generation
- CUDA tree-attention mask generation:
  - emits FP16 `[K, K]` masks
  - writes `0` when row node `i` is an ancestor of column node `j` or `i == j`
  - writes `-inf` for invalid cross-branch attention edges
  - supports chain and branching candidate trees
- Greedy speculative verification:
  - consumes supplied main-model logits shaped `[K, vocab_size]`
  - computes deterministic argmax tokens with lower-token tie breaking
  - follows parent-linked candidate paths from the root
  - accepts consecutive proposed tokens while they match the main-model argmax
  - returns accepted token count and terminal accepted node
- Native paged KV-cache module:
  - `include/spoolstream/kv_cache.h`
  - `src/kv_cache.cu`
- Static VRAM KV page window:
  - allocates a fixed device cache window partitioned into physical pages
  - tracks page residency in device global arrays
  - maps logical sequence page positions to physical cache pages
  - records per-page last-access steps for later eviction heuristics
- Constant descriptor caching:
  - stores `c_layer_page_tables[128]` in CUDA constant memory
  - validates and uploads layer page descriptor tables with `cudaMemcpyToSymbolAsync`
  - keeps each layer table compact enough to fit the GPU constant-memory ceiling
- Independent KV eviction stream:
  - creates a non-blocking `stream_kv`
  - schedules old KV pages from device to pinned host memory with `cudaMemcpyAsync`
  - can wait on a supplied quiet-window CUDA event before evicting
  - marks evicted pages through device-side tracking state
- Adaptive verification feedback:
  - tracks moving-average speculative validation accuracy
  - reduces look-ahead depth `K` to `1` when accuracy falls below `0.45`
- Defensive validation:
  - rejects null required pointers
  - rejects invalid dimensions
  - rejects `top_k <= 0`
  - rejects `top_k > vocab_size`
  - rejects malformed parent indices
  - rejects malformed KV page descriptors
  - rejects invalid KV page mappings and oversized evictions
  - checks CUDA launches through `SPOOLSTREAM_CUDA_CHECK`

### Validation Coverage

The Phase 3 test suite covers:

- EAGLE head projection and deterministic top-`K` candidate selection
- lower-token tie breaking in candidate ranking
- chain tree-attention mask generation
- branching tree-attention mask generation
- malformed parent rejection
- greedy verification accepting a full proposed path
- greedy verification stopping at the first mismatch
- paged KV-cache allocation and cleanup
- logical sequence page to physical page mapping
- KV page access-step tracking
- constant-memory page descriptor upload and fetch
- threshold-based KV eviction triggering
- independent `stream_kv` D2H eviction byte correctness
- feedback-driven look-ahead depth reduction
- null pointer and invalid configuration failures
- all Phase 1 parser/workspace tests
- all Phase 2 GEMM and pipeline tests

### Verified Build

Latest test commands passed:

```text
ctest --test-dir build --output-on-failure
spoolstream_parser_tests.exe
spoolstream_memory_manager_tests.exe
spoolstream_kernel_tests.exe
spoolstream_pipeline_tests.exe
spoolstream_speculative_tests.exe
spoolstream_kv_cache_tests.exe
```

Latest result:

```text
100% tests passed, 0 tests failed out of 6
```

### Not Yet Implemented

Phase 3 provides standalone speculative primitives, not the full integrated decoder. Remaining future work includes:

- integration with full transformer execution
- tokenizer-driven candidate decoding
- stochastic speculative acceptance
- full KV cache integration with attention kernels
- full generation loop
- Python `InferenceEngine`
- OpenAI-compatible API server

## Phase 3 Prompt 6: Paged KV-Cache Engine & Interleaved Eviction Streams

Implemented the standalone KV-cache infrastructure primitive:

- fixed-size VRAM page window
- device-resident page residency table
- device-resident logical sequence page table
- device-resident page last-access tracker
- CUDA constant-memory layer descriptor table cache
- pinned host eviction buffer
- independent non-blocking `stream_kv`
- event-gated D2H page eviction
- device-side eviction marker
- adaptive speculative look-ahead downshift when validation accuracy falls below `0.45`

Current limitation: this module manages KV cache pages and eviction movement, but it is not yet wired into a full attention kernel, tokenizer loop, or generation scheduler.

## Phase 4: Compilation, Tooling & Verification

### Status

Implemented and wheel-verified.

Phase 4 turns the native C++17/CUDA runtime into an installable Python package named `spoolstream`. The package is built with PEP 517, scikit-build-core, CMake, Ninja, MSVC, and native CUDA compilation. It exposes a clean CPython C-API extension without adding pybind11 or another binding framework.

### Current Capability

This phase adds:

- Native CPython extension binding:
  - `src/bindings.cpp`
  - module name: `spoolstream._core`
  - public Python class: `spoolstream.InferenceEngine`
- Python package entrypoint:
  - `python/spoolstream/__init__.py`
- PEP 517 manifest:
  - `pyproject.toml`
  - build backend: `scikit_build_core.build`
  - package version: `1.0.0`
- CMake packaging integration:
  - builds `spoolstream_core` as the native static CUDA/C++ library
  - builds `_core` as a Python extension module with Python SOABI tagging
  - installs `_core` and `__init__.py` into the wheel package
  - keeps all native CTest executables available
- CUDA toolkit discovery:
  - uses normal environment/toolchain discovery on Linux and configured shells
  - auto-detects installed Windows CUDA Toolkit roots before enabling the CUDA language
  - emits native `sm_89` code for this RTX 4060 workstation through `CMAKE_CUDA_ARCHITECTURES=89-real`
- Python API surface:
  - `spoolstream.InferenceEngine`
  - `spoolstream.build_info()`
  - `spoolstream.cuda_device_count()`
  - `spoolstream.parse_model_topology(...)`
  - `InferenceEngine.build_info()`
  - `InferenceEngine.cuda_device_count()`
  - `InferenceEngine.parse_model_topology(...)`
  - `InferenceEngine.estimate_h2d_transfer_ns(...)`
  - `InferenceEngine.compute_throttle_cycles(...)`
  - `InferenceEngine.conditional_graph_nodes_available()`
  - `InferenceEngine.kv_feedback(...)`

### Verified Packaging

The final wheel path was verified with:

```text
pip install --force-reinstall .
```

The build produced and installed:

```text
spoolstream-1.0.0-cp313-cp313-win_amd64.whl
```

Installed package smoke checks passed from both the repository root and an external working directory:

```text
import spoolstream
engine = spoolstream.InferenceEngine()
engine.build_info()
engine.cuda_device_count()
engine.kv_feedback(1.0, 4, 1, 4)
```

Latest native CTest result:

```text
100% tests passed, 0 tests failed out of 6
```

### Current Product Boundary

SpoolStream is now a compiled, importable native Python package exposing the completed runtime primitives. It is still not a full text-generation engine. Remaining work before interactive inference includes:

- tokenizer loading and tokenization APIs
- model config execution semantics
- end-to-end transformer layer orchestration
- attention and MLP integration using the Phase 2 GEMM primitive
- scheduler integration across weight streaming, compute, speculative paths, and KV eviction
- logits sampling
- Python `generate()`/chat APIs
- OpenAI-compatible server wrapper

## Phase 5: 30B Model ABI, Config, Tokenizer & Streaming Manifest

### Status

Implemented as the first 30B-readiness layer and build-verified.

Phase 5 starts the transition from standalone runtime primitives toward real 30B model loading. It does not generate text yet, but it now understands LLaMA-family model configuration, tokenizer JSON vocabularies, tensor execution roles, model manifests, and memory budgets for file-backed streaming mode.

### Current Capability

This phase adds:

- Native model ABI:
  - `ModelConfig`
  - `Tokenizer`
  - `ModelManifest`
  - `MemoryBudget`
  - `ModelProfile`
- LLaMA-family `config.json` parsing:
  - hidden size
  - intermediate size
  - layer count
  - attention heads
  - KV heads
  - vocab size
  - context length
  - RoPE theta
  - RMSNorm epsilon
  - AWQ/GPTQ/BF16/FP16 quantization detection
- Tokenizer JSON support:
  - reads `model.vocab`
  - tracks unknown/BOS/EOS/PAD IDs
  - supports deterministic longest-token encode for tokenizer JSON fixtures
  - supports decode with SentencePiece-style space marker normalization
- Full tensor topology preservation:
  - `ModelTopology` now retains all tensors, not only transformer-layer tensors
  - embeddings, final norm, LM head, and quant metadata are visible to higher layers
- Manifest role mapping:
  - token embeddings
  - LM head
  - attention Q/K/V/O
  - MLP gate/up/down
  - layer norms
  - AWQ/GPTQ scale/zero/group/qweight metadata
- 30B streaming budget planner:
  - computes total model bytes
  - computes double-buffer scratchpad requirement
  - computes largest-tensor staging requirement
  - decides whether streaming mode is mandatory
  - rejects insufficient VRAM or pinned staging budgets before allocation
- Python inspection API:
  - `spoolstream.inspect_model(...)`
  - `InferenceEngine.inspect_model(...)`

## Phase 6: Streaming Weight Store And Layer Scheduler Foundation

### Status

Started and build-verified.

This phase now has the first file-backed tensor staging primitive. It does not yet execute a full layer schedule, but it removes the critical full-model RAM residency assumption for future 30B support.

### Current Capability

This phase adds:

- `StreamingTensorStore`
- bounded pinned host staging allocation
- mapped CUDA UVA alias for the staging buffer
- exact SafeTensors shard byte-range reads using manifest tensor offsets
- validation that staged tensors fit the configured pinned window
- async H2D copy from staged tensor bytes into device memory
- no full-model host copy requirement for staged reads
- layer execution planning for transformer layers
- aligned tensor placement into scratchpad slots
- layer prefetch scheduling into caller-provided device slots
- CUDA event signaling when a streamed layer slot is ready
- Python `inspect_model(...)` now reports layer plan count and slot capacity

### Validation Coverage

The new model/streaming tests cover:

- config parsing
- AWQ quantization detection
- tokenizer encode/decode round trip
- manifest tensor role mapping
- all-tensor topology preservation
- streaming-required profile decision
- rejection of insufficient host staging budget
- exact shard byte-range staging from disk
- non-null pinned/UVA staging pointers
- H2D copy correctness from staged bytes
- rejection of tensors larger than the staging window
- layer plan construction
- slot offset alignment
- layer 0 to `slot_A` copy correctness
- layer 1 to `slot_B` copy correctness
- slot-capacity rejection
- missing-layer-plan rejection

Latest native CTest result:

```text
100% tests passed, 0 tests failed out of 8
```

Latest wheel verification:

```text
pip install --force-reinstall .
import spoolstream
engine = spoolstream.InferenceEngine()
hasattr(engine, "inspect_model") == True
```

### Remaining Work Toward 30B

The next required step is transformer execution: consume scheduled layer slots and implement RMSNorm, RoPE, attention projections, MLP composition, and logits output. Full 30B generation still requires attention/KV integration, sampling, and the generation loop.

## Phase 7: LLaMA Transformer Executor

### Status

Started and build-verified as standalone CUDA transformer math primitives.

Phase 7 begins the bridge from streamed weights to actual transformer computation. This pass does not yet run a full LLaMA layer end-to-end, but it adds the activation workspace and the core CUDA kernels needed by attention and MLP execution.

### Current Capability

This phase adds:

- Native transformer executor module:
  - `include/spoolstream/transformer_executor.h`
  - `src/transformer_executor.cu`
- Activation workspace allocation:
  - hidden state
  - residual
  - normalized state
  - Q/K/V buffers
  - attention output
  - MLP gate/up/down buffers
- CUDA RMSNorm:
  - FP16 input/output
  - FP32 reduction
  - per-channel FP16 weight
  - epsilon validation
- CUDA RoPE:
  - applies rotary embedding to Q and K
  - supports separate Q heads and KV heads
  - supports position offsets for decode
- CUDA residual add
- CUDA SiLU/SwiGLU composition
- CUDA half-buffer copy helper
- Defensive validation for null pointers, invalid dimensions, invalid RoPE head dimensions, and invalid workspace sizes.

### Validation Coverage

The Phase 7 test suite covers:

- activation workspace allocation and cleanup
- invalid workspace rejection
- RMSNorm against CPU reference
- RoPE against CPU reference for Q and K
- residual add against CPU reference
- SwiGLU against CPU reference
- half-buffer copy correctness
- null pointer validation

Latest native CTest result:

```text
100% tests passed, 0 tests failed out of 9
```

### Remaining Work Toward 30B

The next step is to compose these primitives with the Phase 6 scheduled layer slots:

- locate RMSNorm and projection weights by tensor role
- run attention Q/K/V projections using streamed quantized weights
- write/read the paged KV cache during prefill and decode
- run output projection and MLP projections
- produce a verified one-layer LLaMA forward pass against a CPU reference
- then scale to full prefill/decode over all streamed layers

## Phase 8: Portable Execution Contract + First Complete LLaMA Decoder Layer

### Status

Completed and build-verified.

Phase 8 turns the standalone runtime primitives into the first complete execution path. It adds a portable hardware/model policy layer for broader PC compatibility planning and implements a correctness-first LLaMA decoder-layer prefill path using FP16 fixture weights.

### Current Capability

This phase adds:

- Portable execution policy module:
  - `HardwareProfile` for CUDA device, VRAM, host RAM, compute capability, and conservative H2D bandwidth estimates
  - `ExecutionPolicy` for streaming mode, scratchpad slot size, host staging size, KV budget, quantization use, and backend selection
  - `CompatibilityReport` for readable rejection reasons
- Python inspection visibility:
  - `InferenceEngine.hardware_profile()`
  - `inspect_model(...)` now reports `hardware` and `execution_policy`
  - `build_info()` reports Phase 8 capability
- Transformer execution additions:
  - correctness-first FP16 dense matmul kernel
  - batch-1 causal attention prefill kernel
  - grouped-query attention support
  - role-based LLaMA decoder-layer weight resolver from a scheduled layer slot
  - complete LLaMA decoder-layer prefill orchestration:
    - input RMSNorm
    - Q/K/V projections
    - RoPE
    - causal attention
    - output projection
    - residual add
    - MLP RMSNorm
    - gate/up projections
    - SwiGLU
    - down projection
    - final residual add

### Validation Coverage

The Phase 8 test suite covers:

- real CUDA hardware profile probing
- synthetic consumer/high-VRAM/unsupported hardware policy checks
- readable compatibility rejection paths
- FP16 dense matmul against CPU reference
- causal attention against CPU reference
- grouped-query attention head mapping
- complete tiny LLaMA decoder-layer prefill against CPU reference

Latest native CTest result:

```text
100% tests passed, 0 tests failed out of 10
```

### Remaining Work Toward Broad Model Support

SpoolStream now has the first verified full decoder-block execution path, but it is still not a complete text-generation engine. Remaining work includes:

- adapt the projection path to real AWQ/GPTQ checkpoint tensor layouts
- stream real layer payloads into scratchpad slots and execute them without FP16 fixture shortcuts
- integrate paged KV-cache reads/writes into attention
- implement full-model prefill and decode over all layers
- add final norm, `lm_head`, logits, sampling, EOS handling, and token loop
- expand architecture adapters beyond LLaMA-family models
- add CLI/server product interfaces and real 7B/13B/30B hardware validation

## Product UI Phase: Tech-Blue Operator Dashboard

### Status

Completed and build-verified.

This phase adds the first SpoolStream user interface: a local browser dashboard for runtime visibility, version tracking, model inspection, and bounded benchmark estimates. It is intentionally an operator console rather than a chat interface, because generation runtime is still future work.

### Current Capability

This phase adds:

- Local dashboard server:
  - `spoolstream.dashboard.serve_dashboard(...)`
  - standard-library HTTP server
  - local-only default binding to `127.0.0.1`
  - no web framework or npm dependency
- CLI entry point:
  - `spoolstream ui`
  - `--host`
  - `--port`
  - `--no-browser`
- Static tech-blue UI:
  - overview metrics
  - hardware profile
  - runtime capability summary
  - memory visualization
  - phase timeline from `Versions.md`
  - model inspection form
  - H2D transfer estimate panel
  - benchmark history chart
  - local system logs
- JSON endpoints:
  - `GET /api/health`
  - `GET /api/build`
  - `GET /api/hardware`
  - `GET /api/versions`
  - `GET /api/logs`
  - `POST /api/inspect-model`
  - `POST /api/benchmark/h2d`
- Wheel packaging:
  - dashboard Python modules are installed into `spoolstream`
  - UI static assets are installed into `spoolstream/ui/static`
  - `Versions.md` is installed with the package for dashboard timeline rendering

### Validation Coverage

The dashboard test suite covers:

- version ledger parsing
- missing model-path validation
- invalid benchmark validation
- local HTTP health endpoint
- build endpoint
- hardware endpoint
- model inspection endpoint with a fake engine
- H2D benchmark endpoint with throttle-cycle reporting
- HTTP 400 behavior for invalid benchmark payloads

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 11
```

### Remaining Work

The UI is ready for operator visibility, but it cannot run real model chat yet. Remaining UI work depends on runtime phases:

- wire real generation benchmarks after `generate()` exists
- add model load sessions after `load_model()` exists
- add CLI/server launch controls after the local API server exists
- persist benchmark history to disk
- add compatibility reports for additional model families and backends

## Phase 9: Real Quantized Checkpoint Adapter

### Status

Started and build-verified.

Phase 9 begins the transition from synthetic FP16 decoder-layer fixtures toward real quantized checkpoint execution. This phase adds an adapter report that groups AWQ/GPTQ tensor families, validates their metadata, and distinguishes projections that are directly compatible with the current fused GEMM metadata contract from projections that need layout conversion first.

### Current Capability

This phase adds:

- Native quantized adapter module:
  - `include/spoolstream/quantized_adapter.h`
  - `src/quantized_adapter.cpp`
- Quantized projection descriptors:
  - projection role
  - layer ID
  - base tensor name
  - qweight tensor
  - scales tensor
  - qzeros/zeros tensor
  - optional `g_idx`
  - input features
  - output features
  - packed output columns
  - group count
  - inferred group size
  - zero encoding
  - kernel compatibility flag
  - compatibility notes
- Supported quantized tensor family detection:
  - attention Q/K/V/O projections
  - MLP gate/up/down projections
  - `lm_head`
- Metadata validation for:
  - `qweight` rank and int32 dtype
  - row-packed int4 layout `[K, N / 8]`
  - `scales` shape `[groups, N]`
  - expanded FP16 zeros shape `[groups, N]`
  - packed int32 qzeros shape `[groups, N / 8]`
  - optional `g_idx` shape `[K]`
- Broader manifest role inference:
  - any `.qweight` tensor is now recognized as quantized weight metadata
- Python inspection visibility:
  - `inspect_model(...)` now includes a `quantized_adapter` section

### Validation Coverage

The Phase 9 test suite covers:

- directly kernel-compatible AWQ metadata with expanded FP16 zeros
- real-checkpoint-style packed int32 qzeros
- projection role inference for attention and MLP projections
- inferred group counts and group sizes
- missing scale metadata rejection
- malformed `g_idx` rejection

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Remaining Work Toward Real Quantized Execution

Phase 9 can understand real quantized checkpoint families, but it does not yet execute packed-qzeros real checkpoints directly. Remaining work includes:

- implement qzeros unpack/fixup into expanded CUDA half metadata
- support `g_idx`-aware grouping or reject those models earlier with a precise compatibility report
- connect quantized projection descriptors to streamed scratchpad layer slots
- update the fused GEMM launcher to consume adapter descriptors
- run one real streamed AWQ/GPTQ LLaMA layer end-to-end
- then scale to full prefill/decode and token generation

## Phase 10: Quantized Metadata Materialization & First Packed-QZeros Projection

### Status

Completed and build-verified.

Phase 10 converts packed real-checkpoint qzeros metadata into the expanded half-precision zero metadata required by the current fused int4 GEMM path. This is the first phase where a real checkpoint-style packed-qzeros projection can move from adapter description to executable CUDA projection.

### Current Capability

This phase adds:

- Packed qzeros expansion:
  - input layout: int32 packed qzeros `[groups, output_features / 8]`
  - output layout: expanded FP16 zeros `[groups, output_features]`
  - low-nibble-first decode order matching the existing int4 GEMM kernel
- Quantized projection metadata workspace:
  - owns device-side expanded zero metadata
  - validates projection shape and zero encoding
  - uploads expanded FP16 zeros directly
  - unpacks packed int32 qzeros before device upload
  - cleans up CUDA memory defensively
- GEMM config materialization:
  - converts a materializable quantized projection descriptor into `FusedGemmConfig`
  - rejects unsupported `g_idx` execution paths for now
  - preserves activation selection for future projection fusion
- Adapter report improvements:
  - each projection now reports `materializable`
  - adapter report now counts materializable projections separately from directly kernel-compatible projections
- Python inspection visibility:
  - `inspect_model(...)` now reports `materializable`
  - `inspect_model(...)` now reports `materializable_projection_count`

### Validation Coverage

The Phase 10 test suite covers:

- packed qzeros expansion value-by-value
- null qzeros validation
- packed qzeros adapter report materializability
- metadata workspace allocation and cleanup
- packed-qzeros upload into expanded device metadata
- fused CUDA int4 GEMM execution using:
  - FP16 activation input
  - packed int4 qweight
  - FP16 scales
  - packed int32 qzeros expanded through the Phase 10 workspace
- CPU reference comparison for the packed-qzeros projection output

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Remaining Work Toward Real Layer Execution

SpoolStream can now execute a packed-qzeros quantized projection in isolation. Remaining work includes:

- connect projection materialization to `StreamingTensorStore`
- materialize qweight, scales, and qzeros directly from staged SafeTensors byte ranges
- resolve projection descriptors from a real scheduled layer scratchpad
- replace FP16 fixture projections in the decoder layer with quantized projection execution
- implement or precisely reject `g_idx`-based checkpoints
- execute one full real streamed AWQ/GPTQ LLaMA layer end-to-end

## Phase 11: Streamed Quantized Projection Binding & First Real Layer Slot Execution

### Status

Completed and build-verified.

Phase 11 connects the real checkpoint streaming path to the quantized projection executor. Instead of launching the int4 GEMM from synthetic device buffers, SpoolStream can now stage SafeTensors bytes through the bounded pinned streaming store, schedule a layer into a VRAM scratchpad slot, bind qweight/scales placements directly from that slot, materialize packed qzeros into the metadata workspace, and execute a quantized projection from the scheduled layer view.

### Current Capability

This phase adds:

- Quantized projection runtime view:
  - points to qweight inside a scheduled device layer slot
  - points to scales inside the same scheduled device layer slot
  - points to expanded device zero metadata in the Phase 10 workspace
  - carries the fused GEMM config for the bound projection
- Slot binding API:
  - `bind_quantized_projection_runtime_view(...)`
  - validates layer ID, required placements, byte sizes, metadata workspace dimensions, and non-null device pointers
- Projection launch API:
  - `launch_quantized_projection(...)`
  - dispatches the existing fused AWQ/GPTQ-compatible int4 GEMM through the runtime view
- First streamed quantized projection flow:
  - parse a SafeTensors checkpoint manifest
  - build a layer execution plan
  - stage qweight, scales, and qzeros from file-backed offsets
  - copy the layer payloads into a scratchpad slot
  - expand packed qzeros into CUDA half metadata
  - execute the projection from scratchpad-resident qweight/scales

### Validation Coverage

The Phase 11 test suite adds an end-to-end tiny GPTQ-style SafeTensors fixture that verifies:

- manifest parsing recognizes real quantized tensor roles
- layer scheduling places qweight/scales/qzeros into the scratchpad slot
- the streaming store reads exact SafeTensors byte ranges
- packed qzeros are staged from the fixture and expanded into device metadata
- the runtime view resolves qweight and scales from their scheduled slot offsets
- `launch_quantized_projection(...)` produces the same result as the CPU reference GEMM

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Remaining Work Toward Real Layer Execution

SpoolStream can now execute one real streamed quantized projection from a scheduled layer slot. Remaining work includes:

- replace all FP16 fixture projections in the LLaMA decoder layer with quantized slot-bound projections
- bind all required layer tensor roles for Q/K/V/O and MLP gate/up/down projections
- add quantized projection support for `g_idx` checkpoints or reject them before execution
- stream and execute one full real AWQ/GPTQ LLaMA layer end-to-end
- implement full-model prefill/decode across all layers
- connect logits, sampling, tokenizer loop, CLI chat, and server endpoints

## Phase 12: Full Streamed Quantized LLaMA Decoder Layer

### Status

Completed and build-verified.

Phase 12 converts the Phase 11 single-projection bridge into the first complete streamed quantized decoder-layer execution path. SpoolStream can now execute a full tiny LLaMA-style decoder layer using qweight/scales/qzeros loaded from a SafeTensors checkpoint into a scheduled VRAM scratchpad slot, while preserving the existing CUDA RMSNorm, RoPE, causal attention, residual, and SwiGLU primitives.

### Current Capability

This phase adds:

- Quantized decoder-layer runtime descriptor:
  - attention RMSNorm pointer from the scheduled layer slot
  - slot-bound Q/K/V/O projection runtime views
  - MLP RMSNorm pointer from the scheduled layer slot
  - slot-bound gate/up/down projection runtime views
- Full quantized layer binding API:
  - `bind_quantized_llama_decoder_layer_weights(...)`
  - validates projection roles, scheduled placements, metadata workspaces, and layer-local norm tensors
- Full quantized prefill execution API:
  - `execute_quantized_llama_decoder_layer_prefill(...)`
  - runs input RMSNorm
  - streamed quantized Q/K/V projections
  - RoPE
  - batch-1 causal prefill attention with GQA support
  - streamed quantized output projection
  - attention residual
  - MLP RMSNorm
  - streamed quantized gate/up projections
  - SwiGLU
  - streamed quantized down projection
  - final residual
- Shape validation for each projection role:
  - Q/O: `hidden -> hidden`
  - K/V: `hidden -> kv_heads * head_dim`
  - gate/up: `hidden -> intermediate`
  - down: `intermediate -> hidden`

### Validation Coverage

The Phase 12 test suite adds a complete tiny GPTQ-style SafeTensors checkpoint with:

- one LLaMA decoder layer
- attention and MLP norm tensors
- all seven quantized projections:
  - `q_proj`
  - `k_proj`
  - `v_proj`
  - `o_proj`
  - `gate_proj`
  - `up_proj`
  - `down_proj`
- packed int4 qweights
- FP16 scales
- packed int32 qzeros

The test verifies:

- manifest parsing recognizes every real quantized tensor family
- layer scheduling places the entire decoder layer into one scratchpad slot
- packed qzeros are staged from SafeTensors offsets and expanded into CUDA metadata
- all seven projection runtime views bind to scheduled slot offsets
- the full CUDA quantized decoder-layer prefill output matches a CPU reference implementation using the same int4 dequantization math

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Remaining Work Toward Full Generation

SpoolStream can now execute one complete streamed quantized LLaMA decoder layer from a real SafeTensors-style fixture. Remaining work includes:

- execute all model layers in sequence for full-model prefill
- integrate real paged KV-cache writes during prefill
- implement decode-time KV-cache reads
- add final norm, `lm_head`, logits, sampling, EOS handling, and token loop
- connect `InferenceEngine.load_model(...)` and `InferenceEngine.generate(...)`
- run real 7B/13B/30B checkpoint compatibility and performance tests
- add `g_idx` support or precise early rejection for those GPTQ variants

## Phase 13: Multi-Layer Streamed Prefill Executor

### Status

Completed and build-verified.

Phase 13 extends the Phase 12 single-layer execution path into the first streamed model-body prefill executor. SpoolStream can now iterate through every layer in a quantized LLaMA-style manifest, schedule each layer from SafeTensors offsets into alternating scratchpad slots, bind the seven quantized projections for that layer, execute the full decoder block, and carry activations forward into the next layer.

### Current Capability

This phase adds:

- Multi-layer prefill API:
  - `execute_streamed_llama_model_prefill(...)`
  - accepts a `StreamingTensorStore`
  - accepts a `ModelManifest`
  - accepts a `LayerPlanSet`
  - accepts a `QuantizedAdapterReport`
  - uses two caller-provided scratchpad slots
  - returns `StreamedPrefillResult`
- Runtime layer loop:
  - validates model/config/workspace agreement
  - alternates scratchpad slot A/B by layer
  - schedules each layer through `schedule_layer_prefetch(...)`
  - stages and expands qzeros metadata for every projection
  - binds Q/K/V/O and gate/up/down projections from the scheduled layer slot
  - calls `execute_quantized_llama_decoder_layer_prefill(...)`
  - reuses activation buffers across layers
- Stream accounting:
  - reports layers executed
  - reports scheduled bytes streamed

### Validation Coverage

The Phase 13 test suite adds a complete two-layer GPTQ-style SafeTensors fixture with:

- two decoder layers
- per-layer attention and MLP RMSNorm tensors
- all seven packed int4 projection families per layer
- per-projection FP16 scales
- packed int32 qzeros expanded at runtime
- two scratchpad slots used by the model-body executor

The test verifies:

- SafeTensors manifest parsing across multiple layers
- layer-plan construction for each layer
- alternating scratchpad scheduling
- full quantized decoder-layer execution for each layer
- activation handoff from layer 0 to layer 1
- final streamed model-body output against a CPU reference implementation

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream can now execute a streamed quantized model body for tiny LLaMA fixtures without loading all layer weights into VRAM or normal RAM at once. It still stops at the final hidden states and does not yet produce logits or tokens.

### Next Phase Plan

Phase 14 will add final RMSNorm, `lm_head` projection, logits, and deterministic greedy token selection so a completed model-body prefill can produce a next-token ID.

## Phase 14: Final Norm, LM Head, Logits & Greedy Token Output

### Status

Completed and build-verified.

Phase 14 adds the first native next-token selection path after streamed model-body execution. SpoolStream can now normalize final hidden states, execute a quantized `lm_head`, materialize logits, and select the greedy token ID from the final token position with deterministic tie-breaking.

### Current Capability

This phase adds:

- Quantized `lm_head` support:
  - fixed tensor-role inference so `lm_head.qweight`, `lm_head.scales`, and `lm_head.qzeros` are recognized as quantized metadata
  - plain `lm_head.weight` remains available as a non-quantized tensor role
- Device projection view binding:
  - `bind_quantized_projection_device_view(...)`
  - supports qweight/scales staged into dedicated device buffers or future caches
- Final logits API:
  - `execute_quantized_final_logits_greedy(...)`
  - runs final RMSNorm
  - launches quantized `lm_head`
  - writes `[tokens, vocab]` FP16 logits
  - returns `GreedyTokenResult`
- CUDA greedy argmax:
  - scans the last token row
  - returns token ID and logit
  - breaks ties by lower token ID

### Validation Coverage

The Phase 14 test suite adds a checkpoint-backed final-head fixture that verifies:

- `model.norm.weight` staging through the streaming store
- quantized `lm_head` adapter detection
- qweight/scales/qzeros staging from SafeTensors offsets
- packed qzeros expansion for `lm_head`
- final RMSNorm and quantized logits generation
- greedy token ID and logit against CPU reference

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream can now produce a real next-token ID from final hidden states in tiny quantized fixtures. The remaining missing piece for multi-token generation is autoregressive decode state: token embedding input, KV-cache writes/reads, and repeated token-loop execution.

### Next Phase Plan

Phase 15 will add a correctness-first decode loop with KV-cache write/read integration and greedy multi-token generation over tiny fixtures. Speculative decoding remains disabled until the baseline token loop is stable.

## Phase 15: Greedy Decode Loop & KV-Cache Token Records

### Status

Completed and build-verified.

Phase 15 adds the first repeated autoregressive execution loop. SpoolStream can now take an initial token ID, look up its embedding, run one-token streamed quantized model execution, produce greedy logits, feed the selected token into the next step, and record generated tokens into the paged KV-cache window.

### Current Capability

This phase adds:

- Token embedding lookup:
  - `launch_token_embedding_lookup(...)`
  - maps a token ID to a `[1, hidden]` FP16 activation row
- Greedy decode loop:
  - `execute_greedy_decode_loop(...)`
  - batch size 1
  - greedy-only sampling
  - configurable `max_new_tokens`
  - optional EOS stop
  - repeats streamed model-body execution plus final logits
- KV-cache integration:
  - `record_decode_token_in_kv_cache(...)`
  - maps sequence pages
  - writes generated token records into the device KV window
  - marks page access for the generated step
- Decode output:
  - host output token buffer
  - generated token count
  - last token ID

### Validation Coverage

The Phase 15 test suite adds a tiny checkpoint-backed decode fixture that verifies:

- token embedding lookup feeds decode input
- two greedy decode steps execute without OOM or CUDA errors
- generated tokens are valid vocabulary IDs
- paged KV-cache records are written into the device cache window
- KV active page metadata is updated

Latest native and Python CTest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream can now generate multiple greedy token IDs from tiny quantized fixtures. The current decode loop records token-level KV activity, but attention still recomputes a one-token path and does not yet consume full K/V tensor history from the paged cache. That is acceptable for the first baseline loop, but it is the main correctness/performance gap before real model quality.

### Next Phase Plan

Phase 16 will expose the load/generate path through the Python `InferenceEngine` API. The API will start with inspection and readiness-oriented generation entry points, then use native runtime capability reports to reject unsupported real checkpoints clearly rather than failing deep in CUDA execution.

## Phase 16: Python Load/Generate API Surface

### Status

Completed and build-verified.

Phase 16 exposes the first product-facing model lifecycle methods on the Python `InferenceEngine`. The API now has a persistent model-load readiness state and a guarded generation entry point that refuses unsupported real generation with an explicit structured reason instead of failing deep inside CUDA.

### Current Capability

This phase adds:

- `InferenceEngine.load_model(...)`:
  - builds the native manifest
  - computes memory profile
  - computes hardware execution policy
  - builds quantized adapter report
  - stores the readiness report on the engine instance
  - returns a dictionary with `loaded`, `generation_ready`, and `generation_reason`
- `InferenceEngine.generate(...)`:
  - validates that `load_model(...)` was called first
  - validates sampling arguments
  - returns a structured `not_ready` response until real checkpoint text generation is enabled
- Engine load state cleanup:
  - loaded report is owned per engine instance
  - Python reference is released during deallocation

### Validation Coverage

The full native and Python CTest suite remains green after adding Python engine state and methods.

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream now has the Python product API shape needed by callers: model loading, readiness reporting, and generation entry point. Real text generation is still guarded because tokenizer-backed checkpoint execution and hardware compatibility testing are not yet complete.

### Next Phase Plan

Phase 17 will add a real checkpoint compatibility pass: richer compatibility reports, required tensor-family checks for generation readiness, explicit `g_idx` rejection, tokenizer presence checks, and benchmark/load readiness flags for 7B/13B/30B AWQ/GPTQ checkpoints.

## Phase 17: Real Checkpoint Compatibility Pass

### Status

Completed and build-verified.

Phase 17 adds a readiness report for real checkpoint attempts. SpoolStream can now inspect a candidate model directory and explain whether it has the tokenizer, embeddings, final norm, quantized `lm_head`, and per-layer projection families required by the current streamed quantized execution path.

### Current Capability

This phase adds `generation_readiness` to `inspect_model(...)` and `load_model(...)` reports:

- tokenizer checks:
  - requires local `tokenizer.json`
- tensor role checks:
  - token embeddings
  - final norm
  - quantized `lm_head`
- per-layer projection checks:
  - Q/K/V/O
  - gate/up/down
  - materializable qweight/scales/qzeros metadata
- quantization checks:
  - AWQ/GPTQ int4 only for the current runtime path
- unsupported layout checks:
  - flags `g_idx` projections as not executable yet
- readiness summary:
  - `ready`
  - `issues`
  - required projection count
  - materializable projection count

### Validation Coverage

The full native and Python CTest suite remains green after adding compatibility reporting.

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream now has the compatibility screen needed before real model attempts. Instead of failing inside CUDA, a real checkpoint can be rejected early with concrete missing tensor families or unsupported quantization metadata.

### Next Phase Plan

Phase 18 will add consumer-hardware benchmark readiness: a Python benchmark method that combines model inspection, compatibility reporting, H2D estimates, scratchpad planning, and a dry-run readiness summary suitable for the UI and first real model-load attempts.

## Phase 18: Consumer Hardware Benchmark Readiness

### Status

Completed and build-verified.

Phase 18 adds a dry-run benchmark path for first real model attempts on consumer hardware. SpoolStream can now inspect a candidate checkpoint, evaluate compatibility, compute execution policy, build layer plans, estimate model-body H2D transfer cost, and report whether the checkpoint is ready for a first attempt.

### Current Capability

This phase adds:

- `InferenceEngine.benchmark_model(...)`:
  - builds the native manifest
  - computes memory profile
  - computes execution policy
  - computes generation readiness
  - builds layer execution plans
  - sums scheduled layer bytes per streamed pass
  - estimates H2D transfer time per generated token
  - estimates H2D transfer time for a requested decode length
  - reports `ready_for_first_attempt`
- Build metadata now reports Phase 18.
- Benchmark output is explicitly a dry run:
  - no hidden model execution
  - no fake token throughput
  - no silent compatibility assumptions

### Validation Coverage

The native and Python test suite remains green after adding benchmark reporting.

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream is now ready to attempt real model loading and dry-run benchmarking. It can tell us whether a candidate AWQ/GPTQ LLaMA checkpoint has the required tensor families, whether the workstation memory policy accepts it, and what the model-body streaming transfer estimate looks like before we try a live run.

### Remaining Work After The Six-Phase Run

The next step is no longer another synthetic primitive phase. The next step is to point SpoolStream at actual local checkpoints in increasing size:

- tiny real/synthetic packaged fixture
- real 7B AWQ/GPTQ
- real 13B AWQ/GPTQ
- first 30B/32B AWQ/GPTQ attempt

Known remaining limitations:

- tokenizer-backed prompt encoding is not wired into native generation yet
- real checkpoint embedding staging is not wired into `generate(...)`
- decode attention records KV activity but does not yet consume historical K/V tensors
- `g_idx` GPTQ variants are rejected
- performance optimization has not started beyond transfer estimates and strict streaming shape

## Phase 19: Real Qwen2 Checkpoint Inspection Smoke

### Status

Completed and build-verified.

Phase 19 is the first phase driven by an actual local model checkpoint instead of only synthetic fixtures. The local `qwen 5B` folder is a single-shard Qwen2 BF16 SafeTensors checkpoint with no `model.safetensors.index.json`, so this phase added the ingestion support needed to inspect it correctly and report the real execution blocker.

### Current Capability

This phase adds:

- single-shard SafeTensors discovery when `model.safetensors.index.json` is absent
- Qwen2 config admission through the portable model-family field
- BF16 detection from `torch_dtype: "bfloat16"`
- Python inspection metadata exposing `family: "QWEN2"`
- execution policy recognition for Qwen2 decoder-style manifests
- deterministic tests for:
  - no-index single-shard SafeTensors parsing
  - Qwen2 BF16 config and manifest construction

### Real Model Smoke

Verified against the local model folder:

```text
model path: qwen 5B
phase: Phase 19
family: QWEN2
model_type: qwen2
quantization: BF16
tensor_count: 338
layers: 28
total_model_bytes: 3087428608
w_max_bytes: 93595648
max_tensor_bytes: 466747392
policy_supported: True
policy_backend: QWEN2
profile_supported: True
generation_readiness: False
ready_for_first_attempt: False
estimated_model_body_h2d_ns_per_token: 163792384
```

The checkpoint is now inspected correctly, but it is not executable by the current generation path because it is BF16/unquantized. The current runtime execution path expects AWQ/GPTQ int4 projections and quantized `lm_head` metadata.

### Validation Coverage

The native and Python CTest suite remains green after adding real-checkpoint ingestion support.

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream now understands the real local Qwen2 checkpoint well enough to profile it and reject it cleanly for the right reason. That is an important step: the blocker is no longer parser shape, missing index files, or architecture naming. The blocker is execution support for BF16 dense checkpoints or converting/using an AWQ/GPTQ int4 Qwen checkpoint.

### Next Phase Plan

Phase 20 should choose one of two concrete paths:

- add a BF16 dense streaming fallback for small real checkpoints like this Qwen2 5B model, useful for correctness but not VRAM/cost advantage
- prioritize Qwen2 AWQ/GPTQ adapter support so the runtime can execute quantized checkpoints through the existing int4 streaming path

For the final consumer-hardware goal, the second path matters more. BF16 support is valuable as a correctness bridge, but 30B-class execution on low RAM/VRAM requires quantized weights and file-backed streaming.

## Phase 20: Qwen2 AWQ/GPTQ Adapter Readiness

### Status

Completed and build-verified.

Phase 20 prepares SpoolStream for the next real-model attempt: a Qwen2-family AWQ/GPTQ int4 SafeTensors checkpoint. It does not add GGUF support and does not make the existing BF16 Qwen checkpoint executable. Instead, it hardens the compatibility layer around the quantized tensor families the current int4 runtime can execute.

### Current Capability

This phase adds:

- `tie_word_embeddings` parsing from `config.json`
- Python inspection output for:
  - `config.family`
  - `config.tie_word_embeddings`
- generation-readiness output-head diagnostics:
  - `has_quantized_lm_head`
  - `tied_word_embeddings`
  - `tied_embedding_output_detected`
  - `output_head_mode`
  - `requires_quantized_lm_head`
  - `requires_tied_embedding_logits`
- Qwen2 quantized adapter fixture coverage:
  - Q/K/V/O projections
  - gate/up/down MLP projections
  - model-level quantized `lm_head`
  - GQA-shaped K/V output projections
  - packed `qzeros` materialization path
- Build metadata now reports Phase 20.

### Important Behavior

SpoolStream now distinguishes these cases:

- **Quantized `lm_head` present**:
  - output mode is `QUANTIZED_LM_HEAD`
  - current int4 final-logits path can use it
- **Tied embeddings present but no quantized `lm_head`**:
  - output mode is `TIED_EMBEDDING_PENDING`
  - checkpoint is recognized, but generation readiness remains false until dense tied logits are integrated
- **No usable output head**:
  - output mode is `MISSING`
  - checkpoint is rejected with a direct missing-output-head reason

### Validation Coverage

The full native and Python CTest suite remains green after adding Qwen2 AWQ/GPTQ adapter-readiness coverage.

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream is now better positioned for the model you should download next: a SafeTensors AWQ/GPTQ Qwen2/Qwen2.5-style model. If that checkpoint includes materializable int4 projection families and a quantized `lm_head`, the readiness checker should move much closer to a first execution attempt. If it relies on tied embeddings instead, SpoolStream will now say that precisely instead of emitting a misleading generic `lm_head` failure.

### Next Phase Plan

Phase 21 should run against the first real AWQ/GPTQ SafeTensors model:

- inspect the downloaded checkpoint
- compare tensor naming and shapes against the Phase 20 Qwen2 fixture
- fix any real naming/layout mismatch
- stage one real Qwen2 quantized layer from the checkpoint into the streaming scratchpad
- execute at least one real quantized projection from that checkpoint
- keep `generate(...)` guarded until tokenizer, embeddings, logits, and KV-cache integration are verified together

## Phase 21: Real LLAMA GPTQ ExLlama Projection Bring-Up

### Status

Completed and build-verified.

Phase 21 brings SpoolStream onto the first real GPTQ SafeTensors execution target: the local `LLAMA-GPT4Q` checkpoint. This phase does not enable full generation yet. It verifies that SpoolStream can recognize the real ExLlama GPTQ tensor layout, stage real checkpoint projection tensors, execute one CUDA quantized projection, and match a CPU reference.

### Current Capability

This phase adds:

- GPTQ ExLlama int4 layout detection:
  - `qweight [K / 8, N]`
  - `scales [groups, N]`
  - `qzeros [groups, N / 8]`
  - `g_idx [K]`
- `GPTQ_EXLLAMA_INT4` projection layout metadata.
- g_idx-aware CUDA projection execution:
  - FP16 input activations `[M, K]`
  - packed int4 qweight lookup by `k / 8`
  - group lookup by `g_idx[k]`
  - packed qzero expansion to FP16 metadata
  - FP32 accumulation and FP16 output
- Projection bias readiness handling:
  - absent bias is accepted
  - file-backed all-zero FP16 bias is accepted
  - nonzero projection bias is rejected with a clear issue
- Dense FP16 `lm_head.weight` readiness reporting:
  - `output_head_mode: DENSE_FP16_LM_HEAD_PENDING`
  - generation readiness remains false until dense final logits are integrated
- Build metadata now reports Phase 21.

### Real Model Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed inspection result:

```text
phase: Phase 21
model_type: llama
quantization: GPTQ_INT4
layers: 32
quantized_adapter.supported: true
projection_count: 224
materializable_projection_count: 224
generation_readiness.ready: false
output_head_mode: DENSE_FP16_LM_HEAD_PENDING
```

Real CUDA projection smoke:

```text
target projection: model.layers.0.self_attn.q_proj
K: 4096
N: 4096
result: CUDA output matched CPU reference
max_abs_error: 7.62939e-06
```

### Validation Coverage

The full native and Python CTest suite remains green after adding Phase 21.

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

Additional optional real-model smoke:

```text
spoolstream_real_gptq_smoke.exe LLAMA-GPT4Q
LLAMA-GPT4Q q_proj smoke passed: projections=224 K=4096 N=4096 max_abs_error=7.62939e-06
```

### Current Review

SpoolStream has crossed an important line: it is no longer only validating synthetic quantized fixtures. It can now execute a real LLaMA GPTQ ExLlama projection from disk-backed SafeTensors bytes and prove correctness against a CPU reference.

### Remaining Work

The checkpoint still cannot generate text because the final output head is dense FP16 and the current final-logits path only handles quantized `lm_head` projections. The next phase should add dense FP16 final logits execution and then wire real-token prefill/decode checks around the existing tokenizer, embedding, layer, and KV-cache pieces.

## Phase 22: Streaming Dense FP16 lm_head Final Logits

### Status

Completed and build-verified.

Phase 22 removes the Phase 21 output-head blocker for checkpoints like `LLAMA-GPT4Q` that provide a dense FP16 `lm_head.weight` instead of a quantized `lm_head.qweight`. The implementation does not allocate the full dense head in VRAM. It streams vocabulary-row tiles from SafeTensors into a bounded CUDA staging path and computes greedy logits tile by tile.

### Current Capability

This phase adds:

- File-backed tensor slice staging through `stage_tensor_slice(...)`.
- Streaming dense FP16 `lm_head.weight` execution:
  - accepts shape `[vocab_size, hidden_size]`
  - normalizes the final hidden state with RMSNorm
  - streams lm-head row tiles through pinned host memory
  - computes CUDA dot products for each tile
  - returns greedy token, logit, bytes streamed, and tile count
- Synthetic CTest coverage for:
  - non-divisible vocabulary tile sizes
  - dense final-logit correctness against a CPU reference
  - streamed byte count and tile count validation

### Real Model Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed result:

```text
target projection: model.layers.0.self_attn.q_proj
q_proj max_abs_error: 7.62939e-06
dense_lm_head_token: 83596
dense_lm_head_logit: 10.7031
dense_lm_head_tiles: 126
```

The dense output head is now executable without full-head VRAM residency.

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream can now execute real GPTQ ExLlama projections and the real dense FP16 output head from the LLAMA GPTQ checkpoint. The next blocker is prompt materialization: tokenizer IDs must become device hidden states through streamed token embeddings.

### Next Phase Plan

Phase 23 will add tokenizer-backed prompt embedding materialization:

- encode prompt text through local `tokenizer.json`
- stream only required embedding rows from `model.embed_tokens.weight`
- build `[tokens, hidden_size]` device hidden states
- validate the real LLAMA embedding tensor path without full embedding-table VRAM residency

## Phase 23: Tokenizer Prompt Path And Streamed Embedding Rows

### Status

Completed and build-verified.

Phase 23 adds the first real prompt materialization path. SpoolStream can now load the local tokenizer, encode prompt text into token IDs, and stream only the needed rows from `model.embed_tokens.weight` into a device hidden-state buffer.

### Current Capability

This phase adds:

- LLaMA-style tokenizer JSON tolerance for `added_tokens`.
- BOS/EOS special-token detection from tokenizer added-token metadata.
- A safe fallback unknown token when a tokenizer has no explicit UNK token.
- Streamed token embedding lookup:
  - validates `model.embed_tokens.weight` shape `[vocab_size, hidden_size]`
  - validates token ID ranges
  - reads one FP16 embedding row per token from SafeTensors
  - copies rows directly into the device activation buffer
  - reports tokens embedded and bytes streamed
- CTest coverage for repeated token IDs and exact streamed embedding-row contents.

### Real Model Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed result:

```text
prompt: Hello from SpoolStream
prompt_tokens: 6
embedding_bytes: 49152
dense_lm_head_token: 83596
dense_lm_head_tiles: 126
```

The embedding table is not loaded into VRAM. Only the prompt rows were streamed.

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream now has the front and back edges of a real inference path for the LLAMA GPTQ checkpoint:

- prompt text can become real device hidden states
- real quantized projections can execute
- dense final logits can execute by streaming `lm_head.weight`

The next blocker is the middle of the network: running an actual LLaMA decoder block with real streamed GPTQ projection families.

### Next Phase Plan

Phase 24 will execute one complete real LLaMA decoder layer:

- stream layer 0 into a scratchpad slot
- upload qzeros and `g_idx` metadata for all seven projections
- run RMSNorm, Q/K/V, RoPE, causal attention, O projection, MLP, and residuals
- verify the layer completes on the real checkpoint without OOM or invalid metadata

## Phase 24: First Complete Real LLaMA Decoder Layer

### Status

Completed and build-verified.

Phase 24 executes the first full real decoder block from the local GPTQ checkpoint. This phase uses the same streamed layer scheduler as the future full-model path and fixes the shared metadata upload path so `g_idx` is uploaded for every GPTQ ExLlama projection workspace.

### Current Capability

This phase adds:

- `g_idx` upload inside the shared streamed projection metadata path.
- Real layer execution with:
  - input RMSNorm
  - Q/K/V GPTQ ExLlama projections
  - RoPE
  - causal attention
  - O projection
  - residual add
  - MLP RMSNorm
  - gate/up/down GPTQ ExLlama projections
  - SwiGLU
  - final residual add
- Optional real smoke coverage for layer 0 on `LLAMA-GPT4Q`.

### Real Model Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed result:

```text
prompt_tokens: 6
embedding_bytes: 49152
layer0_bytes: 113569792
layer0_first: 21.7969
q_proj max_abs_error: 7.62939e-06
dense_lm_head_tiles: 126
```

Layer 0 completed with real streamed tensors and finite output.

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream can now execute a real LLaMA decoder block from a GPTQ ExLlama checkpoint under the streaming memory model. The next step is to run all layers in sequence for a prompt prefill and produce final logits from the resulting hidden state.

### Next Phase Plan

Phase 25 will add full-model real prefill smoke:

- embed a short prompt
- stream and execute all 32 layers
- apply final RMSNorm
- stream dense `lm_head.weight`
- return a greedy next-token candidate

## Phase 25: Full Real Model Prefill And Greedy Next Token

### Status

Completed and build-verified.

Phase 25 runs the real model body end to end for a one-token prefill smoke. It streams all 32 decoder layers from the `LLAMA-GPT4Q` checkpoint, applies final RMSNorm, streams dense `lm_head.weight`, and returns a greedy next-token candidate.

### Current Capability

This phase adds:

- Full 32-layer streamed LLaMA prefill smoke on the real checkpoint.
- Correct GPTQ ExLlama qzero decode offset for packed `qzeros`.
- End-to-end real checkpoint path:
  - tokenizer prompt smoke
  - streamed embedding rows
  - streamed quantized decoder layers
  - dense streamed final logits
  - greedy token selection

### Real Model Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed result:

```text
q_proj max_abs_error: 0
prompt_tokens: 6
embedding_bytes: 49152
layer0_bytes: 113569792
layer0_first: 0.000509262
full_layers: 32
full_bytes: 3634233344
full_token: 32
full_logit: 11.1875
dense_lm_head_tiles: 126
```

The full model body completed without CUDA OOM and produced finite output.

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

This is the first real end-to-end inference-shaped path through SpoolStream: prompt rows, streamed layers, final logits, and a token candidate. It is still a smoke path, not a product chat loop. It recomputes prefill and does not yet expose user-facing generation.

### Next Phase Plan

Phase 26 will add a decode loop around the real prefill path:

- keep generated token IDs
- run repeated one-token/full-context prefill steps for correctness-first generation
- record generated tokens into the paged KV tracking system
- keep KV historical attention consumption listed as an optimization/follow-up item

## Phase 26: Correctness-First Decode Loop And KV Tracking

### Status

Completed and build-verified.

Phase 26 adds a real decode smoke loop around the full-prefill path. It is correctness-first: each decode step reruns full-context prefill over the current token sequence, then streams the dense output head and records the generated token in the paged KV tracking window.

### Current Capability

This phase adds:

- Repeated real-checkpoint decode smoke over streamed model weights.
- Generated-token tracking in host token vectors.
- KV tracking records for generated decode tokens.
- Verification that the KV device window matches generated token IDs.

### Real Model Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed result:

```text
full_layers: 32
full_bytes: 3634233344
full_token: 32
decode_tokens: 2
decode_last: 502
```

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
```

### Current Review

SpoolStream can now move through the shape of generation on a real model: encode, embed, prefill, logits, choose a token, append it, and repeat. The current decode loop prioritizes correctness and checkpoint integration; it does not yet use historical KV tensors to accelerate attention, so it is much slower than the final architecture should be.

### Next Phase Plan

Phase 27 will add sampling controls:

- greedy selection
- temperature sampling
- top-k filtering
- top-p filtering
- repetition penalty
- deterministic seed support for tests and repeatable smoke runs

## Phase 27: Streamed Dense-Logit Sampling Controls

### Status

Completed and build-verified.

Phase 27 adds sampling over the streamed dense FP16 `lm_head.weight` path. The implementation keeps the output head file-backed, streams it in bounded tiles, computes logits for the last hidden state, then applies user-facing sampling controls without materializing the full model in RAM.

### Current Capability

This phase adds:

- Temperature sampling.
- Top-k filtering.
- Top-p nucleus filtering.
- Repetition penalty over recent token IDs.
- Deterministic seed-based sampling.
- Validation for bad sampling settings.

### Real Model Smoke Target

Verification target:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed smoke additions:

```text
sample_token: 43
```

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
LLAMA-GPT4Q smoke passed with streamed sampling
```

### Current Review

The project now has enough pieces for a minimal user-visible generation path: streamed prompt embedding, streamed full-layer execution, streamed dense logits, and configurable token sampling. The path is still correctness-first and slow because decode currently repeats full-context prefill rather than using an optimized KV-cache attention path.

### Next Phase Plan

Phase 28 will expose the real path through the Python API:

- store loaded model paths in `InferenceEngine`
- mark dense FP16 `lm_head.weight` as supported for generation readiness
- add a correctness-first `InferenceEngine.generate(...)`
- run a one-token real-model Python smoke test

## Phase 28: First Real Python Generate Path

### Status

Completed and build-verified.

Phase 28 exposes the real streamed model path through `spoolstream.InferenceEngine.generate()`. It is still correctness-first: every generated token reruns a full-context prefill over the current prompt context, streams all quantized decoder layers, streams the dense FP16 output head, and samples a token.

### Current Capability

This phase adds:

- `InferenceEngine.load_model(...)` stores model path and budget metadata.
- Generation readiness now treats dense FP16 `lm_head.weight` as supported through streamed logits.
- `InferenceEngine.generate(...)` can run the real `LLAMA-GPT4Q` checkpoint.
- Python-visible sampling parameters:
  - `temperature`
  - `top_p`
  - `top_k`
  - `repetition_penalty`
- Python result metadata:
  - generated token IDs
  - decoded generated text
  - full decoded context
  - total streamed bytes
  - layers executed
  - staging capacity

### Current Limits

- Batch size 1 only.
- LLaMA GPTQ ExLlama layout only for real checkpoint generation.
- Prompt plus generated tokens are capped at 32 tokens in this smoke path.
- Decode uses repeated full-context prefill, not optimized KV-cache reuse.
- Performance is not yet representative of the final target.

### Real Model Python Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Smoke command loaded the model and generated one token:

```text
ready: True
output_head_mode: DENSE_FP16_LM_HEAD_STREAMING
status: ok
tokens: [4999]
text: '!Ċ'
layers_executed: 32
total_streamed_bytes: 4684955648
```

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 12
Python InferenceEngine.generate smoke passed on LLAMA-GPT4Q
```

### Current Review

SpoolStream now has the first end-user-shaped flow: install/import the Python package, load a real local LLaMA GPTQ checkpoint, and ask the engine to produce a token. The architecture is finally connected end to end. The next major work is turning this from a correctness smoke into a useful chat engine by removing repeated full-prefill decode, integrating real KV-cache reads/writes into attention, and adding performance instrumentation.

### Next Phase Plan

Phase 29 should focus on optimized decode correctness:

- write K/V tensors from each layer into paged KV cache
- read historical K/V during decode attention
- avoid recomputing the entire prompt for every new token
- keep the existing full-prefill path as a correctness fallback
- compare optimized decode logits against repeated-prefill logits on short prompts

## RIFT MVP R0-R8: Runtime Inference Fitting Tool

### Status

Completed and build-verified as the first RIFT MVP layer over the SpoolStream
native backend.

RIFT changes the product surface from a low-level experimental runtime into a
hardware-aware local LLM deployment tool. It can inspect a model and PC,
benchmark local streaming conditions, create a `.riftplan`, execute supported
models through SURVIVAL mode, expose a local API server, and write a usability
report.

### Current Capability

RIFT currently supports:

- `RiftEngine` Python facade.
- `rift` CLI alias.
- Hardware profile inspection.
- Model inspection with RIFT compatibility levels:
  - `INSPECT_ONLY`
  - `PLAN_READY`
  - `NATIVE_RUN_READY`
  - `UNSUPPORTED`
- RIFT deployment modes:
  - `FAST`
  - `BALANCED`
  - `SURVIVAL`
  - `REJECTED`
- Local disk streaming benchmark samples.
- H2D transfer estimates from the native backend.
- `.riftplan` schema version 1.
- `.riftplan` writer and reader.
- SURVIVAL run wrapper around the Phase 28 real generation path.
- Usability reports with:
  - mode
  - load time
  - generation time
  - token throughput
  - streamed bytes
  - verdict
  - recommendations
- Local API server endpoints:
  - `GET /v1/models`
  - `POST /v1/completions`
  - `POST /v1/chat/completions`
  - `GET /rift/status`
  - `GET /rift/metrics`
  - `GET /rift/report`
- Dashboard backend routes for:
  - RIFT benchmark
  - RIFT plan
  - RIFT run
  - latest RIFT report
- RIFT documentation:
  - README quickstart
  - `RIFT_QUICKSTART.md`
  - `RIFT_KNOWN_LIMITATIONS.md`
  - `RIFT_COMPATIBILITY_MATRIX.md`
  - `RIFT_DEVELOPMENT_LOG.md`
  - example `.riftplan`

### Verified Real Model Target

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed installed-package smoke:

```text
compatibility_level: NATIVE_RUN_READY
recommended_mode: SURVIVAL
layers: 32
plan: SURVIVAL
run_status: ok
generated_tokens: 1
tokens_per_second: 0.1431
usability_verdict: SLOW
```

### Validation Coverage

Latest RIFT MVP verification:

```text
cmake --build build --config Release
100% tests passed, 0 tests failed out of 13
cmake --install build --config Release --prefix phase19_install
Installed-package RIFT API smoke passed on LLAMA-GPT4Q
Installed CLI help/report smoke passed
```

### Current Limits

- Only SURVIVAL mode is executable.
- FAST and BALANCED are planned but not implemented.
- Native generation support is limited to the validated LLaMA GPTQ SafeTensors
  path.
- Decode still uses repeated full-context prefill instead of optimized KV-cache
  reuse.
- Performance is slow and reported honestly as `SLOW` for the current real-model
  smoke.
- The local server is an MVP local server, not a production multi-user runtime.

### Next Product Direction

The next major phase should start post-MVP optimization:

- add `rift doctor`
- implement optimized KV-cache decode
- compare optimized decode logits against repeated-prefill fallback
- make BALANCED mode real with RAM/VRAM cache reuse
- add model-family adapters and external backend strategy options
- improve dashboard reporting and report history

## RIFT R9: Doctor And Fit-Aware Planner

### Status

Completed and build-verified.

R9 adds the product distinction RIFT needs before optimization work: a model can
be **hardware-suitable** for a better mode while the current runtime can only
execute a slower fallback. This directly addresses the current LLaMA GPTQ case:
the model can fit better than SURVIVAL in principle, but RIFT still runs
SURVIVAL until BALANCED/FAST backends exist.

### Current Capability

R9 adds:

- `RiftEngine.doctor(...)`
- CLI:
  - `rift doctor --model <path>`
- Dashboard route:
  - `POST /api/rift/doctor`
- Mode analysis in inspection and plans:
  - `best_hardware_fit_mode`
  - `best_executable_mode`
  - `recommended_executable_mode`
  - `runtime_gap`
  - per-mode `hardware_suitable`
  - per-mode `runtime_available`
- `.riftplan` fields:
  - `hardware_fit_mode`
  - `best_executable_mode`
  - `mode_analysis`
- Post-MVP roadmap:
  - `RIFT_POST_MVP_PHASES.md`

### Important Behavior

`recommended_mode` remains executable. If the current runtime can only execute
SURVIVAL, the plan keeps:

```text
recommended_mode: SURVIVAL
```

But the same plan can now say:

```text
hardware_fit_mode: BALANCED
runtime_gap: true
```

That means the PC/model pair deserves a better runtime path, and SURVIVAL is
only the current fallback.

### Real Model Doctor Smoke

Verified against:

```text
C:\Users\aksha\Desktop\Code Files\SpoolStream\LLAMA-GPT4Q
```

Observed:

```text
overall_status: WARN
recommended_mode: SURVIVAL
hardware_fit_mode: BALANCED
runtime_gap: true
BALANCED hardware_suitable: true
BALANCED runtime_available: false
```

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 13
Installed CLI doctor smoke passed on LLAMA-GPT4Q
```

### Remaining Work

The next phase must make the runtime match the fit analysis:

- optimized KV-cache decode
- repeated-prefill fallback comparison
- BALANCED VRAM/RAM tensor cache
- eventually FAST mostly-resident runtime

## RIFT R10: Cached Decode Attention Primitive

### Status

Completed and build-verified as a native CUDA primitive.

R10 starts the move away from repeated full-prefill decode by adding the first
low-level cached decode attention building block. It does not yet replace
`generate(...)`, but it proves that a one-token decode attention kernel can read
K/V history from cache and match the equivalent last-token causal prefill
result.

### Current Capability

R10 adds:

- `launch_store_kv_cache_token(...)`
  - stores one token's K/V vectors into contiguous cache buffers
  - validates cache capacity and pointer inputs
- `launch_causal_attention_decode(...)`
  - consumes current-token Q
  - reads cached K/V for `cached_tokens`
  - supports GQA head mapping
  - uses FP32 softmax math internally
  - emits FP16 attention output for the current token
- Native build metadata now reports:
  - `Phase 28 + R10 primitives`

### Validation Coverage

The transformer executor tests now cover:

- storing every K/V token into cache
- running decode attention for the last token
- comparing decode output against the last-token slice from full causal prefill
- rejecting invalid decode config with zero cached tokens

Latest result:

```text
100% tests passed, 0 tests failed out of 13
```

### Remaining Work

The primitive is not yet wired into the full real model generation loop.
Remaining R10/R11 integration work:

- allocate per-layer K/V cache storage
- store projected K/V during real prefill
- use cached K/V during one-token decode
- compare optimized decode logits against repeated-prefill logits
- expose optimized decode as the default path when validation passes

## RIFT R11-R17: Seven-Phase Post-MVP Product Bridge

### Status

Completed and build-verified.

This seven-phase pass makes RIFT materially more useful around the current
native runtime while keeping BALANCED/FAST runtime availability honest.

### Current Capability

RIFT now adds:

- R11 decode readiness:
  - `RiftEngine.decode_readiness()`
  - `rift decode-readiness`
  - cached decode primitive status
  - optimized generation integration blockers
- R12 BALANCED cache planning:
  - `balanced_cache_plan`
  - planned VRAM cache bytes
  - planned host cache bytes
  - estimated cached-weight fraction
  - runtime promotion blocker
- R13 richer report metrics:
  - first-token latency estimate
  - per-token latency list
  - p50 token latency
  - p95 token latency
  - `decode_path`
- R14 serving hardening:
  - server busy state
  - single-request guard
  - MVP SSE streaming response shape
- R15 report history:
  - `.rift/reports/*.riftreport.json`
  - `RiftEngine.list_reports(...)`
  - `rift reports`
  - dashboard report-history route
- R16 model compatibility advice:
  - `RiftEngine.compatibility_advice(...)`
  - `rift compat --model <path>`
  - LLAMA GPTQ native candidate detection
  - GGUF external-backend recommendation
  - Qwen/Mistral/Gemma/Phi adapter-pending guidance
- R17 release hardening:
  - server tests
  - dashboard route tests
  - product-layer tests
  - docs updated

### Important Behavior

RIFT can now say:

```text
hardware_fit_mode: BALANCED
recommended_mode: SURVIVAL
runtime_gap: true
balanced_cache_plan.runtime_available: false
```

That means the model/hardware pair deserves BALANCED, but the native runtime has
not yet been promoted.

### Validation Coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 14
```

### Remaining Work

The next engineering milestone is native runtime promotion:

- integrate cached K/V into real LLaMA layer execution
- compare optimized decode logits against repeated-prefill logits
- make BALANCED runtime available
- then add FAST runtime for comfortably resident models

## RIFT R18: Hugging Face Hub Pull

### Status

Completed and build-verified.

R18 adds direct Hugging Face Hub snapshot pulling to RIFT. The feature is
implemented without adding PyTorch, Transformers, Accelerate, or
`huggingface_hub` to the runtime path. It uses the Hub HTTP API directly, keeps
downloads local and explicit, and preserves the existing RIFT inspect/plan/run
workflow.

### Current Capability

RIFT now adds:

- stdlib-only Hub client:
  - model metadata lookup through the Hub model API
  - filtered snapshot file selection
  - resumable `.part` file downloads through HTTP range requests
  - bearer-token support through argument or `HF_TOKEN` /
    `HUGGING_FACE_HUB_TOKEN`
- CLI:
  - `rift pull <org/model> --dry-run`
  - `rift pull <org/model> --output <local-folder>`
  - `--revision`
  - `--include`
  - `--ignore`
  - `--max-bytes`
  - `--endpoint`
- Python API:
  - `RiftEngine.pull_model_from_hub(...)`
  - `HfHubClient`
  - `HubFile`
- Dashboard:
  - `POST /api/rift/pull`
  - Hub Pull panel for dry-run/download workflows
- Default file policy:
  - includes SafeTensors, GGUF, JSON/tokenizer, text/metadata files
  - ignores legacy `.bin`, `.pt`, `.pth`, ONNX, H5, and msgpack blobs
  - rejects unsafe remote paths such as absolute paths or `..`

### Important Behavior

`rift pull` prepares a local model folder for RIFT. It does not guarantee that
the pulled model is executable. After download, RIFT runs compatibility advice
and optional inspection so unsupported model families still fail with readable
reasons.

### Validation Coverage

The new test suite uses an in-process Hub-compatible HTTP server and verifies:

- model API metadata parsing
- default include/ignore filtering
- nested path preservation
- unsafe path rejection
- dry-run byte accounting
- `--max-bytes` rejection
- real local snapshot download
- RIFT wrapper inspection/advice after download
- dashboard route coverage

Latest result:

```text
100% tests passed, 0 tests failed out of 15
```

### Remaining Work

The next product/runtime milestones are still:

- native cached-KV decode integration
- BALANCED runtime promotion
- Hub model-card preflight and license/display metadata
- optional integration with external backends for GGUF and non-LLaMA families

## RIFT R19: Optimized Hub Scout And Model Recommender

### Status

Completed and build-verified.

R19 adds a bounded Hugging Face Hub recommendation layer. RIFT can now inspect
the local hardware profile, query a tight Hub candidate window, enrich only the
best candidates, score them with explainable factors, and return practical
deployment advice instead of asking the user to manually search the entire Hub.

### Current Capability

RIFT now adds:

- bounded Hub search through `HfHubClient.search_models(...)`
- selective metadata enrichment through `model_info(..., expand=[...])`
- local Hub metadata cache under `.rift/hub_cache/`
- cache TTL default of 24 hours and refresh bypass support
- `RiftEngine.recommend_models(...)`
- CLI:
  - `rift recommend --task chat`
  - `rift recommend --task coding --mode balanced --top 10`
  - `rift recommend --formats gptq,gguf,safetensors`
  - `rift recommend --max-download-gb 12`
  - `rift recommend --pull-best --output .\models\best`
  - `rift recommend --refresh`
  - `rift recommend --write-report recommendations.json`
- dashboard/API:
  - `POST /api/rift/recommend`
  - ranked model cards with fit, speed, quality, safety, and popularity scores
  - warnings, evidence, backend advice, and ready-to-run pull commands
- mode-free best-for-hardware summary:
  - `absolute_best`
  - `best_performance`
  - `best_accuracy_proxy`
  - `best_overall`
- simplified user answer:
  - headline recommendation
  - why this model fits
  - tradeoffs
  - pull command
- laptop-first ranking:
  - runtime support is shown as context
  - native RIFT support no longer drives the primary recommendation
  - unknown Hub file sizes are estimated from parameter count and format
- CLI typo alias:
  - `rift reccommend` maps to `rift recommend`
- source layout transition:
  - CUDA survival-runtime `.cu` files moved from `src/` to `src/Survival/`

### Important Behavior

RIFT does not crawl the full Hugging Face Hub live. It uses a query funnel:

```text
bounded search arms -> cheap pre-rank -> finalist enrichment -> explainable score
```

The score weights are:

```text
hardware fit 25%
expected speed 20%
quality proxy 35%
safety/trust 15%
popularity/community 5%
```

Popularity and model-card metadata are treated as evidence, not guarantees.
Recommendations include confidence and warnings so users can see why RIFT chose
a model and where the advice is uncertain.

### Validation Coverage

The new test coverage uses an in-process Hub-compatible fake server and
verifies:

- bounded model search through the Hub API shape
- cache hit avoids repeated server calls
- `--refresh` bypasses cache
- finalist enrichment is capped
- oversized repositories are filtered by `max_download_gb`
- format filters work
- gated/private models are excluded by default
- 8 GB VRAM / 16 GB RAM ranks practical GPTQ/GGUF above oversized BF16
- coding task boosts coding-tagged models
- optional `--pull-best` calls the existing pull path
- dashboard recommendation route coverage
- CLI report writing

Latest result:

```text
100% tests passed, 0 tests failed out of 16
```

Focused Python tests and the full native CTest suite passed.

Live hardware report generated on this workstation:

```text
.rift\reports\hardware-model-recommendations-r19.json
.rift\reports\laptop-best-model-r19.json
```

The latest laptop-first run queried 9 bounded Hub arms, received 347 raw
candidates, kept 191 after filters, enriched 50 finalists, and returned 25
ranked recommendations for the RTX 4060 Laptop GPU / 16 GB RAM profile.

Latest headline result:

```text
Best model for this laptop: Qwen/Qwen2.5-7B-Instruct-GGUF
Best speed: Qwen/Qwen1.5-0.5B-Chat-GPTQ-Int4
Best quality proxy: Qwen/Qwen2.5-7B-Instruct-GGUF
```

### Remaining Work

R19 improves discovery and deployment advice. The runtime work remains:

- integrate cached-KV decode into real generation
- promote BALANCED mode after parity checks
- add external backend launch guidance for GGUF
- broaden native adapters beyond LLaMA GPTQ
- add live Hub metadata rate-limit handling and richer safety/license display

## RIFT Milestone 3: Backend-Aware Local LLM Orchestrator

### Status

Completed and focused-test verified.

Milestone 3 moves RIFT from "model recommender plus experimental native
runtime" toward the intended product shape: a hardware-aware local LLM
orchestrator. RIFT can now inspect a local model/workload pair, recommend a
real serving backend, explain the decision, and write a `.riftplan` that
contains the backend, launch shape, KV/context estimate, and install/readiness
state.

### Current Capability

RIFT now adds:

- backend catalog:
  - `llama.cpp`
  - `vLLM`
  - `SGLang`
  - `LMCache-aware mode`
  - experimental `RIFT native survival`
- CLI:
  - `rift backends`
  - `rift backend --model <path>`
  - `rift compat --model <path> --context-length 8192 --concurrency 2`
  - `rift plan --model <path> --workload chat --context-length 4096`
- backend recommendation inputs:
  - model format
  - model family/type
  - quantization method
  - CUDA/VRAM/RAM profile
  - workload
  - context length
  - concurrency
  - prefix reuse signal
- backend choices:
  - GGUF routes to `llama.cpp`
  - AWQ/GPTQ/SafeTensors routes to `vLLM` by default
  - structured/prefix-heavy workloads can route to `SGLang`
  - high prefix-reuse and long-context workloads can route to `LMCache-aware mode`
  - RIFT native survival remains available for correctness-first LLaMA GPTQ smoke runs
- plan schema v2 with:
  - `backend_decision`
  - `serving_plan`
  - `kv_plan`
  - legacy fields preserved for compatibility
- local server additions:
  - `GET /health`
  - `GET /rift/plan`
  - `GET /api/rift/plan`
  - backend fields included in status
- dashboard recommendation cards now show backend and support level.

### Important Behavior

RIFT does not fake backend availability. A selected backend is marked
`runtime_available: false` unless the executable, environment variable, or
Python package is detected locally. Plans include install hints and launch
templates so users can see the practical next action.

RIFT native CUDA remains an experimental survival path. Milestone 3 treats
llama.cpp, vLLM, SGLang, and LMCache-aware mode as product-level orchestration
targets rather than pretending the native runtime can serve every model family.

### Validation Coverage

Focused Python tests now verify:

- GPTQ/SafeTensors models route to `vLLM` planning
- GGUF models route to `llama.cpp`
- prefix-heavy long-context workloads route to `LMCache-aware mode`
- `.riftplan` schema v2 contains backend, serving, and KV planning sections
- compatibility advice includes backend decisions
- server status and plan endpoints expose Milestone 3 backend planning
- dashboard route coverage still passes
- Hub recommendation tests still pass with updated backend advice

Latest focused result:

```text
spoolstream rift tests passed
spoolstream recommend tests passed
spoolstream dashboard tests passed
spoolstream server tests passed
100% tests passed, 0 tests failed out of 16
```

CLI smoke verification:

```text
rift backends
rift backend --model LLAMA-GPT4Q --context-length 4096 --concurrency 1
rift plan --model LLAMA-GPT4Q --context-length 4096 --concurrency 1 --benchmark-read-bytes 1048576 --output .rift\milestone3-smoke.riftplan
```

The `LLAMA-GPT4Q` smoke plan selected `vLLM` as the stable serving backend for
the GPTQ SafeTensors model, marked it `runnable_now: false` because vLLM is not
installed on PATH/in the venv, generated an OpenAI-compatible launch template,
and estimated KV pressure as `LOW` for 4096 context at concurrency 1.

### Remaining Work

Milestone 3 makes RIFT usable as a planner/orchestrator, but the next product
steps are:

- launch and supervise external backends directly from `rift serve`
- detect installed backend versions and supported quantization features
- generate backend-specific config files for vLLM/SGLang/LMCache
- add live health probing for launched OpenAI-compatible endpoints
- make the dashboard start/stop backend processes
- benchmark the selected backend and write a real usability report
- keep native RIFT runtime research separate from stable orchestration paths

## RIFT Terraform-Style Control Plane: llama.cpp Provider Gate

### Status

Implemented and focused-test verified.

This step turns RIFT into a declarative LLM serving control-plane skeleton. The
new direction is explicit: RIFT is the planner, orchestrator, launcher,
benchmark runner, tuner, monitor, and recovery layer for external LLM serving
backends. The first verified provider gate is `llama.cpp`.

### Current Capability

RIFT now adds:

- `rift.yaml` config generation and validation.
- Terraform-style commands:
  - `rift init`
  - `rift discover`
  - `rift generate`
  - `rift plan`
  - `rift apply`
  - `rift status`
  - `rift benchmark`
  - `rift tune`
  - `rift destroy`
  - `rift logs`
- provider command surface:
  - `rift backend detect`
  - `rift backend install-plan llama.cpp`
  - `rift backend install llama.cpp --allow-install`
  - `rift backend install llama.cpp --allow-install --variant cpu|cuda12|cuda13`
  - `rift backend health llama.cpp`
- local source generation:
  - scans local model folders
  - ranks GGUF quant files for the detected workstation
  - selects practical `llama.cpp` deployment shape
  - writes human-readable decision justifications and alternatives
- side-effect safety:
  - `plan` is read-only
  - `apply` refuses download/install/launch without explicit flags
  - unavailable backends produce install plans instead of fake launches
  - `apply --allow-install` can install missing `llama.cpp` into `.rift/backends/llama.cpp`
  - `apply --allow-install --allow-launch` replans after install and launches only after the backend is detected
- persistent state and artifacts:
  - `.rift/state.json`
  - `.rift/discovery/*.json`
  - `.rift/generated/rift.generated.yaml`
  - `.rift/generated/rift.optimized.yaml`
  - `.rift/plans/*.riftplan.json`
  - `.rift/reports/*.json`
  - `.rift/logs/*.log`
- local control API for the future dashboard:
  - `GET /api/rift/state`
  - `GET /api/rift/discovery`
  - `GET /api/rift/generated-config`
  - `GET /api/rift/plan`
  - `GET /api/rift/backends`
  - `GET /api/rift/services`
  - `GET /api/rift/metrics`
  - `GET /api/rift/reports`
  - `POST /api/rift/discover`
  - `POST /api/rift/generate`
  - `POST /api/rift/plan`
  - `POST /api/rift/apply`
  - `POST /api/rift/benchmark`
  - `POST /api/rift/tune`
  - `POST /api/rift/destroy`
- replacement UI requirements are captured in `RIFT_UI_DESIGN_PROMPT.md`.

### Important Behavior

RIFT still does not bundle or silently install third-party backends. If
`llama.cpp` is not available, `rift plan` reports the official install plan.
`rift backend install llama.cpp --allow-install` and
`rift apply --allow-install` are the explicit approval paths that download
official `ggml-org/llama.cpp` release archives into `.rift/backends/llama.cpp`.
Model downloads are separately gated by `--allow-download`, and launching is
gated by `--allow-launch`.

The old dashboard remains in the tree only as legacy surface area. The product
UI is now expected to target the new `/api/rift/*` control API.

### Validation Coverage

Focused tests now verify:

- starter `rift.yaml` creation
- local hardware discovery
- local GGUF source scanning
- `Q4_K_M` preference on an 8 GB VRAM profile
- justified generated YAML
- read-only plan generation
- apply permission gates
- unavailable-backend install-plan behavior
- fake-release `llama.cpp` archive extraction and post-install executable detection
- `apply --allow-install --allow-launch` install, replan, and launch sequencing with a fake provider
- tuning candidate/report generation
- control API routes for state, generate, plan, and backends
- CLI smoke for `init`, `discover`, `generate`, `plan`, `apply`, and `backend detect`
- existing RIFT, recommendation, dashboard, and server tests still pass

Latest focused result:

```text
spoolstream orchestrator tests passed
spoolstream server tests passed
spoolstream rift tests passed
spoolstream recommend tests passed
spoolstream dashboard tests passed
```

### Remaining Work

Next gates:

- run a real `llama-server` launch/health/benchmark once installed locally
- add process recovery with restart limits and crash reason capture
- implement the vLLM adapter only after the `llama.cpp` gate has real launch verification
- implement SGLang and LMCache-aware adapters after vLLM
- expand cluster commands beyond local-plus-inventory into agentless SSH/PowerShell execution
- replace the legacy UI with a dashboard built on the new control API

## RIFT Multi-Provider Adapter Gate: vLLM, SGLang, LMCache-Aware Overlay

### Status

Implemented and build-verified.

This step expands RIFT from a single verified `llama.cpp` provider into a
multi-backend orchestration layer. RIFT can now detect, plan, health-check,
benchmark, tune, and install-gate four backend targets:

- `llama.cpp`
- `vllm`
- `sglang`
- `lmcache_aware`

### Current Capability

RIFT now adds provider adapters for:

- vLLM:
  - detects `VLLM_SERVER`, `VLLM_BIN`, `vllm` on PATH, or the Python `vllm`
    module
  - produces OpenAI-compatible `vllm serve ...` or Python-module launch plans
  - tunes GPU memory utilization, sequence count, and batched token limits
  - reports official install guidance
- SGLang:
  - detects `SGLANG_SERVER`, `SGLANG_BIN`, `sglang` on PATH, or the Python
    `sglang` module
  - produces OpenAI-compatible `sglang.launch_server` launch plans
  - tunes static memory fraction and logging level
  - reports official install guidance
- LMCache-aware overlay:
  - detects both `lmcache` and vLLM availability
  - emits an LMCache YAML config
  - passes vLLM `--kv-transfer-config` with `LMCacheConnectorV1`
  - tunes chunk size and local CPU KV-cache budget

Shared provider infrastructure now handles:

- OpenAI-compatible `/health` and `/v1/models` probes
- OpenAI-compatible chat-completions benchmark calls
- managed backend process launch with per-service logs
- package/module/executable detection
- user-approved Python package install attempts on supported platforms

### Important Behavior

RIFT remains conservative on native Windows. `vllm`, `sglang`, and
`lmcache_aware` now provide install plans and can be installed through the
provider contract on supported Linux/WSL2-style environments, but RIFT refuses
automatic native-Windows pip installs with a clear reason instead of attempting
large CUDA backend installs that are likely unsupported.

The actual `rift.exe` venv command now reports all providers through:

```text
rift backend detect
rift backend install-plan vllm
rift backend install-plan sglang
rift backend install-plan lmcache_aware
```

### Validation Coverage

New tests cover:

- provider registry includes `llama.cpp`, `vllm`, `sglang`, and
  `lmcache_aware`
- fake executable detection for vLLM and SGLang
- vLLM launch-plan generation
- SGLang launch-plan generation
- LMCache-aware launch-plan generation with config/env wiring
- SafeTensors auto-backend routing to the vLLM provider gate
- CLI `backend install` permission behavior
- installed `rift.exe` backend detection and install-plan smoke
- unsupported native-Windows install refusal for vLLM, SGLang, and
  LMCache-aware mode

Latest result:

```text
100% tests passed, 0 tests failed out of 17
```

Real local model smoke:

```text
rift plan --model .\LLAMA-GPT4Q --context-length 4096 --concurrency 1 --benchmark-read-bytes 1048576 --output .rift\multi-provider-llama-gptq-smoke.riftplan
```

Observed:

```text
selected_backend: vllm
runtime_available: false
reason: vLLM selected as the best stable strategy for GPTQ SafeTensors, but it is not installed/on PATH.
```

### Remaining Work

The next practical gate is real backend execution:

- install or point RIFT at a working `llama-server`
- run a real `llama.cpp` launch, health probe, and benchmark
- add backend log parsing and crash recovery limits
- validate vLLM/SGLang in WSL2/Linux or Docker
- add cluster remote execution for provider install/launch

## RIFT Real Workstation Serve Smoke - 2026-07-11

RIFT has now completed a real local setup flow on this workstation:

- inspected the RTX 4060 Laptop GPU / 8 GB VRAM / 16 GB RAM hardware profile
- checked available disk space before model download
- recommended a bounded GGUF model for the laptop
- installed a CUDA llama.cpp Windows backend after explicit approval
- pulled `hugging-quants/Llama-3.2-1B-Instruct-Q8_0-GGUF`
- generated `.rift/generated/setup-rift.yaml`
- planned and applied a llama.cpp service
- launched a healthy OpenAI-compatible endpoint at `http://127.0.0.1:11735/v1`
- ran a successful prompt through the server
- wrote benchmark, tuning, and setup reports under `.rift/reports`

Observed real prompt timing on the selected 1B Q8 GGUF model:

```text
prompt eval: 54.89 tok/s
decode:      130.76 tok/s
```

RIFT benchmark reports:

```text
baseline: 132.36 tok/s estimate, batch=512, ubatch=128, threads=8
tuned:    130.30 tok/s estimate, batch=256, ubatch=128, threads=8
```

The tuning pass correctly generated `.rift/generated/rift.optimized.yaml` and
the optimized launch command used the selected `batch=256` setting. For this
small model, the baseline profile remained slightly faster.

### Fixes Added During The Smoke Run

- llama.cpp installation now ignores CUDA runtime-only archives when choosing
  the primary Windows server artifact.
- Windows backend process launch has stronger process creation flags for
  long-running servers.
- `rift tune` now accepts `--config`.
- `rift apply --optimize` now rebuilds the actual launch command from the
  winning tuning candidate instead of only recording it in metadata.
- `serving.optimized_tuning` in generated YAML now feeds real provider launch
  plans.

### Validation

```text
spoolstream_orchestrator_tests: passed
full CTest suite: 17/17 passed
```

### Important Product Finding

The selected 1B model is mechanically successful and very fast, but it
hallucinates product explanations. RIFT's serving path works; the next quality
step is a higher-quality recommendation profile and live benchmark-driven tuning
for larger Q4/Q5 GGUF models that still fit this laptop.

## RIFT Milestone 3: Exact Artifact Recommendation - 2026-07-12

### Status

Complete and verified.

### Capabilities Added

- RIFT now resolves the exact GGUF artifact inside a multi-quant Hugging Face
  repository instead of treating every quant file as one download.
- GGUF selection is hardware-aware and currently prefers `Q4_K_M` on this
  8 GB VRAM workstation, with higher- and lower-precision alternatives included
  in the decision evidence.
- Sharded GGUF artifacts are grouped and validated as one logical artifact;
  every required shard is carried into the pull plan.
- Exact file sizes are fetched from the Hub repository tree for a bounded set of
  finalists. When exact metadata is unavailable, RIFT labels the result
  provisional instead of presenting an estimate as exact.
- Recommendation now measures free disk space at the intended model cache,
  preserves a configurable reserve, and excludes artifacts that do not fit.
- `rift pull` performs a second disk-capacity guard immediately before download.
- `rift generate`, `rift plan`, and `rift apply` retain the selected filename,
  shard list, quantization, byte size, and disk-feasibility evidence.
- After a Hub pull, backend launch now receives the downloaded model file path;
  it no longer passes the containing repository directory to `llama-server`.

### Real Workstation Verification

Read-only Hub discovery was run with:

```text
rift recommend --task chat --top 5 --candidate-limit 120 \
  --max-download-gb 12 --formats gguf \
  --download-root .rift/models --disk-reserve-gb 2 --refresh
```

Observed disk policy:

```text
free bytes:    107,876,024,320
reserved:        2,147,483,648
usable bytes:  105,728,540,672
```

The bounded search examined 120 repositories, retained and enriched 25
candidates, and returned five exact deployment candidates. The report is stored
at `.rift/reports/milestone3-exact-artifact.json`.

For `Qwen/Qwen2.5-7B-Instruct-GGUF`, RIFT selected:

```text
quantization: Q4_K_M
shards:       2
exact bytes:  4,683,073,632
exact GiB:    4.361
disk status:  fits
backend:      llama.cpp
```

No model was downloaded during this verification.

### Validation Coverage

- multi-quant GGUF selection
- deterministic `Q4_K_M` preference for an 8 GB GPU
- exact Hub tree size enrichment
- sharded GGUF grouping and completeness
- artifact-scoped pull commands
- insufficient-disk exclusion and pre-download rejection
- generated YAML artifact propagation
- exact downloaded-file handoff to the backend launcher
- Python compilation checks
- full native/Python CTest suite: `17/17` passed

### Known Limits

- Model quality is still ranked from metadata, model size, tags, safety signals,
  and community evidence. It is not yet a local comparative quality evaluation.
- Hardware analysis still needs richer CPU, storage-speed, thermal/power, PCIe,
  memory-pressure, and RIFT-managed resource accounting.
- Long-running process supervision, restart backoff, degraded state, and incident
  reports are not implemented yet.

### Next Milestone

Milestone 4 is the Service Supervisor: process liveness, health timelines,
restart policy, backoff, degraded-state reporting, persistent incidents, and
safe recovery of RIFT-managed services.

## RIFT Milestone 4: Local Service Supervisor - 2026-07-12

### Status

Complete and verified at the local control-plane level.

### Capabilities Added

- `rift status` now combines managed-process liveness with backend HTTP health
  and reports healthy, unhealthy, crashed, degraded, stopped, and unknown
  service counts.
- `rift monitor` performs one-shot, bounded, or continuous reconciliation.
- Observation alone is non-destructive. Automatic restart is enabled only with
  `--allow-recovery`.
- `rift recover --allow-launch` performs an explicitly authorized recovery from
  the exact persisted backend launch plan. `--force` can restart a healthy
  service intentionally.
- Service monitoring policy now includes health timeout and bounded history.
- Recovery policy now includes enable/disable, maximum restarts, exponential
  backoff, maximum backoff, and restart-counter reset after a healthy interval.
- RIFT persists per-service health history and supervisor state in
  `.rift/state.json`.
- Every detected failure, restart, failed restart, or exhausted restart limit
  writes an incident JSON file under `.rift/incidents/`, including the health
  observation, process information, policy state, action, and backend log tail.
- Services become `degraded` after their restart budget is exhausted instead of
  entering an unbounded crash loop.
- `rift destroy` now uses the shared process termination path and records the
  desired service state as stopped, preventing accidental recovery.
- Control API additions:
  - `GET /api/rift/incidents`
  - `POST /api/rift/monitor`
  - `POST /api/rift/recover`

### Real Workstation Verification

A non-recovering monitor pass inspected the currently running service:

```text
service:       chat
backend:       llama.cpp
PID:           23620
process alive: true
HTTP health:   200 /health
phase:         healthy
restart count: 0
incidents:     0
endpoint:      http://127.0.0.1:11735/v1
```

The real service was not restarted or interrupted during verification.

### Failure-Injection Verification

Deterministic provider/process tests verify:

- healthy process and endpoint detection
- crashed-process detection
- recovery refusal without permission
- authorized relaunch from persisted launch configuration
- old-process termination before relaunch
- exponential retry backoff
- second relaunch after backoff expiry
- restart ceiling enforcement
- degraded-state transition
- bounded health-history retention
- incident creation and log-tail capture
- monitor and incident control API routes
- CLI permission behavior for monitor/recover/incidents

### Test Result

```text
full native/Python CTest suite: 17/17 passed
```

### Known Limits

- Continuous supervision currently requires a running
  `rift monitor --iterations 0` process; Windows Service/systemd installation is
  not implemented yet.
- Recovery restarts the same backend and configuration. Rollback, fallback
  models, alternate backends, and cross-node failover remain future milestones.
- Operational metrics currently cover liveness and HTTP health; request-level
  latency, queue depth, rate limits, and token accounting belong to the gateway.

### Next Milestone

Milestone 5 is the RIFT Gateway and Limits layer: a stable OpenAI-compatible
front door with request IDs, backend routing, concurrency control, rate limits,
token budgets, timeout policy, and gateway metrics.

## RIFT Milestone 5: Gateway And Limits - 2026-07-12

### Status

Complete and verified at the local data-plane level.

### Capabilities Added

- `rift gateway --config <path> --service <name>` exposes a stable
  OpenAI-compatible endpoint in front of a RIFT-managed backend.
- Supported proxy surfaces include chat completions, text completions,
  embeddings, and model listing.
- JSON responses and OpenAI-compatible SSE streams are passed through without
  converting streaming requests into buffered responses.
- Every request receives an `X-Request-ID`; valid client-provided IDs are
  preserved end to end.
- The gateway routes from `.rift/state.json`, so backend-specific ports and
  commands remain hidden from clients.
- Ordered fallback services can be configured. RIFT retries connection failures,
  timeouts, and upstream `502`, `503`, or `504` responses on the next route.
- Per-identity sliding-window limits support requests per minute and burst
  requests per second. Identity uses a one-way hash of the API key or client IP.
- A bounded semaphore enforces maximum concurrent requests and returns `429`
  rather than allowing an unbounded backend queue.
- Prompt, completion, and combined token budgets are enforced before forwarding.
  Prompt size uses an explicitly labelled conservative estimate; the backend
  tokenizer remains authoritative.
- Request body and upstream response limits protect the gateway process from
  oversized payloads.
- Upstream timeout policy produces a gateway timeout and can activate fallback.
- Optional Bearer authentication reads comma-separated keys from
  `RIFT_GATEWAY_API_KEYS` or another configured environment variable. Secrets
  are not persisted in `rift.yaml` or request logs.
- Gateway metrics include total/active/successful/failed requests, rejection
  reasons, status codes, backend counts, fallback usage, bytes, and average
  latency.
- Structured JSONL request logs record request ID, hashed identity, route,
  status, latency, byte count, token estimates, and error without recording raw
  authorization credentials.
- Metrics and logs persist under:
  - `.rift/gateway/metrics.json`
  - `.rift/logs/gateway.jsonl`
- `rift status` now includes persisted gateway process and metrics state.
- The RIFT control API exposes `GET /api/rift/gateway`.

### Real Workstation Verification

An ephemeral gateway was started against the existing healthy llama.cpp service
and shut down immediately after the request. The prompt requested an exact
response through the gateway.

Observed result:

```text
gateway status:       200
request ID:           real-gateway-smoke
backend service:      chat
response:             RIFT_GATEWAY_OK
prompt token estimate: 12
completion budget:    16
total token estimate: 28
gateway latency:      2.848 seconds
fallbacks:            0
```

The underlying llama.cpp process remained running and healthy.

### Integration Verification

The gateway tests cover:

- normal OpenAI chat proxying
- caller request-ID preservation
- backend route headers
- real SSE passthrough
- token-budget rejection
- per-key authentication
- rate-limit rejection with `Retry-After`
- concurrency saturation while another request is active
- primary `503` failure and successful fallback routing
- request-log redaction
- persistent metrics
- policy loading from `rift.yaml`
- control API gateway status

### Test Result

```text
full native/Python CTest suite: 18/18 passed
```

### Known Limits

- Rate-limit counters are local to one gateway process; distributed counters
  require a shared state provider in the cluster milestone.
- Token accounting before forwarding is an estimate because RIFT does not yet
  invoke each backend's exact tokenizer at the gateway boundary.
- TLS termination, certificate rotation, and public-network hardening are not
  included. The safe default remains `127.0.0.1`.
- The gateway currently runs as a foreground RIFT process. Windows Service,
  systemd, and node-agent lifecycle integration remain production work.
- Fallback is transport/status based. Semantic quality fallback and model-aware
  retry policies remain future work.

### Next Milestone

Milestone 6 is the Benchmark-Driven Optimizer: launch real candidate
configurations, measure each one, reject regressions and failures, select the
measured winner, and preserve rollback evidence instead of choosing the first
heuristic candidate.

## RIFT Milestone 6: Benchmark-Driven Optimizer - 2026-07-12

### Status

Complete and verified for the local llama.cpp provider.

### Capabilities Added

- `rift tune --live --allow-restart` now performs real warmup and repeated
  generation measurements rather than selecting the first heuristic candidate.
- Only candidates that launch, become HTTP Ready, and return non-empty valid
  generations are eligible to win.
- Median backend-native decode throughput is the selection metric; the report
  also preserves raw samples, wall latency, prompt speed, and backend timings.
- Candidate replacement is transactional. A failed candidate is terminated and
  the baseline is restored; an applied winner becomes the last-known-good plan.
- Windows process replacement now uses `TerminateProcess` with a bounded wait
  and a `taskkill` fallback, fixing detached `llama-server` lifecycle handling.
- llama.cpp benchmark parsing now uses its native `timings` object for decode
  throughput instead of conflating model decode with HTTP wall time.
- Optimized settings and complete comparison evidence are persisted under
  `.rift/reports/` and `.rift/generated/rift.optimized.yaml`.

### Real Workstation Verification

The deployed Llama 3.2 1B Instruct Q8_0 service was measured with three batch
configurations, one warmup, and two scored 64-token runs per configuration:

```text
batch 256 baseline: 154.020 tok/s median
batch 512:          154.385 tok/s median
batch 768 winner:   155.992 tok/s median
measured gain:        1.280%
```

### Known Limits

- Tuning currently optimizes one service at a time and uses decode throughput as
  the primary objective. Multi-objective SLO tuning is still future work.
- Restart-based tuning briefly interrupts a single-replica service. Canary
  tuning requires the production-operations milestone.

## RIFT Milestone 7: Cluster Scheduler And Reconciler - 2026-07-12

### Status

Complete and verified in deterministic multi-node emulation. Real remote-node
transport is not yet implemented.

### Capabilities Added

- New cluster lifecycle commands cover `init`, `discover`, `check`, `plan`,
  `deploy`, `status`, `monitor`, `benchmark`, `tune`, `fault`, `recover`,
  `restore-node`, and `destroy`.
- Placement uses Kubernetes-style filter-then-score behavior: readiness,
  labels, backend compatibility, unreserved VRAM, and host RAM are hard filters;
  headroom, accelerator class, cache locality, reliability, and replica spread
  are scored preferences.
- Every placement records positive reasons, alternatives, and rejected-node
  reasons.
- Deployments persist desired state, generation, tuning, reservations, health,
  and recovery history under `.rift/cluster/state.json`.
- Emulated benchmarks and tuning are explicitly labelled simulated.
- Process failure triggers a bounded restart; node loss triggers capacity-checked
  rescheduling and moves resource reservations to the replacement node.
- Cluster control API routes expose discover, check, plan, apply, monitor,
  benchmark, tune, fault injection, recover, status, and destroy operations.

### Emulated Cluster Verification

The acceptance topology contained an 8 GB laptop GPU node, a 24 GB workstation
GPU node, and a 32 GB CPU-only edge node. RIFT scheduled all three requested
instances:

```text
chat-0  -> laptop-4060       llama.cpp / 7B GGUF
chat-1  -> workstation-4090  llama.cpp / 7B GGUF
coder-0 -> workstation-4090  vLLM / 14B AWQ
```

Baseline emulated aggregate throughput was `39.190 tok/s`. Tuning preserved the
optimal laptop configuration and estimated gains of `9.890%` for the 24 GB
llama.cpp instance and `9.896%` for the vLLM instance.

Failure tests then:

- crashed `coder-0` and verified an authorized same-node restart;
- marked `laptop-4060` NotReady and verified `chat-0` rescheduling to the
  capacity-compatible workstation node;
- finished with all three desired instances Running and two persisted incidents.

### Known Limits

- These cluster performance values are deterministic estimates, not physical
  measurements.
- SSH/PowerShell transport, a node agent, artifact distribution, and real remote
  process launch remain to be built.
- The control-plane state file is single-controller and not yet HA replicated.

## RIFT Milestone 8A: Recovery And Recommendation Hardening - 2026-07-12

### Status

Operational foundation complete; full production operations remain in progress.

### Capabilities Added

- Monitoring now distinguishes process liveness, HTTP readiness, and startup
  grace instead of treating every failed probe as an immediate restart signal.
- Readiness failures use a configurable threshold; process crashes can recover
  immediately within restart policy.
- Recovery supports last-known-good rollback when the active launch plan differs
  from the last healthy plan.
- Hub query arms are interleaved, preventing one popularity sort from exhausting
  the entire candidate budget.
- Finalist enrichment now requests structured evaluation evidence, model
  lineage, inference-provider mapping, library metadata, storage, and disabled
  status when available.
- Disabled repositories are rejected. Structured evaluation evidence raises
  confidence without comparing heterogeneous benchmark values as one score.
- Backend recommendation now evaluates every registered provider using format,
  hardware fit, operating-system support, workload fit, and installed state.
- Deployment planning repeats provider fit checks before producing a launch
  action.
- Benchmark connection failures now return structured reports instead of raw
  CLI tracebacks.

### Real Disaster-Recovery Verification

The local tuned backend was deliberately observed in a crashed state. RIFT
refused recovery without permission, then `rift recover --allow-launch`
restarted the persisted batch-768 plan as PID `5164`. Two readiness checks
reported process alive and HTTP `200 /health`. A post-recovery prompt returned
exactly `RIFT_RECOVERY_OK`:

```text
decode throughput: 142.019 tok/s
estimated TTFT:       48.789 ms
restart count:         1
final phase:            healthy
```

### Test Result

```text
full native/Python CTest suite: 19/19 passed
```

### Remaining Production Work

- persistent OS service/node-agent installation for the reconcile loop;
- real multi-node transport and secure enrollment;
- replicated controller state and leader election;
- disruption budgets, rolling/canary deployment, and graceful request drain;
- Prometheus/OpenTelemetry export and distributed gateway limits;
- standardized task evaluation to supplement Hub-provided quality evidence.

## RIFT Milestone 8B: Trustworthy Control Plane And Live Operator Console - 2026-07-12

### Status

Implemented and verified as a local-workstation/community-preview foundation.
Remote and alternate-provider production gates remain explicitly unverified.

### Control-Plane Capabilities Added

- Measurement-aware hardware profiles now separate stable capacity, current
  pressure, and RIFT-managed service occupancy. CPU identity, disk reserve,
  GPU thermal/power telemetry, profile fingerprints, and freshness-labelled
  bounded disk calibration are available through CLI/API/UI.
- Recommendation evidence has an explicit provenance ladder: estimates, Hub
  metadata, publisher claims, curated evaluation records, reproducible
  benchmarks, and locally verified results are no longer flattened into one
  implied accuracy claim.
- Exact artifact manifests classify GGUF/GPTQ/AWQ/SafeTensors layouts, preserve
  revisions/dependencies/bytes, compute SHA-256 hashes, detect corruption, and
  support resumable Hub downloads with final byte-count validation.
- Provider adapters now share a complete lifecycle contract covering detection,
  install planning, installation, fit, launch planning, launch, readiness,
  health, benchmarking, tuning, stop, recovery, and capabilities.
- llama.cpp remains `verified_local`. vLLM and SGLang are marked
  `implemented_platform_gate_pending`; LMCache-aware serving is an experimental
  overlay. Contract completeness is never reported as real-platform readiness.
- Fixed benchmark suites add warmups, repetitions, median/p95 summaries,
  cold/warm cache labels, exact launch/artifact evidence, regression decisions,
  and local evidence recording.
- Gateway security now includes hash-only API-key persistence, one-time secret
  creation, revoke/rotate operations, CORS policy, request IDs, redacted audit
  logs, and bounded request/token/concurrency/rate controls.
- Observability adds a structured operation timeline, redaction, retention
  pruning, report snapshots, log access, and Prometheus text export.
- Governance policies can allow/deny sources, licenses, providers, gated access,
  and missing hashes; deployment manifests and audit exports preserve the final
  decision trail.
- State/config migration previews, versioned writes, and redacted diagnostic ZIP
  bundles support upgrades and troubleshooting.

### Cluster And Recovery Foundations

- SSH and PowerShell remoting transports are implemented with strict host
  validation and explicit `allow_remote` permission, but are labelled
  unverified until physical nodes pass acceptance.
- The scheduler accounts for VRAM, RAM, disk, network reachability, backend fit,
  cache locality, reservations, and replica spreading with deterministic
  rejected-node explanations.
- Emulated process/node failure moves and releases reservations correctly.
  Recreate, canary, and blue/green rollout plans include readiness and
  performance promotion gates.

### Operator Dashboard

- The supplied TanStack frontend no longer uses dummy arrays. Overview,
  Hardware, Models, Plan, Apply, Services, Benchmarks, Monitoring/Security, and
  Cluster views consume the live RIFT control API.
- Apply, stop, recovery, pruning, and credential operations expose explicit
  confirmation/permission states rather than silently changing the machine.
- A compact mobile navigation sheet preserves all views below the desktop
  sidebar breakpoint. Data tables remain bounded horizontal work surfaces.
- `rift ui --port 8765 --control-port 8777` launches the frontend and local
  control API together from this source checkout.

### Verification

```text
native CUDA and Python CTest suite: 20/20 passed
frontend TypeScript check:          passed
frontend ESLint:                    0 errors, 6 component-export warnings
frontend production build:         passed
desktop browser check:              1440x900, live API data, no page overflow
mobile browser check:               390x844, navigation and route transition passed
installed CLI smoke:                help, backend detection, calibration passed
PEP 517 native wheel:               built and installed in an isolated venv
wheel module smoke:                 cluster, gateway, orchestrator imports passed
live service observed:              llama.cpp / chat / healthy
```

### Remaining Release Gates

- Measure practical pinned-memory CUDA H2D bandwidth instead of retaining the
  native estimate label.
- Package compiled dashboard assets into the wheel/installers and add browser
  E2E CI; the current dashboard is source-checkout operational.
- Complete real two-node SSH/PowerShell discovery, deploy, benchmark, failure,
  failover, and destroy acceptance with secure credentials and host keys.
- Run vLLM and SGLang end to end on supported Linux/WSL CUDA systems before
  advertising them as verified providers; then validate LMCache benefit.
- Add replicated controller state, distributed gateway limits, TLS automation,
  OpenTelemetry aggregation, real canary traffic/drain, signed release assets,
  and cross-platform installer/upgrade tests.

The exact roadmap status and evidence boundary are recorded in
[`docs/roadmap/status.md`](../roadmap/status.md).

## RIFT Repository And CLI Consolidation - 2026-07-12

### Product Surface

- The repository is organized by ownership: `dashboard`, `docs`, `models`,
  `native`, `python`, and language-specific tests.
- Local checkpoints, runtime state, environments, dashboard dependencies, and
  build artifacts are excluded from source control.
- `rift` is the sole installed console entry point. Native survival experiments
  remain internal and no longer appear as product commands.
- The CLI follows the public workflow directly: discover, recommend, generate,
  plan, apply, operate, and inspect. Advanced provider, service, cluster, and
  support commands live in named groups.
- Human-readable summaries and tables are the default. `rift --json COMMAND`
  preserves complete machine-readable output for automation.
- Windows terminals receive an electric-blue/cyan ANSI palette, command-context
  banners, state/action colors, and worked examples in grouped help pages.

### Dashboard And Build

- The operator console moved to `dashboard/` and uses the standard TanStack
  Start, Vite, Tailwind, and Nitro stack without the previous generator wrapper.
- Unreachable component templates and 110 unused frontend packages were
  removed. The live pages, control API integration, responsive navigation, and
  confirmation gates remain intact.
- Nitro now owns `/api/rift/*` forwarding for development and production.
  Dashboard discovery walks checkout parents, supports `--root`, and waits for
  HTTP readiness instead of reporting success after a fixed delay.
- `rift dashboard --detach` provides a persistent background launch with
  normalized environment handling, PID/URL output, and `.rift/logs` streams.
- CMake paths now follow the reorganized native and test trees. Native wheel
  builds target the local CUDA GPU by default and permit an explicit
  `CMAKE_CUDA_ARCHITECTURES` override.

### Verification

The consolidation is accepted only after the Python/CUDA CTest suite, wheel
build and install smoke, CLI help and command smoke, dashboard TypeScript/lint,
production build, and live desktop/mobile browser checks complete. Current
results are maintained in [`docs/roadmap/status.md`](../roadmap/status.md).

## RIFT Seismic Operator Console Integration - 2026-07-17

### Current Capability

- The Seismic TanStack frontend is now the preferred source-checkout dashboard.
- A typed compatibility adapter maps the shipped `/api/rift` controller into
  nodes, services, incidents, benchmarks, revisions, plans, models, and fleet
  health without fabricating successful mutations.
- Home, deployments, nodes, models, operations, and backend settings consume
  real controller resources. Hardware-aware Hub search runs only after an
  explicit user action.
- Live, derived-live, preview, and unavailable data are visibly distinguished.
- The dashboard launcher supplies a same-origin API proxy and retains the older
  dashboard only as a fallback.

### Verified On This Workstation

```text
TypeScript check:                     passed
ESLint:                               0 errors, 6 inherited warnings
TanStack/Vite production build:       passed
Python dashboard launcher tests:      passed
Python controller server tests:       passed
Live typed adapter verification:      passed
Observed GPU:                         NVIDIA GeForce RTX 4060 Laptop GPU
Observed managed service:             chat / llama.cpp / failed
Retained incident history:            available
Retained benchmark history:           available
Controller timeline and logs:         available
```

The managed service is reported as failed because its historical process is no
longer alive. The UI preserves that controller truth instead of showing a
healthy demo state.

### Remaining UI Work

- Implement immutable plan/apply/rollback and enrollment resources in the v1
  controller before enabling those mutations in the new console.
- Replace preview source/security/policy administration with real controller
  resources.
- Package production frontend assets in releases and add automated browser E2E
  coverage for desktop and mobile layouts.

## RIFT Automatic Hub Discovery And Pull - 2026-07-17

### Corrected User Flow

- Guided setup no longer asks ordinary users for a Hugging Face `org/repo` ID.
- `rift pull` now measures hardware and disk, searches the Hub index, ranks
  candidates, selects the exact artifact, and downloads the winner.
- `rift pull --dry-run` performs the complete selection and disk preflight
  without downloading files.
- `rift model pull org/repository` remains the deterministic expert override.
- Recommendation reports state that repository input was not required and
  identify the bounded multi-arm search strategy explicitly.

### Verification

```text
Frontend TypeScript check:            passed
Fake-Hub recommendation suite:        passed
Top-level pull without repo argument: passed
Real Hugging Face dry run:            passed, no files downloaded
Indexed query arms exercised:         9
Dashboard recommendation API:         10 real candidates returned
Smoke-test winner:                     bartowski/Meta-Llama-3.1-8B-Instruct-GGUF
Exact selected artifact:               Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf
```

RIFT searches the global Hugging Face model index through bounded task, format,
popularity, recency, and parameter query arms. It does not claim to crawl every
repository page during each run; finalists receive the more expensive metadata
and artifact enrichment.

## RIFT 1.1 - Modular Adapter And Universal Control Foundation - 2026-07-18

### Adapter Host

- Recommendation Contract V2 represents model identity, revision, exact
  artifact, backend plan, and deployment candidate separately while retaining
  legacy recommendation fields for one compatibility release.
- Backend, artifact, and converter adapters load from versioned Python entry
  points. API negotiation, conflicts, disable policy, malformed manifests, and
  diagnostics fail closed.
- llama.cpp remains the verified reference. vLLM, SGLang, and MLX-LM implement
  complete external-process lifecycles without modifying upstream projects.
- LMCache is an optimization overlay. Conversion is a separate, explicitly
  permissioned plan and never an implicit recommendation side effect.

### Exact Artifacts And Recommendations

- GGUF, SafeTensors, AWQ, GPTQ, FP8, EXL2, and MLX variants resolve tokenizer,
  config, processor, chat-template, multimodal projection, shard, revision,
  byte-count, and hash dependencies.
- Missing shards or serving dependencies cannot win backend compatibility.
- Discovery starts from task/model identity and enriches exact artifacts only
  for finalists. Encountered Hub metadata remains bounded by TTL/LRU cache.
- Behavioral safety, license trust, artifact integrity, deployment feasibility,
  quality proxy, performance, and popularity remain separate dimensions.
- `rift recommend --verify` performs an explicitly permissioned finalist
  install/pull/launch/health/benchmark/stop tournament and records matching
  artifact/backend evidence for future `best_verified` decisions.

### Controller And Cluster

- API V2 exposes adapters, capabilities, artifacts, compatibility,
  recommendation runs, deployment plans, and verification runs.
- The optional node agent uses TLS 1.2+ mutual authentication, monotonically
  increasing desired state, idempotent reconcile, and independent node-side
  install/download/launch policy gates.
- Deterministic 50-node emulation verifies heterogeneous placement, capacity
  reservation, replica spreading, network partition recovery, canary promotion,
  and benchmark accounting. It remains labelled emulation.

### Verification Boundary

- Shared conformance passes for all four built-in serving adapters and all seven
  built-in artifact adapters.
- Test entry-point packages prove new backend and artifact formats require no
  registry, planner, or recommender edits.
- The release build completed all 39 native C++/CUDA compile and link steps,
  then passed all 24 native and Python CTest targets on the RTX 4060 Laptop GPU.
- A PEP 517 `rift-llm 1.1.0` wheel was built, installed in the isolated `rift`
  environment, and exercised through `rift --version`, adapter listing,
  inspection, and install-plan commands.
- Timed pinned-memory CUDA events measured 11.43 GB/s H2D on this workstation
  using an 8 MiB sample over four measured iterations.
- Real Linux CUDA acceptance for vLLM/SGLang, Apple Silicon acceptance for
  MLX-LM, and three heterogeneous physical-node acceptance remain mandatory
  before those paths are advertised as production verified.

## RIFT 1.2 - Elastic Intelligence Mesh Foundation - 2026-08-14

### Current Capability

- The controller exposes API V2 resources for untrusted node sightings,
  explicit enrollment, pairing approval, CSR certificate issuance, trusted-node
  inventory, capability publication, directional link evidence, topology, and
  inference route resolution.
- Discovery is transport neutral. Passive mDNS and ADB are registered by
  default; consent-gated private-subnet, USB-network, and mass-storage bootstrap
  providers are implemented for configured deployments.
- Enrollment uses expiring six-digit challenges with scrypt verifiers. Pairing
  creates a non-routable enrolled node; CSR issuance or explicit certificate
  activation is required before the node becomes active.
- Active nodes publish monotonically sequenced hardware, pressure, health, and
  runtime-offer snapshots. Link reports retain latency, jitter, loss,
  throughput, timestamp, and evidence class.
- The policy-balanced route planner enforces trust, health, reachability,
  privacy, task, context, quality, and offer constraints. It returns explained
  primary/fallback choices and persists short-lived policy-bound route leases.
- Manual recovery-key promotion and optional odd-quorum controller election
  primitives exist. The default operating direction remains a centralized
  control plane with direct node-to-node inference traffic outside the
  controller hot path.
- The dashboard setup flow is UI first: it scans, labels sightings untrusted,
  requires explicit selection, exposes the bootstrap fingerprint, verifies the
  pairing code, and reloads the trusted-node inventory after approval.
- Android now has a secure node/client scaffold with controller discovery,
  explicit enrollment, telemetry, Keystore-protected leases, local-first
  routing, and an honest llama.cpp JNI availability boundary.
- Controller, node, gateway, and emulator have separate hardened OCI/Compose
  definitions with runtime-mounted secrets and an optional NVIDIA override.

### Verification Evidence

- Mesh contracts, discovery TTL/deduplication, consent gates, pairing,
  activation, CSR identity, capability sequencing, link validation, topology,
  route selection, lease expiry, recovery voting, and the deterministic fleet
  laboratory are covered by Python tests.
- Controller route persistence and all mesh API dispatch paths are covered by
  server tests.
- Dashboard lint and production compilation cover the typed mesh onboarding
  client and setup flow.
- Android and container delivery are statically checked for required manifests,
  security settings, role separation, health checks, volumes, and secret
  handling.
- OpenAPI contracts and the architecture boundary are maintained in
  `docs/reference` and `docs/architecture/elastic-intelligence-mesh.md`.

### Physical Acceptance Pending

- Real LAN, private-subnet, USB-network, mass-storage, and ADB discovery across
  heterogeneous devices.
- A physical pairing and mTLS certificate lifecycle through the controller,
  including authenticated controller ingress for capability/link publication.
- Direct node-to-node inference under route leases and failover during
  controller loss or node saturation.
- Android APK compilation/device execution and a real llama.cpp JNI runtime.
- OCI image builds, Compose startup, GPU passthrough, and container mTLS.
- State/PKI-safe manual controller promotion and three-voter election under real
  network partitions.

## RIFT 1.3.0 RC Addendum - Hypothetical Hardware Recommendation - 2026-08-18

### Current Capability

- `rift recommend --simulate-hardware` evaluates Hub candidates against a
  user-supplied workstation profile instead of the local machine profile.
- Compact `key=value` input and JSON profile files are supported. GPU, VRAM,
  host RAM, and free disk are required; free-memory and platform details are
  optional refinements.
- The simulated profile flows through the normal artifact resolver, exact file
  sizing, adapter compatibility, backend ranking, hardware fit, and disk
  feasibility calculations.
- Reports explicitly mark simulated capacity, assumptions, and read-only
  provenance. Simulated recommendations cannot pull, install, launch, or run
  local verification.

### Verification Evidence

- Recommendation tests cover compact profile parsing, RTX 5090-style capacity,
  simulated disk feasibility, parser exposure, and result provenance.
- Existing recommendation, evidence, orchestrator, and adapter suites remain
  the regression gate.

## RIFT 1.3.0 RC Addendum - External Evidence Calibrated Recommendation Funnel - 2026-08-18

### Current Capability

- `rift recommend` now uses a diversified, format-neutral Hub funnel. It
  searches task, format, model-family, and small/medium/large parameter arms
  before enriching only finalists. The default format arms cover GGUF, GPTQ,
  AWQ, and SafeTensors; `--formats` remains an explicit hard constraint.
- The ranking separates disk capacity, host-RAM headroom, and practical VRAM
  residency. A model can fit on disk while still receiving an offload and
  throughput penalty when its estimated weights exceed the reserved VRAM
  window.
- RIFT publishes benchmark provenance for Chatbot Arena, EvalPlus, LiveBench,
  and BigCodeBench. These are evidence references, not one universal accuracy
  score. Signed operator snapshots can be supplied with repeated
  `--benchmark-snapshot` options and are merged only when their trust policy
  validates them.
- Backend probing is cached for the duration of a recommendation run, which
  avoids repeatedly probing Docker, Python environments, and platform tools
  for every Hub candidate.
- A reproducible calibration harness evaluates the real workstation plus 50
  simulated profiles (weaker GPUs, stronger GPUs, and a mobile profile). It
  performs live bounded Hub searches with no download, install, launch, or
  local verification side effects.

### Verification Evidence

- Focused recommendation, evidence, and adapter-host tests pass after the
  funnel and VRAM scoring changes.
- Live measured-profile search on the RTX 4060 Laptop GPU selected
  `bartowski/Qwen2.5-7B-Instruct-GGUF`, exact `Qwen2.5-7B-Instruct-Q4_K_M.gguf`,
  with llama.cpp as the installable backend candidate.
- The live 51-profile matrix completed 46 feasible searches, 5 honest
  no-feasible mobile profiles, and 0 errors. A GTX 1650 profile preferred a
  3B quantized candidate over a 7B candidate whose estimated VRAM residency
  would require expensive offload.
- With a larger 40 GB artifact budget, live high-memory simulations surfaced
  14B-30B AWQ/GPTQ candidates on RTX 4090/5090-class profiles. No models were
  downloaded or launched during calibration.
- The full Python suite passed except the existing dashboard launcher test,
  which reports `dependencies_ready=False` because the checkout does not have
  the dashboard's installed Vite dependencies. This is an environment
  dependency gap, not a recommender failure.

### Known Boundary

- Hub metadata and external leaderboards remain evidence, not a guaranteed
  local quality measurement. `rift recommend --verify` is still the path for a
  permissioned local finalist test.
- High-memory recommendations depend on exact artifact enrichment and the
  operator's disk/download budget. RIFT must not infer that a model is
  runnable merely because its parameter count is popular.
