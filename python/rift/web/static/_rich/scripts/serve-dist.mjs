import http from "node:http";
import https from "node:https";
import { readFile, stat } from "node:fs/promises";
import { extname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import app from "../dist/server/server.js";

const scriptDir = resolve(fileURLToPath(new URL(".", import.meta.url)));
const uiRoot = resolve(scriptDir, "..");
const clientRoot = resolve(uiRoot, "dist", "client");
const host = process.env.RIFT_UI_HOST || "127.0.0.1";
const port = Number(process.env.RIFT_UI_PORT || process.env.PORT || 8765);
const controlApi = String(process.env.RIFT_CONTROL_API || "http://127.0.0.1:8777").replace(/\/$/, "");

const contentTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function safeClientPath(requestPath) {
  let decoded;
  try {
    decoded = decodeURIComponent(requestPath.split("?", 1)[0]);
  } catch {
    return null;
  }
  const candidate = resolve(clientRoot, `.${decoded}`);
  const relativePath = relative(clientRoot, candidate);
  if (relativePath.startsWith("..") || relativePath.includes("..")) return null;
  return candidate;
}

function requestHeaders(request) {
  const headers = {};
  for (const [name, value] of Object.entries(request.headers)) {
    if (value !== undefined && name.toLowerCase() !== "host") {
      headers[name] = Array.isArray(value) ? value.join(", ") : value;
    }
  }
  return headers;
}

async function bodyBuffer(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

function writeResponse(response, nodeResponse) {
  nodeResponse.statusCode = response.status;
  for (const [name, value] of response.headers) {
    if (name.toLowerCase() !== "transfer-encoding") nodeResponse.setHeader(name, value);
  }
  return response.arrayBuffer().then((body) => nodeResponse.end(Buffer.from(body)));
}

async function proxyController(request, response) {
  const target = new URL(request.url, controlApi);
  const method = request.method || "GET";
  const body = method === "GET" || method === "HEAD" ? undefined : await bodyBuffer(request);
  const transport = target.protocol === "https:" ? https : http;
  const headers = requestHeaders(request);
  await new Promise((resolvePromise, rejectPromise) => {
    const upstream = transport.request(
      {
        protocol: target.protocol,
        hostname: target.hostname,
        port: target.port || undefined,
        path: `${target.pathname}${target.search}`,
        method,
        headers,
        timeout: 30 * 60 * 1000,
      },
      (upstreamResponse) => {
        response.statusCode = upstreamResponse.statusCode || 502;
        for (const [name, value] of Object.entries(upstreamResponse.headers)) {
          if (value !== undefined && !["transfer-encoding", "connection"].includes(name.toLowerCase())) {
            response.setHeader(name, value);
          }
        }
        upstreamResponse.on("error", rejectPromise);
        upstreamResponse.on("end", resolvePromise);
        upstreamResponse.pipe(response);
      },
    );
    upstream.on("timeout", () => {
      upstream.destroy(new Error("RIFT controller request timed out after 30 minutes"));
    });
    upstream.on("error", rejectPromise);
    if (body && body.length > 0) upstream.write(body);
    upstream.end();
  });
}

async function serveAsset(requestPath, response) {
  const assetPath = requestPath === "/favicon.ico" ? "/rift-mark.svg" : requestPath;
  const filePath = safeClientPath(assetPath);
  if (!filePath) return false;
  try {
    const metadata = await stat(filePath);
    if (!metadata.isFile()) return false;
    const file = await readFile(filePath);
    response.statusCode = 200;
    response.setHeader("Content-Type", contentTypes[extname(filePath)] || "application/octet-stream");
    response.end(file);
    return true;
  } catch (error) {
    if (error?.code !== "ENOENT") throw error;
    return false;
  }
}

async function renderPage(request, response) {
  const url = `http://${request.headers.host || `${host}:${port}`}${request.url}`;
  const rendered = await app.fetch(
    new Request(url, { method: request.method || "GET", headers: requestHeaders(request) }),
    {},
    {},
  );
  await writeResponse(rendered, response);
}

const server = http.createServer(async (request, response) => {
  try {
    const requestPath = request.url || "/";
    if (requestPath.startsWith("/api/rift")) {
      await proxyController(request, response);
      return;
    }
    if (await serveAsset(requestPath, response)) return;
    await renderPage(request, response);
  } catch (error) {
    console.error(error);
    if (!response.headersSent) response.statusCode = 500;
    response.end("RIFT dashboard failed to render");
  }
});

server.listen(port, host, () => {
  console.log(`RIFT rich dashboard listening on http://${host}:${port}`);
  console.log(`RIFT controller proxy ${controlApi}`);
});
server.requestTimeout = 30 * 60 * 1000;
server.headersTimeout = 30 * 60 * 1000;

function close() {
  server.close(() => process.exit(0));
}

process.once("SIGINT", close);
process.once("SIGTERM", close);
