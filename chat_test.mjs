// Chat page persistence verification test
// Uses Playwright directly (not @playwright/test) as a standalone Node script

import { chromium } from "playwright";

const BASE = "http://localhost:5173";
const TIMEOUT_LLM = 180_000; // 180s for real LLM calls
const TIMEOUT_NAV = 15_000;

const consoleErrors = [];

async function waitForAssistantReply(page, beforeCount) {
  // Wait for a new assistant bubble to appear beyond what was already there
  await page.waitForFunction(
    (count) => {
      const bubbles = document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)");
      return bubbles.length > count;
    },
    beforeCount,
    { timeout: TIMEOUT_LLM }
  );
}

function countAssistantBubbles(page) {
  return page.$$eval(".chat-bubble--assistant:not(.chat-bubble--pending)", (els) => els.length);
}

function countUserBubbles(page) {
  return page.$$eval(".chat-bubble--user", (els) => els.length);
}

function getBubbleTexts(page) {
  return page.$$eval(".chat-bubble", (els) =>
    els.map((el) => ({
      role: el.classList.contains("chat-bubble--user") ? "user" : "assistant",
      text: el.textContent?.trim().slice(0, 120) ?? "",
    }))
  );
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(`[console.error] ${msg.text()}`);
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(`[pageerror] ${err.message}`);
  });

  const results = {};

  try {
    // ── Step 1: Navigate to /chat, wait for input to become enabled ──────────
    console.log("Step 1: Navigate to /chat...");
    await page.goto(`${BASE}/chat`, { waitUntil: "networkidle", timeout: TIMEOUT_NAV });
    const inputSelector = 'input[placeholder*="Ask a question"]';
    await page.waitForSelector(`${inputSelector}:not([disabled])`, { timeout: TIMEOUT_NAV });
    results[1] = "PASS — input enabled";
    console.log("  PASS");

    // ── Step 2: Send first message and wait for reply ─────────────────────────
    console.log("Step 2: Send first message...");
    const assistantBefore = await countAssistantBubbles(page);
    await page.fill(inputSelector, "What entities are in the knowledge graph?");
    await page.click('button[type="submit"]');
    await waitForAssistantReply(page, assistantBefore);
    const userCount1 = await countUserBubbles(page);
    const assistantCount1 = await countAssistantBubbles(page);
    if (userCount1 >= 1 && assistantCount1 >= 1) {
      results[2] = `PASS — ${userCount1} user msg(s), ${assistantCount1} assistant msg(s)`;
    } else {
      results[2] = `FAIL — user=${userCount1}, assistant=${assistantCount1}`;
    }
    console.log(`  ${results[2]}`);

    // ── Step 3: SPA nav away, then back — check history survives ─────────────
    console.log("Step 3: SPA nav away then back...");
    // Click Dashboard in sidebar
    await page.click('a[href="/"]');
    await page.waitForURL(`${BASE}/`, { timeout: TIMEOUT_NAV });
    // Navigate back via sidebar link
    await page.click('a[href="/chat"]');
    await page.waitForURL(`${BASE}/chat`, { timeout: TIMEOUT_NAV });
    // Allow React to restore state
    await page.waitForTimeout(1000);
    const userCountAfterSPA = await countUserBubbles(page);
    const assistantCountAfterSPA = await countAssistantBubbles(page);
    if (userCountAfterSPA >= 1 && assistantCountAfterSPA >= 1) {
      results[3] = `PASS — history survived SPA nav (user=${userCountAfterSPA}, assistant=${assistantCountAfterSPA})`;
    } else {
      results[3] = `FAIL — chat cleared after SPA nav (user=${userCountAfterSPA}, assistant=${assistantCountAfterSPA})`;
    }
    console.log(`  ${results[3]}`);

    // ── Step 4: Full page reload — check localStorage persistence ─────────────
    console.log("Step 4: Full reload...");
    await page.reload({ waitUntil: "networkidle", timeout: TIMEOUT_NAV });
    await page.waitForSelector(`${inputSelector}:not([disabled])`, { timeout: TIMEOUT_NAV });
    const userCountAfterReload = await countUserBubbles(page);
    const assistantCountAfterReload = await countAssistantBubbles(page);
    if (userCountAfterReload >= 1 && assistantCountAfterReload >= 1) {
      results[4] = `PASS — history survived full reload (user=${userCountAfterReload}, assistant=${assistantCountAfterReload})`;
    } else {
      results[4] = `FAIL — chat cleared after reload (user=${userCountAfterReload}, assistant=${assistantCountAfterReload})`;
    }
    console.log(`  ${results[4]}`);

    // ── Step 5: Send second message — confirm full 4-message thread ───────────
    console.log("Step 5: Send second message...");
    const assistantBefore2 = await countAssistantBubbles(page);
    await page.fill(inputSelector, "What relationships exist between them?");
    await page.click('button[type="submit"]');
    await waitForAssistantReply(page, assistantBefore2);
    const userCountFinal = await countUserBubbles(page);
    const assistantCountFinal = await countAssistantBubbles(page);
    const bubbles = await getBubbleTexts(page);
    if (userCountFinal >= 2 && assistantCountFinal >= 2) {
      results[5] = `PASS — ${userCountFinal} user, ${assistantCountFinal} assistant messages in order`;
    } else {
      results[5] = `FAIL — only user=${userCountFinal}, assistant=${assistantCountFinal} visible`;
    }
    console.log(`  ${results[5]}`);
    console.log("  Message log:");
    bubbles.forEach((b, i) => console.log(`    [${i + 1}] ${b.role}: ${b.text}`));

    // ── Step 6: Click "New conversation" — confirm clear + fresh thread ───────
    console.log("Step 6: New conversation...");
    await page.click('button:text("New conversation")');
    // Wait for messages to clear
    await page.waitForFunction(
      () => document.querySelectorAll(".chat-bubble").length === 0,
      { timeout: 10_000 }
    );
    // Wait for input to become enabled (fresh thread created)
    await page.waitForSelector(`${inputSelector}:not([disabled])`, { timeout: TIMEOUT_NAV });
    const countAfterClear = await countUserBubbles(page);

    // Send a short test message to confirm the new thread works
    const assistantBefore3 = await countAssistantBubbles(page);
    await page.fill(inputSelector, "Hello, fresh thread!");
    await page.click('button[type="submit"]');
    await waitForAssistantReply(page, assistantBefore3);
    const userCountNew = await countUserBubbles(page);
    const assistantCountNew = await countAssistantBubbles(page);

    if (countAfterClear === 0 && userCountNew >= 1 && assistantCountNew >= 1) {
      results[6] = `PASS — cleared (0 msgs after clear), then new thread works (user=${userCountNew}, assistant=${assistantCountNew})`;
    } else {
      results[6] = `FAIL — after clear: ${countAfterClear} user bubbles; after new msg: user=${userCountNew}, assistant=${assistantCountNew}`;
    }
    console.log(`  ${results[6]}`);

  } catch (err) {
    const step = Object.keys(results).length + 1;
    // Capture any error text visible on page
    let pageError = "";
    try {
      pageError = await page.$eval(".error", (el) => el.textContent?.trim() ?? "");
    } catch {}
    const errorDetail = pageError ? ` [page error: ${pageError}]` : "";
    results[step] = `FAIL — unhandled error: ${err.message}${errorDetail}`;
    console.error("  UNHANDLED ERROR:", err.message, errorDetail);
  } finally {
    await browser.close();
  }

  // Print summary
  console.log("\n========== TEST SUMMARY ==========");
  for (const [step, result] of Object.entries(results)) {
    console.log(`Step ${step}: ${result}`);
  }
  console.log("\n========== CONSOLE ERRORS =========");
  if (consoleErrors.length === 0) {
    console.log("  (none)");
  } else {
    consoleErrors.forEach((e) => console.log("  " + e));
  }
  console.log("===================================");
}

run().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
