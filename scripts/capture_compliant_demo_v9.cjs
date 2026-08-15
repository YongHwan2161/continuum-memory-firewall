"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`missing ${name}`);
  return process.argv[index + 1];
}

const baseUrl = argument("--base-url").replace(/\/$/, "");
const timingsPath = path.resolve(argument("--timings"));
const outputDirectory = path.resolve(argument("--output-dir"));
const markersPath = path.resolve(argument("--markers"));
const segments = JSON.parse(fs.readFileSync(timingsPath, "utf8")).segments;
if (!Array.isArray(segments) || segments.length !== 9) {
  throw new Error("timings must contain exactly nine segments");
}
fs.mkdirSync(outputDirectory, { recursive: true });

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function installOverlay(page, scene) {
  await page.evaluate(({ caption, number, href }) => {
    document.querySelectorAll("[data-continuum-demo-overlay]").forEach((node) => node.remove());
    const style = document.createElement("style");
    style.dataset.continuumDemoOverlay = "style";
    style.textContent = `
      #continuum-demo-url{position:fixed;z-index:2147483645;left:0;right:0;top:0;height:38px;display:flex;align-items:center;gap:12px;padding:0 18px;background:#07110eeb;border-bottom:1px solid #31584a;color:#d9f4e8;font:600 13px/1.2 ui-monospace,Consolas,monospace;box-shadow:0 4px 18px #0006}
      #continuum-demo-url b{color:#3ee6a8;letter-spacing:.08em}#continuum-demo-url span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      #continuum-demo-caption{position:fixed;z-index:2147483646;left:54px;right:54px;bottom:24px;padding:14px 20px;border-radius:12px;background:#06100df2;border:1px solid #3e8068;color:white;text-align:center;font:700 22px/1.3 "Segoe UI",sans-serif;box-shadow:0 8px 28px #000a}
      #continuum-demo-cursor{position:fixed;z-index:2147483647;width:18px;height:18px;border:3px solid #fff;border-radius:50%;background:#21d894aa;box-shadow:0 0 0 5px #21d8943b;pointer-events:none;transform:translate(-50%,-50%);transition:left .55s ease,top .55s ease}
      #continuum-demo-cursor.click{animation:continuum-click .48s ease}@keyframes continuum-click{50%{box-shadow:0 0 0 18px #21d89422;transform:translate(-50%,-50%) scale(.72)}}
    `;
    const bar = document.createElement("div");
    bar.id = "continuum-demo-url";
    bar.dataset.continuumDemoOverlay = "url";
    const label = document.createElement("b");
    label.textContent = `LIVE BROWSER · ${String(number).padStart(2, "0")}/09`;
    const url = document.createElement("span");
    url.textContent = href;
    bar.append(label, url);
    const subtitle = document.createElement("div");
    subtitle.id = "continuum-demo-caption";
    subtitle.dataset.continuumDemoOverlay = "caption";
    subtitle.textContent = caption;
    const cursor = document.createElement("div");
    cursor.id = "continuum-demo-cursor";
    cursor.dataset.continuumDemoOverlay = "cursor";
    cursor.style.left = "1130px";
    cursor.style.top = "84px";
    document.documentElement.append(style, bar, subtitle, cursor);
  }, { caption: scene.caption, number: scene.number, href: page.url() });
}

async function moveCursor(page, x, y, click = false) {
  await page.evaluate(({ x, y, click }) => {
    const cursor = document.querySelector("#continuum-demo-cursor");
    if (!cursor) return;
    cursor.style.left = `${x}px`;
    cursor.style.top = `${y}px`;
    if (click) {
      cursor.classList.remove("click");
      void cursor.offsetWidth;
      cursor.classList.add("click");
    }
  }, { x, y, click });
  await sleep(click ? 520 : 650);
}

async function clickVisible(page, selector) {
  const box = await page.locator(selector).boundingBox();
  if (!box) throw new Error(`cannot click invisible selector: ${selector}`);
  const x = Math.round(box.x + box.width / 2);
  const y = Math.round(box.y + box.height / 2);
  await moveCursor(page, x, y, true);
  await page.mouse.click(x, y);
}

async function scrollTo(page, selector, offset = 70) {
  await page.locator(selector).scrollIntoViewIfNeeded();
  await page.evaluate((offset) => window.scrollBy({ top: -offset, behavior: "smooth" }), offset);
  await sleep(850);
}

