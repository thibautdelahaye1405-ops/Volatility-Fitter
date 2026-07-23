// P6 V3 locks: the Dynamics policy card seeds from draft-else-active policy,
// stages edits through PUT /graph/config/messages/policy, and maps the
// semantics-defaults selects to a minimal override map (auto = absent).
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DynamicsPolicyCard from "./DynamicsPolicyCard";
import type { DynamicPolicy, MessageConfigPair } from "../../state/useMessageConfig";

const putPolicy = vi.fn((_p: DynamicPolicy) =>
  Promise.resolve({ draft: null, active: null } as MessageConfigPair),
);
vi.mock("../../state/useMessageConfig", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../state/useMessageConfig")>()),
  putMessagePolicy: (p: DynamicPolicy) => putPolicy(p),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const pair = (policy: DynamicPolicy | null): MessageConfigPair => ({
  draft: {
    name: "default", version: 2, createdAt: "", author: "desk",
    parentVersion: 1, notes: "", rows: [], policy,
  },
  active: null,
});

describe("DynamicsPolicyCard", () => {
  it("seeds from the staged policy and stages edits via PUT", async () => {
    const onSaved = vi.fn();
    render(
      <DynamicsPolicyCard
        config={pair({
          clampMaxAgeDays: 2.5,
          residualHalfLifeDays: 5,
          semanticsDefaults: { custom: "directed_state" },
        })}
        onSaved={onSaved}
      />,
    );
    const clamp = screen.getByTitle(/Clamp freshness window/)
      .querySelector("input") as HTMLInputElement;
    expect(clamp.value).toBe("2.5");
    fireEvent.change(clamp, { target: { value: "3" } });
    fireEvent.click(screen.getByText("Save draft policy"));
    await waitFor(() => expect(putPolicy).toHaveBeenCalled());
    expect(putPolicy.mock.lastCall?.[0]).toEqual({
      clampMaxAgeDays: 3,
      residualHalfLifeDays: 5,
      semanticsDefaults: { custom: "directed_state" },
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it("defaults with no policy; empty half-life = never; auto clears an override", async () => {
    render(<DynamicsPolicyCard config={pair(null)} />);
    const half = screen.getByTitle(/Residual half-life/)
      .querySelector("input") as HTMLInputElement;
    expect(half.value).toBe(""); // null = never (random walk)
    fireEvent.change(half, { target: { value: "7" } });
    // Semantics defaults: set broad_index to reciprocal, then back to auto.
    fireEvent.click(screen.getByText(/Semantics defaults/));
    const sel = screen.getByTitle(/Default semantics for broad_index/) as HTMLSelectElement;
    expect(sel.value).toBe("auto");
    fireEvent.change(sel, { target: { value: "reciprocal_harmonic" } });
    fireEvent.click(screen.getByText("Save draft policy"));
    await waitFor(() => expect(putPolicy).toHaveBeenCalled());
    expect(putPolicy.mock.lastCall?.[0]).toEqual({
      clampMaxAgeDays: 1,
      residualHalfLifeDays: 7,
      semanticsDefaults: { broad_index: "reciprocal_harmonic" },
    });
    // Back to auto removes the key entirely (minimal override map).
    fireEvent.change(sel, { target: { value: "auto" } });
    fireEvent.click(screen.getByText("Save draft policy"));
    await waitFor(() => expect(putPolicy).toHaveBeenCalledTimes(2));
    expect(putPolicy.mock.lastCall?.[0].semanticsDefaults).toEqual({});
  });
});
