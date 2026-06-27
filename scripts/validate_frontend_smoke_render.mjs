#!/usr/bin/env node
/**
 * Phase 64B — frontend smoke: dist integrity + vite preview routes (+ optional Playwright).
 */
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { spawn, spawnSync } from "child_process";
import { fileURLToPath } from "url";
import http from "http";

const ROOT = join(fileURLToPath(import.meta.url), "..", "..");
const FRONTEND = join(ROOT, "base44-d");
const DIST = join(FRONTEND, "dist");
const PREVIEW_PORT = Number(process.env.FRONTEND_SMOKE_PORT || 4173);
const PREVIEW_HOST = process.env.FRONTEND_SMOKE_HOST || "127.0.0.1";
const BASE = `http://${PREVIEW_HOST}:${PREVIEW_PORT}`;

const ROUTES = ["/", "/login", "/archive", "/results", "/matches"];

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function parseIndexAssets() {
  const indexPath = join(DIST, "index.html");
  if (!existsSync(indexPath)) {
    throw new Error(`missing ${indexPath}`);
  }
  const html = readFileSync(indexPath, "utf8");
  const scripts = [...html.matchAll(/src="(\/assets\/[^"]+\.js)"/g)].map((m) => m[1]);
  const styles = [...html.matchAll(/href="(\/assets\/[^"]+\.css)"/g)].map((m) => m[1]);
  if (!scripts.length) throw new Error("index.html has no /assets/*.js script");
  if (!html.includes('id="root"')) throw new Error('index.html missing #root');
  return { html, scripts, styles };
}

function verifyDistFiles(assets) {
  const missing = [];
  for (const rel of [...assets.scripts, ...assets.styles]) {
    const name = rel.replace(/^\//, "");
    const path = join(DIST, name);
    if (!existsSync(path)) missing.push(rel);
  }
  return missing;
}

async function waitForServer(maxMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(`${BASE}/`);
      if (res.ok) return true;
    } catch {
      /* retry */
    }
    await sleep(400);
  }
  return false;
}

function startPreview() {
  const child = spawn("npm", ["run", "preview", "--", "--host", PREVIEW_HOST, "--port", String(PREVIEW_PORT), "--strictPort"], {
    cwd: FRONTEND,
    shell: true,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, BROWSER: "none" },
  });
  return child;
}

async function fetchRoute(path) {
  const res = await fetch(`${BASE}${path}`, { redirect: "follow" });
  const body = await res.text();
  return { path, status: res.status, body, ok: res.ok };
}

async function runPreviewSmoke() {
  const assets = parseIndexAssets();
  const missing = verifyDistFiles(assets);
  if (missing.length) {
    console.log("DIST_ASSET_FAIL missing:", missing.join(", "));
    return false;
  }
  console.log("DIST_ASSET_CHECK PASS", assets.scripts.join(", "));

  const preview = startPreview();
  let previewOk = false;
  try {
    previewOk = await waitForServer();
    if (!previewOk) {
      console.log("PREVIEW_START_FAIL could not reach vite preview");
      return false;
    }
    console.log(`PREVIEW_OK ${BASE}`);

    let allOk = true;
    for (const route of ROUTES) {
      const r = await fetchRoute(route);
      const hasRoot = r.body.includes('id="root"');
      const hasScript = r.body.includes("/assets/") && r.body.includes(".js");
      const pass = r.ok && hasRoot && hasScript;
      console.log(`${pass ? "PASS" : "FAIL"} route ${route} status=${r.status} root=${hasRoot} script=${hasScript}`);
      if (!pass) allOk = false;
    }
    return allOk;
  } finally {
    preview.kill("SIGTERM");
    await sleep(500);
  }
}

async function runPlaywrightSmoke() {
  try {
    await import("playwright");
  } catch {
    console.log("PLAYWRIGHT_SKIP not installed (preview smoke only)");
    return { skipped: true, ok: true };
  }

  const { chromium } = await import("playwright");
  const preview = startPreview();
  const errors = [];
  try {
    if (!(await waitForServer())) {
      return { skipped: false, ok: false, errors: ["preview failed for playwright"] };
    }
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    page.on("pageerror", (err) => errors.push(String(err.message || err)));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });

    for (const route of ROUTES) {
      await page.goto(`${BASE}${route}`, { waitUntil: "networkidle", timeout: 30000 });
      const mounted = await page.locator("#root").evaluate((el) => el.childElementCount > 0).catch(() => false);
      console.log(`${mounted ? "PASS" : "FAIL"} playwright mount ${route}`);
      if (!mounted) errors.push(`#root empty on ${route}`);
    }
    await browser.close();
    const fatal = errors.filter((e) => !/manifest\.json|favicon/i.test(e));
    return { skipped: false, ok: fatal.length === 0, errors: fatal };
  } finally {
    preview.kill("SIGTERM");
    await sleep(500);
  }
}

async function main() {
  if (!existsSync(DIST)) {
    console.log("SMOKE_FAIL dist/ missing — run npm run build first");
    process.exit(1);
  }

  console.log("=== Phase 64B frontend smoke render ===");
  const previewPass = await runPreviewSmoke();
  const pw = await runPlaywrightSmoke();

  if (!pw.skipped && !pw.ok) {
    console.log("PLAYWRIGHT_FAIL", pw.errors?.slice(0, 10));
  } else if (!pw.skipped && pw.ok) {
    console.log("PLAYWRIGHT_PASS");
  }

  const ok = previewPass && (pw.skipped || pw.ok);
  console.log(`\nSMOKE_RENDER: ${ok ? "PASS" : "FAIL"}`);
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error("SMOKE_RENDER_ERROR", e);
  process.exit(1);
});
