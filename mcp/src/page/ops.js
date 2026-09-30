// Browser-side Unit4 operations.
//
// Every function here is serialised with Function.prototype.toString() and
// executed by Playwright MCP's browser_run_code tool with a real Playwright
// `page`. Functions must therefore be self-contained: they may call each other
// (all functions in this module are injected together) but must not close over
// module state or imports. Arguments arrive as one JSON-serialisable object and
// every operation returns a JSON-serialisable object.
//
// Selectors come from read-only discovery against Knowit's production Unit4
// (CR 26.1). Unit4 mixes ExtJS chrome (top page) with ASP.NET report forms in
// nested iframes: tab -> #activity-N -> Container.aspx -> contentcontainer.

const ACTIVITY_LIMIT_TEXT = 'Systemet tillater at opptil 10 aktiviteter er åpne samtidig';

async function u4Visibility(page) {
  return page.evaluate(() => document.visibilityState);
}

async function u4Company(page) {
  const button = page.getByRole('toolbar', { name: 'Program' }).getByRole('button', { name: /^\d{2,10} / });
  if ((await button.count()) !== 1) return null;
  const label = await button.getAttribute('aria-label');
  const match = /^(\d{2,10}) (.+)$/.exec(label ?? '');
  return match ? { code: match[1], name: match[2] } : null;
}

async function u4Tabs(page) {
  return page.getByRole('tab').evaluateAll((tabs) => tabs
    .map((t) => ({ name: t.getAttribute('aria-label'), selected: t.getAttribute('aria-selected') === 'true' }))
    .filter((t) => t.name));
}

async function u4Modals(page) {
  return page.locator('[role=dialog]:visible, [role=alertdialog]:visible').evaluateAll((ds) => ds.map((d) => ({
    role: d.getAttribute('role'),
    kind: d.getAttribute('data-u4id'),
    text: d.innerText.replace(/\s+/g, ' ').trim().slice(0, 300),
  })));
}

