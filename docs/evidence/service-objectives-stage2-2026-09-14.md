# Stage 2 service-objective verification

## Backend and CLI

- Planned and applied the existing local Qwen2.5 1.5B GGUF service through llama.cpp with a policy containing adjustable GPU-temperature and request-error-ratio objectives.
- The applied service selected nine telemetry metrics, including `gpu_temperature_c` and the derived `request.error_ratio` metric.
- The live llama.cpp service reached `healthy`; `rift service objectives --service chat --events --json` reported `gpu-temperature: pass` at 49–51°C and `request-error-ratio: unknown` because no RIFT gateway traffic was observed.
- A direct OpenAI-compatible chat request completed successfully.
- After stopping from a fresh CLI process, the persisted resource report contained the final objective snapshot and transition event. GPU model process termination was confirmed; `nvidia-smi` showed 1186 MiB residual device usage from other host processes.

## UI and API

- Rebuilt the UI (`npm run verify:live-actions`, `npx tsc --noEmit`, `npm run build`).
- Live dashboard monitoring view showed both objective cards, their thresholds, status, transition history, and the nine selected metrics.
- `GET /api/rift/telemetry/objectives?service=chat&events=true` returned two configured objectives, two evaluations, and persisted transition events.

## Automated tests

Focused Stage 2 backend suite: **37 passed**. The full Python suite reports **371 passed, 2 unrelated Windows environment failures** (temporary SQLite database permissions and the global RIFT report directory permission). UI action-contract verification, TypeScript checking, and production build all pass.
