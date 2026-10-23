import { AxiosError } from "axios";
import { describe, expect, it } from "vitest";
import { queryClient, shouldRetryQuery } from "./queryClient";

const httpError = (status: number) =>
  new AxiosError("x", "ERR", undefined, undefined, { status } as never);

describe("queryClient retry rule", () => {
  it("is wired into default query options", () => {
    expect(queryClient.getDefaultOptions().queries?.retry).toBe(shouldRetryQuery);
  });
  it("does not retry on 404 / 4xx", () => {
    expect(shouldRetryQuery(0, httpError(404))).toBe(false);
    expect(shouldRetryQuery(0, httpError(422))).toBe(false);
  });
  it("retries on 500", () => {
    expect(shouldRetryQuery(0, httpError(500))).toBe(true);
    expect(shouldRetryQuery(3, httpError(500))).toBe(false);
  });
  it("retries on network errors (no response)", () => {
    expect(shouldRetryQuery(1, new AxiosError("Network Error"))).toBe(true);
    expect(shouldRetryQuery(1, new Error("x"))).toBe(true);
  });
});
