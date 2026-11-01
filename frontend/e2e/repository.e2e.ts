import { expect, test } from "@playwright/test";

// e2e/seed.py indexes one repository, e2e/demo, with src/app.py and README.md

test("the seeded repository opens from the dashboard", async ({ page }) => {
  await page.goto("/dashboard");
  await page.getByRole("link", { name: "View Details" }).click();

  await expect(page.getByRole("heading", { name: "e2e/demo" })).toBeVisible();
  await expect(page.getByText("Indexed at")).toContainText("abc1234");
  await expect(page.getByText("Repository analysis complete!")).toBeVisible();
});

test("a definition opens the file viewer at its lines, and back", async ({ page }) => {
  await page.goto("/repository/1");
  await page.getByRole("link", { name: "Greeter", exact: true }).click();

  await expect(page).toHaveURL(/\/repository\/1\/file\?path=src%2Fapp\.py&line=5&end=7$/);
  await expect(page.locator("#L5")).toContainText("class Greeter:");
  await expect(page.locator("#L5")).toHaveClass(/bg-yellow-100/);
  await expect(page.locator("#L4")).not.toHaveClass(/bg-yellow-100/);

  await page.getByRole("link", { name: "← Back to repository" }).click();
  await expect(page.getByRole("heading", { name: "e2e/demo" })).toBeVisible();
});
