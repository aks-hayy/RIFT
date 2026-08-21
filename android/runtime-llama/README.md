# RIFT llama.cpp runtime boundary

This module owns the stable Kotlin runtime contract and JNI boundary. The current
native library is deliberately a non-generating stub: it reports unavailable until
the reviewed upstream llama.cpp source is pinned under `src/main/cpp/llama.cpp`.

The production integration must:

1. Pin an immutable llama.cpp commit and record it in the release SBOM.
2. Replace the stub CMake target with upstream Android builds for `arm64-v8a` and
   debug `x86_64`.
3. Keep `NativeRuntimeBridge` method signatures stable.
4. Validate CPU execution repeatedly before adding any Vulkan backend.
