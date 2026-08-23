// Playwright verification script for kg-local React migration
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(`[CONSOLE ERROR] ${msg.text()}`);
    }
  });
  page.on('pageerror', err => {
    consoleErrors.push(`[PAGE ERROR] ${err.message}`);
  });

  function logErrors(label) {
    if (consoleErrors.length > 0) {
      console.log(`\n--- Console errors at "${label}" ---`);
      consoleErrors.forEach(e => console.log(e));
    } else {
      console.log(`  [No console errors at "${label}"]`);
    }
    consoleErrors.length = 0;
  }

  // =====================================================
  // STEP 3 FIRST: Check sidebar
  // =====================================================
  console.log('\n=== STEP 3: Sidebar navigation check ===');
  await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1000);

  // Get all nav links text
  const navLinks = await page.$$eval('nav a, aside a, [role="navigation"] a, .sidebar a, .nav-link, .sidebar-link',
    els => els.map(el => el.textContent.trim()).filter(t => t.length > 0)
  );
  console.log('Sidebar nav links found:', JSON.stringify(navLinks));

  // Also try to get sidebar title
  const sidebarTitle = await page.$eval(
    '.sidebar h1, .sidebar h2, .sidebar-title, aside h1, aside h2, nav h1, nav h2',
    el => el.textContent.trim()
  ).catch(() => '(no sidebar title element found)');
  console.log('Sidebar title:', sidebarTitle);

  // Check for forbidden links
  const forbidden = ['entity review', 'relationships', 'ambiguity resolution', 'graph impact analysis', 'graph difference view'];
  const presentForbidden = navLinks.filter(l => forbidden.some(f => l.toLowerCase().includes(f)));
  if (presentForbidden.length > 0) {
    console.log('FAIL: Forbidden sidebar links present:', JSON.stringify(presentForbidden));
  } else {
    console.log('PASS: No forbidden leftover links in sidebar');
  }

  const expected7 = ['dashboard', 'review', 'candidate graph', 'production graph', 'ontology preview', 'publish', 'ask the knowledge graph'];
  const missing = expected7.filter(e => !navLinks.some(l => l.toLowerCase().includes(e)));
  if (missing.length > 0) {
    console.log('FAIL: Missing expected sidebar links:', JSON.stringify(missing));
  } else {
    console.log('PASS: All 7 expected sidebar links present');
  }

  logErrors('sidebar check');

  // =====================================================
  // STEP 1: /review page
  // =====================================================
  console.log('\n=== STEP 1: /review page ===');
  await page.goto('http://localhost:5173/review', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  // Check for h2 headings
  const h2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  console.log('h2 headings on /review:', JSON.stringify(h2s));

  const hasEntityReview = h2s.some(h => h.toLowerCase().includes('entity review'));
  const hasRelReview = h2s.some(h => h.toLowerCase().includes('relationship review'));
  const hasAmbiguity = h2s.some(h => h.toLowerCase().includes('ambiguity'));
  console.log(`Entity Review h2: ${hasEntityReview ? 'PASS' : 'FAIL'}`);
  console.log(`Relationship Review h2: ${hasRelReview ? 'PASS' : 'FAIL'}`);
  console.log(`Ambiguity Resolution h2: ${hasAmbiguity ? 'PASS' : 'FAIL'}`);

  // Check for tab-strip UI (should NOT exist)
  const tabStrip = await page.$('[role="tablist"], .tab-strip, .tabs, [data-tabs]');
  if (tabStrip) {
    console.log('FAIL: Tab-strip UI found (should not exist)');
  } else {
    console.log('PASS: No tab-strip UI found');
  }

  // Check for section dividers
  const dividers = await page.$$('hr.section-divider, hr');
  console.log(`Section <hr> dividers found: ${dividers.length}`);

  // Check Entity Review section filters
  const checkboxes = await page.$$('input[type="checkbox"]');
  console.log(`Status-filter checkboxes found: ${checkboxes.length}`);

  // Check for "Approve all" button
  const approveAllBtn = await page.$('button:has-text("Approve all")');
  if (approveAllBtn) {
    const approveText = await approveAllBtn.textContent();
    console.log(`PASS: "Approve all" button found: "${approveText.trim()}"`);
  } else {
    console.log('FAIL or N/A: No "Approve all" button found (may be absent if 0 filtered pending)');
  }

  // Check for collapsible details rows
  const detailsRows = await page.$$('details');
  console.log(`Collapsible <details> rows found: ${detailsRows.length}`);

  logErrors('review page initial load');

  // --- Open first entity details ---
  if (detailsRows.length > 0) {
    console.log('\n--- Opening first entity <details> ---');
    const firstDetails = detailsRows[0];
    const summary = await firstDetails.$('summary');
    if (summary) {
      const summaryText = await summary.textContent();
      console.log(`First details summary text: "${summaryText.trim().substring(0, 80)}"`);
      await summary.click();
      await page.waitForTimeout(800);

      // Check internal structure
      const defTextarea = await firstDetails.$('textarea');
      const textareas = await firstDetails.$$('textarea');
      console.log(`Textareas inside details: ${textareas.length}`);

      // Check for Save/Approve/Reject buttons
      const saveBtn = await firstDetails.$('button:has-text("Save")');
      const approveBtn = await firstDetails.$('button:has-text("Approve")');
      const rejectBtn = await firstDetails.$('button:has-text("Reject")');
      console.log(`Save button: ${saveBtn ? 'FOUND' : 'NOT FOUND'}`);
      console.log(`Approve button: ${approveBtn ? 'FOUND' : 'NOT FOUND'}`);
      console.log(`Reject button: ${rejectBtn ? 'FOUND' : 'NOT FOUND'}`);

      // Check for merge target dropdown
      const mergeSelect = await firstDetails.$('select');
      console.log(`Merge target dropdown: ${mergeSelect ? 'FOUND' : 'NOT FOUND'}`);

      // Check for confidence tile
      const confidenceTile = await firstDetails.$('.confidence, [class*="confidence"], [data-confidence]');
      console.log(`Confidence tile: ${confidenceTile ? 'FOUND' : 'NOT FOUND (may use different class)'}`);

      // --- SAVE PERSISTENCE TEST ---
      console.log('\n--- Save persistence test ---');
      if (textareas.length > 0 && saveBtn) {
        const firstTextarea = textareas[0];
        const originalValue = await firstTextarea.inputValue();
        console.log(`Definition textarea current value (first 60 chars): "${originalValue.substring(0, 60)}"`);

        // Get the entity key from summary for re-identification
        const entitySummaryText = summaryText.trim().substring(0, 60);

        // Append " (test)" to the textarea
        await firstTextarea.click();
        await firstTextarea.fill(originalValue + ' (test)');
        console.log('Appended " (test)" to definition textarea');

        // Capture network response for Save
        const [response] = await Promise.all([
          page.waitForResponse(resp => resp.url().includes('/api/') && resp.request().method() !== 'GET', { timeout: 8000 }).catch(() => null),
          saveBtn.click()
        ]);

        await page.waitForTimeout(1000);

        if (response) {
          console.log(`Save API response: ${response.status()} ${response.url()}`);
          const ok = response.ok();
          console.log(`Save response OK: ${ok ? 'PASS' : 'FAIL'}`);
        } else {
          console.log('Save API response: (no non-GET API call detected in 8s)');
        }

        // Check for error banners
        const errorBanner = await page.$('.error, [class*="error"], [class*="Error"], [role="alert"]');
        if (errorBanner) {
          const bannerText = await errorBanner.textContent();
          console.log(`Error banner after save: "${bannerText.trim()}"`);
        } else {
          console.log('No error banner after save — PASS');
        }

        logErrors('after save click');

        // Reload and check persistence
        console.log('\n--- Reloading page to verify persistence ---');
        await page.goto('http://localhost:5173/review', { waitUntil: 'networkidle' });
        await page.waitForTimeout(2000);

        const detailsAfterReload = await page.$$('details');
        if (detailsAfterReload.length > 0) {
          // Find the same entity by summary text
          let targetDetails = null;
          for (const d of detailsAfterReload) {
            const s = await d.$('summary');
            if (s) {
              const st = await s.textContent();
              if (st.trim().substring(0, 60) === entitySummaryText) {
                targetDetails = d;
                break;
              }
            }
          }
          if (!targetDetails) targetDetails = detailsAfterReload[0]; // fallback to first

          const sumEl = await targetDetails.$('summary');
          if (sumEl) await sumEl.click();
          await page.waitForTimeout(800);

          const textareasAfter = await targetDetails.$$('textarea');
          if (textareasAfter.length > 0) {
            const valueAfterReload = await textareasAfter[0].inputValue();
            if (valueAfterReload.endsWith(' (test)') || valueAfterReload.includes('(test)')) {
              console.log('PASS: Persistence check — "(test)" suffix persisted after reload');
            } else {
              console.log(`FAIL: Persistence check — value after reload: "${valueAfterReload.substring(0, 80)}" (expected "(test)" suffix)`);
            }
          } else {
            console.log('Could not find textarea after reload to verify persistence');
          }
        }

        logErrors('after reload persistence check');
      } else {
        console.log('No textarea or Save button found — skipping save persistence test');
      }
    }
  } else {
    console.log('No <details> rows found on /review page');
  }

  // =====================================================
  // Check Relationship Review section
  // =====================================================
  console.log('\n--- Relationship Review section check ---');
  await page.goto('http://localhost:5173/review', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  const allDetails = await page.$$('details');
  console.log(`Total <details> rows on page: ${allDetails.length}`);

  // Look for Relationship Review h2 and its section
  const relH2 = await page.$('h2:has-text("Relationship Review"), h2:has-text("Relationship")');
  if (relH2) {
    console.log('PASS: Relationship Review h2 found');
  } else {
    console.log('FAIL: Relationship Review h2 not found');
  }

  // Check Ambiguity section
  const ambigH2 = await page.$('h2:has-text("Ambiguity")');
  if (ambigH2) {
    console.log('PASS: Ambiguity Resolution h2 found');

    // Check for radio buttons or empty-state message
    const radios = await page.$$('input[type="radio"]');
    const emptyMsg = await page.$('text=/No ambiguous/i, text=/no ambiguous/i');
    if (radios.length > 0) {
      console.log(`PASS: ${radios.length} radio button(s) found in ambiguity section`);
      // Check for "None of the above" option
      const noneOption = await page.$('label:has-text("None of the above"), input[value*="none"]');
      console.log(`"None of the above" option: ${noneOption ? 'FOUND' : 'NOT FOUND'}`);
    } else {
      // Check for empty state message
      const pageText = await page.textContent('body');
      if (pageText.toLowerCase().includes('no ambiguous')) {
        console.log('PASS: Empty-state "no ambiguous entities" message found (expected if no ambiguities)');
      } else {
        console.log('INFO: No radio buttons and no explicit empty-state message found for ambiguity');
      }
    }
  } else {
    console.log('FAIL: Ambiguity Resolution h2 not found');
  }

  logErrors('relationship and ambiguity sections');

  // =====================================================
  // STEP 2: /candidate-graph page
  // =====================================================
  console.log('\n=== STEP 2: /candidate-graph page ===');
  await page.goto('http://localhost:5173/candidate-graph', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);

  const candH2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  console.log('h2 headings on /candidate-graph:', JSON.stringify(candH2s));

  // Check existing entity/relationship tables
  const tables = await page.$$('table');
  console.log(`Tables found: ${tables.length}`);

  // Check for GraphDiffSection headings
  const hasImpact = candH2s.some(h => h.toLowerCase().includes('impact'));
  const hasDiff = candH2s.some(h => h.toLowerCase().includes('diff') || h.toLowerCase().includes('difference'));
  console.log(`"Graph Impact Analysis" section: ${hasImpact ? 'PASS' : 'FAIL'}`);
  console.log(`"Graph Difference View" section: ${hasDiff ? 'PASS' : 'FAIL'}`);

  // Scroll to bottom to trigger lazy rendering
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(1000);

  // Re-check after scroll
  const candH2sAfterScroll = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  console.log('h2 headings after scroll:', JSON.stringify(candH2sAfterScroll));

  const hasImpactAfter = candH2sAfterScroll.some(h => h.toLowerCase().includes('impact'));
  const hasDiffAfter = candH2sAfterScroll.some(h => h.toLowerCase().includes('diff') || h.toLowerCase().includes('difference'));
  console.log(`"Graph Impact Analysis" after scroll: ${hasImpactAfter ? 'PASS' : 'FAIL'}`);
  console.log(`"Graph Difference View" after scroll: ${hasDiffAfter ? 'PASS' : 'FAIL'}`);

  // Check for metric tiles in impact section
  const metricTiles = await page.$$('.metric-tile, [class*="metric"], [class*="tile"], [class*="stat"]');
  console.log(`Metric/stat tiles found: ${metricTiles.length}`);

  // Check for diff tables or empty-state messages
  const pageText2 = await page.textContent('body');
  const diffKeywords = ['added', 'removed', 'modified', 'merged', 'no new entities', 'no new relationships'];
  const foundDiffKeywords = diffKeywords.filter(k => pageText2.toLowerCase().includes(k));
  console.log(`Diff-section keywords found: ${JSON.stringify(foundDiffKeywords)}`);

  logErrors('/candidate-graph page');

  // Final summary
  console.log('\n=== ALL DONE ===');
  console.log('Total console errors captured overall:', consoleErrors.length);

  await browser.close();
})();
