import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AnimatedProgress } from "./animated-progress";

describe("AnimatedProgress", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reaches the final value", () => {
    render(<AnimatedProgress value={80} />);
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.getByText("80%")).toBeInTheDocument();
  });

  it("animates from the previous value to a new target", () => {
    const { rerender } = render(<AnimatedProgress value={20} />);
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.getByText("20%")).toBeInTheDocument();
    rerender(<AnimatedProgress value={60} />);
    act(() => void vi.advanceTimersByTime(400));
    const mid = parseInt(screen.getByText(/%$/, { selector: "span.text-muted-foreground" }).textContent!);
    expect(mid).toBeGreaterThan(20);
    expect(mid).toBeLessThan(60);
    act(() => void vi.advanceTimersByTime(1000));
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("clears its interval on unmount", () => {
    const { unmount } = render(<AnimatedProgress value={50} />);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
