# RIFT Interactive Shell Design

## Purpose

Give RIFT operators a persistent, discoverable terminal workspace for deploying and operating services, while preserving the existing one-shot CLI and its safety behavior. The shell should feel like an operational console: compact live machine and RIFT state remains visible, while command output and interaction take priority.

## Agreed requirements

- On Windows, invoking bare `rift` from an interactive terminal opens the RIFT shell in a new terminal window. `rift shell` opens it in the current terminal.
- On Linux and macOS, bare `rift` opens the shell in the current terminal; RIFT does not guess which terminal application to launch.
- Existing one-shot commands remain valid and unchanged, for example `rift model recommend`.
- The shell uses `prompt_toolkit`, with the current `argparse` command definitions and command handlers as the source of truth. The shell does not duplicate command semantics.
- Inside the shell, command groups retain their existing hierarchy without the `rift` prefix: `model recommend`, `service list`, and similar.
- The status display stays visible and dynamic, but compact. Command output receives the main area.
- CPU and memory are sampled once per second; GPU metrics are shown when available. Service and node state refresh every five seconds. Unavailable sources display `unknown` and do not prevent command use.
- Help has three levels: `help`, `help <group>`, and `help <group> <command>`. It covers shell controls, command groups/subcommands, then options and usage examples.
- Existing download, install, launch, approval, and confirmation safeguards continue to be enforced by the current command handlers.

## Proposed architecture

The CLI entry point will route invocation modes before the existing one-shot parsing path:

1. Explicit command arguments continue through the current normalization, `build_parser()`, and `execute()` flow.
2. `rift shell` starts the interactive shell in the current terminal.
3. Bare `rift` starts the interactive shell according to the platform rules above, but only for an interactive terminal. Non-interactive/piped invocations retain a finite help response and must not launch a terminal or hang.

On Windows, the parent process will launch a child RIFT shell in a new console and exit. The child will be marked as already launched so the bare-command behavior cannot recursively open more windows. If opening a new console fails, report the error and provide `rift shell` as a way to run in the current terminal. Exact terminal selection should use the platform console mechanism and must not require Windows Terminal to be installed.

The shell is a small module under `rift.cli` with clear boundaries:

- **Launcher/dispatcher:** distinguishes bare launch, explicit shell, and existing one-shot commands. It shares parser construction and execution with the one-shot CLI.
- **Interactive command runner:** tokenizes one entered command, strips an optional `rift` prefix for convenience, parses it with the existing parser, and passes the resulting namespace to the existing `execute()` function. Each command returns to the prompt after success, parser help, or an error. An interrupted command returns to the prompt after the existing interruption behavior is rendered.
- **Help renderer:** walks existing parser/subparser definitions to provide group and command help. Detailed command help reuses argparse formatting and examples where available; help output must not execute the command.
- **Status collector and renderer:** refreshes local system readings and read-only RIFT service/node snapshots in the background, then renders compact sparklines/metrics in a persistent status area. Collection errors are isolated per source and represented as unavailable data rather than exceptions escaping into the prompt.

Use `prompt_toolkit`'s prompt/session, completion, history, layout, and terminal-safe command execution facilities. Keep rendering adaptive to terminal width. At narrow widths, abbreviate or omit graph labels before wrapping user command output or making the prompt unusable. Preserve `NO_COLOR`, `--no-color` for one-shot commands, and safe non-TTY output behavior.

## User experience

The shell opens with a small RIFT identity/header, a persistent status strip, and an editable `rift>` prompt. The strip includes host/platform, CPU and memory readings with short trend graphs, optional GPU usage/memory, and counts or states for locally managed services and enrolled nodes. It must avoid filling the screen with repeated status output.

Command output is rendered in the scrollable terminal history below the status display. A long-running command may display its ordinary progress output while background sampling continues; status updates must not corrupt progress bars, prompts, or command output. The current command owns keyboard input while it runs. Ctrl+C interrupts that command and returns control to the shell if the command's established behavior permits it. `exit`, `quit`, or Ctrl+D closes the shell cleanly.

