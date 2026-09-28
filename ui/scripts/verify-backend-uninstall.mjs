import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const settings = await readFile(
  new URL("../src/routes/settings.tsx", import.meta.url),
  "utf8",
);
const client = await readFile(new URL("../src/lib/rift/client.ts", import.meta.url), "utf8");
const orchestrator = await readFile(
  new URL("../../python/rift/orchestrator.py", import.meta.url),
  "utf8",
);

assert.match(settings, /const removable = uninstall\.removable === true/);
assert.match(settings, /\{removable \? \(/);
assert.match(settings, /Not RIFT-managed/);
assert.match(settings, /blockers\.map\(\(blocker\) => \(/);
assert.match(
  settings,
  /window\.confirm\(\s*`Remove the RIFT-managed \$\{name\} runtime at \$\{target\}\? Models, service configuration, and logs will be preserved\.`,/,
);
assert.match(settings, /await rift\.uninstallBackend\(name, true\)/);
assert.match(settings, /invalidateQueries\(\{ queryKey: keys\.backends \}\)/);
assert.match(settings, /busyBackend === name \? "Removing…" : "Remove runtime"/);
assert.match(settings, /role=\{actionError \? "alert" : "status"\}/);
assert.match(client, /uninstallBackend: \(backendId: string, confirm: true\)/);
assert.match(client, /"POST", `\/backends\/\$\{encodeURIComponent\(backendId\)\}\/uninstall`/);
assert.match(client, /confirm,\s*request_id:/);
assert.match(orchestrator, /"uninstall": self\.backend_uninstall_plan\(name\)/);

console.log("backend uninstall UI contract verification passed");
