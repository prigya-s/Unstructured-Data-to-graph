import { chromium } from "file:///C:/Users/PrigyaShukla/AppData/Local/npm-cache/_npx/db89d7302a373f10/node_modules/playwright/index.mjs";

const TIMEOUT = 90_000; // 90 s for the LLM call

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`PAGE ERROR: ${err.message}`));

  console.log("Navigating to /chat …");
  await page.goto("http://localhost:5173/chat", { waitUntil: "networkidle" });

  // Wait for the text input to be enabled (thread created)
  console.log("Waiting for input to be enabled …");
  const input = page.locator('input[type="text"]');
  await input.waitFor({ state: "visible", timeout: 15_000 });
  await page.waitForFunction(
    () => !document.querySelector('input[type="text"]')?.disabled,
    null,
    { timeout: 15_000 },
  );
  console.log("Input is enabled — thread created.");

  // Type and submit the question
  const question = "What entities are in the knowledge graph?";
  console.log(`Typing: "${question}"`);
  await input.fill(question);
  await page.keyboard.press("Enter");

  // Wait for assistant reply (up to 90 s)
  console.log("Waiting for assistant reply (up to 90 s) …");
  const assistantBubble = page.locator(".chat-bubble--assistant:not(.chat-bubble--pending)");
  await assistantBubble.first().waitFor({ state: "visible", timeout: TIMEOUT });

  // Give a moment for any final DOM updates
  await page.waitForTimeout(1000);

  // --- Inspect the rendered HTML structure ---
  const bubbleHtml = await assistantBubble.first().innerHTML();
  const bubbleText = await assistantBubble.first().innerText();

  // Check for <ul><li> elements
  const hasUl = bubbleHtml.includes("<ul>");
  const hasLi = bubbleHtml.includes("<li>");
  const hasParagraph = bubbleHtml.includes("<p>");
  const hasBold = bubbleHtml.includes("<strong>");

  console.log("\n=== ASSISTANT BUBBLE HTML (first 2000 chars) ===");
  console.log(bubbleHtml.slice(0, 2000));

  console.log("\n=== PLAIN TEXT (first 500 chars) ===");
  console.log(bubbleText.slice(0, 500));

  console.log("\n=== MARKDOWN RENDER CHECK ===");
  console.log(`  Has <ul>: ${hasUl}`);
  console.log(`  Has <li>: ${hasLi}`);
  console.log(`  Has <p>: ${hasParagraph}`);
  console.log(`  Has <strong>: ${hasBold}`);

  // Literal-star check (would indicate bug is still present)
  const literalStarPattern = /\* [A-Za-z]/;
  const rawTextInPage = await page.evaluate(() => document.body.innerText);
  const stillHasLiteralStar = literalStarPattern.test(rawTextInPage);
  console.log(`  Literal '* Item' still in page text: ${stillHasLiteralStar}`);

  // --- "Show sources" ---
  const showSourcesBtn = page.locator("button.sources__toggle");
  const hasSources = await showSourcesBtn.count();
  console.log(`\n=== SOURCES PANEL ===`);
  console.log(`  "Show sources" button present: ${hasSources > 0}`);

  if (hasSources > 0) {
    await showSourcesBtn.first().click();
    const sourcesContent = page.locator(".sources__content");
    await sourcesContent.first().waitFor({ state: "visible", timeout: 5_000 });
    const sourcesHtml = await sourcesContent.first().innerHTML();
    console.log(`  Sources panel expanded successfully.`);
    console.log(`  Sources HTML (first 800 chars): ${sourcesHtml.slice(0, 800)}`);
  }

  // --- Console errors ---
  console.log(`\n=== BROWSER CONSOLE ERRORS (${consoleErrors.length}) ===`);
  if (consoleErrors.length === 0) {
    console.log("  None.");
  } else {
    consoleErrors.forEach((e, i) => console.log(`  [${i + 1}] ${e}`));
  }

  await browser.close();
  process.exit(0);
})().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
