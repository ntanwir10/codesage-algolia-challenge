import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/services/api";
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
