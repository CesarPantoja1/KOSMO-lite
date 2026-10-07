"use strict";

// Runs only in CI/deployment with a synthetic project and a fake API key.
// No prompt is sent, so no provider request or user credential is involved.
const { execFileSync } = require("node:child_process");
const crypto = require("node:crypto");
const { setTimeout: pause } = require("node:timers/promises");

const suppliedProjectId = process.argv[2];
const projectId = suppliedProjectId || `prj_smoke_${crypto.randomBytes(10).toString("hex")}`;
const token = process.env.OPENCODE_LAUNCHER_TOKEN;
const stack = process.env.KOSMO_STACK;
const fakeKey = "kosmo-smoke-no-provider-call";
const launcherUrl = "http://127.0.0.1:8082";

if (!/^prj_smoke_[a-zA-Z0-9_-]{1,80}$/.test(projectId) || !token ||
    (!suppliedProjectId && stack !== "production" && stack !== "staging")) {
  throw new Error("OpenCode smoke configuration is incomplete");
}

function createFixture() {
  const backendName = stack === "production" ? "kosmo-backend" : "kosmo-staging-backend";
  execFileSync("/usr/local/bin/docker", ["exec", "-i", "--user", "1000:1000", backendName,
    "/opt/venv/bin/python", "-c", `
from pathlib import Path
import re, sys
name = sys.stdin.read()
if not re.fullmatch(r"prj_smoke_[a-zA-Z0-9_-]{1,80}", name):
    raise SystemExit(2)
project = Path("/workspaces") / name
project.mkdir()
project.chmod(0o750)
(project / "opencode.json").write_text("{}", encoding="utf-8")
`], { input: projectId, encoding: "utf8" });
}

function removeFixture() {
  const backendName = stack === "production" ? "kosmo-backend" : "kosmo-staging-backend";
  execFileSync("/usr/local/bin/docker", ["exec", "-i", "--user", "1000:1000", backendName,
    "/opt/venv/bin/python", "-c", `
from pathlib import Path
import re, shutil, sys
name = sys.stdin.read()
root = Path("/workspaces").resolve()
project = (root / name).resolve()
if not re.fullmatch(r"prj_smoke_[a-zA-Z0-9_-]{1,80}", name) or project.parent != root:
    raise SystemExit(2)
shutil.rmtree(project)
`], { input: projectId, encoding: "utf8" });
}

async function launcherRequest(route, method = "GET", body) {
  return fetch(`${launcherUrl}${route}`, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(15_000),
  });
}

async function main() {
  const created = await launcherRequest("/jobs", "POST", {
    project_id: projectId,
    provider: "deepseek",
    model: "deepseek-flash",
    api_key: fakeKey,
  });
  if (created.status !== 201) throw new Error(`Launcher rejected smoke job (${created.status}): ${await created.text()}`);
  const job = await created.json();
  if (!/^[a-f0-9]{64}$/.test(job.job_id) || !/^http:\/\/kosmo-oc-[a-f0-9]{24}:4096$/.test(job.base_url)) {
    throw new Error("Launcher returned an invalid smoke job endpoint");
  }
  try {
    const auth = `Basic ${Buffer.from(`opencode:${job.password}`).toString("base64")}`;
    for (let attempt = 0; attempt < 60; attempt++) {
      try {
        const health = await fetch(`${job.base_url}/health`, {
          headers: { Authorization: auth }, signal: AbortSignal.timeout(5_000),
        });
        if (health.ok) {
          const provider = await fetch(`${job.base_url}/provider`, {
            headers: { Authorization: auth }, signal: AbortSignal.timeout(30_000),
          });
          if (!provider.ok) throw new Error(`OpenCode provider catalog failed (${provider.status})`);
          const catalog = await provider.json();
          if (!Array.isArray(catalog.all)) throw new Error("OpenCode provider catalog is malformed");
          if (!catalog.all.some((entry) => entry.id === "deepseek" && entry.models && entry.models["deepseek-flash"])) {
            throw new Error("The smoke model is missing from OpenCode's provider catalog");
          }

          const metadata = execFileSync("/usr/local/bin/docker", ["inspect", job.job_id], { encoding: "utf8" });
          if (metadata.includes(fakeKey)) throw new Error("Provider key leaked into Docker metadata");
          const mode = execFileSync("/usr/local/bin/docker", ["exec", "--user", "1000:1000", job.job_id,
            "stat", "-c", "%u:%g %a", "/run/kosmo-secrets/provider-key"], { encoding: "utf8" }).trim();
          if (mode !== "1000:1000 600") throw new Error(`Provider key file has unsafe permissions: ${mode}`);
          console.info("Isolated OpenCode started, loaded provider config, and kept the fake key out of metadata.");
          return;
        }
      } catch (error) {
        if (error.message && !error.message.includes("fetch failed") && error.name !== "TimeoutError") throw error;
      }
      const status = await launcherRequest(`/jobs/${job.job_id}`);
      if (status.ok) {
        const state = await status.json();
        if (state.status === "exited" || state.oom_killed) {
          const logs = execFileSync("/usr/local/bin/docker", ["logs", "--tail", "20", job.job_id], { encoding: "utf8" });
          throw new Error(`OpenCode exited during smoke: ${logs.replaceAll(fakeKey, "[REDACTED]")}`);
        }
      }
      await pause(2_000);
    }
    throw new Error("OpenCode did not become healthy during smoke startup");
  } finally {
    const removed = await launcherRequest(`/jobs/${job.job_id}`, "DELETE");
    if (!removed.ok) throw new Error(`Could not remove smoke job (${removed.status})`);
  }
}

async function run() {
  if (!suppliedProjectId) createFixture();
  try { await main(); }
  finally { if (!suppliedProjectId) removeFixture(); }
}

run().catch((error) => {
  console.error(String(error).replaceAll(fakeKey, "[REDACTED]"));
  process.exitCode = 1;
});
