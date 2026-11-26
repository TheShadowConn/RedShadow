// Retake the manual's screenshots from a running app seeded by seed_demo.py.
//   BASE=http://127.0.0.1:5173 JOB=<import job id> ENG=<engagement id> MFA=<base32 secret> OUT=docs/manual/shots node capture.js
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { MEDIA_ROOT = "/tmp/rs-demo-media", BASE = "http://127.0.0.1:5173", JOB, ENG, MFA, OUT = "shots", PASSWORD = "Correct-Horse-Battery-9" } = process.env;

function totp(secret) {
  const alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secret.replace(/=+$/, "")) bits += alpha.indexOf(c).toString(2).padStart(5, "0");
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)));
  const step = Buffer.alloc(8); step.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const h = crypto.createHmac("sha1", key).update(step).digest();
  const o = h[19] & 15;
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1e6)).padStart(6, "0");
}

async function login(browser, email, mfa) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, colorScheme: "light" });
  // Production serves files through nginx (X-Accel-Redirect to /protected/). The dev server cannot, so do the same here.
  await ctx.route("**/api/v1/attachments/**/download*", async (route) => {
    const r = await route.fetch();
    const accel = r.headers()["x-accel-redirect"];
    if (!accel) return route.fulfill({ response: r });
    const file = path.join(MEDIA_ROOT, accel.replace(/^\/protected\//, ""));
    return route.fulfill({ status: 200, contentType: r.headers()["content-type"], body: fs.readFileSync(file) });
  });
  const p = await ctx.newPage();
  await p.goto(BASE + "/"); await p.getByLabel("Email").fill(email); await p.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await p.getByRole("button", { name: "Sign in" }).click();
  if (mfa) { await p.getByLabel("Authentication code").fill(totp(mfa)); await p.getByRole("button", { name: "Verify" }).click(); }
  await p.waitForSelector("h1"); await p.waitForTimeout(1200);
  return p;
}
const shot = (p, name, opts = {}) => p.screenshot({ path: `${OUT}/${name}`, ...opts }).then(() => console.log("saved", name));
const settle = (p, ms = 1200) => p.waitForTimeout(ms);

(async () => {
  const b = await chromium.launch();
  // Super Admin
  let p = await login(b, "admin@redshadow.demo", MFA);
  await shot(p, "02-admin-dashboard.png");
  await p.goto(BASE + "/engagements"); await settle(p); await shot(p, "03-engagements.png");
  await p.goto(`${BASE}/engagements/${ENG}`); await settle(p); await shot(p, "04-engagement-overview.png");
  await p.getByRole("button", { name: /^Edit$/ }).first().click(); await settle(p, 800);
  await shot(p, "31-engagement-edit-markdown.png");
  await p.keyboard.press("Escape"); await settle(p, 600);
  await p.evaluate(() => window.scrollBy(0, 560)); await settle(p, 500);
  await shot(p, "35-engagement-sections-markdown.png");
  await p.goto(`${BASE}/engagements/${ENG}?tab=scenarios`); await settle(p, 1800);
  await p.evaluate(() => window.scrollBy(0, 600)); await settle(p, 600);
  await shot(p, "32-scenarios-pictures.png");
  await p.locator("button[aria-label^='Open picture']").first().click(); await settle(p, 900);
  await shot(p, "33-picture-viewer.png");
  await p.keyboard.press("Escape");
  await p.goto(BASE + "/costs"); await settle(p, 1500); await shot(p, "36-costs-page.png");
  await p.getByRole("link", { name: /Total engagement cost/ }).count(); // the dashboard card links here
  // Pentester: import check, import, finding with gaps
  p = await login(b, "priya@redshadow.demo", null);
  await p.goto(`${BASE}/imports/${JOB}`); await settle(p, 1800);
  await settle(p, 6000); // let the "Now importing" toast go
  await p.getByRole("heading", { name: /Step 4/ }).evaluate((el) => el.scrollIntoView({ block: "start" })); await p.evaluate(() => window.scrollBy(0, -420)); await settle(p, 500);
  await shot(p, "23-import-check.png");
  await p.getByRole("radio", { name: /Import everything/ }).check();
  await p.getByRole("button", { name: /^Import/ }).last().click(); await settle(p, 500);
  await p.getByRole("dialog").getByRole("button", { name: "Import", exact: true }).click(); await settle(p, 3500);
  await p.goto(BASE + "/imports"); await settle(p); await shot(p, "22-imports.png");
  const id = await p.evaluate(async () => (await (await fetch("/api/v1/findings?search=Untitled")).json()).results[0]?.id);
  await p.goto(`${BASE}/findings`); await settle(p, 1500); await shot(p, "37-findings-needs-review.png");
  await p.goto(`${BASE}/findings/${id}`); await settle(p, 1400); await shot(p, "34-finding-import-gaps.png");
  // The case that used to blank the app: a reference with a link but no label
  await p.goto(`${BASE}/findings/${id}/edit`); await settle(p, 1200);
  await p.getByRole("button", { name: "Add reference" }).click();
  await p.getByLabel("Link", { exact: true }).fill("https://nvd.nist.gov/vuln/detail/cve-2026-98432");
  await p.getByRole("button", { name: /^Save/ }).click(); await settle(p, 1800);
  console.log("EDIT_WITHOUT_LABEL page ok:", !(await p.getByText("Something went wrong").count()), "| body text length:", (await p.locator("body").innerText()).length, "| url:", p.url());
  // Similar-findings warning while writing a new finding
  await p.goto(`${BASE}/findings/new?engagement=${ENG}`); await settle(p, 1200);
  await p.getByLabel("Title").fill("SQL injection in the search box"); await settle(p, 2200);
  console.log("SIMILAR_WARNING shown:", (await p.getByText("already has similar findings").count()) > 0);
  await shot(p, "38-similar-findings-warning.png");
  // Super Admin deletes the import history
  p = await login(b, "admin@redshadow.demo", MFA);
  await p.goto(BASE + "/imports"); await settle(p, 1200);
  await p.getByRole("button", { name: "Clear history" }).click(); await settle(p, 500);
  await p.getByRole("dialog").getByRole("button", { name: "Clear history" }).click(); await settle(p, 1800);
  console.log("HISTORY_CLEARED, empty state shown:", (await p.getByText("No imports yet").count()) > 0);
  // Undo after deleting a finding, and the backup card on About
  const fid = await p.evaluate(async () => (await (await fetch("/api/v1/findings?search=Debug")).json()).results[0]?.id);
  await p.goto(`${BASE}/findings/${fid}`); await settle(p, 1200);
  await p.getByRole("button", { name: "Delete", exact: true }).first().click(); await settle(p, 500);
  await shot(p, "39-delete-confirm.png");
  await p.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click(); await settle(p, 1500);
  await shot(p, "40-undo-after-delete.png");
  const gone = await p.evaluate(async (id) => (await fetch(`/api/v1/findings/${id}`)).status, fid);
  await p.getByRole("button", { name: "Undo" }).click(); await settle(p, 1500);
  const back = await p.evaluate(async (id) => (await fetch(`/api/v1/findings/${id}`)).status, fid);
  console.log("UNDO: status after delete", gone, "-> after undo", back);
  await p.goto(BASE + "/about"); await settle(p, 1200); await shot(p, "15-about.png");
  // External vendor
  p = await login(b, "vera@redshadow.demo", null);
  await shot(p, "27-vendor-dashboard.png");
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
