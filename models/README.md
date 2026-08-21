# Local Models

Place private or downloaded checkpoints under `models/local/`. RIFT runtime
pulls normally use `.rift/models/`; both locations are excluded from source
control so multi-gigabyte weights, access-controlled artifacts, and model
licenses are not accidentally published.

Examples:

```text
models/local/my-gguf/model-Q4_K_M.gguf
models/local/my-gptq/config.json
models/local/my-gptq/model-00001-of-00002.safetensors
```

Inspect a local artifact with:

```powershell
rift model inspect models/local/my-gptq
rift model verify models/local/my-gptq --hash-mode all
```
