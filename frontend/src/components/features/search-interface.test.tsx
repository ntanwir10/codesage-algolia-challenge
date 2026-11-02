import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/services/api";
import { MCPToolError } from "@/lib/errors";
import type { SearchHit } from "@/types/mcp";
import { SearchInterface } from "./search-interface";

const queryInput = () => screen.getByRole("combobox", { name: /search query/i });

// Results link into the file viewer, so they need a router
const renderSearch = (ui: React.ReactElement) => render(ui, { wrapper: MemoryRouter });

function mockApi(semantic = false) {
  vi.spyOn(api, "getCapabilities").mockResolvedValue({ semantic_search: semantic });
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
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "deb");
    expect(await screen.findByRole("listbox")).toBeInTheDocument();
  });

  it("stays closed when Enter is pressed before the debounce fires", async () => {
    const suggestions = mockApi();
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "deb{enter}");

    // The pending timer still fires; its response must not reopen the dropdown
    await waitFor(() => expect(suggestions).toHaveBeenCalled());
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});

describe("SearchInterface suggestions from the keyboard", () => {
  afterEach(() => vi.restoreAllMocks());

  it("moves with the arrows, searches the pick on Enter and closes on Escape", async () => {
    mockApi();
    vi.mocked(api.getSearchSuggestions).mockResolvedValue(["debounce", "debug"]);
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "deb");
    await screen.findByRole("listbox");

    await userEvent.keyboard("{ArrowDown}{ArrowDown}");
    const [first, second] = screen.getAllByRole("option");
    expect(second).toHaveAttribute("aria-selected", "true");
    expect(first).toHaveAttribute("aria-selected", "false");
    expect(queryInput()).toHaveAttribute("aria-activedescendant", second.id);

    await userEvent.keyboard("{ArrowDown}"); // wraps to the first
    expect(first).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    await userEvent.type(queryInput(), "u");
    await screen.findByRole("listbox");
    await userEvent.keyboard("{ArrowUp}{Enter}"); // up from nothing: the last one
    expect(queryInput()).toHaveValue("debug");
    await waitFor(() =>
      expect(api.searchCode).toHaveBeenCalledWith(expect.objectContaining({ query: "debug" }))
    );
  });
});

describe("SearchInterface states", () => {
  afterEach(() => vi.restoreAllMocks());

  it("explains a failed repository", () => {
    mockApi();
    renderSearch(<SearchInterface repositoryId={2} canSearch={false} status="failed" />);
    expect(screen.getByText(/Indexing failed, so search isn't available/)).toBeInTheDocument();
  });

  it("disables Search for an empty query", async () => {
    mockApi();
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    const button = screen.getByRole("button", { name: "Search" });
    expect(button).toBeDisabled();
    await userEvent.type(queryInput(), "  ");
    expect(button).toBeDisabled();
    await userEvent.type(queryInput(), "x");
    expect(button).toBeEnabled();
  });

  it("searches every repository without one, linking each hit to its own", async () => {
    mockApi();
    const search = vi.spyOn(api, "searchCode").mockResolvedValue({
      query: "store",
      repository: null,
      total_hits: 1,
      page: 0,
      pages: 1,
      results: [
        { repository_id: 7, repository: "octo/other", entity_name: "createStore", entity_type: "function",
          file_path: "src/a.ts", line_start: 3, line_end: 9 } as SearchHit,
      ],
    });
    renderSearch(<SearchInterface canSearch />);
    await userEvent.type(queryInput(), "store{enter}");

    const link = await screen.findByRole("link", { name: "createStore" });
    expect(link).toHaveAttribute("href", "/repository/7/file?path=src%2Fa.ts&line=3&end=9");
    expect(link.querySelector("mark")).toHaveTextContent("Store");
    expect(screen.getByText("📦 octo/other")).toBeInTheDocument();
    expect(search.mock.calls[0][0]).not.toHaveProperty("repository", expect.anything());
  });

  it("re-runs the search when a filter changes, and links hits to the viewer", async () => {
    mockApi();
    const hit = { entity_name: "foo", file_path: "src/a.py", line_start: 3, line_end: 9 } as SearchHit;
    const search = vi.spyOn(api, "searchCode").mockResolvedValue({
      query: "foo",
      repository: "2",
      total_hits: 1,
      page: 0,
      pages: 1,
      results: [hit],
    });
    renderSearch(<SearchInterface repositoryId={2} canSearch languages={["python", "typescript"]} />);
    await userEvent.type(queryInput(), "foo{enter}");

    expect(await screen.findByRole("link", { name: "foo" })).toHaveAttribute(
      "href",
      "/repository/2/file?path=src%2Fa.py&line=3&end=9"
    );
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter by language" }), "python");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Filter by kind" }), "class");
    await waitFor(() =>
      expect(search).toHaveBeenLastCalledWith(
        expect.objectContaining({ query: "foo", language: "python", entity_type: "class", page: 0 })
      )
    );
  });

  it("runs the search named in the URL, and puts a new one there", async () => {
    mockApi();
    const search = vi.spyOn(api, "searchCode").mockResolvedValue({
      query: "store",
      repository: "2",
      total_hits: 0,
      page: 0,
      pages: 0,
      results: [],
    });
    let location = "";
    function Where() {
      location = useLocation().search;
      return null;
    }
    render(
      <MemoryRouter initialEntries={["/repository/2?q=store"]}>
        <SearchInterface repositoryId={2} canSearch />
        <Where />
      </MemoryRouter>
    );

    await waitFor(() => expect(search).toHaveBeenCalledWith(expect.objectContaining({ query: "store" })));
    expect(queryInput()).toHaveValue("store");

    await userEvent.clear(queryInput());
    await userEvent.type(queryInput(), "create{enter}");
    await waitFor(() => expect(location).toBe("?q=create"));
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
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "foo{enter}");
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect(await screen.findByText("Still indexing")).toBeInTheDocument();
    expect(screen.getByText("foo")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
  });
});