async function u4State(page) {
  const visibility = await u4Visibility(page);
  const modals = await u4Modals(page);
  return {
    visibility,
    title: await page.title(),
    url: page.url().replace(/[?#].*/, ''),
    company: modals.length ? null : await u4Company(page),
    tabs: modals.length ? [] : await u4Tabs(page),
    modals,
  };
}

// Resolve the content frame of a Unit4 activity tab by its exact accessible
// name ("<company> <title> : <window id>"). Selecting the tab is required:
// inactive activities are display:none and role locators skip hidden nodes.
async function u4ActivityFrame(page, tabName, timeoutMs = 20000) {
  const tab = page.getByRole('tab', { name: tabName, exact: true });
  if ((await tab.count()) !== 1) throw new Error(`tab_missing:${tabName}`);
  if ((await tab.getAttribute('aria-selected')) !== 'true') await tab.click();
  const panel = await tab.getAttribute('aria-controls');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    // A tab can stack several Container.aspx frames (e.g. a log view opened
    // over the order table); the last one is the one on top.
    const outers = await page.locator(`#${panel} iframe[src*="Container.aspx"]`).elementHandles().catch(() => []);
    for (const outerEl of outers.reverse()) {
      const outer = await outerEl.contentFrame();
      const inner = outer?.childFrames().find((c) => c.name() === 'contentcontainer');
      if (!inner) continue;
      if (await inner.locator('h1.PageTitle').count()) return inner;
      const text = await inner.evaluate(() => document.body?.innerText ?? '').catch(() => '');
      if (text.includes(ACTIVITY_LIMIT_TEXT)) throw new Error('activity_limit');
    }
    await page.waitForTimeout(250);
  }
  throw new Error(`activity_not_ready:${tabName}`);
}

async function u4CloseTab(page, tabName) {
  const tab = page.getByRole('tab', { name: tabName, exact: true });
  if ((await tab.count()) !== 1) return { closed: false, reason: 'absent' };
  await page.locator('div.x-tab', { has: tab }).locator('.x-tab-close-btn').click();
  await tab.waitFor({ state: 'detached', timeout: 10000 }).catch(() => {});
  return { closed: (await tab.count()) === 0, modals: await u4Modals(page) };
}

// Open an activity through the global search, selecting only the single
// result whose title, window id and (when given) path match exactly.
async function u4OpenFromSearch(page, { title, viewId, path }) {
  const box = page.getByRole('combobox', { name: 'Søk (Alt+q)' });
  await box.click();
  await box.fill('');
  // Unit4 search reacts to key events; fill() alone yields no results.
  await box.pressSequentially(title, { delay: 30 });
  const results = page.locator('.u4-search-result-item');
  const read = () => results.evaluateAll((els) => els.map((e) => ({
    title: e.querySelector('b')?.textContent?.trim() ?? null,
    viewId: e.querySelector('.u4-menu-search-result-viewid')?.textContent?.replace('Vindus-ID:', '').trim() ?? null,
    path: e.querySelector('.u4-menu-search-result-path')?.textContent?.trim() ?? null,
  })));
  // The result list keeps the previous query's items until the new search
  // returns, so wait until every item belongs to this query and the list is
  // stable across two reads.
  const needle = title.toLowerCase();
  const deadline = Date.now() + 15000;
  let all = [];
  let previous = '';
  while (Date.now() < deadline) {
    all = await read();
    const current = JSON.stringify(all);
    if (all.length && all.every((r) => r.title?.toLowerCase().includes(needle)) && current === previous) break;
    previous = current;
    await page.waitForTimeout(400);
  }
  const matches = all.map((r, i) => ({ ...r, i }))
    .filter((r) => r.title === title && r.viewId === viewId && (!path || r.path === path));
  if (matches.length !== 1) {
    await page.keyboard.press('Escape');
    return { ok: false, reason: matches.length ? 'search_ambiguous' : 'search_no_match', results: all.slice(0, 10) };
  }
  await results.nth(matches[0].i).click();
  return { ok: true, match: matches[0] };
}

function u4Field(frame, label) {
  const combo = frame.getByRole('combobox', { name: label, exact: true });
  const control = frame.locator('table.Control', { has: combo });
  return {
    combo,
    control,
    rowValue: control.locator('input[id$="_RowValue"]'),
    dropdown: control.locator('td.DropDownButton [role=button]'),
  };
}

async function u4FieldState(frame, label) {
  const f = u4Field(frame, label);
  if ((await f.combo.count()) !== 1) return { label, present: false };
  return {
    label,
    present: true,
    visible: await f.combo.inputValue(),
    committed: (await f.rowValue.count()) ? await f.rowValue.inputValue() : null,
  };
}

// Select a value through the field's dropdown list (never by typing).
async function u4SelectFromDropdown(frame, label, value) {
  const f = u4Field(frame, label);
  await f.dropdown.click();
  const listId = await f.combo.getAttribute('aria-controls');
  if (!listId) throw new Error(`dropdown_no_list:${label}`);
  const option = frame.locator(`[id="${listId}"] tr[role=option]`).filter({ hasText: new RegExp(`^${value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`) });
  if ((await option.count()) !== 1) {
    await f.combo.press('Escape');
    throw new Error(`dropdown_option_missing:${label}`);
  }
  await option.click();
  await frame.locator('h1.PageTitle').click();
}

// Type an account into a lookup field and commit it with Tab.
async function u4CommitLookup(frame, label, value) {
  const f = u4Field(frame, label);
  await f.combo.click();
  await f.combo.fill('');
  await f.combo.pressSequentially(value, { delay: 40 });
  await f.combo.press('Tab');
  await frame.waitForTimeout(800);
  await frame.locator('h1.PageTitle').click();
  await frame.waitForTimeout(300);
}

function u4LagreButton(frame) {
  return frame.getByRole('toolbar', { name: 'Handling' }).getByRole('button', { name: 'Lagre', exact: true });
}

// ---- Operations -----------------------------------------------------------

async function opState(page) {
  const state = await u4State(page);
  const loggedIn = state.modals.length > 0 || state.company !== null;
  return { ...state, loggedIn };
}

async function opSelectCompany(page, { code, name }) {
  const current = await u4Company(page);
  if (current?.code === code && (!name || current.name === name)) return { ok: true, changed: false, company: current };
  await page.getByRole('toolbar', { name: 'Program' }).getByRole('button', { name: /^\d{2,10} / }).click();
  const filter = page.getByRole('search', { name: 'Filtrer søket' });
  await filter.waitFor({ timeout: 10000 });
  await filter.fill('');
  await filter.pressSequentially(code, { delay: 40 });
  await page.waitForTimeout(800);
  const items = page.locator('li.u4-clientmenu-listitem:visible');
  const rows = await items.evaluateAll((els) => els.map((e) => ({
    code: e.querySelector('.u4-clientmenu-listitem-code')?.textContent?.trim(),
    name: e.querySelector('.u4-clientmenu-listitem-name')?.textContent?.trim(),
  })));
  const hits = rows.map((r, i) => ({ ...r, i })).filter((r) => r.code === code && (!name || r.name === name));
  if (hits.length !== 1) {
    await page.keyboard.press('Escape');
    return { ok: false, reason: hits.length ? 'company_ambiguous' : 'company_not_found', candidates: rows.slice(0, 10) };
  }
  await items.nth(hits[0].i).click();
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const now = await u4Company(page).catch(() => null);
    if (now?.code === code) return { ok: !name || now.name === name, changed: true, company: now };
    await page.waitForTimeout(500);
  }
  return { ok: false, reason: 'company_not_confirmed', company: await u4Company(page) };
}

