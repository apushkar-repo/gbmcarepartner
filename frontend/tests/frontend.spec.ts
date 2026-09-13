import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function enter(page: Page, role = "patient") {
  await page.goto("/");
  await page.locator(`input[name="role"][value="${role}"]`).check();
  await page.getByRole("button", { name: "Enter demo workspace" }).click();
}
async function route(page: Page, path: string) {
  await page.evaluate((path) => {
    window.history.pushState({}, "", path);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

test("patient can save and edit a sourced question without messaging anyone", async ({
  page,
}) => {
  await enter(page);
  await page
    .getByRole("link", { name: "Ask about your summaries", exact: true })
    .first()
    .click();
  await page
    .getByRole("button", { name: "What should I bring to my visit?" })
    .click();
  await expect(page.locator(".answer-card")).toContainText("September 8");
  await page
    .getByRole("button", { name: "Save as a question for your visit" })
    .click();
  await page
    .getByLabel("Question for your next visit")
    .fill("Should I bring the original reports or copies?");
  await page
    .getByRole("button", { name: "Save question", exact: true })
    .click();
  await page.getByRole("link", { name: /Visit preparation/ }).click();
  await expect(
    page.getByRole("heading", {
      name: "Should I bring the original reports or copies?",
    }),
  ).toBeVisible();
});

test("unsupported questions abstain without fabricated evidence", async ({
  page,
}) => {
  await enter(page);
  await route(page, "/app/ask");
  await page
    .getByLabel("Your question", { exact: true })
    .fill("What is the dose of my medication?");
  await page.getByRole("button", { name: "Ask question", exact: true }).click();
  await expect(page.locator(".answer-card")).toContainText("can’t find");
  await expect(page.locator(".citation")).toHaveCount(0);
});

test("reminder approval requires explicit confirmation; edits invalidate approval", async ({
  page,
}) => {
  await enter(page);
  await route(page, "/app/reminders");
  await page.getByRole("button", { name: "Review & approve" }).click();
  const approve = page.getByRole("button", {
    name: "Approve simulated reminder",
  });
  await expect(approve).toBeDisabled();
  await page.getByRole("checkbox").check();
  await approve.click();
  await expect(page.locator(".reminder-card")).toContainText(
    "Scheduled · simulated",
  );
  await page.getByRole("button", { name: "Edit reminder" }).click();
  await page.getByLabel("Local time").fill("11:00");
  await page.getByRole("button", { name: "Save new version" }).click();
  await expect(page.locator(".reminder-card")).toContainText(
    "Awaiting approval",
  );
  await route(page, "/app/visit");
  await expect(
    page.getByLabel("Complete Gather your previous visit reports"),
  ).not.toBeChecked();
});

test("care partner cannot approve without delegated capability", async ({
  page,
}) => {
  await enter(page, "partner");
  await route(page, "/app/reminders");
  await expect(
    page.getByRole("button", { name: "Review & approve" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("link", { name: "People & permissions" }),
  ).toHaveCount(0);
});

test("helper sees task fields and direct navigation does not render documents", async ({
  page,
}) => {
  await enter(page, "helper");
  await expect(
    page.getByRole("heading", { name: "Help organize a folder" }),
  ).toBeVisible();
  await expect(page.getByText("Maya Patel")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Visit summaries" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Confirm task is complete" }).click();
  await expect(
    page.getByText("Completed by you", { exact: true }),
  ).toBeVisible();
  await route(page, "/app/documents/draft/review");
  await expect(
    page.getByRole("heading", {
      name: "This view isn’t shared with your role",
    }),
  ).toBeVisible();
  await expect(page.locator(".source-paper")).toHaveCount(0);
});

test("publication requires field review and shows correct clinician authority", async ({
  page,
}) => {
  await enter(page, "clinician");
  await page.getByRole("link", { name: "Review & publish" }).click();
  await expect(
    page.getByRole("button", { name: "Review publication" }),
  ).toBeDisabled();
  await page
    .getByLabel("I reviewed this transcription against the source.")
    .check();
  await page.getByLabel("I reviewed this date against the source.").check();
  await page.getByRole("button", { name: "Review publication" }).click();
  await page
    .getByLabel("I approve this exact wording, date, and audience.")
    .check();
  await page.getByRole("button", { name: "Publish in demo" }).click();
  await expect(page.locator(".page-heading")).toContainText(
    "Clinician-approved",
  );
});

test("patient publication cannot become clinician attestation and pauses approved reminders", async ({
  page,
}) => {
  await enter(page);
  await route(page, "/app/reminders");
  await page.getByRole("button", { name: "Review & approve" }).click();
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Approve simulated reminder" })
    .click();
  await route(page, "/app/documents/draft/review");
  await page
    .getByLabel("I reviewed this transcription against the source.")
    .check();
  await page.getByLabel("I reviewed this date against the source.").check();
  await page.getByRole("button", { name: "Review publication" }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Patient-confirmed transcription",
  );
  await page
    .getByLabel("I approve this exact wording, date, and audience.")
    .check();
  await page.getByRole("button", { name: "Publish in demo" }).click();
  await route(page, "/app/reminders");
  await expect(page.locator(".reminder-card")).toContainText(
    "Paused · needs reapproval",
  );
});

test("reviewer and operations roles have separate limited workspaces", async ({
  page,
}) => {
  await enter(page, "reviewer");
  await expect(page.getByText("Not Run", { exact: true })).toBeVisible();
  await expect(page.getByText("Maya Patel")).toHaveCount(0);
  await page.getByRole("button", { name: /Sign out/ }).click();
  await page.locator('input[value="operations"]').check();
  await page.getByRole("button", { name: "Enter demo workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Integration readiness" }),
  ).toBeVisible();
  await expect(page.getByText("Maya Patel")).toHaveCount(0);
});

test("mobile routes fit viewport and navigation is keyboard accessible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page);
  for (const path of [
    "/app/home",
    "/app/documents",
    "/app/documents/draft/review",
    "/app/visit",
    "/app/reminders",
    "/app/sharing",
  ]) {
    await route(page, path);
    await expect(page.locator("h1")).toBeVisible();
    const width = await page.evaluate(
      () => document.documentElement.scrollWidth,
    );
    expect(width, path).toBeLessThanOrEqual(390);
  }
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Overview", exact: true }).click();
  await expect(page.locator(".sidebar")).not.toHaveClass(/open/);
  await page.screenshot({
    path: "test-results/mobile-overview.png",
    fullPage: true,
  });
});

test("desktop overview and login have no serious automated accessibility violations", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  for (const stage of ["login", "overview"]) {
    if (stage === "overview")
      await page.getByRole("button", { name: "Enter demo workspace" }).click();
    const results = await new AxeBuilder({ page }).analyze();
    expect(
      results.violations
        .filter((v) => ["serious", "critical"].includes(v.impact || ""))
        .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
      stage,
    ).toEqual([]);
  }
  await page.screenshot({
    path: "test-results/desktop-overview.png",
    fullPage: true,
  });
});

test("patient workflow pages and approval dialog pass automated accessibility checks", async ({
  page,
}) => {
  await enter(page);
  for (const path of [
    "/app/documents",
    "/app/capture",
    "/app/documents/draft/review",
    "/app/ask",
    "/app/visit",
    "/app/reminders",
    "/app/sharing",
    "/app/activity",
  ]) {
    await route(page, path);
    const results = await new AxeBuilder({ page }).analyze();
    expect
      .soft(
        results.violations
          .filter((v) => ["serious", "critical"].includes(v.impact || ""))
          .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target) })),
        path,
      )
      .toEqual([]);
  }
  await route(page, "/app/reminders");
  await page.getByRole("button", { name: "Review & approve" }).click();
  const result = await new AxeBuilder({ page }).analyze();
  expect(
    result.violations
      .filter((v) => ["serious", "critical"].includes(v.impact || ""))
      .map((v) => v.id),
  ).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Review & approve" }),
  ).toBeFocused();
});

test("a corrected visit date updates the dashboard and blocks the stale slot", async ({
  page,
}) => {
  await enter(page);
  await route(page, "/app/documents/draft/review");
  await page.getByLabel("Visit date", { exact: true }).fill("2026-10-01");
  await page
    .getByLabel("I reviewed this transcription against the source.")
    .check();
  await page.getByLabel("I reviewed this date against the source.").check();
  await page.getByRole("button", { name: "Review publication" }).click();
  await page
    .getByLabel("I approve this exact wording, date, and audience.")
    .check();
  await page.getByRole("button", { name: "Publish in demo" }).click();
  await route(page, "/app/home");
  await expect(page.locator(".hero-actions")).toContainText("October 1, 2026");
  await route(page, "/app/visit");
  await expect(
    page.getByRole("button", { name: "Review simulated booking" }),
  ).toBeDisabled();
});
