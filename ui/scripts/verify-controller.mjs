import { createServer } from "vite";

const controller = process.env.RIFT_CONTROLLER_URL ?? "http://127.0.0.1:8777";
process.env.VITE_RIFT_CONTROLLER_URL = controller;

const server = await createServer({
    root: process.cwd(),
    configFile: false,
    appType: "custom",
    logLevel: "error",
    server: { middlewareMode: true },
});

try {
    const { rift } = await server.ssrLoadModule("/src/lib/rift/client.ts");
    const [health, nodes, services, incidents, timeline, backends, benchmarks] = await Promise.all([
        rift.health(),
        rift.listNodes(),
        rift.listServices(),
        rift.listIncidents(),
        rift.timeline(),
        rift.backends(),
        rift.listBenchmarks("chat"),
    ]);
    let plan = null;
    try {
        plan = await rift.currentPlan();
    } catch (error) {
        if (error?.reason !== "not-implemented") throw error;
    }
    if (nodes.length === 0) throw new Error("controller returned no hardware nodes");
    if (health.servicesTotal !== services.length) {
        throw new Error(
            `health service count ${health.servicesTotal} does not match services ${services.length}`,
        );
    }
    const summary = {
        controller,
        provenance: health.provenance,
        node: {
            hostname: nodes[0].hostname,
            gpu: nodes[0].accelerators[0]?.name ?? "none",
            ramBytes: nodes[0].ramBytes,
            diskFreeBytes: nodes[0].diskFreeBytes,
        },
        services: services.map((service) => ({
            id: service.id,
            backend: service.backendKind,
            status: service.status,
            model: service.details?.modelPath ?? service.artifactId,
        })),
        incidents: {
            total: incidents.length,
            open: incidents.filter((incident) => incident.status !== "resolved").length,
        },
        timelineEvents: Array.isArray(timeline.events) ? timeline.events.length : 0,
        backendProviders: Object.keys(backends.providers ?? {}).length,
        benchmarks: {
            total: benchmarks.length,
            latestTokensPerSecond: benchmarks[0]?.tokensPerSec ?? null,
        },
        plan: {
            actions: plan?.actions.length ?? 0,
            provenance: plan?.provenance ?? "none",
            previewOnly: plan?.previewOnly ?? false,
        },
    };
    console.log(JSON.stringify(summary, null, 2));
} finally {
    await server.close();
}
