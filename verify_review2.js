// Detailed investigation of /review page 404s and DOM state
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors = [];
  const networkErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(`[CONSOLE ERROR] ${msg.text()}`);
    }
    if (msg.type() === 'warn') {
      console.log(`[WARN] ${msg.text()}`);
    }
  });

  page.on('response', resp => {
    if (!resp.ok() && resp.status() !== 304) {
      networkErrors.push(`${resp.status()} ${resp.request().method()} ${resp.url()}`);
    }
  });

  page.on('pageerror', err => {
    consoleErrors.push(`[PAGE ERROR] ${err.message}`);
  });

  // =====================================================
  // Navigate to /review and capture full state
  // =====================================================
  console.log('=== Navigating to /review ===');
  await page.goto('http://localhost:5173/review', { waitUntil: 'networkidle' });
  await page.waitForTimeout(3000);

  console.log('\n--- Network errors (non-2xx/304 responses) ---');
  networkErrors.forEach(e => console.log(e));
  networkErrors.length = 0;

  console.log('\n--- Console errors ---');
  consoleErrors.forEach(e => console.log(e));
  consoleErrors.length = 0;

  // Get all headings
  const allHeadings = await page.$$eval('h1, h2, h3, h4', els =>
    els.map(el => `${el.tagName}: ${el.textContent.trim()}`)
  );
  console.log('\n--- All headings ---');
  allHeadings.forEach(h => console.log(h));

  // Get page title / top-level text
  const bodyText = await page.textContent('body');
  console.log('\n--- Body text (first 2000 chars) ---');
  console.log(bodyText.substring(0, 2000));

  // Check if there's any loading state or spinner
  const loadingEls = await page.$$('[class*="loading"], [class*="spinner"], [class*="skeleton"]');
  console.log(`\nLoading/spinner elements: ${loadingEls.length}`);

  // Check for any error messages rendered on page
  const errorEls = await page.$$('[class*="error"], [class*="Error"], [role="alert"]');
  console.log(`Error elements on page: ${errorEls.length}`);
  for (const el of errorEls) {
    const text = await el.textContent();
    console.log(`  Error el text: "${text.trim().substring(0, 100)}"`);
  }

  // Get main content area structure
  const mainContent = await page.$('#root, #app, main, .main-content, .content');
  if (mainContent) {
    const innerHTML = await mainContent.innerHTML();
    console.log('\n--- Main content innerHTML (first 3000 chars) ---');
    console.log(innerHTML.substring(0, 3000));
  } else {
    console.log('\nNo main content element found');
    const rootEl = await page.$('#root');
    if (rootEl) {
      const rootHTML = await rootEl.innerHTML();
      console.log('Root element innerHTML (first 3000):', rootHTML.substring(0, 3000));
    }
  }

  // =====================================================
  // Wait longer and check again in case it's async
  // =====================================================
  console.log('\n--- Waiting 5 more seconds for async loads ---');
  await page.waitForTimeout(5000);

  const h2sAfterWait = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  console.log('h2s after 5s wait:', JSON.stringify(h2sAfterWait));

  const detailsAfterWait = await page.$$('details');
  console.log(`<details> elements after wait: ${detailsAfterWait.length}`);

  // Check if there are any more network errors after wait
  if (networkErrors.length > 0) {
    console.log('\n--- New network errors after wait ---');
    networkErrors.forEach(e => console.log(e));
  }

  if (consoleErrors.length > 0) {
    console.log('\n--- New console errors after wait ---');
    consoleErrors.forEach(e => console.log(e));
  }

  // =====================================================
  // Check source code for the Review page component
  // =====================================================
  await browser.close();
})();
