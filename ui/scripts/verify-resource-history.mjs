// Browser regression with clearly synthetic API fixtures, never benchmark evidence.
// Requires Playwright; RIFT_PLAYWRIGHT_MODULE can point to an existing installation.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { dirname, extname, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const modulePath = process.env.RIFT_PLAYWRIGHT_MODULE;
const { chromium } = await import(modulePath ? pathToFileURL(modulePath).href : "playwright");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../../python/rift/web/static");
const server = createServer(async (req, res) => {
  const path = new URL(req.url, "http://localhost").pathname;
  if (path === "/rift-config.js") {
    res.writeHead(200, { "Content-Type": "text/javascript" });
    return res.end("window.RIFT_CONTROL_API = '/api/rift';");
  }
  const target = resolve(root, path === "/" ? "index.html" : `.${path}`);
  if (!target.startsWith(root + sep)) { res.writeHead(403); return res.end(); }
  try {
    const body = await readFile(target);
    res.writeHead(200, { "Content-Type": ({ ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml" })[extname(target)] ?? "application/octet-stream" });
    res.end(body);
  } catch { res.writeHead(404); res.end(); }
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  let empty = false;
  await page.route("**/api/rift/**", async (route) => {
    const url = new URL(route.request().url());
    let value = {};
    if (url.pathname.endsWith("/telemetry/latest")) value = { samples: [{
      session: { session_id: "synthetic-ui-session", service_name: "UI test fixture", node_id: "synthetic-node", started_at: Date.now() / 1000 - 900, status: "running" },
      sample: { observed_at: Date.now() / 1000, cpu_percent: 30 },
    }] };
    if (url.pathname.endsWith("/telemetry/history")) {
      const since = Number(url.searchParams.get("since"));
      const until = Number(url.searchParams.get("until"));
      const width = (until - since) / 180;
      value = { session_id: "synthetic-ui-session", metric: url.searchParams.get("metric"), since, until, bucket_seconds: width,
        source: "synthetic_ui_fixture", aggregation: "sample_mean_min_max", scope: "session_observed_resource_domain",
        points: Array.from({ length: 180 }, (_, i) => {
          const gap = empty || (i > 70 && i < 90);
          const mean = gap ? null : 30 + Math.sin(i / 8) * 10;
          return { observed_at: since + i * width, count: gap ? 0 : 5, mean, minimum: gap ? null : mean - 3, maximum: gap ? null : mean + 4 };
        }),
      };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(value) });
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.getByText("View recorded values", { exact: false }).waitFor();
  assert.equal(await page.locator(".recharts-wrapper").count(), 1);
  const strokes = await page.locator(".recharts-line-curve").evaluateAll((paths) => paths.map((path) => ({ stroke: getComputedStyle(path).stroke, length: path.getTotalLength() })));
  assert.equal(strokes.length, 2);
  assert.ok(strokes.every((path) => path.stroke !== "none" && path.length > 0), "Both chart lines must be visible, not only their axes");
  await page.getByText("View recorded values", { exact: false }).click();
  assert.equal(await page.locator("table tbody tr").count(), 180);
  await page.getByLabel("Time range", { exact: true }).selectOption("3600");
  await page.getByRole("img", { name: /Host CPU over the last 60 minutes/ }).waitFor();
  if (process.env.RIFT_UI_SCREENSHOT) {
    await mkdir(dirname(process.env.RIFT_UI_SCREENSHOT), { recursive: true });
    await page.screenshot({ path: process.env.RIFT_UI_SCREENSHOT, fullPage: true });
  }
  empty = true;
  await page.getByLabel("Resource", { exact: true }).selectOption("gpu_temperature_c");
  await page.getByText("No measurements for this resource", { exact: false }).waitFor();
  assert.deepEqual(errors, [], `Browser errors: ${errors.join("; ")}`);
  console.log("resource-history: PASS (synthetic chart, range selector, 180-row table, missing sensor, no browser errors)");
} finally {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
}
