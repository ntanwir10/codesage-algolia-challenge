import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import { api } from "@/services/api";
import type { Repository } from "@/types/repository";
import { HomePage } from "./HomePage";

describe("HomePage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("invalidates the repositories query after a repository is created", async () => {
    vi.spyOn(api, "createRepository").mockResolvedValue({ id: 7 } as Repository);
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter>
            <HomePage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>
    );
    await userEvent.type(
      screen.getByLabelText(/github repository url/i),
      "https://github.com/owner/repo"
    );
    const submit = screen.getByRole("button", { name: /add repository/i });
    await waitFor(() => expect(submit).toBeEnabled());
    await userEvent.click(submit);
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({ queryKey: ["repositories"] })
    );
  });
});
