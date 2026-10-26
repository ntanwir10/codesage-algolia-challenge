import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/services/api";
import { MCPToolError } from "@/lib/errors";
import type { SearchHit } from "@/types/mcp";
import { SearchInterface } from "./search-interface";

const queryInput = () => screen.getByRole("combobox", { name: /search query/i });

function mockApi() {
  const suggestions = vi
    .spyOn(api, "getSearchSuggestions")
    .mockResolvedValue(["debounce"]);
  vi.spyOn(api, "searchCode").mockResolvedValue({
    query: "deb",
    repository: "lodash",
    total_hits: 0,
    page: 0,
    pages: 0,
    results: [],
  });
  return suggestions;
}

describe("SearchInterface suggestions", () => {
  afterEach(() => vi.restoreAllMocks());

  it("opens after the debounce", async () => {
    mockApi();
    render(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "deb");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
  });

  it("stays closed when Enter is pressed before the debounce fires", async () => {
    const suggestions = mockApi();
    render(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "deb{enter}");

    // The pending timer still fires; its response must not reopen the dropdown
    await waitFor(() => expect(suggestions).toHaveBeenCalled());
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});

describe("SearchInterface states", () => {
  afterEach(() => vi.restoreAllMocks());

  it("explains a failed repository", () => {
    mockApi();
    render(<SearchInterface repositoryId={2} canSearch={false} status="failed" />);
    expect(screen.getByText(/Indexing failed, so search isn't available/)).toBeInTheDocument();
  });

  it("disables Search for an empty query", async () => {
    mockApi();
    render(<SearchInterface repositoryId={2} canSearch />);
    const button = screen.getByRole("button", { name: "Search" });
    expect(button).toBeDisabled();
    await userEvent.type(queryInput(), "  ");
    expect(button).toBeDisabled();
    await userEvent.type(queryInput(), "x");
    expect(button).toBeEnabled();
  });

  it("keeps results and pager when a page change fails", async () => {
    mockApi();
    const hit = {
      entity_name: "foo",
      file_path: "a.py",
      line_start: 1,
      line_end: 2,
    } as SearchHit;
    const search = vi.spyOn(api, "searchCode");
    search.mockResolvedValueOnce({
      query: "foo",
      repository: "2",
      total_hits: 20,
      page: 0,
      pages: 2,
      results: [hit],
    });
    search.mockRejectedValueOnce(new MCPToolError("search_code", "Still indexing"));
    render(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "foo{enter}");
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect(await screen.findByText("Still indexing")).toBeInTheDocument();
    expect(screen.getByText("foo")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  });
});
