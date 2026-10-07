"use strict";

// This service is the only application component allowed to access Docker.
// Provider credentials are streamed through docker exec stdin into job tmpfs,
// never placed in container environment, command line, labels, or logs.
const http = require("node:http");
const crypto = require("node:crypto");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");

const socketPath = "/var/run/docker.sock";
const token = process.env.OPENCODE_LAUNCHER_TOKEN;
const image = process.env.KOSMO_OPENCODE_IMAGE;
const stack = process.env.KOSMO_STACK;
const network = process.env.KOSMO_NETWORK;
const workspaceRoot = process.env.KOSMO_WORKSPACES_HOST_PATH;
const port = 8082;
const maxJobs = 2;
const leases = new Map();
const leaseMillis = 90_000; // inactivity lease, NOT a job-duration limit

if (!token || !image || !stack || !network || !path.posix.isAbsolute(workspaceRoot || "")) {
  throw new Error("OpenCode launcher configuration is incomplete");
}

function docker(method, route, body) {
  return new Promise((resolve, reject) => {
    const request = http.request({ socketPath, path: `/v1.41${route}`, method,
      headers: body ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(body) } : {} }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        const content = Buffer.concat(chunks).toString("utf8");
        if (response.statusCode >= 300) return reject(new Error(`Docker operation failed (${response.statusCode})`));
        try { resolve(content ? JSON.parse(content) : {}); }
        catch { resolve(content); }
      });
    });
    request.on("error", reject);
    request.setTimeout(30_000, () => request.destroy(new Error("Docker operation timed out")));
    request.end(body);
  });
}

function secretExecArgs(containerId, filename) {
  if (!validContainerId(containerId)) throw new Error("Invalid Docker container ID");
  if (filename !== "provider-key" && filename !== "ready") throw new Error("Invalid secret filename");
  return ["exec", "-i", "--user", "1000:1000", containerId, "/bin/sh", "-c",
    `umask 077; cat > /run/kosmo-secrets/${filename}`];
}

function writeSecret(containerId, filename, value) {
  const args = secretExecArgs(containerId, filename);
  const secret = Buffer.from(value, "utf8");
  return new Promise((resolve, reject) => {
    const child = spawn("/usr/local/bin/docker", args, { stdio: ["pipe", "ignore", "pipe"],
      env: { ...process.env, DOCKER_HOST: `unix://${socketPath}` } });
    let diagnostic = "";
    child.stderr.on("data", (chunk) => {
      if (diagnostic.length < 512) diagnostic += chunk.toString("utf8").slice(0, 512 - diagnostic.length);
    });
    child.stdin.on("error", () => {}); // A failed exec may close stdin before the key is sent.
    const timer = setTimeout(() => child.kill("SIGKILL"), 30_000);
    child.on("error", (error) => reject(new Error(`Secret injection could not start: ${error.code || "unknown"}`)));
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) return resolve();
      const safeDiagnostic = diagnostic.replaceAll(value, "[REDACTED]").replace(/[\r\n]+/g, " ").slice(0, 512);
      reject(new Error(`Secret injection failed (${code}): ${safeDiagnostic}`));
    });
    child.stdin.end(secret);
  }).finally(() => secret.fill(0));
}

const labels = { "kosmo.opencode-job": "1", "kosmo.stack": stack };
function containerFilters() {
  return encodeURIComponent(JSON.stringify({ label: Object.entries(labels).map(([k, v]) => `${k}=${v}`) }));
}
async function listJobs() {
  return docker("GET", `/containers/json?all=1&filters=${containerFilters()}`);
}
async function removeJob(id) {
  if (!validContainerId(id)) throw new Error("Invalid Docker container ID");
  try { await docker("DELETE", `/containers/${encodeURIComponent(id)}?force=1&v=1`); }
  catch (error) { if (!String(error).includes("(404)")) throw error; }
  leases.delete(id);
  console.info(JSON.stringify({ event: "opencode.job_removed" }));
}
async function reapAbandoned() {
  const now = Date.now();
  const jobs = await listJobs();
  const known = new Set(jobs.map((job) => job.Id));
  for (const id of leases.keys()) if (!known.has(id)) leases.delete(id);
  for (const job of jobs) {
    if (!leases.has(job.Id)) leases.set(job.Id, now);
    if (now - leases.get(job.Id) > leaseMillis) await removeJob(job.Id);
  }
}

