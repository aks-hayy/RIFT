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
The exact versions used by a build are defined by the package metadata and
installer environment. Run `python scripts/audit_release.py --json` before
packaging.

## Operator Console Dependencies

The `ui/` dashboard source is a separate npm application. Its direct and
development dependencies, resolved versions, and package-declared licenses
are recorded in `ui/package-lock.json`. The release audit reads that lockfile
and reports any missing package license metadata. The packaged Python wheel
does not require those development dependencies.

Native-survival and Android experiments are preserved in the archival Git tag
and are not part of the release tree or release dependency inventory.

## External Backends And Models

RIFT adapts external serving systems such as llama.cpp, vLLM, SGLang, and
MLX-LM without bundling or modifying them. Their licenses and installation
terms remain applicable. A model repository may impose additional model,
dataset, tokenizer, or acceptable-use terms. RIFT reports declared metadata but
does not grant permission to deploy any model.