// Ensure the report activity is open and return its tab name.
async function opEnsureReport(page, { company, report }) {
  const tabName = `${company} ${report.heading} : ${report.viewId}`;
  let opened = false;
  if (!(await u4Tabs(page)).some((t) => t.name === tabName)) {
    // Only activity tabs ("… : TRA015") count; the start page's menu tabs don't.
    const tabs = (await u4Tabs(page)).filter((t) => / : [A-Z]{2,4}\d{3}$/.test(t.name));
    if (tabs.length >= 9) return { ok: false, reason: 'activity_limit', tabs };
    const res = await u4OpenFromSearch(page, { title: report.searchTitle, viewId: report.viewId, path: report.path });
    if (!res.ok) return res;
    await page.getByRole('tab', { name: tabName, exact: true }).waitFor({ timeout: 30000 });
    opened = true;
  }
  try {
    const frame = await u4ActivityFrame(page, tabName);
    const heading = (await frame.locator('h1.PageTitle').innerText()).trim();
    if (heading !== report.heading) return { ok: false, reason: 'heading_mismatch', heading };
  } catch (error) {
    const reason = String(error.message ?? error);
    if (reason === 'activity_limit' && opened) await u4CloseTab(page, tabName);
    return { ok: false, reason };
  }
  return { ok: true, tabName, opened };
}

// Set the requested parameters and read back every relevant field.
async function opSetParams(page, { tabName, report, period, account }) {
  const frame = await u4ActivityFrame(page, tabName);
  if (account) await u4CommitLookup(frame, 'Konto', account);
  await u4SelectFromDropdown(frame, 'Periode', period);
  return opReadParams(page, { tabName, report });
}

async function opReadParams(page, { tabName, report }) {
  const frame = await u4ActivityFrame(page, tabName);
  const fields = {};
  for (const label of report.checkFields) fields[label] = await u4FieldState(frame, label);
  const lagre = u4LagreButton(frame);
  return {
    heading: (await frame.locator('h1.PageTitle').innerText()).trim(),
    fields,
    lagreCount: await lagre.count(),
    lagreEnabled: (await lagre.count()) === 1 ? await lagre.isEnabled() : false,
    modals: await u4Modals(page),
  };
}

// Open (or reuse) "Dine bestilte rapporter" and return every row for the
// date range. Rows are keyed by the stable field names Unit4 puts in each
// cell's onclick handler; data-originaltext holds the untruncated value.
async function opScanOrders(page, { company, fromTabName, fromDate, toDate }) {
  const tabName = `${company} Dine bestilte rapporter : TRA003`;
  if (!(await u4Tabs(page)).some((t) => t.name === tabName)) {
    if (!fromTabName) return { ok: false, reason: 'order_table_not_open' };
    const src = await u4ActivityFrame(page, fromTabName);
    await src.getByRole('toolbar', { name: 'Handling' }).getByRole('button', { name: 'Dine bestilte rapporter', exact: true }).click();
    await page.getByRole('tab', { name: tabName, exact: true }).waitFor({ timeout: 30000 });
  }
  let frame;
  try {
    frame = await u4ActivityFrame(page, tabName);
  } catch (error) {
    return { ok: false, reason: String(error.message ?? error) };
  }
  if ((await frame.locator('h1.PageTitle').innerText()).trim() !== 'Dine bestilte rapporter') {
    return { ok: false, reason: 'order_table_heading_mismatch' };
  }
  for (const [label, value] of [['Fra', fromDate], ['Til', toDate]]) {
    const box = frame.getByRole('textbox', { name: label, exact: true });
    if ((await box.inputValue()) !== value) {
      await box.click();
      await box.fill('');
      await box.pressSequentially(value, { delay: 20 });
      await box.press('Tab');
    }
  }
  await frame.getByRole('button', { name: 'Last', exact: true }).click();
  await frame.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForTimeout(1500);
  await frame.locator('h1.PageTitle').waitFor({ timeout: 20000 });
  const rows = await frame.locator('tr[id^="b_g1s2_row"]').evaluateAll((trs) => trs.map((r) => {
    const v = (k) => r.querySelector(`td[onclick*="'${k}'"] div[data-originaltext]`)?.getAttribute('data-originaltext') ?? null;
    return {
      order: v('orderno'), report: v('description'), reportId: v('report_name'), user: v('user_id'),
      file: v('file_name'), status: v('status'),
      checked: r.querySelector('input[id$="__delete"]')?.checked ?? null,
    };
  }));
  const text = await frame.locator('body').innerText();
  const paged = /Neste side|Forrige side|Side \d+ av \d+/i.test(text);
  return { ok: true, tabName, fromDate, toDate, rows, paged };
}