function validId(value) { return typeof value === "string" && /^[a-zA-Z0-9_-]{1,128}$/.test(value); }
function validModel(value) { return typeof value === "string" && /^[a-zA-Z0-9_.:-]{1,100}$/.test(value); }
function validContainerId(value) { return typeof value === "string" && /^[a-f0-9]{64}$/.test(value); }
const providers = new Set(["openai", "anthropic", "google", "deepseek"]);
function ownedJobId(jobs, candidate) {
  const job = jobs.find((item) => item.Id === candidate);
  return job && validContainerId(job.Id) ? job.Id : null;
}
function workspaceReadError(error, missingMessage) {
  if (error && (error.code === "EACCES" || error.code === "EPERM")) {
    return Object.assign(new Error("El servicio de generación no tiene permisos para leer el workspace del proyecto."),
      { status: 503 });
  }
  if (error && error.code === "ENOENT") {
    return Object.assign(new Error(missingMessage), { status: 422 });
  }
  return Object.assign(new Error("No se pudo verificar el workspace del proyecto."), { status: 503 });
}

function buildJobConfig(input, password) {
  const workspace = path.posix.join(workspaceRoot, input.project_id);
  const configPath = path.posix.join(workspace, "opencode.json");
  return {
    Image: image,
    User: "1000:1000",
    WorkingDir: `/workspaces/${input.project_id}`,
    Entrypoint: ["/bin/sh", "-c"],
    Cmd: ["while [ ! -f /run/kosmo-secrets/ready ]; do sleep 0.2; done; exec /usr/local/bin/start-opencode"],
    Env: ["HOME=/home/node", `OPENCODE_SERVER_PASSWORD=${password}`,
      `OPENCODE_MODEL=${input.provider}/${input.model}`, `KOSMO_AI_PROVIDER=${input.provider}`,
      "OPENCODE_PERMISSION={\"read\":{\"*\":\"allow\"},\"edit\":{\"*\":\"allow\"},\"bash\":\"deny\",\"external_directory\":\"deny\"}"],
    Labels: labels,
    HostConfig: {
      NetworkMode: network,
      Binds: [
        `${workspace}:/workspaces/${input.project_id}:rw`,
        `${configPath}:/workspaces/${input.project_id}/opencode.json:ro`,
      ],
      Memory: 1073741824,
      NanoCpus: 1500000000,
      PidsLimit: 256,
      CapDrop: ["ALL"],
      SecurityOpt: ["no-new-privileges:true"],
      ReadonlyRootfs: true,
      Tmpfs: {
        "/tmp": "rw,nosuid,nodev,size=256m,mode=1777",
        "/home/node": "rw,nosuid,nodev,size=512m,mode=0700,uid=1000,gid=1000",
        "/run/kosmo-secrets": "rw,noexec,nosuid,nodev,size=1m,mode=0700,uid=1000,gid=1000",
      },
    },
  };
}

async function createJob(input) {
  if (!validId(input.project_id) || !providers.has(input.provider) || !validModel(input.model) ||
      typeof input.api_key !== "string" || !input.api_key.trim() || input.api_key.length > 500) {
    throw Object.assign(new Error("Configuración de IA o proyecto inválido"), { status: 422 });
  }
  const jobs = await listJobs();
  if (jobs.length >= maxJobs) {
    throw Object.assign(new Error("Hay dos implementaciones activas; inténtalo cuando termine una."), { status: 429 });
  }
  const id = `kosmo-oc-${crypto.randomBytes(12).toString("hex")}`;
  const password = crypto.randomBytes(32).toString("base64url");
  let visibleRoot;
  let visibleWorkspace;
  try {
    visibleRoot = fs.realpathSync("/workspaces");
    visibleWorkspace = fs.realpathSync(path.join("/workspaces", input.project_id));
  } catch (error) {
    throw workspaceReadError(error, "Workspace de proyecto no encontrado");
  }
  if (path.dirname(visibleWorkspace) !== visibleRoot) {
    throw Object.assign(new Error("Workspace de proyecto inválido"), { status: 422 });
  }
  let workspaceStat;
  try { workspaceStat = fs.statSync(visibleWorkspace); }
  catch (error) { throw workspaceReadError(error, "Workspace de proyecto no encontrado"); }
  if (!workspaceStat.isDirectory()) {
    throw Object.assign(new Error("Workspace de proyecto inválido"), { status: 422 });
  }
  const projectConfigPath = path.join(visibleWorkspace, "opencode.json");
  let projectConfigStat;
  try { projectConfigStat = fs.lstatSync(projectConfigPath); }
  catch (error) { throw workspaceReadError(error, "Configuración OpenCode del proyecto no encontrada"); }
  if (!projectConfigStat.isFile() || projectConfigStat.isSymbolicLink()) {
    throw Object.assign(new Error("Configuración OpenCode del proyecto inválida"), { status: 422 });
  }
  let projectConfig;
  let projectConfigContent;
  try { projectConfigContent = fs.readFileSync(projectConfigPath, "utf8"); }
  catch (error) { throw workspaceReadError(error, "Configuración OpenCode del proyecto no encontrada"); }
  try { projectConfig = JSON.parse(projectConfigContent); }
  catch { throw Object.assign(new Error("Configuración OpenCode del proyecto inválida"), { status: 422 }); }
  if (!projectConfig || typeof projectConfig !== "object" || Array.isArray(projectConfig) ||
      "model" in projectConfig || "small_model" in projectConfig || "provider" in projectConfig) {
    throw Object.assign(new Error("El proyecto no puede sobrescribir el proveedor o modelo personal"), { status: 422 });
  }
  const config = buildJobConfig(input, password);
  const created = await docker("POST", `/containers/create?name=${id}`, JSON.stringify(config));
  if (!validContainerId(created.Id)) throw new Error("Invalid Docker container ID");
  let stage = "start";
  try {
    await docker("POST", `/containers/${created.Id}/start`);
    stage = "provider-key";
    await writeSecret(created.Id, "provider-key", input.api_key.trim());
    stage = "ready";
    await writeSecret(created.Id, "ready", "1");
    leases.set(created.Id, Date.now());
    console.info(JSON.stringify({ event: "opencode.job_created", job_id: created.Id,
      provider: input.provider, model: input.model, memory_bytes: config.HostConfig.Memory }));
    return { job_id: created.Id, base_url: `http://${id}:4096`, password };
  } catch (error) {
    console.error(JSON.stringify({ event: "opencode.job_start_failed", stage,
      detail: String(error).replaceAll(input.api_key.trim(), "[REDACTED]") }));
    try { await removeJob(created.Id); }
    catch (cleanupError) { console.error(JSON.stringify({ event: "opencode.job_cleanup_failed", stage,
      detail: String(cleanupError) })); }
    const message = stage === "start" ? "No se pudo arrancar el contenedor aislado de OpenCode."
      : "No se pudieron preparar las credenciales del contenedor aislado de OpenCode.";
    throw Object.assign(new Error(message), { status: 503 });
  }
}

