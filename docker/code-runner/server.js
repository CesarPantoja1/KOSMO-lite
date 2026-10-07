"use strict";
const http = require("http");
const fs = require("fs/promises");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const token = process.env.CODE_RUNNER_TOKEN;
if (!token) throw new Error("CODE_RUNNER_TOKEN must be set");
const commands = { typecheck: "npx tsc --noEmit", lint: "npx eslint .", tests: "npx vitest run", build: "npx next build" };
const allowed = new Set(["npm", "npx", "tsc", "eslint", "vitest", "next", "git", "node", "pnpm", "yarn", "pytest", "python", "pyright", "ruff"]);
const runnerTmpDir = process.env.RUNNER_TMP_DIR || "/tmp/kosmo-runner";

function respond(res, status, body) { res.writeHead(status, { "content-type": "application/json" }); res.end(JSON.stringify(body)); }
function exec(command, cwd, timeoutSeconds) {
  return new Promise((resolve) => {
    const started = Date.now(); let output = ""; let timedOut = false;
    const child = spawn(command, { cwd, shell: true, detached: true, env: { PATH: process.env.PATH, HOME: process.env.HOME || os.homedir() } });
    child.stdout.on("data", d => output += d); child.stderr.on("data", d => output += d);
    const timer = setTimeout(() => { timedOut = true; try { process.kill(-child.pid, "SIGKILL"); } catch { child.kill("SIGKILL"); } }, Math.min(Math.max(Number(timeoutSeconds) || 300, 1), 600) * 1000);
    child.on("close", code => { clearTimeout(timer); resolve({ output: timedOut ? `${output}\nCommand timed out.` : output, exit_code: timedOut ? -1 : (code ?? 1), duration_ms: Date.now() - started }); });
  });
}
async function unpack(archive) {
  if (typeof archive !== "string" || archive.length > 70_000_000) throw new Error("Invalid workspace archive");
  await fs.mkdir(runnerTmpDir, { recursive: true });
  const root = await fs.mkdtemp(path.join(runnerTmpDir, "run-")); const file = path.join(root, "workspace.tgz"); const workspace = path.join(root, "workspace");
  await fs.mkdir(workspace); await fs.writeFile(file, Buffer.from(archive, "base64"));
  const result = await exec(`tar -xzf ${file} --no-same-owner --no-same-permissions -C ${workspace}`, root, 30);
  if (result.exit_code !== 0) throw new Error("Could not unpack workspace"); return { root, workspace };
}
http.createServer(async (req, res) => {
  if (req.url === "/health") return respond(res, 200, { ok: true });
  if (req.method !== "POST" || req.url !== "/run" || req.headers.authorization !== `Bearer ${token}`) return respond(res, 401, { error: "unauthorized" });
  let raw = ""; req.on("data", chunk => { raw += chunk; if (raw.length > 70_000_000) req.destroy(); });
  req.on("end", async () => {
    let temp; try {
      const input = JSON.parse(raw); temp = await unpack(input.archive);
      if (input.operation === "step") { const step = input.step; if (!commands[step]) throw new Error("Unknown validation step"); return respond(res, 200, { result: { ...(await exec(commands[step], temp.workspace, input.timeout_seconds)), step } }); }
      if (input.operation === "command") { const first = String(input.command || "").trim().split(/\s+/)[0].replace(/^.*\//, ""); if (!allowed.has(first)) throw new Error("Command is not allowed"); return respond(res, 200, { result: await exec(input.command, temp.workspace, input.timeout_seconds) }); }
      if (input.operation !== "pipeline") throw new Error("Unknown operation");
      const install = await exec("npm install", temp.workspace, 600); if (install.exit_code !== 0) return respond(res, 200, { all_passed: false, results: [], error_summary: [`npm install failed: ${install.output.slice(0, 2000)}`] });
      const lockPath = path.join(temp.workspace, "package-lock.json");
      const lockStat = await fs.lstat(lockPath);
      if (!lockStat.isFile() || lockStat.size > 5_000_000) throw new Error("Invalid generated package-lock.json");
      const packageLock = await fs.readFile(lockPath, "utf8");
      const results = []; for (const step of input.steps || []) { if (!commands[step]) throw new Error("Unknown validation step"); const result = { ...(await exec(commands[step], temp.workspace, 300)), step }; results.push(result); if (result.exit_code !== 0) break; }
      return respond(res, 200, { all_passed: results.length === (input.steps || []).length && results.every(r => r.exit_code === 0), results, error_summary: results.filter(r => r.exit_code !== 0).map(r => r.output.slice(0, 2000)), package_lock: packageLock });
    } catch (error) { return respond(res, 400, { error: String(error.message || error) }); } finally { if (temp) await fs.rm(temp.root, { recursive: true, force: true }); }
  });
}).listen(8081, "0.0.0.0");