describe("SearchInterface search by meaning", () => {
  afterEach(() => vi.restoreAllMocks());

  const modeSelect = () => screen.queryByRole("combobox", { name: "Search mode" });

  it("offers no mode switch when the server has no embeddings key", async () => {
    mockApi(false);
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await waitFor(() => expect(api.getCapabilities).toHaveBeenCalled());
    expect(modeSelect()).not.toBeInTheDocument();
  });

  it("searches and suggests by meaning, and shows each hit's similarity", async () => {
    const suggestions = mockApi(true);
    const hit = { entity_name: "createStore", file_path: "src/vanilla.ts", line_start: 60, line_end: 97, score: 0.7134 } as SearchHit;
    const search = vi.spyOn(api, "searchCode").mockResolvedValue({
      query: "make a store",
      repository: "2",
      mode: "semantic",
      total_hits: 1012,
      page: 0,
      pages: 102,
      results: [hit],
    });
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Search mode" }), "semantic");
    await userEvent.type(queryInput(), "make a store");
    await waitFor(() =>
      expect(suggestions).toHaveBeenCalledWith("make a store", expect.objectContaining({ mode: "semantic" }))
    );
    await userEvent.type(queryInput(), "{enter}");

    await waitFor(() => expect(search).toHaveBeenCalledWith(expect.objectContaining({ mode: "semantic" })));
    expect(await screen.findByText(/Ranked by meaning for/)).toBeInTheDocument();
    expect(screen.queryByText(/Found 1,012/)).not.toBeInTheDocument();
    expect(screen.getByText("similarity 0.71")).toBeInTheDocument();
  });

  it("keeps the mode in the URL, so a reload or Back reruns the same ranking", async () => {
    mockApi(true);
    const search = vi.spyOn(api, "searchCode").mockResolvedValue({
      query: "store",
      repository: "2",
      mode: "semantic",
      total_hits: 0,
      page: 0,
      pages: 0,
      results: [],
    });
    let location = "";
    function Where() {
      location = useLocation().search;
      return null;
    }
    render(
      <MemoryRouter initialEntries={["/repository/2?q=store&mode=semantic"]}>
        <SearchInterface repositoryId={2} canSearch />
        <Where />
      </MemoryRouter>
    );
    await waitFor(() => expect(search).toHaveBeenCalledWith(expect.objectContaining({ query: "store", mode: "semantic" })));
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Search mode" }), "keyword");
    await waitFor(() => expect(location).toBe("?q=store"));
  });

  it("shows no similarity on keyword hits", async () => {
    mockApi(true);
    const hit = { entity_name: "foo", file_path: "a.py", line_start: 1, line_end: 2 } as SearchHit;
    vi.spyOn(api, "searchCode").mockResolvedValue({
      query: "foo",
      repository: "2",
      total_hits: 1,
      page: 0,
      pages: 1,
      results: [hit],
    });
    renderSearch(<SearchInterface repositoryId={2} canSearch />);
    await userEvent.type(queryInput(), "foo{enter}");
    expect(await screen.findByText(/Found 1 result/)).toBeInTheDocument();
    expect(screen.queryByText(/similarity/)).not.toBeInTheDocument();
  });
});
