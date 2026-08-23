import { chromium } from "playwright";

const BASE = "http://localhost:5173";
const RESULTS = [];
const CONSOLE_ERRORS = [];

function log(step, status, detail = "") {
  const line = `[${status}] Step ${step}: ${detail}`;
  console.log(line);
  RESULTS.push({ step, status, detail });
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Capture all console errors throughout the session
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const text = msg.text();
      CONSOLE_ERRORS.push(text);
      console.error("[CONSOLE ERROR]", text);
    }
  });
  page.on("pageerror", (err) => {
    CONSOLE_ERRORS.push(`[pageerror] ${err.message}`);
    console.error("[PAGE ERROR]", err.message);
  });

  try {
    // ── Step 1: Navigate to /chat, wait for input ────────────────────────────
    await page.goto(`${BASE}/chat`, { waitUntil: "networkidle" });
    // Input is disabled while threadId is null; wait up to 10 s for it to become enabled
    const inputSel = 'input[placeholder="Ask a question about the knowledge graph..."]';
    try {
      await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 10_000 });
      log(1, "PASS", "Navigated to /chat, input is enabled");
    } catch {
      log(1, "FAIL", "Input did not become enabled within 10 s");
      await browser.close();
      printSummary();
      return;
    }

    // ── Step 2: Send first message ───────────────────────────────────────────
    const msg1 = "What entities are in the knowledge graph?";
    await page.fill(inputSel, msg1);
    await page.click('button[type="submit"]');

    // Wait for user bubble to appear
    await page.waitForSelector(".chat-bubble--user", { timeout: 5_000 });

    // Wait for assistant reply – real LLM call, allow 90 s
    let assistantReply1 = null;
    try {
      await page.waitForFunction(
        () => document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)").length >= 1,
        { timeout: 90_000 }
      );
      assistantReply1 = await page.textContent(".chat-bubble--assistant:not(.chat-bubble--pending)");
      log(2, "PASS", `Got assistant reply (first 120 chars): "${assistantReply1?.slice(0, 120)}"`);
    } catch {
      log(2, "FAIL", "No assistant reply within 90 s");
      await browser.close();
      printSummary();
      return;
    }

    // ── Step 3: SPA nav away and back ────────────────────────────────────────
    await page.click('a:has-text("Dashboard")');
    await page.waitForURL(`${BASE}/`, { timeout: 5_000 });
    await page.click('a:has-text("Ask the Knowledge Graph")');
    await page.waitForURL(`${BASE}/chat`, { timeout: 5_000 });

    // Give React a moment to mount and render stored messages
    await page.waitForTimeout(500);

    const userBubbles3 = await page.$$(".chat-bubble--user");
    const assistantBubbles3 = await page.$$(".chat-bubble--assistant:not(.chat-bubble--pending)");
    if (userBubbles3.length >= 1 && assistantBubbles3.length >= 1) {
      log(3, "PASS", `After SPA nav: ${userBubbles3.length} user bubble(s), ${assistantBubbles3.length} assistant bubble(s) visible`);
    } else {
      log(3, "FAIL", `After SPA nav: ${userBubbles3.length} user bubble(s), ${assistantBubbles3.length} assistant bubble(s) — expected ≥1 each`);
    }

    // ── Step 4: Full page reload ─────────────────────────────────────────────
    await page.reload({ waitUntil: "networkidle" });
    // Input should become enabled (thread_id restored from localStorage)
    try {
      await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 10_000 });
    } catch {
      log(4, "FAIL", "Input did not re-enable after reload");
      await browser.close();
      printSummary();
      return;
    }
    await page.waitForTimeout(300);

    const userBubbles4 = await page.$$(".chat-bubble--user");
    const assistantBubbles4 = await page.$$(".chat-bubble--assistant:not(.chat-bubble--pending)");
    if (userBubbles4.length >= 1 && assistantBubbles4.length >= 1) {
      log(4, "PASS", `After full reload: ${userBubbles4.length} user bubble(s), ${assistantBubbles4.length} assistant bubble(s) visible`);
    } else {
      log(4, "FAIL", `After full reload: ${userBubbles4.length} user bubble(s), ${assistantBubbles4.length} assistant bubble(s) — expected ≥1 each`);
    }

    // ── Step 5: Second message ───────────────────────────────────────────────
    const msg2 = "What relationships exist between them?";
    await page.fill(inputSel, msg2);
    await page.click('button[type="submit"]');

    // Wait for a second real (non-pending) assistant bubble
    let assistantCount5 = 0;
    let userCount5 = 0;
    try {
      await page.waitForFunction(
        () => document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)").length >= 2,
        { timeout: 90_000 }
      );
      assistantCount5 = (await page.$$(".chat-bubble--assistant:not(.chat-bubble--pending)")).length;
      userCount5 = (await page.$$(".chat-bubble--user")).length;
      const total = assistantCount5 + userCount5;
      if (userCount5 >= 2 && assistantCount5 >= 2 && total >= 4) {
        log(5, "PASS", `Full conversation: ${userCount5} user + ${assistantCount5} assistant = ${total} total bubbles`);
      } else {
        log(5, "FAIL", `Expected ≥4 total (2 user + 2 assistant), got ${userCount5} user + ${assistantCount5} assistant`);
      }
    } catch {
      log(5, "FAIL", "Second assistant reply did not arrive within 90 s");
    }

    // ── Step 6: New conversation ─────────────────────────────────────────────
    await page.click('button:has-text("New conversation")');
    await page.waitForTimeout(1_000); // Allow async createChatThread to complete

    const bubblesAfterClear = await page.$$(".chat-bubble");
    if (bubblesAfterClear.length === 0) {
      log("6a", "PASS", "Chat log cleared after 'New conversation'");
    } else {
      log("6a", "FAIL", `Chat log still has ${bubblesAfterClear.length} bubble(s) after 'New conversation'`);
    }

    // Input should be enabled (fresh thread created)
    try {
      await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 10_000 });
    } catch {
      log("6b", "FAIL", "Input did not become enabled after new conversation");
      await browser.close();
      printSummary();
      return;
    }

    // Send a short test message to confirm fresh thread works
    const msg3 = "Hello from fresh thread";
    await page.fill(inputSel, msg3);
    await page.click('button[type="submit"]');
    try {
      await page.waitForFunction(
        () => document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)").length >= 1,
        { timeout: 90_000 }
      );
      log("6b", "PASS", "Fresh thread accepted a new message and received assistant reply");
    } catch {
      log("6b", "FAIL", "Fresh thread did not receive assistant reply within 90 s");
    }

  } catch (err) {
    console.error("Unexpected error:", err);
    RESULTS.push({ step: "?", status: "ERROR", detail: String(err) });
  } finally {
    await browser.close();
  }

  printSummary();
}

function printSummary() {
  console.log("\n====== RESULTS ======");
  for (const r of RESULTS) {
    console.log(`Step ${r.step}: ${r.status} — ${r.detail}`);
  }
  console.log("\n====== CONSOLE ERRORS ======");
  if (CONSOLE_ERRORS.length === 0) {
    console.log("(none)");
  } else {
    for (const e of CONSOLE_ERRORS) {
      console.log(e);
    }
  }
}

run().catch(console.error);
