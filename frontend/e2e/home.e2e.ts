import { expect, test } from "@playwright/test";

test("the add form checks its input and shows the server's refusal inline", async ({ page }) => {
  await page.goto("/");
  const field = page.getByLabel(/^repository/i);
  const add = page.getByRole("button", { name: "Add Repository" });

  await field.fill("owner");
  await expect(field).toHaveAccessibleDescription(/enter owner\/repo for github/i);
  await expect(add).toBeDisabled();

  await field.fill("gitlab.com/group/project");
  await expect(page.getByText("gitlab.com/group/project", { exact: true })).toBeVisible();

  await field.fill("owner/repo");
  await add.click();
  // This stack has no Algolia keys, so the server refuses before any GitHub call
  await expect(page.getByRole("alert")).toHaveText(/Search indexing is not configured/);
  await expect(page).toHaveURL(/:5183\/$/);
});
