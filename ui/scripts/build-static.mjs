import { cp, mkdir, readdir, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { pathToFileURL } from "node:url";

const scriptDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const uiRoot = resolve(scriptDir, "..");
const clientRoot = resolve(uiRoot, "dist", "client");
const serverBundle = resolve(uiRoot, "dist", "server", "server.js");
const staticRoot = resolve(uiRoot, "..", "python", "rift", "web", "static");

const routes = [
    { url: "/", filename: "index.html" },
    { url: "/setup", filename: "setup.html" },
    { url: "/deployments", filename: "deployments.html" },
    { url: "/nodes", filename: "nodes.html" },
    { url: "/models", filename: "models.html" },
    { url: "/operations?tab=operations", filename: "operations.html" },
    { url: "/settings?tab=controller", filename: "settings.html" },
];

async function main() {
    const { default: app } = await import(pathToFileURL(serverBundle).href);
    await mkdir(staticRoot, { recursive: true });
    for (const entry of await readdir(staticRoot)) {
        if (entry === "assets" || entry.endsWith(".html") || entry === "rift-mark.svg") {
            await rm(join(staticRoot, entry), { recursive: true, force: true });
        }
    }
    await cp(join(clientRoot, "assets"), join(staticRoot, "assets"), { recursive: true });
    await cp(join(clientRoot, "rift-mark.svg"), join(staticRoot, "rift-mark.svg"));

    for (const route of routes) {
        const response = await app.fetch(new Request(`http://127.0.0.1:8765${route.url}`), {}, {});
        if (!response.ok)
            throw new Error(`static export failed for ${route.url}: HTTP ${response.status}`);
        const page = (await response.text()).replace(
            "</head>",
            '<script src="/rift-config.js"></script></head>',
        );
        await writeFile(join(staticRoot, route.filename), page, "utf8");
    }
    console.log(`Exported ${routes.length} RIFT dashboard routes to ${staticRoot}`);
}

await main();
