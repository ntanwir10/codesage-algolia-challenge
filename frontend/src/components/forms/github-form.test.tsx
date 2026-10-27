import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AxiosError } from "axios";
import { MemoryRouter } from "react-router-dom";
import { GitHubForm } from "./github-form";

const renderForm = (onSubmit = vi.fn()) =>
  render(
    <MemoryRouter>
      <GitHubForm onSubmit={onSubmit} />
    </MemoryRouter>
  );
const axiosErr = (status: number, data: unknown) =>
  new AxiosError("bad", "ERR_BAD_REQUEST", undefined, undefined, {
    status,
    data,
  } as never);
const URL_OK = "https://github.com/owner/repo";
const SHORT = "owner/repo";
const submitValid = async (url = SHORT) => {
  await userEvent.type(urlInput(), url);
  await waitFor(() => expect(submitBtn()).toBeEnabled());
  await userEvent.click(submitBtn());
};

const submitBtn = () => screen.getByRole("button", { name: /add repository/i });
const urlInput = () => screen.getByLabelText(/github repository/i);

describe("GitHubForm", () => {
  it("disables submit when empty", () => {
    renderForm();
    expect(submitBtn()).toBeDisabled();
  });

  it.each(["owner", "owner/repo/extra", "https://gitlab.com/a/b"])(
    "rejects %s with a hint",
    async (junk) => {
      const onSubmit = vi.fn();
      renderForm(onSubmit);
      await userEvent.type(urlInput(), junk);
      expect(await screen.findByText(/enter owner\/repo/i)).toBeInTheDocument();
      expect(submitBtn()).toBeDisabled();
      expect(onSubmit).not.toHaveBeenCalled();
    }
  );

  it.each([
    SHORT,
    "https://github.com/owner/repo.git/",
    "github.com/owner/repo",
    "http://www.github.com/owner/repo/",
  ])("submits %s as the full URL and resets on success", async (input) => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(onSubmit);
    await submitValid(input);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ url: URL_OK, branch: "" });
    await waitFor(() => expect(urlInput()).toHaveValue(""));
  });

  it("keeps input when onSubmit rejects", async () => {
    const onSubmit = vi.fn().mockRejectedValue(new Error("boom"));
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderForm(onSubmit);
    await submitValid();
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(urlInput()).toHaveValue(SHORT);
  });

  it("shows a 422 array detail inline", async () => {
    const onSubmit = vi
      .fn()
      .mockRejectedValue(
        axiosErr(422, { detail: [{ msg: "repo not found" }, { msg: "bad branch" }] })
      );
    renderForm(onSubmit);
    await submitValid();
    expect(await screen.findByRole("alert")).toHaveTextContent("repo not found; bad branch");
    expect(urlInput()).toHaveValue(SHORT);
  });

  it("shows a branch error under the Branch field, not the URL", async () => {
    const msg = "Branch 'dev' does not exist in owner/repo.";
    renderForm(vi.fn().mockRejectedValue(axiosErr(422, { detail: msg })));
    await submitValid();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(msg);
    expect(alert).toHaveAttribute("id", "branch-error");
    expect(urlInput()).not.toHaveAttribute("aria-invalid", "true");
  });

  it("shows a 422 string detail under the URL input", async () => {
    const msg = "Repository owner/repo was not found, or it is private.";
    renderForm(vi.fn().mockRejectedValue(axiosErr(422, { detail: msg })));
    await submitValid();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(msg);
    expect(alert).toHaveAttribute("id", "url-server-error");
    expect(urlInput()).toHaveAttribute("aria-invalid", "true");
    expect(urlInput()).toHaveAttribute("aria-describedby", "url-server-error");
  });

  it("links to the existing repository on 409", async () => {
    renderForm(
      vi
        .fn()
        .mockRejectedValue(
          axiosErr(409, { detail: "owner/repo has already been added.", repository_id: 42 })
        )
    );
    await submitValid();
    expect(await screen.findByRole("alert")).toHaveTextContent("owner/repo has already been added.");
    expect(screen.getByRole("link", { name: /open it/i })).toHaveAttribute(
      "href",
      "/repository/42"
    );
  });

  it.each([
    ["503", axiosErr(503, { detail: "GitHub is not available right now." }), /not available/i],
    ["network", new AxiosError("Network Error", "ERR_NETWORK"), /cannot reach the codesage server/i],
  ])("shows a %s error inline", async (_name, err, text) => {
    renderForm(vi.fn().mockRejectedValue(err));
    await submitValid();
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("clears the server error when the URL is edited", async () => {
    renderForm(vi.fn().mockRejectedValue(axiosErr(422, { detail: "nope" })));
    await submitValid();
    await screen.findByRole("alert");
    await userEvent.type(urlInput(), "x");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("accepts a URL with trailing whitespace", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(onSubmit);
    await submitValid(`${SHORT} `);
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].url).toBe(URL_OK);
  });

  it("shows a checking label while loading", () => {
    render(
      <MemoryRouter>
        <GitHubForm onSubmit={vi.fn()} isLoading />
      </MemoryRouter>
    );
    expect(screen.getByRole("button", { name: /checking repository/i })).toBeDisabled();
  });
});