// Double-click Lagre once and observe Unit4's response for up to waitMs.
async function opLagre(page, { tabName, waitMs }) {
  const frame = await u4ActivityFrame(page, tabName);
  const lagre = u4LagreButton(frame);
  if ((await lagre.count()) !== 1) return { clicked: false, reason: 'lagre_not_unique' };
  if (!(await lagre.isEnabled())) return { clicked: false, reason: 'lagre_disabled' };
  if ((await u4Modals(page)).length) return { clicked: false, reason: 'modal_open' };
  await lagre.scrollIntoViewIfNeeded().catch(() => {});
  // What is actually under the button's centre (an overlay would intercept
  // the click and make Playwright's actionability check time out).
  const hitTarget = await lagre.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const describe = (n) => n ? `${n.tagName.toLowerCase()}#${n.id}.${[...n.classList].slice(0, 3).join('.')}` : null;
    return { rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], inside: !!hit && (hit === el || el.contains(hit)), hit: describe(hit), viewport: [innerWidth, innerHeight] };
  });
  const t0 = Date.now();
  try {
    await lagre.dblclick({ timeout: 15000 });
  } catch (error) {
    // A timeout here comes from Playwright's actionability checks, before any
    // input is dispatched; the caller still treats it as an unconfirmed save
    // and applies the order-table evidence check.
    return { clicked: false, reason: 'dblclick_failed', error: String(error.message ?? error).slice(0, 1200), hitTarget, lagreDisabledSeen: false, dialogs: await u4Modals(page) };
  }
  let lagreDisabledSeen = false;
  const dialogs = [];
  while (Date.now() - t0 < waitMs) {
    const enabled = await lagre.isEnabled().catch(() => null);
    if (enabled === false) lagreDisabledSeen = true;
    for (const m of await u4Modals(page)) {
      if (!dialogs.some((d) => d.text === m.text)) dialogs.push({ ...m, ms: Date.now() - t0 });
    }
    if (dialogs.length) break;
    await page.waitForTimeout(250);
  }
  return { clicked: true, ms: Date.now() - t0, lagreDisabledSeen, dialogs };
}

async function opAckSuccess(page) {
  const dialog = page.locator('[data-u4id=u4_messageoverlay_success]:visible');
  if ((await dialog.count()) !== 1) return { ok: false, reason: 'no_success_dialog' };
  await dialog.getByRole('button', { name: 'OK', exact: true }).click();
  await dialog.waitFor({ state: 'hidden', timeout: 10000 }).catch(() => {});
  return { ok: (await dialog.count()) === 0 || !(await dialog.isVisible()) };
}

// Tick exactly the given order rows and untick every other row.
async function opSelectRows(page, { tabName, orders }) {
  const frame = await u4ActivityFrame(page, tabName);
  const rows = frame.locator('tr[id^="b_g1s2_row"]');
  const count = await rows.count();
  for (let i = 0; i < count; i++) {
    const row = rows.nth(i);
    const order = await row.locator(`td[onclick*="'orderno'"] div[data-originaltext]`).getAttribute('data-originaltext');
    const box = row.locator('input[id$="__delete"]');
    if ((await box.isChecked()) !== orders.includes(order)) await row.locator('label.DeleteRowCheckLabel').click();
  }
  await page.waitForTimeout(400);
  const checked = await rows.evaluateAll((trs) => trs
    .filter((r) => r.querySelector('input[id$="__delete"]')?.checked)
    .map((r) => r.querySelector(`td[onclick*="'orderno'"] div[data-originaltext]`)?.getAttribute('data-originaltext')));
  return { checked, rowCount: count };
}

