import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider, useToast } from "./toast";

function Trigger({ duration }: { duration?: number }) {
  const { addToast } = useToast();
  return (
    <button onClick={() => addToast({ type: "info", title: "Hello", duration })}>
      add
    </button>
  );
}

describe("toast", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("auto-dismisses after the duration", () => {
    render(
      <ToastProvider>
        <Trigger duration={1000} />
      </ToastProvider>
    );
    act(() => screen.getByText("add").click());
    expect(screen.getByText("Hello")).toBeInTheDocument();
    act(() => void vi.advanceTimersByTime(1001));
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
  });

  it("clears pending timers on unmount", () => {
    const { unmount } = render(
      <ToastProvider>
        <Trigger duration={1000} />
      </ToastProvider>
    );
    act(() => screen.getByText("add").click());
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("clears the timer when a toast is dismissed manually", () => {
    render(
      <ToastProvider>
        <Trigger duration={5000} />
      </ToastProvider>
    );
    act(() => screen.getByText("add").click());
    act(() => screen.getByLabelText("Dismiss notification").click());
    act(() => void vi.advanceTimersByTime(250));
    expect(screen.queryByText("Hello")).not.toBeInTheDocument();
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe("toast accessibility", () => {
  it("renders a labelled live region and alerts for errors", () => {
    function Errors() {
      const { addToast } = useToast();
      return (
        <button onClick={() => addToast({ type: "error", title: "Boom" })}>
          add
        </button>
      );
    }
    render(
      <ToastProvider>
        <Errors />
      </ToastProvider>
    );
    const region = screen.getByRole("region", { name: "Notifications" });
    expect(region).toHaveAttribute("aria-live", "polite");
    act(() => screen.getByText("add").click());
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
  });
});
