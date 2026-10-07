"use strict";

const assert = require("node:assert/strict");
const { test } = require("node:test");

process.env.OPENCODE_LAUNCHER_TOKEN = "test-only-token";
process.env.KOSMO_OPENCODE_IMAGE = "example/opencode:fixed-sha";
process.env.KOSMO_STACK = "test";
process.env.KOSMO_NETWORK = "kosmo-test-network";
process.env.KOSMO_WORKSPACES_HOST_PATH = "/opt/kosmo/test/workspaces";

const { buildJobConfig, secretExecArgs, validId, validModel, validContainerId, ownedJobId,
  workspaceReadError } = require("./launcher");

test("job mounts one project and never exposes provider key in Docker metadata", () => {
  const config = buildJobConfig(
    { project_id: "prj_123", provider: "deepseek", model: "deepseek-flash", api_key: "sk-sensitive" },
    "one-time-password",
  );
  assert.equal(config.HostConfig.Memory, 1073741824);
  assert.equal(config.HostConfig.NanoCpus, 1500000000);
  assert.equal(config.HostConfig.ReadonlyRootfs, true);
  assert.deepEqual(config.HostConfig.Binds, [
    "/opt/kosmo/test/workspaces/prj_123:/workspaces/prj_123:rw",
    "/opt/kosmo/test/workspaces/prj_123/opencode.json:/workspaces/prj_123/opencode.json:ro",
  ]);
  assert.ok(config.Env.includes("OPENCODE_MODEL=deepseek/deepseek-flash"));
  assert.ok(!JSON.stringify(config).includes("sk-sensitive"));
  assert.ok(!config.Env.some((value) => value.startsWith("DEEPSEEK_API_KEY=")));
  assert.ok(config.HostConfig.Tmpfs["/run/kosmo-secrets"].includes("size=1m"));
});

test("secret injection uses stdin and mode 0600, never Docker metadata or arguments", () => {
  const id = "a".repeat(64);
  const args = secretExecArgs(id, "provider-key");
  assert.deepEqual(args.slice(0, 5), ["exec", "-i", "--user", "1000:1000", id]);
  assert.match(args.at(-1), /umask 077; cat > \/run\/kosmo-secrets\/provider-key/);
  assert.ok(!JSON.stringify(args).includes("sk-sensitive"));
  assert.throws(() => secretExecArgs(id, "../escape"), /Invalid secret filename/);
  assert.throws(() => secretExecArgs("../escape", "ready"), /Invalid Docker container ID/);
});

test("only safe project and model identifiers are accepted", () => {
  assert.equal(validId("prj_123"), true);
  assert.equal(validId("../secrets"), false);
  assert.equal(validModel("deepseek-flash"), true);
  assert.equal(validModel("model;cat /etc/passwd"), false);
});

test("only an owned canonical Docker ID can reach Docker job routes", () => {
  const id = "a".repeat(64);
  const jobs = [{ Id: id }];
  assert.equal(validContainerId(id), true);
  assert.equal(validContainerId("../etc/passwd"), false);
  assert.equal(ownedJobId(jobs, id), id);
  assert.equal(ownedJobId(jobs, "b".repeat(64)), null);
  assert.equal(ownedJobId([{ Id: "../etc/passwd" }], "../etc/passwd"), null);
});

test("workspace permission failures are not misreported as missing projects", () => {
  const denied = workspaceReadError(Object.assign(new Error("permission denied"), { code: "EACCES" }),
    "Workspace de proyecto no encontrado");
  assert.equal(denied.status, 503);
  assert.match(denied.message, /no tiene permisos/);

  const missing = workspaceReadError(Object.assign(new Error("not found"), { code: "ENOENT" }),
    "Workspace de proyecto no encontrado");
  assert.equal(missing.status, 422);
  assert.equal(missing.message, "Workspace de proyecto no encontrado");
});