async function opClickDownload(page, { tabName, orders }) {
  const frame = await u4ActivityFrame(page, tabName);
  const checked = await frame.locator('tr[id^="b_g1s2_row"]').evaluateAll((trs) => trs
    .filter((r) => r.querySelector('input[id$="__delete"]')?.checked)
    .map((r) => r.querySelector(`td[onclick*="'orderno'"] div[data-originaltext]`)?.getAttribute('data-originaltext')));
  if (checked.length !== orders.length || !orders.every((o) => checked.includes(o))) {
    return { clicked: false, reason: 'selection_mismatch', checked };
  }
  const button = frame.getByRole('toolbar', { name: 'Handling' }).getByRole('button', { name: 'Last ned', exact: true });
  if ((await button.count()) !== 1) return { clicked: false, reason: 'download_button_not_unique' };
  await button.click();
  return { clicked: true, checked };
}

// Open an order's log view (it replaces the order table in the same tab as
// TRA014) and click the log file link. The file lands in Chrome's download
// folder; the caller detects it there.
async function opOpenLog(page, { company, order }) {
  const tabName = `${company} Dine bestilte rapporter : TRA003`;
  const frame = await u4ActivityFrame(page, tabName);
  const row = frame.locator('tr[id^="b_g1s2_row"]').filter({ has: frame.locator(`td[onclick*="'orderno'"] div[data-originaltext="${order}"]`) });
  if ((await row.count()) !== 1) return { ok: false, reason: 'row_not_unique' };
  const reportName = await row.locator(`td[onclick*="'description'"] div[data-originaltext]`).getAttribute('data-originaltext');
  await row.getByRole('button', { name: 'Vis logg' }).click();
  const deadline = Date.now() + 30000;
  let logTab = null;
  while (Date.now() < deadline && !logTab) {
    logTab = (await u4Tabs(page)).find((t) => t.name.startsWith(`${company} `) && t.name.endsWith(' : TRA014'))?.name ?? null;
    if (!logTab) await page.waitForTimeout(300);
  }
  if (!logTab) return { ok: false, reason: 'log_view_not_opened' };
  // The tab is renamed before its frame swaps from the order table to the
  // log view, so re-resolve the frame until the log link is present.
  let link = null;
  while (Date.now() < deadline + 20000) {
    const logFrame = await u4ActivityFrame(page, logTab).catch(() => null);
    const candidate = logFrame?.getByRole('link', { name: new RegExp(`_${order}\\.log$`) });
    const n = candidate ? await candidate.count() : 0;
    if (n > 1) return { ok: false, reason: 'log_link_not_unique', logTab };
    if (n === 1) { link = candidate; break; }
    await page.waitForTimeout(400);
  }
  if (!link) return { ok: false, reason: 'log_link_missing', logTab };
  const logName = (await link.innerText()).trim();
  await link.click();
  return { ok: true, logTab, logName, reportName };
}

async function opClearBuffer(page) {
  await page.getByRole('toolbar', { name: 'Program' }).getByRole('button', { name: /Handlingsmeny$/ }).click();
  await page.getByRole('link', { name: 'Om Unit4 ERP', exact: true }).click();
  const about = page.getByRole('dialog').filter({ hasText: 'Tøm bufferen' });
  await about.getByRole('button', { name: 'Tøm bufferen', exact: true }).click();
  const done = page.locator('[role=alertdialog]:visible, [role=dialog]:visible').filter({ hasText: 'Fullført' });
  await done.first().waitFor({ timeout: 30000 });
  await done.getByRole('button', { name: 'OK', exact: true }).first().click();
  await page.getByRole('dialog').getByRole('button', { name: 'Steng (Escape)', exact: true }).click().catch(() => {});
  await page.waitForTimeout(1500);
  return { ok: (await u4Modals(page)).length === 0, company: await u4Company(page) };
}

