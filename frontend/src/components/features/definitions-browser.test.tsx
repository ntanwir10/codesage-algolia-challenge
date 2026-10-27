import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/services/api";
import { DefinitionsBrowser } from "./definitions-browser";

describe("DefinitionsBrowser", () => {
  afterEach(() => vi.restoreAllMocks());

  it("filters by name and kind, and links each definition to the viewer", async () => {
    const list = vi.spyOn(api, "listDefinitions").mockResolvedValue({
      repository: "octo/demo",
      total: 250,
      definitions: [
        { entity_type: "class", entity_name: "Store", file_path: "src/store.ts", line_start: 4, line_end: 20, signature: null, description: null },
      ],
    });
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <DefinitionsBrowser repositoryId={2} />
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(await screen.findByRole("link", { name: "Store" })).toHaveAttribute(
      "href",
      "/repository/2/file?path=src%2Fstore.ts&line=4&end=20"
    );
    expect(screen.getByText("Showing 1 of 250 definitions")).toBeInTheDocument();

    await userEvent.type(screen.getByRole("textbox", { name: "Filter definitions by name" }), "sto");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Kind of definition" }), "class");
    // Typing is debounced into one request (tool calls are rate limited)
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(2, { name: "sto", entity_type: "class", limit: 100 })
    );
    expect(list.mock.calls.filter(([, f]) => f?.name === "s" || f?.name === "st")).toHaveLength(0);
  });
});
