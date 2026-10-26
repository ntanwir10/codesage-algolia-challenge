import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";
import { AppRoutes } from "@/App";

describe("ErrorBoundary", () => {
  afterEach(() => vi.restoreAllMocks());

  it("renders the fallback when a child crashes", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    function Bomb(): never {
      throw new Error("boom");
    }
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>
      </MemoryRouter>
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Reload page")).toBeInTheDocument();
  });

  it("shows Page not found for unknown routes", () => {
    render(
      <MemoryRouter initialEntries={["/repositories/4"]}>
        <AppRoutes />
      </MemoryRouter>
    );
    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go home" })).toHaveAttribute("href", "/");
  });
});