async function waitForBudget(startedAt, milliseconds) {
  const remaining = milliseconds - (Date.now() - startedAt);
  if (remaining > 0) await sleep(remaining);
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    deviceScaleFactor: 1,
    recordVideo: { dir: outputDirectory, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(90000);
  const video = page.video();
  const recordingStartedAt = Date.now();
  const markers = [];

  async function scene(index, setup, perform = async () => {}) {
    const segment = segments[index];
    await setup(segment);
    await installOverlay(page, segment);
    const startedAt = Date.now();
    markers.push({
      number: segment.number,
      start_ms: startedAt - recordingStartedAt,
      duration_ms: segment.duration_ms,
      caption: segment.caption,
      url: page.url(),
    });
    await perform(segment);
    await waitForBudget(startedAt, segment.duration_ms);
  }

  try {
    await scene(0, async () => {
      await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
      await page.locator("#proof-status").waitFor({ state: "visible" });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    });

    await scene(1, async () => {
      await scrollTo(page, "#live-story", 52);
    }, async () => {
      await clickVisible(page, "#run-story");
      await page.waitForFunction(() => document.querySelector("#story-state")?.textContent?.startsWith("PASS ·"));
      const state = await page.locator("#story-state").textContent();
      if (!state || !state.includes("live Titan/CockroachDB")) throw new Error(`live story did not prove production path: ${state}`);
    });

    await scene(2, async () => {
      await scrollTo(page, "#story-receipt", 62);
      const receipt = page.locator("#story-receipt");
      await receipt.evaluate((node) => { node.open = true; });
      await page.locator("#story-rls").waitFor({ state: "visible" });
    });

    await scene(3, async () => {
      await page.goto(`${baseUrl}/online-memory-lineage.html`, { waitUntil: "networkidle" });
      await page.waitForFunction(() => document.querySelector("#status")?.textContent === "PASS");
      await scrollTo(page, "#status", 120);
    });

    await scene(4, async () => {
      await page.goto(`${baseUrl}/episodes.html`, { waitUntil: "networkidle" });
      await page.waitForFunction(() => document.querySelector("#digest-status")?.textContent === "PASS");
      await page.locator(".arms").waitFor({ state: "visible" });
      await scrollTo(page, ".incident", 62);
    });

    await scene(5, async () => {
      await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
      await page.locator("#proof-status").waitFor({ state: "visible" });
      await page.waitForFunction(() => document.querySelector("#cas-outcomes")?.textContent !== "—");
      await scrollTo(page, "#outcome-replay-cas", 58);
    });

    await scene(6, async () => {
      await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
      await page.locator("#proof-status").waitFor({ state: "visible" });
      await scrollTo(page, "#architecture", 58);
    });

    await scene(7, async () => {
      await page.goto(`${baseUrl}/verify.html`, { waitUntil: "networkidle" });
      await page.locator("#run").waitFor({ state: "visible" });
    }, async (segment) => {
      for (let attempt = 1; attempt <= 2; attempt += 1) {
        await clickVisible(page, "#run");
        try {
          await page.waitForFunction(
            () => document.querySelector("#run")?.textContent?.startsWith("PASS · browser verified"),
            undefined,
            { timeout: 20000 },
          );
          break;
        } catch (error) {
          if (attempt === 2) throw error;
          await page.reload({ waitUntil: "networkidle" });
          await page.locator("#run").waitFor({ state: "visible" });
          await installOverlay(page, segment);
        }
      }
      await scrollTo(page, "#run", 110);
    });

    await scene(8, async () => {
      await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
      await page.locator("#proof-status").waitFor({ state: "visible" });
      await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
    });
  } finally {
    await context.close();
    await browser.close();
  }

  const videoPath = await video.path();
  const target = path.join(outputDirectory, "continuum-live-browser-v9.webm");
  fs.copyFileSync(videoPath, target);
  fs.writeFileSync(markersPath, JSON.stringify({ recording_started_at: recordingStartedAt, video: target, markers }, null, 2) + "\n");
  process.stdout.write(JSON.stringify({ video: target, markers: markersPath, scenes: markers.length }) + "\n");
})().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exitCode = 1;
});
