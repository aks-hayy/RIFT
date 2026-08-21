# RIFT Quickstart

This guide deploys one local LLM service through RIFT's declarative workflow.
No download, installation, launch, remote action, or stop occurs without an
explicit permission flag.

## 1. Check The Machine

```powershell
rift discover
rift system hardware
rift backend list
```

Run a bounded disk calibration when the profile reports missing or stale
evidence:

```powershell
rift system calibrate --sample-mib 32
```

## 2. Choose A Model

Search Hugging Face with hardware, artifact, disk, backend, and evidence
constraints:

```powershell
rift recommend --task chat --top 5
```

For machine-readable output:

```powershell
rift --json recommend --task coding --formats gguf,gptq > recommendations.json
```

RIFT labels recommendation quality as metadata, publisher evidence, curated
evaluation, reproducible benchmark, or locally verified evidence. Popularity is
not presented as measured accuracy.

## 3. Generate Intent

```powershell
rift generate --task chat --output rift.yaml
```

For a private Hub-compatible endpoint:

```powershell
rift generate --task chat --source private --endpoint https://models.example.com
```

For checkpoints already on disk:

```powershell
rift generate --source local --models models/local --output rift.yaml
```

## 4. Review The Plan

```powershell
rift plan --config rift.yaml
```

Planning is read-only. It reports the exact model files, backend, launch
settings, ports, required permissions, governance findings, and rejected
alternatives.

## 5. Apply Explicitly

Preview blocked actions without allowing side effects:

```powershell
rift apply --config rift.yaml
```

Authorize only the actions you reviewed:

```powershell
rift apply --config rift.yaml `
  --allow-download `
  --allow-install `
  --allow-launch

# Equivalent concise deployment command:
rift up --config rift.yaml --allow-download --allow-install --allow-launch
```

Remote execution additionally requires `--allow-remote`.

## 6. Operate The Service

```powershell
rift status
rift service logs --service chat --tail 100
rift service monitor --service chat --iterations 1
```

Run a repeatable suite:

```powershell
rift benchmark --service chat --suite --warmups 1 --repeats 3
```

Preview safe tuning candidates, then optionally measure them with controlled
restarts:

```powershell
rift tune --service chat
rift tune --service chat --live --allow-restart
```

Recovery remains permission-gated:

```powershell
rift service restart --service chat --allow-launch
rift service incidents --limit 20

# Back up controller state before maintenance or migration.
rift system backup --output .rift/backups/state-before-maintenance.db
```

Stop a service without deleting model files:

```powershell
rift destroy --service chat --yes

# Equivalent concise stop command:
rift down --service chat --yes

# Restore only after reviewing the validated backup; RIFT makes a pre-restore backup.
rift system restore --input .rift/backups/state-before-maintenance.db --yes
```

## 7. Dashboard

Install dashboard dependencies once from a source checkout:

```powershell
cd seismic-deploy-main
npm install
npm run verify:controller
cd ..
```

Launch the operator interface and local control API:

```powershell
rift dashboard --host 127.0.0.1 --port 8765 --control-port 8777
rift dashboard --detach
```

RIFT searches the current checkout and parent directories for
`seismic-deploy-main/`, then falls back to `dashboard/`. If the command is
launched elsewhere, point it at the source explicitly:

```powershell
rift dashboard --root C:\path\to\RIFT\seismic-deploy-main
```

The UI is available at `http://127.0.0.1:8765`. Prometheus-format metrics are
available at `http://127.0.0.1:8777/api/rift/metrics/prometheus`.

The console labels live controller values, values derived from live state, and
preview-only surfaces separately. See [Operator Console Data](operator-console.md).

## 8. Model Artifacts

Let RIFT discover the repository and exact artifact automatically:

```powershell
rift pull --task chat --dry-run
rift pull --task chat --output models/best
```

The default flow does not ask for a Hugging Face repository ID. RIFT queries
multiple task, format, popularity, recency, and parameter-size arms in the Hub
index, filters them against live hardware and disk capacity, and enriches only
the finalists. This is intentionally broader and faster than searching one
known repo, but it is not a literal page-by-page crawl of every Hub repository.

Dry-run an exact-repository pull only when you deliberately need an override:

```powershell
rift model pull org/model --dry-run --max-bytes 12000000000
```

Inspect and verify local files:

```powershell
rift model inspect models/local/my-model
rift model verify models/local/my-model --hash-mode all
```

## 9. Backend Installation

```powershell
rift backend detect
rift backend install-plan llama.cpp
rift backend install llama.cpp --allow-install
```

RIFT does not silently install unsupported native-Windows CUDA packages. vLLM,
SGLang, and LMCache plans explain when WSL2, Linux, or containers are required.

## 10. Support Bundle

```powershell
rift system doctor
rift system export --output .rift/exports/deployment.json
rift system diagnostics --output .rift/diagnostics/rift-diagnostics.zip
```

Review diagnostic bundles before sharing them, even though RIFT applies its
redaction policy.
