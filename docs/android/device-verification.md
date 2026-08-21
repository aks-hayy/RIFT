# RIFT Android device verification

The catalog is evidence, not an installation allowlist. A record is keyed by:

- manufacturer/model and Android build;
- model SHA-256;
- llama.cpp commit, backend, and runtime settings;
- benchmark workload version and reviewed anonymized report.

The early-access release gate requires three physical ARM64 phones from two SoC/GPU
families spanning Android 9–16. Every phone must pass remote mode and a ten-turn
`VERIFIED_STABLE` soak; at least one must meet `VERIFIED_INTERACTIVE` (median TTFT
at most 5 seconds and median decode at least 10 tokens/second). Vulkan is optional.

Reports are shared only after explicit user review and export. They contain no
prompts, generated text, or controller credentials.
