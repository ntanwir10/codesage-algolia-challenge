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
const urlInput = () => screen.getByLabelText(/^repository/i);

describe("GitHubForm", () => {
  it("disables submit when empty", () => {
    renderForm();
    expect(submitBtn()).toBeDisabled();
  });

  it.each([
    "owner",
    "owner/repo/extra",
    "https://gitlab.com/group",
    "ftp://gitlab.com/a/b",
    // Never sent: the password would reach the server
    "https://user:pw@gitlab.com/a/b",
  ])(
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

  it("keeps a duplicate under the URL even when the repository is named 'branch'", async () => {
    renderForm(
      vi.fn().mockRejectedValue(
        axiosErr(409, { detail: "owner/branch has already been added.", repository_id: 7 })
      )
    );
    await submitValid("owner/branch");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveAttribute("id", "url-server-error");
    expect(screen.getByRole("link", { name: /open it/i })).toBeInTheDocument();
  });

  it("puts a 422 on the branch field under Branch", async () => {
    renderForm(
      vi.fn().mockRejectedValue(
        axiosErr(422, { detail: [{ loc: ["body", "branch"], msg: "String should have at most 100 characters" }] })
      )
    );
    await submitValid();
    expect(await screen.findByRole("alert")).toHaveAttribute("id", "branch-error");
  });

  it.each([
    [SHORT, "owner/repo"],
    ["https://gitlab.com/group/project", "gitlab.com/group/project"],
  ])("shows a branch error for %s under the Branch field, not the URL", async (url, name) => {
    const msg = `Branch 'dev' does not exist in ${name}.`;
    renderForm(vi.fn().mockRejectedValue(axiosErr(422, { detail: msg })));
    await submitValid(url);
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

  it.each([
    ["https://github.com/owner/repo/tree/feature/x", "https://github.com/owner/repo/tree/feature/x"],
    ["git@github.com:owner/repo.git", "https://github.com/owner/repo"],
    // A branch may end in .git; only the repository's clone suffix goes
    ["github.com/owner/repo.git/tree/release.git", "https://github.com/owner/repo/tree/release.git"],
    // Other hosts go as https URLs; the server parses their paths and branches
    ["https://gitlab.com/group/sub/project", "https://gitlab.com/group/sub/project"],
    ["gitlab.com/group/project/-/tree/dev", "https://gitlab.com/group/project/-/tree/dev"],
    ["git@gitlab.com:group/project.git", "https://gitlab.com/group/project.git"],
    ["http://bitbucket.org/team/repo/src/main/", "https://bitbucket.org/team/repo/src/main"],
    ["https://git.example.org/team/repo", "https://git.example.org/team/repo"],
  ])("accepts %s, which the server also understands", async (input, sent) => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(onSubmit);
    await submitValid(input);
    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ url: sent })));
  });

  it.each([
    [SHORT, "owner/repo"],
    ["https://gitlab.com/group/project", "gitlab.com/group/project"],
  ])("previews %s as %s, the name the server gives it", async (input, name) => {
    renderForm();
    await userEvent.type(urlInput(), input);
    expect(await screen.findByText(name)).toBeInTheDocument();
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
