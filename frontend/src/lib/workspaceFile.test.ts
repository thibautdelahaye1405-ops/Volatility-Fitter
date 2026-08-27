// Workspace-file bundle helpers (UI SHELL v2 wave 3, A1): envelope validation,
// canonical hashing, filenames and the recent list.
import { describe, expect, it } from "vitest";
import {
  WORKSPACE_SCHEMA,
  buildWorkspaceBundle,
  canonicalJson,
  hashShell,
  hashString,
  parseWorkspaceBundle,
  pushRecent,
  restoreRecent,
  workspaceFilename,
  workspaceNameOf,
} from "./workspaceFile";

const backend = { v: 1, universe: { tickers: ["SPY"] } };

describe("parseWorkspaceBundle", () => {
  it("accepts a well-formed bundle and normalises optional fields", () => {
    const r = parseWorkspaceBundle({ schema: WORKSPACE_SCHEMA, backend, shell: { activity: "graph" } });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.bundle.schema).toBe(WORKSPACE_SCHEMA);
    expect(r.bundle.backend).toBe(backend);
    expect(r.bundle.shell).toEqual({ activity: "graph" });
    expect(r.bundle.savedAt).toBe("");
    expect(r.bundle.app.version).toBe("");
  });

  it("treats a non-object shell as absent", () => {
    const r = parseWorkspaceBundle({ schema: WORKSPACE_SCHEMA, backend, shell: "x" });
    expect(r.ok && r.bundle.shell).toBeNull();
  });

  it.each([
    [null, "not a JSON object"],
    [[1], "not a JSON object"],
    [{ backend }, 'missing "schema"'],
    [{ schema: "volfit-snapshot/1", backend }, "not a workspace file"],
    [{ schema: "volfit-workspace/2", backend }, "unsupported workspace schema"],
    [{ schema: WORKSPACE_SCHEMA }, "no backend document"],
    [{ schema: WORKSPACE_SCHEMA, backend: { universe: {} } }, "no version"],
  ])("refuses %j with a diagnostic", (raw, needle) => {
    const r = parseWorkspaceBundle(raw);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain(needle);
  });
});

describe("buildWorkspaceBundle", () => {
  it("stamps savedAt to the second and carries the server's schema + version", () => {
    const b = buildWorkspaceBundle(
      { schema: WORKSPACE_SCHEMA, app: { version: "0.1.0" }, backend },
      { activity: "parametric" },
      new Date("2026-08-27T14:30:05.123Z"),
    );
    expect(b.savedAt).toBe("2026-08-27T14:30:05Z");
    expect(b.app.version).toBe("0.1.0");
    expect(b.shell).toEqual({ activity: "parametric" });
    // Round-trips through the validator.
    expect(parseWorkspaceBundle(JSON.parse(JSON.stringify(b))).ok).toBe(true);
  });
});

describe("hashing", () => {
  it("is stable, key-order independent and sensitive to content", () => {
    expect(hashString("abc")).toBe(hashString("abc"));
    expect(hashString("abc")).not.toBe(hashString("abd"));
    expect(hashString("")).toHaveLength(8);
    expect(canonicalJson({ b: 1, a: [{ d: 2, c: 3 }] })).toBe('{"a":[{"c":3,"d":2}],"b":1}');
    expect(hashShell({ activity: "graph", expiryFormat: "dmy" })).toBe(
      hashShell({ expiryFormat: "dmy", activity: "graph" }),
    );
    expect(hashShell({ activity: "graph" })).not.toBe(hashShell({ activity: "quality" }));
  });
});

describe("filenames", () => {
  it("slugs the name and falls back to a dated default", () => {
    expect(workspaceFilename("My desk (SPY)")).toBe("my-desk-spy.volfit.json");
    expect(workspaceFilename("   ", new Date("2026-08-27T10:00:00Z"))).toBe("workspace-2026-08-27.volfit.json");
    expect(workspaceNameOf("desk-a.volfit.json")).toBe("desk-a");
    expect(workspaceNameOf("desk-a.JSON")).toBe("desk-a");
  });
});

describe("recent list", () => {
  it("moves duplicates to the head and caps the length", () => {
    let list = pushRecent([], { kind: "file", name: "a", at: 1 });
    list = pushRecent(list, { kind: "server", name: "b", at: 2 });
    list = pushRecent(list, { kind: "file", name: "a", at: 3 });
    expect(list.map((e) => `${e.kind}:${e.name}`)).toEqual(["file:a", "server:b"]);
    expect(list[0].at).toBe(3);
    for (let i = 0; i < 20; i++) list = pushRecent(list, { kind: "file", name: `n${i}`, at: i });
    expect(list).toHaveLength(8);
    expect(list[0].name).toBe("n19");
  });

  it("restores only well-formed rows", () => {
    expect(
      restoreRecent([{ kind: "file", name: "x", at: 5 }, { kind: "nope", name: "y" }, { kind: "server", name: "" }, 3]),
    ).toEqual([{ kind: "file", name: "x", at: 5 }]);
    expect(restoreRecent("junk")).toEqual([]);
  });
});
