// Isolated test for step 6b: verify "New conversation" creates a working fresh thread
// Assumes a conversation already exists in localStorage from the main test, but if not it
// seeds one first.
import { chromium } from "playwright";

const BASE = "http://localhost:5173";
const CONSOLE_ERRORS = [];

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

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

  const inputSel = 'input[placeholder="Ask a question about the knowledge graph..."]';

  try {
    // Navigate and wait for input
    await page.goto(`${BASE}/chat`, { waitUntil: "networkidle" });
    await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 15_000 });
    console.log("[INFO] Page loaded, input enabled");

    // Seed: send one message so we have something to clear
    console.log("[INFO] Seeding a message to have something to clear...");
    await page.fill(inputSel, "Brief test seed message");
    await page.click('button[type="submit"]');
    // Wait for the user bubble at minimum
    await page.waitForSelector(".chat-bubble--user", { timeout: 5_000 });
    console.log("[INFO] User bubble visible, waiting for assistant reply (up to 90s)...");
    await page.waitForFunction(
      () => document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)").length >= 1,
      { timeout: 90_000 }
    );
    console.log("[INFO] Seed reply received");

    // Click New conversation
    await page.click('button:has-text("New conversation")');
    console.log("[INFO] Clicked 'New conversation'");

    // Wait for messages to clear
    await page.waitForFunction(
      () => document.querySelectorAll(".chat-bubble").length === 0,
      { timeout: 5_000 }
    );
    console.log("[PASS] 6a: Chat log cleared");

    // Wait for input to be enabled (new thread_id set)
    await page.waitForSelector(`${inputSel}:not([disabled])`, { timeout: 15_000 });
    console.log("[INFO] Input enabled after new conversation");

    // Inspect the localStorage to confirm a new threadId was stored
    const stored = await page.evaluate(() => localStorage.getItem("kg-local-chat"));
    console.log("[INFO] localStorage after new conversation:", stored ? stored.slice(0, 200) : "(empty)");

    // Send a message on the fresh thread
    console.log("[INFO] Sending message on fresh thread (up to 120s for reply)...");
    await page.fill(inputSel, "Hello from fresh thread");
    await page.click('button[type="submit"]');
    await page.waitForSelector(".chat-bubble--user", { timeout: 5_000 });
    console.log("[INFO] User bubble visible");

    try {
      await page.waitForFunction(
        () => document.querySelectorAll(".chat-bubble--assistant:not(.chat-bubble--pending)").length >= 1,
        { timeout: 120_000 }
      );
      const reply = await page.textContent(".chat-bubble--assistant:not(.chat-bubble--pending)");
      console.log(`[PASS] 6b: Fresh thread reply (first 120 chars): "${reply?.slice(0, 120)}"`);
    } catch {
      // Check for error state on page
      const errorEl = await page.$(".error");
      const errorText = errorEl ? await errorEl.textContent() : null;
      const pendingEl = await page.$(".chat-bubble--pending");
      console.log(`[FAIL] 6b: No reply in 120s. Error on page: ${errorText ?? "(none)"}. Still pending: ${!!pendingEl}`);
      // Grab DOM snapshot for debugging
      const bubbles = await page.$$eval(".chat-bubble", els => els.map(el => el.className + ": " + el.textContent?.slice(0, 80)));
      console.log("[DEBUG] Chat bubbles:", JSON.stringify(bubbles));
    }
  } catch (err) {
    console.error("[ERROR]", err);
  } finally {
    await browser.close();
  }

  console.log("\n====== CONSOLE ERRORS ======");
  if (CONSOLE_ERRORS.length === 0) {
    console.log("(none)");
  } else {
    CONSOLE_ERRORS.forEach(e => console.log(e));
  }
}

run().catch(console.error);
