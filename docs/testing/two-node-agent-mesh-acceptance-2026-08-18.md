# RIFT Four-Node Agent Mesh Acceptance

Date: 2026-08-18  
Environment: Windows workstation, Docker Desktop Linux containers, local RTX 4060 host  
Model: `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf`  
Backend: RIFT-managed `llama.cpp` host processes

## Topology

```text
controller container :12100
  | mTLS over isolated Docker bridge
  +-- node-a          :12101  deployed + inference proxy -> host llama.cpp :11831
  +-- node-b          :12102  deployed + inference proxy -> host llama.cpp :11832
  +-- node-inference  :12103  inference-only proxy
```

The controller and node agents were separate containers on the `rift-two-node-test`
network. The node agents used ephemeral ECDSA certificates signed by a temporary
test CA. The host model was mounted nowhere into the containers and was not
duplicated; the agents reached the two host services only through
`host.docker.internal`.

## Verified Results

| Check | Result | Evidence |
|---|---:|---|
| Four isolated roles started | PASS | Docker containers `rift-mesh-controller`, `rift-mesh-node-a`, `rift-mesh-node-b`, `rift-mesh-node-inference` |
| Controller health | PASS | `http://127.0.0.1:12100/health` returned `ok: true` |
| Node mTLS health | PASS | All three agents returned `mutual_tls_required: true` and their own node IDs |
| Controller remote discovery | PASS | 3/3 agents ready; live `rift_agent` transport; 6 GiB aggregate reported test RAM |
| Desired-state submission | PASS | All three agents accepted generation 1 and repeated submission was idempotent |
| Real prompt through node A | PASS | HTTP 200 and non-empty generated text from host service `:11831` |
| Real prompt through node B | PASS | HTTP 200 and non-empty generated text from host service `:11832` |
| Elastic peer fallback | PASS | Stopping node A produced connection refusal; node B returned a non-empty response |
| Controller loss view | PASS | Controller rediscovery reported 2/3 ready while node A was stopped |
| Node recovery | PASS | Restarting node A restored 3/3 ready and both prompt routes |
| Dashboard | PASS | Vite UI served on `http://127.0.0.1:8765`; `/api/rift/state`, `/api/rift/services`, and `/api/rift/v2/mesh/nodes` proxied to controller port `12100` |

## Important Boundary

The read-only controller placement plan scheduled `0/2` replicas for the
container agents. This is correct for the test image: it intentionally contains
the RIFT control plane but no serving backend binary, GPU runtime, or model
artifact. RIFT reported `no compatible installed backend` rather than claiming
that a control-only node could serve a model.

The successful inference path therefore proves real networked RIFT agent
forwarding and elasticity around two real RIFT-managed host inference services;
it does not prove a model binary running inside the node containers. A production
node image must add or detect an approved backend and expose its artifact and
resource inventory before the controller should place workloads there.

## Cleanup

The temporary model services were stopped through RIFT, the controller and node
containers and bridge network were removed, the ephemeral certificate/state
directory was deleted, and the pre-test RIFT state backup was restored. The
frontend dependencies remain installed in the historical checkout so the UI
could be started reproducibly; the release tree now uses `ui/` as its only
dashboard source and does not commit its dependency directory. No model files
were deleted.

This report predates the platform runtime-path migration. Its `.rift/reports/`
references identify the original evidence location; current reports belong
under the platform-specific `RIFT_HOME` reports directory.

Reports generated during the run:

- `.rift/reports/two-node-agent-mesh-acceptance-2026-08-18/agent-flow.json`
- `.rift/reports/two-node-agent-mesh-acceptance-2026-08-18/failover.json`
- `.rift/reports/two-node-agent-mesh-acceptance-2026-08-18/discovery.json`
- `.rift/reports/two-node-agent-mesh-acceptance-2026-08-18/plan.json`
