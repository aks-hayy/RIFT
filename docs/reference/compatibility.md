# RIFT Compatibility Matrix

Updated: 2026-07-18

RIFT is an orchestrator. Model compatibility is the intersection of an exact
artifact, an installed provider, its supported platform, and measured hardware
capacity. A complete adapter contract does not imply that a provider has passed
real-platform acceptance.

## Provider Status

| Provider | Formats | Platforms declared | Current status |
| --- | --- | --- | --- |
| llama.cpp | GGUF | Windows, Linux, macOS; CPU/CUDA/Metal/Vulkan as supported upstream | `VERIFIED_LOCAL` on this Windows RTX 4060 workstation |
| vLLM | SafeTensors, AWQ, GPTQ, FP8, FP16, BF16 | Linux and WSL2; CUDA/ROCm where supported upstream | `IMPLEMENTED_PLATFORM_GATE_PENDING` |
| SGLang | SafeTensors, AWQ, GPTQ, FP8, FP16, BF16 | Linux and WSL2 CUDA | `IMPLEMENTED_PLATFORM_GATE_PENDING` |
| MLX-LM | MLX SafeTensors/conversions | Apple Silicon/macOS | `IMPLEMENTED_PLATFORM_GATE_PENDING`; raw server restricted to loopback |
| LMCache-aware vLLM | Same model formats as the base vLLM service | Linux and WSL2 CUDA | `EXPERIMENTAL_OVERLAY` |
| RIFT native survival runtime | Validated LLaMA GPTQ ExLlama-style SafeTensors subset | Windows/Linux CUDA build targets | Experimental; not the default production provider |

Native Windows installations do not silently install vLLM, SGLang, or
LMCache. RIFT presents WSL2/Docker/Linux guidance and requires explicit install
permission.

## Artifact Intelligence

| Artifact family | Discover/rank | Exact manifest/hash | Runnable provider path |
| --- | --- | --- | --- |
| GGUF, including quant files such as Q4_K_M/Q5_K_M/Q8_0 | Yes | Yes | llama.cpp |
| GPTQ SafeTensors | Yes | Yes | vLLM when accepted on a supported platform; experimental native LLaMA subset |
| AWQ SafeTensors | Yes | Yes | vLLM/SGLang when accepted on a supported platform |
| FP8 SafeTensors | Yes | Yes | vLLM/SGLang when hardware and detected backend version support it |
| EXL2 SafeTensors | Yes | Yes | No built-in serving adapter yet; third-party adapter may advertise support |
| MLX artifacts | Yes | Yes | MLX-LM on Apple Silicon |
| Dense FP16/BF16 SafeTensors | Yes | Yes | vLLM/SGLang when capacity and platform allow |
| Sharded SafeTensors | Yes | Yes, including dependency files | Provider/model-family dependent |
| Legacy `.bin`, `.pt`, `.pth` | Rejected by default | No production path | Unsupported unless a future provider explicitly accepts it |

## Model Families

RIFT Hub discovery is not restricted to one architecture. Execution depends on
the selected external provider:

- LLaMA, Qwen, Mistral, Gemma, Phi, and MoE families can be recommended when a
  compatible GGUF or supported SafeTensors artifact and provider exist.
- RIFT does not claim universal architecture support independently of those
  providers.
- The native experimental runtime remains limited to its validated LLaMA GPTQ
  path and should not influence general model ranking as if it were universal.

## Hardware Classes

| PC class | Typical RIFT decision |
| --- | --- |
| 8 GB VRAM / 16 GB RAM workstation | Prefer a practical GGUF quant through llama.cpp; constrain context/concurrency and preserve disk reserve. |
| 12-24 GB CUDA GPU / 32-64 GB RAM | Consider higher-quality GGUF or supported AWQ/GPTQ/SafeTensors through a verified Linux/WSL provider. |
| CPU-only PC | Prefer CPU-capable GGUF through llama.cpp with conservative context and explicit speed estimates. |
| Multi-GPU Linux server | Prefer a provider whose real lifecycle gate has passed for tensor/pipeline parallel execution. |
| Heterogeneous cluster | Place per node using provider capability, capacity, cache locality, disk, reachability, and policy constraints. |

Compatibility is resolved from adapter manifests and installed-version probes,
not this documentation table. New backend and artifact adapters are discovered
through Python entry points without editing the planner.

## Support Labels

- `VERIFIED_LOCAL`: a real backend/model workflow completed on the named host.
- `VERIFIED_TEST`: deterministic unit or fake-backend coverage.
- `EMULATED`: no remote backend process or network transfer occurred.
- `IMPLEMENTED_PLATFORM_GATE_PENDING`: adapter exists, but real target-platform
  acceptance is outstanding.
- `UNSUPPORTED`: RIFT will explain the blocker and will not present fake
  readiness.

See [Roadmap Verification Status](../roadmap/status.md) for acceptance evidence
and open gates.
