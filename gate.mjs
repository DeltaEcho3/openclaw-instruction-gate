// Instruction enforcement gate for OpenClaw's before_tool_call hook.
//
// Default deny: any tool not on READ_ONLY must carry a pinned instruction reference
// (INSTR:NAME@N) somewhere in its parameters, and that reference must resolve
// through resolve.py against a manifest-verified registry at
// INSTRUCTION_REGISTRY_ROOT. Unknown tools are gated, never waved through. If
// INSTRUCTION_REGISTRY_ROOT is not set, every gated call is blocked (fail closed).
import { execFile } from "node:child_process";
import { appendFileSync } from "node:fs";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export const READ_ONLY = new Set(["read", "session_status", "agents_list", "memory_search", "memory_get"]);

const REF_ANY = /INSTR:([A-Za-z0-9_.-]+)(@[^\s"'`\\,;)]*)?/;
const PINNED = /^[A-Z][A-Z0-9_]*(\.[A-Z0-9_]+)+@[1-9][0-9]*$/;

export function settings(env = process.env) {
  return {
    root: env.INSTRUCTION_REGISTRY_ROOT || null,
    log: env.INSTRUCTION_GATE_LOG || null, // JSONL decision log; off when unset
    // Test-only failure modes, to prove the host fails closed on a slow or
    // crashing hook: "slow" (sleeps 60 s) and "throw". Leave unset in real use.
    mode: env.INSTRUCTION_GATE_MODE || "normal",
  };
}

function logDecision(cfg, entry) {
  if (!cfg.log) return;
  try {
    appendFileSync(cfg.log, JSON.stringify({ at: new Date().toISOString(), ...entry }) + "\n");
  } catch {
    // Logging must never itself block or crash the gate.
  }
}

async function resolveRef(cfg, ref) {
  if (!cfg.root) return { ok: false, detail: "INSTRUCTION_REGISTRY_ROOT is not set; failing closed" };
  try {
    const { stdout } = await execFileAsync(
      "python3",
      [`${cfg.root}/tools/resolve.py`, ref, "--root", cfg.root],
      { timeout: 15000 },
    );
    return { ok: true, detail: stdout.trim().slice(0, 160) };
  } catch (err) {
    // The resolver prints REJECTED: ... on stdout; keep its own words.
    const detail =
      [err?.stdout, err?.stderr, err?.message].map((v) => (v ? String(v).trim() : "")).find(Boolean) ||
      "resolver failed with no diagnostic output";
    return { ok: false, detail: detail.slice(0, 400) };
  }
}

export function extractRef(params) {
  let text;
  try {
    text = JSON.stringify(params ?? {});
  } catch {
    text = String(params);
  }
  const m = REF_ANY.exec(text);
  if (!m) return { present: false };
  return { present: true, ref: m[1] + (m[2] || "") };
}

/** Returns undefined to allow, or { block: true, blockReason } to block. */
export async function decide(event, ctx, cfg = settings()) {
  if (cfg.mode === "slow") await new Promise((r) => setTimeout(r, 60000));
  if (cfg.mode === "throw") throw new Error("instruction-gate test mode: handler threw on purpose");

  const tool = String(event?.toolName ?? "");
  const kind = event?.toolKind ?? ctx?.toolKind ?? null;
  const base = { agent: ctx?.agentId ?? null, session: ctx?.sessionKey ?? null, tool, kind };

  if (READ_ONLY.has(tool) && kind !== "code_mode_exec") {
    logDecision(cfg, { ...base, decision: "ALLOW", ref: null, reason: "read-only tool" });
    return undefined;
  }
  const found = extractRef(event?.params);
  if (!found.present) {
    const reason = `'${tool}' requires a version-pinned instruction reference (INSTR:NAME@N) and none was given`;
    logDecision(cfg, { ...base, decision: "BLOCK", ref: null, reason });
    return { block: true, blockReason: `Instruction gate: ${reason}` };
  }
  if (!PINNED.test(found.ref)) {
    const reason = `instruction reference '${found.ref}' is not version-pinned (expected NAME@N); unpinned references fail closed`;
    logDecision(cfg, { ...base, decision: "BLOCK", ref: found.ref, reason });
    return { block: true, blockReason: `Instruction gate: ${reason}` };
  }
  const res = await resolveRef(cfg, found.ref);
  if (!res.ok) {
    logDecision(cfg, { ...base, decision: "BLOCK", ref: found.ref, reason: res.detail });
    return { block: true, blockReason: `Instruction gate: ${res.detail}` };
  }
  logDecision(cfg, { ...base, decision: "ALLOW", ref: found.ref, reason: "resolved, manifest verified" });
  return undefined;
}
