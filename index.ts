import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";
// @ts-ignore plain ESM module shared with the Part A tests
import { decide, settings } from "./gate.mjs";

export default definePluginEntry({
  id: "instruction-gate",
  name: "Instruction gate",
  description: "Blocks any non-read-only tool call that lacks a resolvable, pinned instruction reference.",
  register(api) {
    const cfg = settings();
    api.on("before_tool_call", (event, ctx) => decide(event, ctx, cfg), {
      priority: 1000,
      timeoutMs: 20000,
    });
  },
});
