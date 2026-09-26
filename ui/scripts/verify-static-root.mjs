import assert from "node:assert/strict";
import { rootRedirectHtml } from "./static-routes.mjs";

const html = rootRedirectHtml();
assert.match(html, /http-equiv="refresh" content="0;url=\/workloads"/);
assert.match(html, /location\.replace\("\/workloads"\)/);
assert.match(html, /<a href="\/workloads">Workload Deploy<\/a>/);
assert.match(html, /<link rel="icon" href="\/rift-logo-concept-v9\.png"/);

console.log("static root redirects to Workload Deploy");
