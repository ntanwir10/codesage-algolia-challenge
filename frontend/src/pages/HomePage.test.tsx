import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "@/components/ui/toast";
import { api } from "@/services/api";
import type { Repository } from "@/types/repository";
import { HomePage } from "./HomePage";

const addToast = vi.fn();
vi.mock("@/components/ui/toast", async (orig) => ({
  ...(await orig<typeof import("@/components/ui/toast")>()),
  useToast: () => ({ addToast }),
}));

function renderHome() {
  const client = new QueryClient();
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/repository/:id" element={<div>repo page</div>} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
  return client;
}

async function submitUrl() {
  await userEvent.type(
    screen.getByLabelText(/github repository url/i),
    "https://github.com/owner/repo"
  );
  const submit = screen.getByRole("button", { name: /add repository/i });
  await waitFor(() => expect(submit).toBeEnabled());
  await userEvent.click(submit);
}

describe("HomePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    addToast.mockClear();
  });

  it("invalidates the repositories query and navigates on 201", async () => {
    vi.spyOn(api, "createRepository").mockResolvedValue({ id: 7 } as Repository);
    const client = renderHome();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await submitUrl();
    expect(await screen.findByText("repo page")).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["repositories"] });
    expect(addToast).toHaveBeenCalledWith(expect.objectContaining({ type: "success" }));
  });

  it("shows a create failure inline with no redirect and no toast", async () => {
    const msg = "Repository owner/repo was not found, or it is private.";
    vi.spyOn(api, "createRepository").mockRejectedValue(
      new AxiosError("bad", "ERR_BAD_REQUEST", undefined, undefined, {
        status: 422,
        data: { detail: msg },
      } as never)
    );
    renderHome();
    await submitUrl();
    expect(await screen.findByRole("alert")).toHaveTextContent(msg);
    expect(screen.queryByText("repo page")).not.toBeInTheDocument();
    expect(addToast).not.toHaveBeenCalled();
    expect(screen.getByLabelText(/github repository url/i)).toHaveValue(
      "https://github.com/owner/repo"
    );
  });
});
