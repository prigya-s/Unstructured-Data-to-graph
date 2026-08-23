// Isolated step-6b retest with correct Playwright timeout handling.
// Playwright 1.x: page.waitForFunction(fn, arg?, options?) — pass undefined as arg,
// options as third arg. Also set page.setDefaultTimeout() as a belt-and-suspenders.
import { chromium } from "playwright";

const BASE = "http://localhost:5173";
const CONSOLE_ERRORS = [];

async function waitForAssistantReply(page, minCount, timeoutMs) {
  // Use the 3-arg form: fn, arg (undefined), options
  await page.waitForFunction(
    (n) => document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)").length >= n,
    minCount,
    { timeout: timeoutMs }
  );
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  // Belt-and-suspenders: set a long default for all page operations
  page.setDefaultTimeout(120_000);

  page.on("console", (msg) => {
    if (msg.type() === "error") {
      CONSOLE_ERRORS.push(msg.text());
      console.error("[CONSOLE ERROR]", msg.text());
    }
  });
  page.on("pageerror", (err) => {
    CONSOLE_ERRORS.push(`[pageerror] ${err.message}`);
    console.error("[PAGE ERROR]", err.message);
  });

  const inputSel = 'input[placeholder="Ask a question about the knowledge graph..."]';

  try {
    // Navigate and wait for input
    console.log("[INFO] Navigating to /chat...");
    await page.goto(`${BASE}/chat`, { waitUntil: "networkidle" });
    await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 15_000 });
    console.log("[INFO] Input enabled");

    // Seed one message
    console.log("[INFO] Sending seed message (up to 120s for reply)...");
    await page.fill(inputSel, "Quick seed: what is the knowledge graph?");
    await page.click('button[type="submit"]');
    await page.waitForSelector(".chat-bubble--user", { timeout: 5_000 });
    await waitForAssistantReply(page, 1, 120_000);
    console.log("[INFO] Seed reply received");

    // Click New conversation
    await page.click('button:has-text("New conversation")');
    console.log("[INFO] Clicked 'New conversation'");

    // Wait for messages to clear
    await page.waitForFunction(
      () => document.querySelectorAll(".chat-bubble").length === 0,
      undefined,
      { timeout: 10_000 }
    );
    console.log("[PASS] 6a: Chat log cleared");

    // Confirm input still enabled (threadId not null during handleNewConversation)
    await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 15_000 });
    console.log("[INFO] Input enabled after new conversation");

    // Inspect localStorage
    const stored = await page.evaluate(() => localStorage.getItem("kg-local-chat"));
    if (stored) {
      const parsed = JSON.parse(stored);
      console.log(`[INFO] localStorage: threadId=${parsed.threadId}, messages=${parsed.messages.length}`);
    } else {
      console.log("[INFO] localStorage is empty (cleared)");
    }

    // Send message on fresh thread
    console.log("[INFO] Sending message on fresh thread (up to 120s for reply)...");
    await page.fill(inputSel, "Hello from fresh thread");
    await page.click('button[type="submit"]');
    await page.waitForSelector(".chat-bubble--user", { timeout: 5_000 });
    console.log("[INFO] User bubble visible, waiting for reply...");

    try {
      await waitForAssistantReply(page, 1, 120_000);
      const reply = await page.textContent(".chat-bubble--assistant:not(.chat-bubble--pending)");
      console.log(`[PASS] 6b: Fresh thread reply received (first 120 chars): "${reply?.slice(0, 120)}"`);
    } catch (e) {
      // Dump diagnostics
      const errorEl = await page.$(".error");
      const errorText = errorEl ? await errorEl.textContent() : null;
      const pendingEl = await page.$(".chat-bubble--pending");
      const bubbles = await page.$$eval(".chat-bubble", els =>
        els.map(el => `${el.className}: ${el.textContent?.slice(0, 80)}`)
      );
      console.log(`[FAIL] 6b: No reply. Error on page: "${errorText ?? "(none)"}". Still pending: ${!!pendingEl}`);
      console.log("[DEBUG] Bubbles:", JSON.stringify(bubbles, null, 2));
      console.log("[DEBUG] Playwright error:", e.message?.slice(0, 200));
    }

  } catch (err) {
    console.error("[ERROR]", err.message ?? err);
  } finally {
    await browser.close();
  }

  console.log("\n====== CONSOLE ERRORS ======");
  console.log(CONSOLE_ERRORS.length === 0 ? "(none)" : CONSOLE_ERRORS.join("\n"));
}

run().catch(console.error);
