// Browser walkthrough of the main flows for every role. Fails on any page error or console error.
// Usage: node e2e/walkthrough.cjs [baseUrl] [screenshotDir]   (expects freshly seeded data)
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const BASE = process.argv[2] || "http://127.0.0.1:8000";
const SHOTS = process.argv[3] || path.join(__dirname, "screenshots");
const PASSWORD = "Pramaan@2026";
fs.mkdirSync(SHOTS, { recursive: true });

const problems = [];
let step = 0;

async function shot(page, name) {
  step += 1;
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(SHOTS, `${String(step).padStart(2, "0")}-${name}.png`), fullPage: false });
}

async function login(page, username) {
  await page.goto(`${BASE}/login`);
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForSelector(".topbar");
}

async function logout(page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.waitForSelector(".login");
}

async function waitIdle(page, timeout = 90000) {
  // wait until no "Reading…"/"Checking…" spinners remain
  const start = Date.now();
  while (Date.now() - start < timeout) {
    const busy = await page.locator("text=/Checking…|Reading…|re-checking…|Reading the document…/").count();
    if (!busy) return;
    await page.waitForTimeout(800);
  }
  throw new Error("page stayed busy");
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
  const page = await context.newPage();
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  page.on("console", (m) => { if (m.type() === "error") problems.push(`console: ${m.text()}`); });
  page.on("dialog", (d) => d.dismiss());

  // ---- sign in page
  await page.goto(BASE);
  await page.waitForSelector(".login");
  await shot(page, "login");

  // ---- scrutinizer
  await login(page, "a.kulkarni");
  await page.waitForSelector("text=Applications received");
  await shot(page, "dashboard");
  await page.getByRole("link", { name: "Scrutiny queue", exact: true }).click();
  await page.waitForSelector("text=APP-2026-00045");
  await shot(page, "queue");
  await page.locator("tr", { hasText: "APP-2026-00045" }).click();
  await page.waitForSelector("text=Fire NOC lapsed before the application date");
  await page.locator(".fcard", { hasText: "Fire NOC lapsed" }).click();
  await page.waitForSelector(".hlbox");
  await shot(page, "workspace-fire-noc");
  // open the duplicate-photo finding and jump to its evidence
  await page.locator(".fcard", { hasText: "matches a document from another institution" }).click();
  await page.waitForTimeout(800);
  await shot(page, "workspace-duplicate-photo");
  // accept the fire NOC finding, override the faculty-ratio finding with a reason
  await page.locator(".fcard", { hasText: "Fire NOC lapsed" }).click();
  await page.getByRole("button", { name: "Accept finding" }).click();
  await page.waitForSelector(".toast >> text=Finding accepted");
  await page.waitForSelector(".fcard >> text=Accepted");
  await page.locator(".fcard", { hasText: "Student–faculty ratio" }).click();
  await page.locator(".fcard.open").getByRole("button", { name: "Override…" }).click();
  await page.getByLabel("Why is this finding not a problem?").fill("Two new faculty joined in March; appointment letters checked.");
  await page.locator(".modal").getByRole("button", { name: "Override" }).click();
  await page.waitForSelector(".toast >> text=Finding overridden");
  await page.getByRole("button", { name: /Issuer verification/ }).click();
  await shot(page, "workspace-verification-tab");
  await page.getByRole("button", { name: "Validation report" }).click();
  await page.waitForSelector("text=Verification matrix");
  await shot(page, "validation-report");

  // ---- tampered certificate case
  await page.goto(`${BASE}/applications/APP-2026-00150`);
  await page.locator(".fcard", { hasText: "Text covered by a white box" }).click();
  await page.waitForSelector(".hlbox");
  await shot(page, "workspace-tampered-noc");

  await page.getByRole("link", { name: "Verification", exact: true }).click();
  await page.waitForSelector("text=Issuer verification");
  await page.getByRole("button", { name: "Source unavailable" }).click();
  await page.waitForSelector("text=Affiliating-university API");
  await shot(page, "verification-log");
  await page.getByRole("link", { name: "Audit trail", exact: true }).click();
  await page.waitForSelector("text=Chain verified");
  await page.locator("tbody tr").first().click();
  await shot(page, "audit-trail");
  // Hindi toggle
  await page.getByRole("button", { name: "हिंदी" }).click();
  await page.waitForSelector("text=डैशबोर्ड");
  await page.getByRole("button", { name: "EN" }).click();
  await logout(page);

  // ---- institution completes a draft and submits
  await login(page, "sit.dehradun");
  await page.waitForSelector("text=APP-2026-00301");
  await page.getByRole("link", { name: "APP-2026-00301" }).click();
  await page.waitForSelector("text=Required documents");
  await shot(page, "institution-draft");
  for (let i = 0; i < 4; i++) {
    const btn = page.getByRole("button", { name: "Use sample" }).first();
    if (!(await btn.count())) break;
    await btn.click();
    await page.waitForTimeout(500);
    await waitIdle(page);
  }
  await waitIdle(page);
  await shot(page, "institution-after-uploads");
  await page.getByRole("tab", { name: "Application form" }).click();
  await page.waitForSelector("text=Programmes and intake requested");
  await shot(page, "institution-form");
  await page.getByRole("tab", { name: "Documents and pre-check" }).click();
  await page.getByRole("button", { name: "Submit application" }).first().click();
  await page.locator(".modal").getByRole("button", { name: "Submit" }).click();
  await page.waitForSelector("text=Under scrutiny");
  await waitIdle(page);
  await shot(page, "institution-submitted");
  await logout(page);

  // ---- institution answers a deficiency letter
  await login(page, "ksm.kochi");
  await page.getByRole("link", { name: "APP-2026-00203" }).click();
  await page.waitForSelector("text=deficiency letter");
  await page.getByRole("tab", { name: /Deficiency letters/ }).click();
  await page.getByLabel("Reply").fill("NBA renewal applied for; fresh lab photos with location will follow.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await page.waitForSelector("text=Replied");
  await shot(page, "institution-replied");
  await logout(page);

  // ---- rule admin edits a rule, tries it, dry-runs and submits
  await login(page, "s.rao");
  await page.getByRole("link", { name: "Rulebook", exact: true }).click();
  await page.getByRole("button", { name: /New draft from/ }).click();
  await page.waitForSelector("text=What changed");
  await page.locator("button", { hasText: "FAC-RATIO-01" }).click();
  await page.getByLabel("Value").first().fill("25");
  await page.getByLabel("What changed").fill("Student-faculty norm set to 1:25 for this cycle");
  await page.getByRole("button", { name: "Save" }).click();
  await page.waitForSelector("text=Draft saved");
  await page.getByRole("button", { name: "Evaluate" }).click();
  await page.waitForSelector("text=row(s) matched");
  await page.getByRole("button", { name: "Dry run" }).click();
  await page.waitForSelector("text=findings with this version", { timeout: 60000 });
  await shot(page, "rulebook-draft");
  await page.getByRole("button", { name: "Submit for approval" }).click();
  await page.waitForSelector("text=Waiting for a senior officer");
  await logout(page);

  // ---- senior officer approves the rulebook and records a decision
  await login(page, "r.menon");
  await page.getByRole("link", { name: "Rulebook", exact: true }).click();
  await page.getByRole("button", { name: "Approve and publish" }).click();
  await page.waitForSelector("text=Published");
  await shot(page, "rulebook-published");
  await page.goto(`${BASE}/applications/APP-2026-00264`);
  await page.waitForSelector("text=Findings");
  await page.getByRole("button", { name: "Record decision" }).click();
  await page.locator(".modal select").selectOption("APPROVED_WITH_CONDITIONS");
  await page.getByLabel("Reasons and conditions").fill("Renew the Fire NOC before 31-05-2026 and upload it.");
  await page.getByLabel(/I have reviewed the evidence myself/).check();
  await page.locator(".modal").getByRole("button", { name: "Record decision" }).click();
  await page.waitForSelector("text=Decision: Approved with conditions");
  await shot(page, "decision-recorded");

  await browser.close();
  const real = problems.filter((p) => !p.includes("favicon"));
  if (real.length) {
    console.error("Problems found:\n" + real.join("\n"));
    process.exit(1);
  }
  console.log(`Walkthrough passed: ${step} screenshots in ${SHOTS}`);
})().catch((e) => {
  console.error("Walkthrough failed:", e.message);
  if (problems.length) console.error(problems.join("\n"));
  process.exit(1);
});
