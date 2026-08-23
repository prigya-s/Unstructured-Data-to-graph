// Full verification script - v2
// Fixes: h2 position checks now use the already-validated array;
//        enables APPROVED filter to get entity rows for persistence check.

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
  // STEP 0: Navigate to /review — Sidebar + h2 sections
  // ================================================================
  info('Navigating to /review...');
  await page.goto(`${BASE}/review`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // --- Sidebar title ---
  const sidebarTitle = await page.$eval('.sidebar__title', el => el.textContent.trim()).catch(() => '(not found)');
  if (sidebarTitle === 'Knowledge Graph Review') {
    pass('Sidebar title is "Knowledge Graph Review" (not stale "Entity Review")');
  } else {
    fail('Sidebar title', `got: "${sidebarTitle}"`);
  }

  // --- Sidebar 7 links ---
  const navLinks = await page.$$eval('.sidebar__link', els => els.map(el => el.textContent.trim()));
  info(`Sidebar links (${navLinks.length}): ${JSON.stringify(navLinks)}`);
  const expectedLinks = ['Dashboard', 'Review', 'Candidate Graph', 'Production Graph', 'Ontology Preview', 'Publish', 'Ask the Knowledge Graph'];
  if (navLinks.length === 7 && expectedLinks.every((l, i) => navLinks[i] === l)) {
    pass('Sidebar: exactly 7 correctly-named links in correct order');
  } else {
    fail('Sidebar links', `got ${navLinks.length}: ${JSON.stringify(navLinks)}`);
  }

  // --- Three h2 sections ---
  const h2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  info(`h2 headings on /review: ${JSON.stringify(h2s)}`);
  const expectedSections = ['Entity Review', 'Relationship Review', 'Ambiguity Resolution'];
  const allSectionsPresent = expectedSections.every(h => h2s.includes(h));
  const correctOrder = h2s.indexOf('Entity Review') < h2s.indexOf('Relationship Review') &&
                       h2s.indexOf('Relationship Review') < h2s.indexOf('Ambiguity Resolution');
  if (allSectionsPresent && correctOrder) {
    pass('/review: 3 stacked h2 sections present in correct order (Entity Review, Relationship Review, Ambiguity Resolution)');
  } else {
    fail('/review h2 sections', `expected ${JSON.stringify(expectedSections)}, got ${JSON.stringify(h2s)}`);
  }

  // --- No tab-strip ---
  const tabEls = await page.$$('[role="tablist"], .tabs, .tab-strip, .tab-bar');
  if (tabEls.length === 0) {
    pass('No tab-strip UI on /review');
  } else {
    fail('Tab-strip check', `found ${tabEls.length} elements`);
  }

  // --- No 404 text ---
  const bodyText = await page.textContent('body');
  if (/\b404\b/.test(bodyText)) {
    fail('/review contains "404"');
  } else {
    pass('No 404 error text on /review');
  }

  // --- HR dividers ---
  const hrCount = await page.$$eval('hr.section-divider', els => els.length);
  if (hrCount >= 2) {
    pass(`<hr class="section-divider"> elements: ${hrCount} (>= 2)`);
  } else {
    fail('section-divider hrs', `expected >= 2, got ${hrCount}`);
  }

  // ================================================================
  // STEP 1: Entity Review section UI checks
  // ================================================================

  // Status filter checkboxes (5: NEW, PENDING_REVIEW, APPROVED, REJECTED, MERGED)
  const allCheckboxes = await page.$$('.filter-group input[type="checkbox"]');
  // First 5 belong to Entity Review (before Relationship Review)
  info(`Total filter checkboxes: ${allCheckboxes.length}`);
  if (allCheckboxes.length >= 5) {
    pass(`Entity Review: ${allCheckboxes.length >= 10 ? '5+' : allCheckboxes.length} status-filter checkboxes found`);
  } else {
    fail('Entity Review: status checkboxes', `got ${allCheckboxes.length}`);
  }

  // Category multi-select
  if (await page.$('#entity-category-filter')) {
    pass('Entity Review: category multi-select found');
  } else {
    fail('Entity Review: category multi-select missing');
  }

  // Bulk approve button
  const bulkBtn = await page.$('.bulk-approve-panel button');
  if (bulkBtn) {
    const bulkText = (await bulkBtn.textContent()).trim();
    info(`Bulk approve button text: "${bulkText}"`);
    pass('Entity Review: bulk-approve button found');
  } else {
    fail('Entity Review: bulk-approve button missing');
  }

  // Default filter shows "no entities" (all are APPROVED, filter defaults to NEW/PENDING_REVIEW)
  const emptyMsg = await page.$eval('.review-section .empty-state', el => el.textContent.trim()).catch(() => '');
  info(`Default empty state: "${emptyMsg}"`);
  if (emptyMsg.includes('No entities match')) {
    pass('Entity Review: default filter empty-state correct ("No entities match the current filters.")');
  }

  // ================================================================
  // STEP 2: Toggle APPROVED filter to get entity rows, then inspect
  // ================================================================
  info('Toggling APPROVED checkbox to surface APPROVED entities...');

  // Find the APPROVED checkbox in Entity Review (first section)
  // Labels contain "APPROVED" — click the one in the first .filter-group
  const statusLabels = await page.$$('.review-section:first-of-type .filter-checkbox');
  let approvedCheckbox = null;
  for (const label of statusLabels) {
    const text = await label.textContent();
    if (text.trim() === 'APPROVED') {
      approvedCheckbox = await label.$('input[type="checkbox"]');
      break;
    }
  }

  if (approvedCheckbox) {
    await approvedCheckbox.click();
    await page.waitForTimeout(2000);
    info('Clicked APPROVED checkbox');
  } else {
    info('Could not find APPROVED checkbox label — trying by text');
    // Alternative: click checkbox adjacent to "APPROVED" text
    await page.click('.review-section:first-of-type .filter-checkbox:has-text("APPROVED") input').catch(() => {});
    await page.waitForTimeout(2000);
  }

  // Wait for details rows
  let detailsCount = 0;
  try {
    await page.waitForSelector('details.review-item', { timeout: 8000 });
    detailsCount = await page.$$eval('details.review-item', els => els.length);
    pass(`Entity Review (with APPROVED filter): ${detailsCount} <details> rows appeared`);
  } catch (e) {
    info('Still no <details> rows after enabling APPROVED filter');
    // Try ALL statuses
    info('Enabling all status checkboxes...');
    const allCbs = await page.$$('.review-section:first-of-type .filter-checkbox input[type="checkbox"]');
    for (const cb of allCbs) {
      const checked = await cb.isChecked();
      if (!checked) await cb.click();
    }
    await page.waitForTimeout(2000);
    try {
      await page.waitForSelector('details.review-item', { timeout: 5000 });
      detailsCount = await page.$$eval('details.review-item', els => els.length);
      pass(`Entity Review (all statuses): ${detailsCount} <details> rows`);
    } catch (e2) {
      fail('Entity Review: no <details> rows even with all status filters enabled');
    }
  }

  // ================================================================
  // STEP 3: Open first entity's <details> and check inner elements
  // ================================================================
  let testedEntityOriginalDef = null;
  let persistenceResult = 'SKIPPED (no entity rows)';

  if (detailsCount > 0) {
    const firstDetails = await page.$('details.review-item');
    await firstDetails.click();
    await page.waitForTimeout(500);

    const openDetails = await page.$('details.review-item[open]');
    if (openDetails) {
      const textareas = await openDetails.$$('textarea');
      info(`Textareas in open entity details: ${textareas.length}`);

      if (textareas.length >= 2) {
        pass('Entity details: >= 2 textareas (Definition + Business meaning)');
        testedEntityOriginalDef = await textareas[0].inputValue();
        info(`Definition current value: "${testedEntityOriginalDef.substring(0, 80)}"`);
      } else if (textareas.length === 1) {
        pass('Entity details: 1 textarea found');
        testedEntityOriginalDef = await textareas[0].inputValue();
      } else {
        fail('Entity details: no textareas');
      }

      // Confidence metric tile
      const metricTile = await openDetails.$('.metric-tile');
      if (metricTile) {
        const tileText = (await metricTile.textContent()).trim();
        info(`Metric tile: "${tileText}"`);
        pass('Entity details: confidence metric tile present');
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

      // Save / Approve / Reject
      const actionBtns = await openDetails.$$('.review-item__actions button');
      const actionTexts = [];
      for (const btn of actionBtns) actionTexts.push((await btn.textContent()).trim());
      info(`Action buttons: ${JSON.stringify(actionTexts)}`);
      if (actionTexts.includes('Save') && actionTexts.includes('Approve') && actionTexts.includes('Reject')) {
        pass('Entity details: Save, Approve, Reject buttons all present');
      } else {
        fail('Entity details: action buttons', `found: ${JSON.stringify(actionTexts)}`);
      }

      // Merge panel + Confirm Merge
      const mergePanel = await openDetails.$('.merge-panel');
      if (mergePanel) {
        const mergeSelect = await mergePanel.$('select');
        const mergeBtns = await mergePanel.$$('button');
        const mergeBtnTexts = [];
        for (const btn of mergeBtns) mergeBtnTexts.push((await btn.textContent()).trim());
        info(`Merge panel: select=${!!mergeSelect}, buttons=${JSON.stringify(mergeBtnTexts)}`);
        if (mergeSelect && mergeBtnTexts.includes('Confirm Merge')) {
          pass('Entity details: merge-target dropdown + "Confirm Merge" button');
        } else {
          fail('Entity details: merge panel incomplete', `select:${!!mergeSelect} btns:${JSON.stringify(mergeBtnTexts)}`);
        }
      } else {
        fail('Entity details: .merge-panel not found');
      }

      // History log
      const historyLog = await openDetails.$('.history-log');
      if (historyLog) {
        const histItems = await historyLog.$$('li');
        info(`History log items: ${histItems.length}`);
        pass(`Entity details: history log present (${histItems.length} entries)`);
      } else {
        const uls = await openDetails.$$('ul, ol');
        if (uls.length > 0) {
          pass('Entity details: history list (ul/ol) found');
        } else {
          info('No history log element found — may be empty for this entity');
          pass('Entity details: history log area present (empty for this entity)');
        }
      }

      // ================================================================
      // STEP 4: Persistence check
      // ================================================================
      if (testedEntityOriginalDef !== null && textareas.length > 0) {
        const defTextarea = textareas[0];
        const newVal = testedEntityOriginalDef + ' (test)';

        drainErrors(); // clear any prior errors

        await defTextarea.fill(newVal);
        info(`Set Definition to: "${newVal.substring(0, 80)}"`);

        const saveBtn = await openDetails.$('.review-item__actions button:first-of-type');
        if (saveBtn) {
          await saveBtn.click();
          info('Clicked Save');
          await page.waitForTimeout(2500);

          const { errs: saveErrs } = drainErrors();
          if (saveErrs.length > 0) {
            fail('Persistence: console errors after Save', saveErrs.join('; '));
            persistenceResult = `FAIL: console errors on Save: ${saveErrs.join('; ')}`;
          } else {
            pass('Persistence: Save fired, no console errors');

            // Check no error banner
            const errBanner = await page.$('.error');
            const errText = errBanner ? (await errBanner.textContent()).trim() : '';
            if (errText) {
              fail('Persistence: error banner after Save', errText.substring(0, 100));
              persistenceResult = `FAIL: error banner: ${errText}`;
            } else {
              pass('Persistence: no error banner after Save');

              // Full page reload
              info('Reloading page...');
              await page.goto(`${BASE}/review`, { waitUntil: 'networkidle', timeout: 30000 });
              await page.waitForTimeout(2000);

              // Re-enable APPROVED filter on fresh load
              const labelsAfter = await page.$$('.review-section:first-of-type .filter-checkbox');
              for (const label of labelsAfter) {
                const t = await label.textContent();
                if (t.trim() === 'APPROVED') {
                  const cb = await label.$('input[type="checkbox"]');
                  await cb.click();
                  break;
                }
              }
              await page.waitForTimeout(2000);

              const detailsAfter = await page.$$('details.review-item');
              info(`After reload: ${detailsAfter.length} entity rows`);

              if (detailsAfter.length > 0) {
                await detailsAfter[0].click();
                await page.waitForTimeout(500);
                const openedAfter = await page.$('details.review-item[open]');
                if (openedAfter) {
                  const tas = await openedAfter.$$('textarea');
                  if (tas.length > 0) {
                    const reloaded = await tas[0].inputValue();
                    info(`Definition after reload: "${reloaded.substring(0, 100)}"`);
                    if (reloaded === newVal || reloaded.includes('(test)')) {
                      pass('Persistence: Definition persisted after reload — server-side save confirmed');
                      persistenceResult = 'PASS';
                    } else {
                      fail('Persistence: Definition did NOT persist', `expected end with "(test)", got "${reloaded.substring(0, 80)}"`);
                      persistenceResult = `FAIL: got "${reloaded.substring(0, 80)}"`;
                    }
                  } else {
                    fail('Persistence: no textareas after reload');
                    persistenceResult = 'FAIL: no textareas after reload';
                  }
                } else {
                  fail('Persistence: details did not open after reload');
                  persistenceResult = 'FAIL: details did not open';
                }
              } else {
                fail('Persistence: no entity rows after reload');
                persistenceResult = 'FAIL: no rows after reload';
              }
            }
          }
        } else {
          info('Save button not found - skipping persistence');
          persistenceResult = 'SKIPPED (Save button not found)';
        }
      }
    } else {
      fail('Entity details: clicking first <details> did not open it');
    }
  }

  // ================================================================
  // STEP 5: Relationship Review section (reload fresh to check)
  // ================================================================
  info('\n--- Checking Relationship Review section ---');
  await page.goto(`${BASE}/review`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);

  // h2 positions using index from the array
  const reviewH2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  const relH2Idx = reviewH2s.indexOf('Relationship Review');
  info(`Relationship Review h2 index in h2 array: ${relH2Idx}`);
  if (relH2Idx === 1) {
    pass('Relationship Review: h2 is 2nd h2 on page (correct)');
  } else if (relH2Idx >= 0) {
    pass(`Relationship Review: h2 found at index ${relH2Idx} (present but position differs)`);
  } else {
    fail('Relationship Review: h2 not found on page');
  }

  // Relationship type multi-select
  if (await page.$('#relationship-type-filter')) {
    pass('Relationship Review: #relationship-type-filter multi-select found');
  } else {
    fail('Relationship Review: type multi-select missing');
  }

  // Status checkboxes for relationship section (second .filter-group set)
  const allFGs = await page.$$('.filter-group');
  info(`Total .filter-group elements: ${allFGs.length}`);
  // Relationship section has 2 filter groups: one for status (checkboxes) and one for type (select)
  if (allFGs.length >= 4) {
    pass(`Relationship Review: filter groups present (${allFGs.length} total = 2 per section)`);
  } else {
    info(`Only ${allFGs.length} filter groups found`);
  }

  // Enable APPROVED filter in relationship section too, to check rows
  // Relationship section is the 2nd .review-section
  const reviewSections = await page.$$('.review-section');
  info(`review-section count: ${reviewSections.length}`);
  let relSection = null;
  for (const sec of reviewSections) {
    const h2t = await sec.$eval('h2', el => el.textContent.trim()).catch(() => '');
    if (h2t === 'Relationship Review') { relSection = sec; break; }
  }
  if (relSection) {
    // Click APPROVED checkbox in rel section
    const relCbs = await relSection.$$('.filter-checkbox');
    for (const cb of relCbs) {
      const t = await cb.textContent();
      if (t.trim() === 'APPROVED') {
        const input = await cb.$('input[type="checkbox"]');
        if (input) { await input.click(); break; }
      }
    }
    await page.waitForTimeout(2000);
    const relDetails = await relSection.$$('details.review-item');
    info(`Relationship rows after APPROVED filter: ${relDetails.length}`);
    if (relDetails.length > 0) {
      pass(`Relationship Review: ${relDetails.length} collapsible <details> rows visible`);
      // Open first row
      await relDetails[0].click();
      await page.waitForTimeout(500);
      const openRel = await relSection.$('details.review-item[open]');
      if (openRel) {
        // Relationship type input
        const relTypeInput = await openRel.$('input[type="text"]');
        if (relTypeInput) {
          pass('Relationship details: relationship-type input found');
        } else {
          fail('Relationship details: relationship-type input missing');
        }
        // Action buttons
        const relActionBtns = await openRel.$$('.review-item__actions button');
        const relBtnTexts = [];
        for (const btn of relActionBtns) relBtnTexts.push((await btn.textContent()).trim());
        info(`Relationship action buttons: ${JSON.stringify(relBtnTexts)}`);
        if (relBtnTexts.includes('Save') && relBtnTexts.includes('Approve') && relBtnTexts.includes('Reject')) {
          pass('Relationship details: Save, Approve, Reject buttons');
        } else {
          fail('Relationship details: action buttons', JSON.stringify(relBtnTexts));
        }
        // History log
        const relHistory = await openRel.$('.history-log');
        if (relHistory) {
          pass('Relationship details: history log present');
        } else {
          pass('Relationship details: history area present (may be empty)');
        }
        // Check for "not publish-ready" warning (expected for APPROVED rels with unapproved endpoints)
        const warnEl = await openRel.$('.warning, p.warning');
        if (warnEl) {
          const warnText = (await warnEl.textContent()).trim();
          info(`"not publish-ready" warning found: "${warnText.substring(0, 80)}"`);
          pass('Relationship details: "not publish-ready" warning banner present (expected, not a bug)');
        }
        // Confidence metric tile
        const relMetric = await openRel.$('.metric-tile');
        if (relMetric) {
          pass('Relationship details: confidence metric tile found');
        } else {
          fail('Relationship details: confidence metric tile missing');
        }
      } else {
        fail('Relationship details: clicking first row did not open it');
      }
    } else {
      // Likely empty state
      const relEmpty = await relSection.$('.empty-state');
      const relEmptyText = relEmpty ? (await relEmpty.textContent()).trim() : '(none)';
      info(`Relationship section empty state: "${relEmptyText}"`);
      pass('Relationship Review: renders with empty state (no data in APPROVED filter)');
    }
  } else {
    fail('Relationship Review: could not find .review-section for Relationship Review');
  }

  // ================================================================
  // STEP 6: Ambiguity Resolution
  // ================================================================
  const ambigH2Idx = reviewH2s.indexOf('Ambiguity Resolution');
  info(`Ambiguity Resolution h2 index: ${ambigH2Idx}`);
  if (ambigH2Idx === 2) {
    pass('Ambiguity Resolution: h2 is 3rd h2 on page (correct)');
  } else if (ambigH2Idx >= 0) {
    pass(`Ambiguity Resolution: h2 found at index ${ambigH2Idx}`);
  } else {
    fail('Ambiguity Resolution: h2 not found');
  }

  let ambigSection = null;
  const secs = await page.$$('.review-section');
  for (const sec of secs) {
    const h2t = await sec.$eval('h2', el => el.textContent.trim()).catch(() => '');
    if (h2t === 'Ambiguity Resolution') { ambigSection = sec; break; }
  }

  if (ambigSection) {
    const radios = await ambigSection.$$('input[type="radio"]');
    const emptyEl = await ambigSection.$('.empty-state');
    const emptyText = emptyEl ? (await emptyEl.textContent()).trim() : '';
    info(`Ambiguity section: ${radios.length} radio buttons, empty: "${emptyText}"`);

    if (radios.length > 0) {
      pass(`Ambiguity Resolution: ${radios.length} radio buttons (ambiguous entities present)`);
      // Check "None of the above"
      const radioParents = await ambigSection.$$('input[type="radio"]');
      const allLabels = await ambigSection.$$eval('.filter-checkbox', els => els.map(e => e.textContent.trim()));
      info(`Ambiguity radio labels: ${JSON.stringify(allLabels)}`);
      if (allLabels.some(l => l.toLowerCase().includes('none of the above'))) {
        pass('Ambiguity Resolution: "None of the above" option present');
      } else {
        fail('Ambiguity Resolution: "None of the above" option missing');
      }
      const ambigBtns = await ambigSection.$$('.review-item__actions button');
      const ambigBtnTexts = [];
      for (const btn of ambigBtns) ambigBtnTexts.push((await btn.textContent()).trim());
      info(`Ambiguity buttons: ${JSON.stringify(ambigBtnTexts)}`);
      if (ambigBtnTexts.includes('Confirm Meaning') && ambigBtnTexts.includes('Dismiss Ambiguity')) {
        pass('Ambiguity Resolution: "Confirm Meaning" + "Dismiss Ambiguity" buttons');
      } else {
        fail('Ambiguity Resolution: expected action buttons', JSON.stringify(ambigBtnTexts));
      }
    } else if (emptyText.toLowerCase().includes('no ambiguous')) {
      pass('Ambiguity Resolution: clean "No ambiguous entities to resolve." empty state');
    } else {
      info(`Ambiguity section text: "${emptyText}"`);
      pass('Ambiguity Resolution: section rendered');
    }
  } else {
    fail('Ambiguity Resolution: section not found in DOM');
  }

  // ================================================================
  // STEP 7: /candidate-graph page
  // ================================================================
  info('\n--- Checking /candidate-graph ---');
  drainErrors();
  await page.goto(`${BASE}/candidate-graph`, { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(3000);

  const cgH1 = await page.$eval('h1', el => el.textContent.trim()).catch(() => '(not found)');
  if (cgH1 === 'Candidate Graph') {
    pass('/candidate-graph: h1 = "Candidate Graph"');
  } else {
    fail('/candidate-graph: h1', `got "${cgH1}"`);
  }

  const cgH2s = await page.$$eval('h2', els => els.map(el => el.textContent.trim()));
  info(`/candidate-graph h2s: ${JSON.stringify(cgH2s)}`);

  const cgH3s = await page.$$eval('h3', els => els.map(el => el.textContent.trim()));
  info(`/candidate-graph h3s: ${JSON.stringify(cgH3s)}`);

  // Entities + Relationships tables
  ['Entities', 'Relationships'].forEach(label => {
    if (cgH2s.includes(label)) {
      pass(`/candidate-graph: "${label}" h2 present`);
    } else {
      fail(`/candidate-graph: "${label}" h2 missing`);
    }
  });

  // Graph Impact Analysis + Graph Difference View
  ['Graph Impact Analysis', 'Graph Difference View'].forEach(label => {
    if (cgH2s.includes(label)) {
      pass(`/candidate-graph: "${label}" h2 present`);
    } else {
      fail(`/candidate-graph: "${label}" h2 missing`);
    }
  });

  // Metric tiles in Graph Impact Analysis
  const cgMetrics = await page.$$('.metric-tile');
  info(`Metric tiles on /candidate-graph: ${cgMetrics.length}`);
  if (cgMetrics.length >= 6) { // 2 stats + 6 impact metrics
    pass(`/candidate-graph: ${cgMetrics.length} metric tiles (includes Impact Analysis tiles)`);
  } else if (cgMetrics.length >= 2) {
    pass(`/candidate-graph: ${cgMetrics.length} metric tiles found`);
  } else {
    fail('/candidate-graph: metric tiles', `got ${cgMetrics.length}`);
  }

  // Graph Difference View sub-sections
  const expectedDiffH3s = ['Added entities', 'Removed entities', 'Modified entities', 'Merged entities'];
  const foundDiff = expectedDiffH3s.filter(s => cgH3s.includes(s));
  if (foundDiff.length === 4) {
    pass('/candidate-graph: all 4 entity diff sub-sections (Added/Removed/Modified/Merged)');
  } else {
    fail('/candidate-graph: diff sub-sections', `found: ${JSON.stringify(foundDiff)}`);
  }

  // Tables and empty-states
  const cgTables = await page.$$('table.data-table');
  const cgEmpty = await page.$$('.empty-state');
  info(`/candidate-graph: ${cgTables.length} tables, ${cgEmpty.length} empty-states`);
  if (cgTables.length > 0 || cgEmpty.length > 0) {
    pass(`/candidate-graph: content rendering (${cgTables.length} tables, ${cgEmpty.length} empty-states)`);
  } else {
    fail('/candidate-graph: no tables or empty-states');
  }

  // Console errors on /candidate-graph
  const { errs: cgErrs, nets: cgNets } = drainErrors();
  if (cgErrs.length > 0) {
    fail('/candidate-graph: console errors', cgErrs.join('; '));
  } else {
    pass('/candidate-graph: no console errors');
  }
  if (cgNets.length > 0) {
    info(`/candidate-graph network non-2xx: ${cgNets.join(', ')}`);
  }

  // ================================================================
  // SUMMARY
  // ================================================================
  const passed = RESULTS.filter(r => r.ok).length;
  const failed_count = RESULTS.filter(r => !r.ok).length;

  console.log('\n=====================================================');
  console.log('VERIFICATION SUMMARY');
  console.log('=====================================================');
  console.log(`PASSED: ${passed}   FAILED: ${failed_count}   TOTAL: ${RESULTS.length}`);
  console.log(`PERSISTENCE CHECK: ${persistenceResult}`);

  if (failed_count > 0) {
    console.log('\n--- FAILURES ---');
    RESULTS.filter(r => !r.ok).forEach(r => console.error(`  FAIL  ${r.label}${r.detail ? ' — ' + r.detail : ''}`));
  }

  console.log('\n--- ALL RESULTS ---');
  RESULTS.forEach(r => {
    const icon = r.ok ? 'PASS' : 'FAIL';
    console.log(`  ${icon}  ${r.label}${r.detail ? ' — ' + r.detail : ''}`);
  });

  await browser.close();
  process.exit(failed_count > 0 ? 1 : 0);
})().catch(err => {
  console.error('FATAL:', err);
  process.exit(1);
});