function reply(response, code, data) {
  response.writeHead(code, { "Content-Type": "application/json", "Cache-Control": "no-store" });
  response.end(JSON.stringify(data));
}

let creating = false;
const server = http.createServer(async (request, response) => {
  if (request.url === "/health" && request.method === "GET") {
    try { await listJobs(); reply(response, 200, { ok: true }); }
    catch { reply(response, 503, { error: "Docker no está disponible" }); }
    return;
  }
  const supplied = request.headers.authorization || "";
  const expected = `Bearer ${token}`;
  if (supplied.length !== expected.length || !crypto.timingSafeEqual(Buffer.from(supplied), Buffer.from(expected))) {
    reply(response, 401, { error: "No autorizado" });
    return;
  }
  try {
    if (request.method === "POST" && request.url === "/jobs") {
      if (creating) return reply(response, 429, { error: "El lanzador está ocupado" });
      creating = true;
      try {
        const chunks = [];
        let size = 0;
        for await (const chunk of request) {
          size += chunk.length;
          if (size > 4096) throw Object.assign(new Error("Solicitud demasiado grande"), { status: 413 });
          chunks.push(chunk);
        }
        reply(response, 201, await createJob(JSON.parse(Buffer.concat(chunks).toString("utf8"))));
      } finally { creating = false; }
      return;
    }
    const match = /^\/jobs\/([a-f0-9]{64})(\/heartbeat)?$/.exec(request.url || "");
    if (match && request.method === "POST" && match[2]) {
      const jobs = await listJobs();
      const jobId = ownedJobId(jobs, match[1]);
      if (!jobId) return reply(response, 404, { error: "Trabajo no encontrado" });
      leases.set(jobId, Date.now());
      return reply(response, 200, { ok: true });
    }
    if (match && request.method === "GET" && !match[2]) {
      const jobs = await listJobs();
      const jobId = ownedJobId(jobs, match[1]);
      if (!jobId) return reply(response, 404, { error: "Trabajo no encontrado" });
      const detail = await docker("GET", `/containers/${encodeURIComponent(jobId)}/json`);
      return reply(response, 200, { status: detail.State.Status, oom_killed: detail.State.OOMKilled });
    }
    if (match && request.method === "DELETE" && !match[2]) {
      const jobs = await listJobs();
      const jobId = ownedJobId(jobs, match[1]);
      if (!jobId) return reply(response, 404, { error: "Trabajo no encontrado" });
      await removeJob(jobId);
      return reply(response, 200, { ok: true });
    }
    reply(response, 404, { error: "Ruta no encontrada" });
  } catch (error) {
    reply(response, error.status || 503, { error: error.status ? error.message : "No se pudo iniciar el asistente de implementación" });
  }
});

if (require.main === module) {
  setInterval(() => reapAbandoned().catch(() => {}), 30_000).unref();
  server.listen(port, "0.0.0.0");
}

module.exports = { buildJobConfig, secretExecArgs, validId, validModel, validContainerId,
  ownedJobId, workspaceReadError };
