import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

async function noA11yViolations(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(["section508", "wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)).toEqual([]);
}

test("a visitor replays a run, reviews it and downloads the PR description", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto("./");
  await expect(page.getByRole("heading", { name: "Agentic PR preparation with a human in the loop" })).toBeVisible();
  await noA11yViolations(page);

  await page.getByRole("button", { name: /^Watch a run/ }).click();
  await expect(page).toHaveURL(/\?run=invoicing$/);
  await expect(page.getByText("Agents working")).toBeVisible();
  await expect(page.getByRole("region", { name: "Planner" })).toContainText("Reading the diff");

  await page.getByRole("button", { name: "Skip to review" }).click();
  await expect(page.getByText("Needs your review")).toBeVisible();
  await page.getByText("The diff under review").click();
  await expect(page.getByText("4 findings marked")).toBeVisible();
  await noA11yViolations(page);

  const review = page.getByRole("region", { name: "Human review" });
  await review.getByLabel("Dismiss Hardcoded password or secret").check();
  await review.getByLabel("PR title").fill("Discounts and invoice export");
  await review.getByLabel("Note for the PR (optional)").fill("Rotate the key before merging.");
  await review.getByRole("button", { name: "Approve" }).click();

  const result = page.getByRole("region", { name: "Result" });
  await expect(result.getByRole("heading", { name: "Approved" })).toBeFocused();
  const pr = result.getByRole("region", { name: "PR description" });
  await expect(pr.getByRole("heading", { name: "Discounts and invoice export" })).toBeVisible();
  await expect(pr.getByRole("table")).not.toContainText("Hardcoded password");
  await expect(pr).toContainText("Rotate the key before merging.");
  await noA11yViolations(page);

  const download = page.waitForEvent("download");
  await result.getByRole("link", { name: "Download PR_DESCRIPTION.md" }).click();
  const file = await download;
  expect(file.suggestedFilename()).toBe("PR_DESCRIPTION.md");
  const text = await (await file.createReadStream()).toArray();
  expect(Buffer.concat(text).toString("utf8")).toMatch(/^# Discounts and invoice export\n/);
  expect(errors).toEqual([]);
});

test("the clean run reaches review on its own and passes", async ({ page }) => {
  await page.goto("./?run=clean");
  await page.getByRole("button", { name: "4x" }).click();
  await expect(page.getByText("Needs your review")).toBeVisible({ timeout: 20_000 });
  const review = page.getByRole("region", { name: "Human review" });
  await expect(review.getByText("No findings.")).toBeVisible();
  await expect(review.getByText("low risk")).toBeVisible();
  await review.getByRole("button", { name: "Reject" }).click();
  const result = page.getByRole("region", { name: "Result" });
  await expect(result.getByRole("heading", { name: "Rejected" })).toBeVisible();
  await expect(result.getByRole("link", { name: /^Download/ })).toHaveCount(1);
});

test("the page fits a phone and the review is one tap away", async ({ page }, info) => {
  test.skip(info.project.name !== "phone", "phone layout only");
  await page.goto("./?run=invoicing");
  await page.getByRole("button", { name: "Skip to review" }).click();
  await page.getByRole("button", { name: "The agents are done. Go to your review" }).click();
  await expect(page.getByRole("region", { name: "Human review" })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test("with reduced motion the run is shown at once", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("./?run=invoicing");
  await expect(page.getByText("Needs your review")).toBeVisible({ timeout: 2_000 });
});
