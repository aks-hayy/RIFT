# Third-Party Notices

RIFT is Apache-2.0 software. This file records the direct dependencies and
external systems that a source checkout may use. It is an attribution index,
not a relicensing statement for those projects.

## Direct Python Dependencies

| Dependency | License | Upstream notice |
| --- | --- | --- |
| PyYAML | MIT | https://github.com/yaml/pyyaml/blob/main/LICENSE |
| zeroconf | LGPL-2.1-or-later | https://github.com/python-zeroconf/python-zeroconf/blob/master/LICENSE |
| cryptography | Apache-2.0 or BSD-3-Clause | https://github.com/pyca/cryptography/blob/main/LICENSE |
| scikit-build-core | BSD-3-Clause | https://github.com/scikit-build/scikit-build-core/blob/main/LICENSE.txt |

The exact versions used by a build are defined by the lockfiles or installer
environment. Run `python scripts/audit_release.py --json` before packaging.

## Operator Console Dependencies

The `seismic-deploy-main/` console is a separate npm application. Its direct
and development dependencies, resolved versions, and package-declared
licenses are recorded in `seismic-deploy-main/package-lock.json`. The release
audit reads that lockfile and reports any missing package license metadata.

## Android Client Dependencies

The Android client records resolved Gradle dependencies in its release SBOM:

| Dependency | License | Upstream notice |
| --- | --- | --- |
| AndroidX Compose, Room, WorkManager, and lifecycle | Apache-2.0 | https://developer.android.com/ |
| Kotlin coroutines | Apache-2.0 | https://github.com/Kotlin/kotlinx.coroutines/blob/master/LICENSE.txt |
| Tink Android | Apache-2.0 | https://github.com/tink-crypto/tink-java/blob/master/LICENSE |
| Bouncy Castle | MIT-style | https://www.bouncycastle.org/licence.html |
| llama.cpp (pinned submodule) | MIT | https://github.com/ggml-org/llama.cpp/blob/master/LICENSE |

## External Backends And Models

RIFT adapts external serving systems such as llama.cpp, vLLM, SGLang, and
MLX-LM without bundling or modifying them. Their licenses and installation
terms remain applicable. A model repository may impose additional model,
dataset, tokenizer, or acceptable-use terms. RIFT reports declared metadata but
does not grant permission to deploy any model.