// Free Unit4's activity slots: the user menu's log-out entry opens the
// "Do you want to log out of your account?" page, and "Return to the
// application" reloads Unit4 in the same session with no activities open.
// Never clicks "Yes".
async function opLogoutReturn(page) {
  const logoutName = /^(Logg ut|Logg av|Log out|Logout|Sign out)$/i;
  await page.getByRole('toolbar', { name: 'Program' }).getByRole('button', { name: /Handlingsmeny$/ }).click();
  const entry = page.getByRole('link', { name: logoutName })
    .or(page.getByRole('menuitem', { name: logoutName }))
    .or(page.getByRole('button', { name: logoutName }))
    .filter({ visible: true });
  await entry.first().waitFor({ timeout: 10000 }).catch(() => {});
  if ((await entry.count()) !== 1) {
    await page.keyboard.press('Escape');
    return { ok: false, reason: 'logout_entry_not_unique', count: await entry.count() };
  }
  await entry.click();
  const back = page.getByRole('button', { name: /^(Return to the application|Tilbake til applikasjonen)$/i })
    .or(page.getByRole('link', { name: /^(Return to the application|Tilbake til applikasjonen)$/i }));
  try {
    await back.first().waitFor({ timeout: 30000 });
  } catch {
    return { ok: false, reason: 'return_button_missing', url: page.url().replace(/[?#].*/, '') };
  }
  if ((await back.count()) !== 1) return { ok: false, reason: 'return_button_not_unique' };
  await back.click();
  // Unit4 reloads; the company button reappears once the shell is ready.
  const deadline = Date.now() + 90000;
  while (Date.now() < deadline) {
    const company = await u4Company(page).catch(() => null);
    if (company) {
      await page.waitForTimeout(1000);
      return { ok: true, company, tabs: await u4Tabs(page).catch(() => []) };
    }
    await page.waitForTimeout(500);
  }
  return { ok: false, reason: 'application_not_ready', url: page.url().replace(/[?#].*/, '') };
}

// Read-only: run Playwright's actionability checks on Lagre without clicking.
async function opProbeLagre(page, { tabName }) {
  const frame = await u4ActivityFrame(page, tabName);
  const lagre = u4LagreButton(frame);
  if ((await lagre.count()) !== 1) return { ok: false, reason: 'lagre_not_unique', count: await lagre.count() };
  const hitTarget = await lagre.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    const describe = (n) => n ? `${n.tagName.toLowerCase()}#${n.id}.${[...n.classList].slice(0, 3).join('.')}` : null;
    return { rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)], inside: !!hit && (hit === el || el.contains(hit)), hit: describe(hit), viewport: [innerWidth, innerHeight], html: el.outerHTML.slice(0, 300) };
  });
  let trial;
  try {
    await lagre.dblclick({ trial: true, timeout: 8000 });
    trial = 'ok';
  } catch (error) {
    trial = String(error.message ?? error).slice(0, 1500);
  }
  return { ok: trial === 'ok', trial, hitTarget, enabled: await lagre.isEnabled(), visible: await lagre.isVisible() };
}

async function opCloseTab(page, { tabName }) {
  return u4CloseTab(page, tabName);
}

// Close exactly the named activity tabs that are open; leave everything else.
async function opCloseTabs(page, { tabNames }) {
  const open = new Set((await u4Tabs(page)).map((t) => t.name));
  const closed = [];
  const failed = [];
  for (const name of tabNames) {
    if (!open.has(name)) continue;
    const res = await u4CloseTab(page, name);
    if (res.closed && !res.modals?.length) closed.push(name);
    else { failed.push({ name, ...res }); break; }
  }
  return { closed, failed };
}

async function opSnapshot(page, { tabName, maxChars }) {
  const target = tabName ? await u4ActivityFrame(page, tabName) : page;
  const snap = await target.locator('body').ariaSnapshot({ timeout: 15000 });
  return { snapshot: snap.slice(0, maxChars ?? 8000), truncated: snap.length > (maxChars ?? 8000) };
}

export const helpers = [
  u4Visibility, u4Company, u4Tabs, u4Modals, u4State, u4ActivityFrame, u4CloseTab,
  u4OpenFromSearch, u4Field, u4FieldState, u4SelectFromDropdown, u4CommitLookup, u4LagreButton,
];

export const ops = {
  opState, opSelectCompany, opEnsureReport, opSetParams, opReadParams, opScanOrders, opLagre,
  opAckSuccess, opSelectRows, opClickDownload, opOpenLog, opCloseTab, opCloseTabs, opProbeLagre,
  opClearBuffer, opLogoutReturn, opSnapshot,
};

export const constants = { ACTIVITY_LIMIT_TEXT };
