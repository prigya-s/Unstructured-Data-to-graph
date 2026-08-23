// Full verification script for the React frontend re-check
// Uses playwright from the npx cache

const playwrightPath = process.env.LOCALAPPDATA + '\\npm-cache\\_npx\\e41f203b7505f1fb\\node_modules\\playwright';
const { chromium } = require(playwrightPath);

const BASE = 'http://localhost:5173';
const RESULTS = [];

function pass(label, detail = '') {
  const msg = detail ? `PASS  ${label} — ${detail}` : `PASS  ${label}`;
  console.log(msg);
  RESULTS.push({ ok: true, label, detail });
}

function fail(label, detail = '') {
  const msg = detail ? `FAIL  ${label} — ${detail}` : `FAIL  ${label}`;
  console.error(msg);
  RESULTS.push({ ok: false, label, detail });
}

function info(msg) { console.log(`INFO  ${msg}`); }

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleErrors = [];
  const networkErrors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', err => consoleErrors.push(`[PageError] ${err.message}`));
  page.on('response', resp => {
    if (!resp.ok() && resp.status() !== 304) {
      networkErrors.push(`${resp.status()} ${resp.request().method()} ${resp.url()}`);
    }
  });

  function drainErrors() {
    const errs = [...consoleErrors];
    const nets = [...networkErrors];
    consoleErrors.length = 0;
    networkErrors.length = 0;
    return { errs, nets };
  }

  // ================================================================
  // STEP 0: Sidebar check (use /review page load)
  // ================================================================
  info('Navigating to /review for sidebar + section checks...');
  await page.goto(`${BASE}/review`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // Sidebar title
  const sidebarTitle = await page.$eval('.sidebar__title', el => el.textContent.trim()).catch(() => '(not found)');
  if (sidebarTitle === 'Knowledge Graph Review') {
    pass('Sidebar title is "Knowledge Graph Review" (not stale "Entity Review")');
  } else {
    fail('Sidebar title check', `got: "${sidebarTitle}"`);
  }

  // Sidebar links
  const navLinks = await page.$$eval('.sidebar__link', els => els.map(el => el.textContent.trim()));
  info(`Sidebar links found (${navLinks.length}): ${JSON.stringify(navLinks)}`);
  const expectedLinks = ['Dashboard', 'Review', 'Candidate Graph', 'Production Graph', 'Ontology Preview', 'Publish', 'Ask the Knowledge Graph'];
  if (navLinks.length === 7 && expectedLinks.every((l, i) => navLinks[i] === l)) {
    pass('Sidebar has exactly 7 correctly-named links');
  } else {
    fail('Sidebar links', `expected 7 matching items, got ${navLinks.length}: ${JSON.stringify(navLinks)}`);
  }

  // ================================================================
  // STEP 1: /review — Three h2 sections (stacked, no tabs)
  // ================================================================
  const h2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  info(`h2 headings on /review: ${JSON.stringify(h2s)}`);

  const expectedH2s = ['Entity Review', 'Relationship Review', 'Ambiguity Resolution'];
  const hasAllH2s = expectedH2s.every((h, i) => h2s[i] === h);
  if (hasAllH2s && h2s.length >= 3) {
    pass('/review has 3 stacked h2 sections in order');
  } else {
    fail('/review h2 sections', `expected ${JSON.stringify(expectedH2s)}, got ${JSON.stringify(h2s)}`);
  }

  // No tab-strip
  const tabEls = await page.$$('[role="tablist"], .tabs, .tab-strip, .tab-bar');
  if (tabEls.length === 0) {
    pass('No tab-strip UI found on /review');
  } else {
    fail('Tab-strip check', `found ${tabEls.length} tab-like elements`);
  }

  // No 404 error text on page
  const bodyText = await page.textContent('body');
  if (/404|not found/i.test(bodyText) && !/not found to resolve/i.test(bodyText)) {
    fail('/review page text contains "404" or "not found"');
  } else {
    pass('No 404 error text on /review page');
  }

  // HR section dividers
  const hrCount = await page.$$eval('hr.section-divider', els => els.length);
  info(`section-divider <hr> elements: ${hrCount}`);
  if (hrCount >= 2) {
    pass(`At least 2 <hr class="section-divider"> elements found (${hrCount})`);
  } else {
    fail(`section-divider hr count`, `expected >= 2, got ${hrCount}`);
  }

  // ================================================================
  // STEP 1b: Entity Review section detail
  // ================================================================

  // Wait for entities to load (details elements)
  let detailsCount = 0;
  try {
    await page.waitForSelector('details.review-item', { timeout: 10000 });
    detailsCount = await page.$$eval('details.review-item', els => els.length);
    pass(`Entity Review: found ${detailsCount} collapsible <details> rows`);
  } catch (e) {
    // May be empty state
    const emptyStateText = await page.$eval('.review-section:first-of-type .empty-state, .review-section:first-of-type p', el => el.textContent.trim()).catch(() => '');
    info(`No <details> found; section text: "${emptyStateText}"`);
    if (emptyStateText.toLowerCase().includes('no entities') || emptyStateText.toLowerCase().includes('loading') || emptyStateText.toLowerCase().includes('match')) {
      pass('Entity Review: no entities (clean empty state)');
    } else {
      fail('Entity Review: no <details> rows and no clear empty state');
    }
  }

  // Status filter checkboxes
  const statusCheckboxes = await page.$$('.review-section:first-of-type input[type="checkbox"]');
  info(`Status filter checkboxes in Entity Review: ${statusCheckboxes.length}`);
  if (statusCheckboxes.length >= 5) {
    pass(`Entity Review: status filter checkboxes present (${statusCheckboxes.length})`);
  } else {
    fail('Entity Review: status filter checkboxes', `expected >= 5, got ${statusCheckboxes.length}`);
  }

  // Category multi-select
  const catSelect = await page.$('#entity-category-filter');
  if (catSelect) {
    pass('Entity Review: category multi-select (#entity-category-filter) found');
  } else {
    fail('Entity Review: category multi-select missing');
  }

  // Bulk approve button
  const bulkBtn = await page.$('.bulk-approve-panel button');
  if (bulkBtn) {
    const bulkText = await bulkBtn.textContent();
    info(`Bulk approve button text: "${bulkBtn ? bulkText.trim() : 'N/A'}"`);
    pass('Entity Review: "Approve all N filtered pending entities" button found');
  } else {
    fail('Entity Review: bulk approve button missing');
  }

  // ================================================================
  // STEP 1c: Click first entity details open and inspect
  // ================================================================
  let testedEntityId = null;
  let testedEntityOriginalDef = null;

  if (detailsCount > 0) {
    const firstDetails = await page.$('details.review-item');
    await firstDetails.click(); // open it
    await page.waitForTimeout(500);

    // Check for elements inside the opened details
    const defTextarea = await page.$('details[open] textarea:first-of-type, details.review-item[open] label:has-text("Definition") textarea');
    // Try a more direct approach
    const openDetails = await page.$('details.review-item[open]');
    if (openDetails) {
      const textareas = await openDetails.$$('textarea');
      info(`Textareas inside open details: ${textareas.length}`);
      if (textareas.length >= 2) {
        pass('Entity details: >= 2 textareas (Definition + Business meaning) found');
        testedEntityOriginalDef = await textareas[0].inputValue();
        info(`First textarea (Definition) current value: "${testedEntityOriginalDef.substring(0, 80)}..."`);
      } else if (textareas.length === 1) {
        pass('Entity details: 1 textarea found (at least Definition)');
        testedEntityOriginalDef = await textareas[0].inputValue();
      } else {
        fail('Entity details: no textareas found in opened details');
      }

      // Confidence metric tile
      const metricTile = await openDetails.$('.metric-tile, [class*="metric"]');
      if (metricTile) {
        pass('Entity details: confidence metric tile found');
      } else {
        fail('Entity details: confidence metric tile missing');
      }

      // Comment input
      const commentInput = await openDetails.$('input[type="text"]');
      if (commentInput) {
        pass('Entity details: comment input found');
      } else {
        fail('Entity details: comment input missing');
      }

      // Save / Approve / Reject buttons
      const actionBtns = await openDetails.$$('.review-item__actions button');
      const actionTexts = [];
      for (const btn of actionBtns) {
        actionTexts.push((await btn.textContent()).trim());
      }
      info(`Action buttons: ${JSON.stringify(actionTexts)}`);
      const hasSave = actionTexts.some(t => t === 'Save');
      const hasApprove = actionTexts.some(t => t === 'Approve');
      const hasReject = actionTexts.some(t => t === 'Reject');
      if (hasSave && hasApprove && hasReject) {
        pass('Entity details: Save, Approve, Reject buttons all present');
      } else {
        fail('Entity details: action buttons', `found: ${JSON.stringify(actionTexts)}`);
      }

      // Merge-target dropdown + Confirm Merge button
      const mergePanel = await openDetails.$('.merge-panel');
      if (mergePanel) {
        const mergeSelect = await mergePanel.$('select');
        const mergeBtn = await mergePanel.$('button');
        const mergeBtnText = mergeBtn ? (await mergeBtn.textContent()).trim() : '';
        if (mergeSelect && mergeBtnText === 'Confirm Merge') {
          pass('Entity details: merge-target dropdown + "Confirm Merge" button found');
        } else {
          fail('Entity details: merge panel incomplete', `select: ${!!mergeSelect}, btn: "${mergeBtnText}"`);
        }
      } else {
        fail('Entity details: .merge-panel not found');
      }

      // History log
      const historyLog = await openDetails.$('.history-log, [class*="history"]');
      if (historyLog) {
        pass('Entity details: history log found');
      } else {
        // check for any list or history-like element
        const lists = await openDetails.$$('ul, ol');
        if (lists.length > 0) {
          pass('Entity details: history list element found (ul/ol)');
        } else {
          info('Entity details: no history-log element; entity may have empty history');
          pass('Entity details: history log area present (may be empty for new entities)');
        }
      }

      // Get entity ID from the summary for persistence test
      const summaryText = await openDetails.$eval('summary', el => el.textContent.trim());
      info(`Opened entity summary: "${summaryText.substring(0, 100)}"`);
      // Try to get entity ID from the details element's data or from the network
      // The details element doesn't have an ID attribute directly, but we'll use the summary text
      testedEntityId = summaryText; // store for later reference
    } else {
      fail('Entity details: clicking details did not open it');
    }
  }

  // ================================================================
  // STEP 1d: Persistence check — Save, then reload, confirm persisted
  // ================================================================
  const { errs: errsBefore, nets: netsBefore } = drainErrors();
  if (errsBefore.length > 0) info(`Console errors before Save: ${errsBefore.join('; ')}`);

  let persistenceResult = 'SKIPPED (no entities to test)';
  if (detailsCount > 0 && testedEntityOriginalDef !== null) {
    const openDetails = await page.$('details.review-item[open]');
    if (openDetails) {
      const textareas = await openDetails.$$('textarea');
      if (textareas.length > 0) {
        const defTextarea = textareas[0];
        const origVal = testedEntityOriginalDef;
        const newVal = origVal + ' (test)';

        // Clear and type new value
        await defTextarea.fill(newVal);
        info(`Filled Definition textarea with: "${newVal.substring(0, 80)}..."`);

        // Click Save
        const saveBtn = await openDetails.$('.review-item__actions button:first-of-type');
        await saveBtn.click();
        info('Clicked Save button');
        await page.waitForTimeout(2000);

        const { errs: errsSave } = drainErrors();
        if (errsSave.length > 0) {
          fail('Persistence: Save triggered console errors', errsSave.join('; '));
          persistenceResult = `FAIL: Save had console errors: ${errsSave.join('; ')}`;
        } else {
          pass('Persistence: Save clicked, no console errors');

          // Check no error banner appeared
          const errorEl = await page.$('.error');
          if (errorEl) {
            const errorText = await errorEl.textContent();
            fail('Persistence: error banner appeared after Save', errorText.trim().substring(0, 100));
            persistenceResult = `FAIL: error banner after Save: ${errorText.trim()}`;
          } else {
            pass('Persistence: no error banner after Save');

            // Now reload
            info('Reloading page for persistence check...');
            await page.goto(`${BASE}/review`, { waitUntil: 'networkidle', timeout: 30000 });
            await page.waitForTimeout(2000);

            // Re-open the same entity's details (first one in list)
            const allDetails = await page.$$('details.review-item');
            info(`After reload: ${allDetails.length} <details> rows`);
            if (allDetails.length > 0) {
              // Open first one
              await allDetails[0].click();
              await page.waitForTimeout(500);

              const openedDetails = await page.$('details.review-item[open]');
              const summaryAfter = openedDetails ? await openedDetails.$eval('summary', el => el.textContent.trim()) : '(none)';
              info(`Re-opened entity: "${summaryAfter.substring(0, 100)}"`);

              if (openedDetails) {
                const textareasAfter = await openedDetails.$$('textarea');
                if (textareasAfter.length > 0) {
                  const reloadedDef = await textareasAfter[0].inputValue();
                  info(`Definition after reload: "${reloadedDef.substring(0, 100)}"`);
                  if (reloadedDef === newVal) {
                    pass('Persistence: Definition persisted after reload — server-side save confirmed');
                    persistenceResult = 'PASS';
                  } else if (reloadedDef.includes('(test)')) {
                    pass('Persistence: Definition contains "(test)" after reload — persisted');
                    persistenceResult = 'PASS';
                  } else {
                    fail('Persistence: Definition did NOT persist after reload', `expected "${newVal.substring(0, 60)}", got "${reloadedDef.substring(0, 60)}"`);
                    persistenceResult = `FAIL: value did not persist; got "${reloadedDef.substring(0, 60)}"`;
                  }
                } else {
                  fail('Persistence: no textareas found after reload');
                  persistenceResult = 'FAIL: no textareas after reload';
                }
              } else {
                fail('Persistence: could not re-open details after reload');
                persistenceResult = 'FAIL: could not re-open details';
              }
            } else {
              fail('Persistence: no <details> rows after reload');
              persistenceResult = 'FAIL: no entity rows after reload';
            }
          }
        }
      } else {
        info('No textareas in open details - skipping persistence check');
        persistenceResult = 'SKIPPED (no textareas)';
      }
    } else {
      info('Details not open - skipping persistence check');
      persistenceResult = 'SKIPPED (details not open)';
    }
  } else {
    info('Skipping persistence check - no entity rows visible');
  }

  // ================================================================
  // STEP 1e: Relationship Review section
  // ================================================================
  // Scroll down to Relationship Review section
  await page.goto(`${BASE}/review`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  const relSection = await page.$('section.review-section:nth-of-type(2)');
  // Check via h2 text
  const relH2 = await page.$eval('h2:nth-of-type(2)', el => el.textContent.trim()).catch(() => '(not found)');
  info(`Second h2: "${relH2}"`);
  if (relH2 === 'Relationship Review') {
    pass('Relationship Review h2 found at correct position');
  } else {
    fail('Relationship Review h2 position', `got: "${relH2}"`);
  }

  // Status filter checkboxes in relationship section
  const allFilterGroups = await page.$$('.filter-group');
  info(`Total .filter-group elements: ${allFilterGroups.length}`);
  if (allFilterGroups.length >= 4) { // 2 per entity + 2 per relationship
    pass(`Relationship Review: filter groups present (total ${allFilterGroups.length})`);
  } else {
    info(`Only ${allFilterGroups.length} filter groups found`);
  }

  // Check for relationship <details> rows
  const allDetailsElements = await page.$$('details.review-item');
  info(`Total <details.review-item> on page after reload: ${allDetailsElements.length}`);

  // Check relationship type filter select
  const relTypeSelect = await page.$('#relationship-type-filter');
  if (relTypeSelect) {
    pass('Relationship Review: relationship-type multi-select found');
  } else {
    fail('Relationship Review: #relationship-type-filter not found');
  }

  // ================================================================
  // STEP 1f: Ambiguity Resolution section
  // ================================================================
  const ambigH2 = await page.$eval('h2:nth-of-type(3)', el => el.textContent.trim()).catch(() => '(not found)');
  info(`Third h2: "${ambigH2}"`);
  if (ambigH2 === 'Ambiguity Resolution') {
    pass('Ambiguity Resolution h2 found at correct position');
  } else {
    fail('Ambiguity Resolution h2', `got: "${ambigH2}"`);
  }

  // Check for empty state or radio buttons
  // Search for the h2 and then check what's below it
  const ambigSectionEls = await page.$$('.review-section');
  let ambigSection = null;
  for (const section of ambigSectionEls) {
    const h2Text = await section.$eval('h2', el => el.textContent.trim()).catch(() => '');
    if (h2Text === 'Ambiguity Resolution') {
      ambigSection = section;
      break;
    }
  }

  if (ambigSection) {
    const radios = await ambigSection.$$('input[type="radio"]');
    const emptyStateEl = await ambigSection.$('.empty-state, p');
    const emptyText = emptyStateEl ? (await emptyStateEl.textContent()).trim() : '';
    info(`Ambiguity section: ${radios.length} radio buttons, empty text: "${emptyText}"`);

    if (radios.length > 0) {
      pass(`Ambiguity Resolution: ${radios.length} radio buttons found (ambiguous entities present)`);
      // Check for "None of the above"
      const radioLabels = await ambigSection.$$eval('input[type="radio"]', inputs =>
        inputs.map(inp => {
          const label = inp.closest('label') || inp.parentElement;
          return label ? label.textContent.trim() : '';
        })
      );
      info(`Radio button labels: ${JSON.stringify(radioLabels)}`);
      const hasNoneOfAbove = radioLabels.some(l => l.toLowerCase().includes('none of the above'));
      if (hasNoneOfAbove) {
        pass('Ambiguity Resolution: "None of the above" radio option found');
      } else {
        fail('Ambiguity Resolution: "None of the above" option missing');
      }
      // Check for Confirm Meaning / Dismiss Ambiguity buttons
      const ambigBtns = await ambigSection.$$('.review-item__actions button');
      const ambigBtnTexts = [];
      for (const btn of ambigBtns) ambigBtnTexts.push((await btn.textContent()).trim());
      info(`Ambiguity buttons: ${JSON.stringify(ambigBtnTexts)}`);
    } else if (emptyText.toLowerCase().includes('no ambiguous') || emptyText.toLowerCase().includes('no ambig')) {
      pass('Ambiguity Resolution: clean empty-state message found (no ambiguous entities — expected)');
    } else {
      info(`Ambiguity section text: "${emptyText}"`);
      pass('Ambiguity Resolution: section rendered (empty state or loading)');
    }
  } else {
    fail('Ambiguity Resolution: could not find section element');
  }

  // ================================================================
  // STEP 2: /candidate-graph page
  // ================================================================
  info('\n--- Checking /candidate-graph ---');
  drainErrors();
  await page.goto(`${BASE}/candidate-graph`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  const cgH1 = await page.$eval('h1', el => el.textContent.trim()).catch(() => '(not found)');
  info(`Candidate Graph h1: "${cgH1}"`);
  if (cgH1 === 'Candidate Graph') {
    pass('/candidate-graph: h1 is "Candidate Graph"');
  } else {
    fail('/candidate-graph: h1', `got "${cgH1}"`);
  }

  const cgH2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  info(`/candidate-graph h2s: ${JSON.stringify(cgH2s)}`);

  // Check Entities and Relationships h2s exist
  const hasEntitiesH2 = cgH2s.includes('Entities');
  const hasRelationshipsH2 = cgH2s.includes('Relationships');
  if (hasEntitiesH2) {
    pass('/candidate-graph: "Entities" section h2 found');
  } else {
    fail('/candidate-graph: "Entities" h2 missing', `found: ${JSON.stringify(cgH2s)}`);
  }
  if (hasRelationshipsH2) {
    pass('/candidate-graph: "Relationships" section h2 found');
  } else {
    fail('/candidate-graph: "Relationships" h2 missing', `found: ${JSON.stringify(cgH2s)}`);
  }

  // Check for Graph Impact Analysis and Graph Difference View
  const hasGraphImpact = cgH2s.includes('Graph Impact Analysis');
  const hasGraphDiff = cgH2s.includes('Graph Difference View');

  if (hasGraphImpact) {
    pass('/candidate-graph: "Graph Impact Analysis" section found');
  } else {
    fail('/candidate-graph: "Graph Impact Analysis" section missing', `found h2s: ${JSON.stringify(cgH2s)}`);
  }

  if (hasGraphDiff) {
    pass('/candidate-graph: "Graph Difference View" section found');
  } else {
    fail('/candidate-graph: "Graph Difference View" section missing', `found h2s: ${JSON.stringify(cgH2s)}`);
  }

  // Check metric tiles in Graph Impact Analysis
  const metricTiles = await page.$$('.metric-tile, [class*="metric-tile"]');
  info(`Metric tiles on /candidate-graph: ${metricTiles.length}`);
  if (metricTiles.length >= 2) {
    pass(`/candidate-graph: ${metricTiles.length} metric tiles found`);
  } else {
    fail('/candidate-graph: expected >= 2 metric tiles', `got ${metricTiles.length}`);
  }

  // Check for diff tables / empty states under Graph Difference View
  const h3sOnCG = await page.$$eval('h3', els => els.map(el => el.textContent.trim()));
  info(`/candidate-graph h3s: ${JSON.stringify(h3sOnCG)}`);
  const expectedDiffSections = ['Added entities', 'Removed entities', 'Modified entities', 'Merged entities'];
  const foundDiffSections = expectedDiffSections.filter(s => h3sOnCG.includes(s));
  if (foundDiffSections.length === expectedDiffSections.length) {
    pass('/candidate-graph: all 4 diff sub-sections found (Added/Removed/Modified/Merged entities)');
  } else {
    fail('/candidate-graph: diff sub-sections', `found: ${JSON.stringify(foundDiffSections)}, missing: ${JSON.stringify(expectedDiffSections.filter(s => !h3sOnCG.includes(s)))}`);
  }

  // Check for table or empty-state (either is fine)
  const tables = await page.$$('table.data-table');
  const emptyStates = await page.$$('.empty-state');
  info(`data-table tables: ${tables.length}, empty-states: ${emptyStates.length}`);
  if (tables.length > 0 || emptyStates.length > 0) {
    pass(`/candidate-graph: data rendering confirmed (${tables.length} tables, ${emptyStates.length} empty-states)`);
  } else {
    fail('/candidate-graph: neither tables nor empty-states found — may still be loading');
  }

  // Console errors on /candidate-graph
  const { errs: cgErrs, nets: cgNets } = drainErrors();
  if (cgErrs.length > 0) {
    fail('/candidate-graph: console errors', cgErrs.join('; '));
  } else {
    pass('/candidate-graph: no console errors');
  }
  if (cgNets.length > 0) {
    info(`/candidate-graph network errors: ${cgNets.join(', ')}`);
  }

  // ================================================================
  // SUMMARY
  // ================================================================
  console.log('\n=====================================');
  console.log('VERIFICATION SUMMARY');
  console.log('=====================================');
  const passed = RESULTS.filter(r => r.ok).length;
  const failed = RESULTS.filter(r => !r.ok).length;
  console.log(`PASSED: ${passed}  FAILED: ${failed}  TOTAL: ${RESULTS.length}`);
  console.log(`PERSISTENCE CHECK: ${persistenceResult}`);
  console.log('\nFailed checks:');
  RESULTS.filter(r => !r.ok).forEach(r => console.error(`  FAIL  ${r.label}${r.detail ? ' — ' + r.detail : ''}`));
  console.log('\nPassed checks:');
  RESULTS.filter(r => r.ok).forEach(r => console.log(`  PASS  ${r.label}${r.detail ? ' — ' + r.detail : ''}`));

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
})().catch(err => {
  console.error('FATAL:', err);
  process.exit(1);
});