Examples:

```text
rift> help
rift> help model
rift> help model recommend
rift> model recommend --task chat
rift> service list
rift> exit
```

History and completion should be available through prompt_toolkit. Completion suggestions are derived from the parser's current command tree and do not replace normal shell execution. Shell-specific controls should be listed by `help`.

## Status data and safety

- CPU/memory readings are local and read-only. Use the existing `psutil` dependency.
- GPU measurements are optional and shown only when an installed RIFT hardware/provider adapter can produce them. This feature must not install a driver, backend, package, or start a service to obtain telemetry.
- Service and node counts/state use existing local RIFT orchestrator/mesh read-only snapshot APIs. The shell must not start a controller or create a network enrollment as a side effect of opening.
- Sample CPU/memory at 1 Hz and RIFT service/node state at 0.2 Hz; coalesce or skip stale refreshes rather than queueing slow requests. Keep a small bounded history for sparklines.
- If a source cannot be queried, show `unknown` or `unavailable` with a concise status indicator and retry at the next interval. A failed service/node query must not be misrepresented as zero services/nodes.
- Opening the shell, collecting status, requesting help, and tab completion are read-only. All mutations continue to require the existing explicit CLI flags, approvals, and confirmations.

## Compatibility and error handling

- Preserve the current project script (`rift = rift.cli:main`), public command names, aliases, parser options, output modes, and handlers.
- Existing invocations with arguments must not enter the shell. JSON output and piped use remain finite and machine-readable.
- Parser errors in an interactive command are shown without terminating the session. The standard argparse one-shot `--help` behavior remains unchanged.
- A command's nonzero return code is reported and the prompt remains available. Unexpected command errors are isolated at the command boundary; `--debug` remains available through the existing CLI path.
- A failed or unavailable optional metrics source cannot block shell startup or command execution.
- The shell does not create new permissions or bypass existing approval hashes/flows.

## Dependencies and files

- Add `prompt_toolkit` as a runtime dependency in `pyproject.toml`.
- Extend `python/rift/cli/__init__.py` with invocation routing while keeping its current path intact for explicit one-shot commands.
- Add focused shell, status collector, and shell help/completion modules under `python/rift/cli/` only where separation keeps each module cohesive.
- Add tests under `tests/python/` for dispatch compatibility, parser-backed shell commands, help levels, prompt interruption/error recovery, sampling and unavailable-source handling, and no-side-effect startup.
- Update README/CLI documentation with launcher behavior, shell controls, and help examples.

## Verification and acceptance

Automated tests should establish that:

1. Existing explicit CLI invocations still call the same parser and executor and do not start an interactive session.
2. Interactive input dispatches to existing handlers with the same arguments; `help` commands never execute handlers.
3. Windows bare-launch and explicit-current-terminal modes are distinct, recursion is prevented, and non-TTY invocation stays finite. Platform-specific launch behavior should be unit-tested through mocked process APIs, with a Windows smoke test when available.
4. CPU/memory and RIFT snapshot sources refresh at their configured intervals, GPU/source failures remain isolated, and unavailable state is not rendered as zero.
5. Status repaint does not corrupt command output, completion, history, resize behavior, or terminal restoration after exit and Ctrl+C.
6. No shell startup path downloads or installs software, launches a model, starts the controller, or enrolls nodes.
7. The package builds and the CLI test suite passes with the new dependency declared.

## Out of scope

- Replacing the RIFT web dashboard or building a full-screen multi-pane TUI.
- Changing command names, deployment semantics, approval requirements, or API behavior.
- Implementing a general-purpose operating-system shell, arbitrary command execution, or scripting language inside RIFT.
- Installing GPU drivers/backends or managing deployments from the status renderer itself.
- Guaranteeing GPU telemetry on every platform or hardware vendor.
