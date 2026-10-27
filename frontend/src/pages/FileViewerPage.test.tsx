import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MCPToolError } from "@/lib/errors";
import { api } from "@/services/api";
import { FileViewerPage } from "./FileViewerPage";

function numbered(from: number, lines: string[]) {
  return lines.map((text, i) => `${String(from + i).padStart(4)}| ${text}`).join("\n");
}

function renderViewer(url: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/repository/:id/file" element={<FileViewerPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("FileViewerPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the window around the target, highlights it and lists the file's definitions", async () => {
    const getFile = vi.spyOn(api, "getFile").mockResolvedValue({
      repository: "octo/demo",
      path: "src/a.py",
      language: "python",
      total_lines: 900,
      start_line: 30,
      end_line: 429,
      truncated: true,
      content: numbered(30, ["", "def f():", "    return 1"]),
    });
    vi.spyOn(api, "listDefinitions").mockResolvedValue({
      repository: "octo/demo",
      total: 2,
      definitions: [
        { entity_type: "function", entity_name: "f", file_path: "src/a.py", line_start: 31, line_end: 32, signature: null, description: null },
        { entity_type: "function", entity_name: "other", file_path: "src/a.py.bak", line_start: 1, line_end: 2, signature: null, description: null },
      ],
    });

    renderViewer("/repository/2/file?path=src%2Fa.py&line=31&end=32");

    expect(await screen.findByText("def f():")).toBeInTheDocument();
    // 20 lines of context above the target (clamped to line 1 here: 31 - 20 = 11), 400 per window
    expect(getFile).toHaveBeenCalledWith(2, "src/a.py", 11, 410);
    expect(screen.getByText("python · lines 30–429 of 900")).toBeInTheDocument();
    expect(document.getElementById("L31")).toHaveClass("bg-yellow-100");
    expect(document.getElementById("L30")).not.toHaveClass("bg-yellow-100");
    // Only this exact file's definitions, not a path that merely starts with it
    expect(await screen.findByRole("link", { name: "f" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "other" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Next 400 lines/ }));
    expect(getFile).toHaveBeenLastCalledWith(2, "src/a.py", 430, 829);
  });

  it("shows the server's message for a missing file", async () => {
    vi.spyOn(api, "getFile").mockRejectedValue(
      new MCPToolError("get_file", "File 'src/b.py' not found in octo/demo. Close paths: src/a.py")
    );
    vi.spyOn(api, "listDefinitions").mockResolvedValue({ repository: "octo/demo", total: 0, definitions: [] });

    renderViewer("/repository/2/file?path=src%2Fb.py");

    expect(await screen.findByRole("alert")).toHaveTextContent("Close paths: src/a.py");
  });
});
