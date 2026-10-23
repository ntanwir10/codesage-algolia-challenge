import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AxiosError } from "axios";
import { GitHubForm } from "./github-form";

const submitBtn = () => screen.getByRole("button", { name: /add repository/i });
const urlInput = () => screen.getByLabelText(/github repository url/i);

describe("GitHubForm", () => {
  it("disables submit when empty", () => {
    render(<GitHubForm onSubmit={vi.fn()} />);
    expect(submitBtn()).toBeDisabled();
  });

  it("rejects a non-GitHub URL with an error", async () => {
    const onSubmit = vi.fn();
    render(<GitHubForm onSubmit={onSubmit} />);
    await userEvent.type(urlInput(), "https://example.com/foo/bar");
    expect(await screen.findByText(/valid github repository url/i)).toBeInTheDocument();
    expect(submitBtn()).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits a valid URL and resets on success", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<GitHubForm onSubmit={onSubmit} />);
    await userEvent.type(urlInput(), "https://github.com/owner/repo");
    await waitFor(() => expect(submitBtn()).toBeEnabled());
    await userEvent.click(submitBtn());
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      url: "https://github.com/owner/repo",
      branch: "",
    });
    await waitFor(() => expect(urlInput()).toHaveValue(""));
  });

  it("keeps input when onSubmit rejects", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("boom"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<GitHubForm onSubmit={onSubmit} />);
    await userEvent.type(urlInput(), "https://github.com/owner/repo");
    await waitFor(() => expect(submitBtn()).toBeEnabled());
    await userEvent.click(submitBtn());
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(urlInput()).toHaveValue("https://github.com/owner/repo");
  });

  it("shows 422 detail messages", async () => {
    const err = new AxiosError("bad", "ERR_BAD_REQUEST", undefined, undefined, {
      status: 422,
      data: { detail: [{ msg: "repo not found" }, { msg: "bad branch" }] },
    } as never);
    const onSubmit = vi.fn().mockRejectedValue(err);
    render(<GitHubForm onSubmit={onSubmit} />);
    await userEvent.type(urlInput(), "https://github.com/owner/repo");
    await waitFor(() => expect(submitBtn()).toBeEnabled());
    await userEvent.click(submitBtn());
    expect(await screen.findByRole("alert")).toHaveTextContent("repo not found; bad branch");
    expect(urlInput()).toHaveValue("https://github.com/owner/repo");
  });
});
