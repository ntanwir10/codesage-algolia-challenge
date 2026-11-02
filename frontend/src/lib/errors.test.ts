import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";
import { describeError } from "./errors";

const withStatus = (status: number, data: unknown) =>
  new AxiosError("x", "ERR_BAD_RESPONSE", undefined, undefined, {
    status,
    data,
    headers: {},
  } as never);

describe("describeError", () => {
  it("reports a timeout separately from a network error", () => {
    expect(describeError(new AxiosError("t", "ECONNABORTED")).message).toBe(
      "The server took too long to respond. Try again."
    );
    expect(describeError(new AxiosError("n", "ERR_NETWORK")).message).toMatch(
      /cannot reach the codesage server/i
    );
  });

  it("tells a refused proxy login apart from a rejected key", () => {
    const login = new AxiosError("x", "ERR_BAD_RESPONSE", undefined, undefined, {
      status: 401,
      data: "<html>401</html>",
      headers: { "www-authenticate": 'Basic realm="CodeSage"' },
    } as never);
    expect(describeError(login).message).toBe("The site's login was refused. Reload the page and sign in again.");
    expect(describeError(withStatus(401, { detail: "Invalid or missing API key" })).message).toMatch(/API key/);
  });

  it.each([502, 503, 504])("uses the string detail for %i", (status) => {
    expect(describeError(withStatus(status, { detail: "GitHub is down." })).message).toBe(
      "GitHub is down."
    );
  });

  it.each([502, 503, 504])("falls back to a generic message for %i", (status) => {
    expect(describeError(withStatus(status, {})).message).toBe(
      "The server is temporarily unavailable. Try again shortly."
    );
  });
});
