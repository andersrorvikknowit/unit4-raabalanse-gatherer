// Guarded Unit4 workflows. Browser steps run through the Bridge; every run
// state transition goes through scripts/run_manifest.py. Each workflow stops
// with a machine-readable status instead of guessing.

import fs from 'node:fs/promises';
import { Bridge, BridgeError } from './bridge.ts';
import { ZIP_PATTERN, logPattern, snapshot, waitForNew } from './downloads.ts';
import { parseUnit4Log, verifyEmptyResultLog } from './logparse.ts';
import { ManifestError, manifestCall, manifestRequire, manifestShow, type ManifestRecord, type RecordKey } from './manifest.ts';

export interface ReportDef {
  searchTitle: string;
  heading: string;
  viewId: string;
  path: string;
  tableNames: string[];
  checkFields: string[];
  expectVisible: Record<string, string>;
}

const PERIODIC = 'Regnskap/Hovedbok/Rapporter/Periodiske lister';

export const REPORTS: Record<'raw_balance' | 'customers' | 'suppliers', ReportDef> = {
  raw_balance: {
    searchTitle: 'Råbalanse', heading: 'Råbalanse', viewId: 'TRA015', path: 'Regnskap/Hovedbok/Rapporter',
    tableNames: ['Råbalanse'],
    checkFields: ['Variant', 'Periode', 'Beløps kolonne'],
    expectVisible: { Variant: 'Råbalanse', 'Beløps kolonne': 'Beløp' },
  },
  customers: {
    searchTitle: 'Periodisert saldospesifikasjon kunder', heading: 'Periodisert saldospesifikasjon kunder',
    viewId: 'TRA015', path: PERIODIC,
    tableNames: ['Periodisert saldospesifikasjon kunder'],
    checkFields: ['Konto', 'Periode', 'Beløps kolonne'],
    expectVisible: { 'Beløps kolonne': 'Beløp' },
  },
  suppliers: {
    // The search result says "leverandør"; the opened form's heading says "leverandører".
    searchTitle: 'Periodisert saldospesifikasjon leverandør', heading: 'Periodisert saldospesifikasjon leverandører',
    viewId: 'TRA015', path: PERIODIC,
    tableNames: ['Periodisert saldospesifikasjon leverandør', 'Periodisert saldospesifikasjon leverandører'],
    checkFields: ['Konto', 'Periode', 'Beløps kolonne', 'Leverandørgruppe'],
    expectVisible: { 'Beløps kolonne': 'Beløp', Leverandørgruppe: '*' },
  },
};

export const KEY_ORDER: RecordKey[] = ['raw_balance', '1510', '1560', '2440', '2444', '2460'];

export function reportFor(key: RecordKey): 'raw_balance' | 'customers' | 'suppliers' {
  if (key === 'raw_balance') return 'raw_balance';
  return key === '1510' || key === '1560' ? 'customers' : 'suppliers';
}

const SCOPE_KEYS: Record<string, RecordKey[]> = {
  raw_balance: ['raw_balance'],
  customers: ['1510', '1560'],
  suppliers: ['2440', '2444', '2460'],
};

export type Outcome = { status: string; [key: string]: unknown };

// The activity tabs a run opens for one company: the three report forms, the
// order table, and log views (TRA014, titled by report). Log views first, as
// they stack on top of the order table.
export function runTabNames(company: string): string[] {
  const reports = Object.values(REPORTS);
  const logTitles = [...new Set(reports.flatMap((r) => [r.heading, ...r.tableNames]))];
  return [
    ...logTitles.map((t) => `${company} ${t} : TRA014`),
    `${company} Dine bestilte rapporter : TRA003`,
    ...reports.map((r) => `${company} ${r.heading} : ${r.viewId}`),
  ];
}

export function formatDate(date: Date): string {
  const dd = String(date.getDate()).padStart(2, '0');
  const mm = String(date.getMonth() + 1).padStart(2, '0');
  return `${dd}.${mm}.${date.getFullYear()}`;
}

function daysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return formatDate(d);
}

const SUCCESS_RE = /Rapporten har ordrenummer (\d+)(?!\d)/;

export function parseConfirmation(dialogs: Array<{ kind: string | null; text: string }>): string | null {
  const success = dialogs.filter((d) => d.kind === 'u4_messageoverlay_success');
  if (success.length !== 1 || dialogs.length !== 1) return null;
  return SUCCESS_RE.exec(success[0].text)?.[1] ?? null;
}

interface StateInfo {
  visibility: string;
  loggedIn: boolean;
  company: { code: string; name: string } | null;
  tabs: Array<{ name: string; selected: boolean }>;
  modals: Array<{ kind: string | null; text: string }>;
}

interface ScanResult {
  ok: boolean;
  reason?: string;
  tabName?: string;
  rows: Array<{ order: string | null; report: string | null; user: string | null; file: string | null; status: string | null; checked: boolean | null }>;
  paged?: boolean;
}

function decodeEntities(value: string | null): string | null {
  return value == null ? value : value.replace(/&#(\d+);/g, (_, n) => String.fromCharCode(Number(n))).replace(/&amp;/g, '&');
}

export class Unit4 {
  readonly bridge: Bridge;
  private bufferCleared = false;
  private downloadClicks = new Map<string, number>();
  // Baseline scan window per manifest and report scope, so the post-click
  // comparison uses the exact same table scope as the baseline.
  private windows = new Map<string, { fromDate: string; toDate: string }>();

  constructor(bridge = new Bridge()) {
    this.bridge = bridge;
  }

  async state(): Promise<StateInfo> {
    return this.bridge.run<StateInfo>('opState');
  }

  // Common precondition: visible window, no modal, the expected company.
  private async guard(company?: string): Promise<Outcome | null> {
    const s = await this.state();
    if (s.visibility !== 'visible') {
      return { status: 'NEEDS_USER', reason: 'window_hidden', message: 'Bring the Unit4 Chrome window to the front and keep it un-minimized, then retry.' };
    }
    if (!s.loggedIn) return { status: 'NEEDS_USER', reason: 'not_logged_in', message: 'Complete Unit4 sign-in in the shared tab, then retry.' };
    if (s.modals.length) return { status: 'NEEDS_USER', reason: 'modal_open', modals: s.modals };
    if (company && s.company?.code !== company) return { status: 'NEEDS_USER', reason: 'company_mismatch', active: s.company };
    return null;
  }

  async attach(): Promise<Outcome> {
    const s = await this.state();
    const blocked = await this.guard();
    return { status: blocked ? blocked.status : 'OK', ...(blocked ?? {}), state: s };
  }

  async selectCompany(code: string, name?: string): Promise<Outcome> {
    const blocked = await this.guard();
    if (blocked) return blocked;
    const res = await this.bridge.run<Record<string, unknown>>('opSelectCompany', { code, name }, 90000);
    return { status: res.ok ? 'OK' : 'BLOCKED', ...res };
  }

  private async scan(company: string, fromTabName: string | undefined, window: { fromDate: string; toDate: string }): Promise<ScanResult> {
    const res = await this.bridge.run<ScanResult>('opScanOrders', { company, fromTabName, ...window }, 90000);
    if (res.ok) res.rows = res.rows.map((r) => ({ ...r, report: decodeEntities(r.report), file: decodeEntities(r.file) }));
    return res;
  }

  private async ensureReport(company: string, key: RecordKey): Promise<{ ok: true; tabName: string } | { ok: false; outcome: Outcome }> {
    const res = await this.bridge.run<Record<string, any>>('opEnsureReport', { company, report: REPORTS[reportFor(key)] }, 90000);
    if (res.ok) return { ok: true, tabName: res.tabName };
    const status = res.reason === 'activity_limit' ? 'ACTIVITY_LIMIT' : 'BLOCKED';
    return { ok: false, outcome: { status, ...res } };
  }

  private verifyParams(key: RecordKey, period: string, read: Record<string, any>): string[] {
    const report = REPORTS[reportFor(key)];
    const problems: string[] = [];
    if (read.heading !== report.heading) problems.push('heading');
    const field = (label: string) => read.fields[label] ?? { present: false };
    for (const label of report.checkFields) if (!field(label).present) problems.push(`missing:${label}`);
    const periode = field('Periode');
    if (periode.visible !== period || periode.committed !== period) problems.push('Periode');
    if (key !== 'raw_balance') {
      const konto = field('Konto');
      if (konto.visible !== key || konto.committed !== key) problems.push('Konto');
    }
    for (const [label, value] of Object.entries(report.expectVisible)) if (field(label).visible !== value) problems.push(label);
    if (read.lagreCount !== 1 || !read.lagreEnabled) problems.push('Lagre');
    if (read.modals?.length) problems.push('modal');
    return problems;
  }

  // Baseline for this key: cached from the previous key in the same report
  // scope (its baseline plus its confirmed order), or a fresh complete scan.
  private async baselineFor(manifestPath: string, records: Record<RecordKey, ManifestRecord>, key: RecordKey, company: string, tabName: string): Promise<{ ok: true; orders: string[]; window: { fromDate: string; toDate: string } } | { ok: false; outcome: Outcome }> {
    const scope = reportFor(key);
    const scopeKey = `${manifestPath}#${scope}`;
    const prior = SCOPE_KEYS[scope].slice(0, SCOPE_KEYS[scope].indexOf(key)).map((k) => records[k]);
    const window = this.windows.get(scopeKey);
    if (records[key].state === 'RETRY_ALLOWED') {
      // The retry must reuse the recorded baseline and the same table scope.
      const retryWindow = window ?? { fromDate: daysAgo(1), toDate: daysAgo(0) };
      this.windows.set(scopeKey, retryWindow);
      return { ok: true, orders: records[key].baseline_orders, window: retryWindow };
    }
    if (prior.length && window) {
      const last = prior[prior.length - 1];
      if (last.order_number) return { ok: true, orders: [...new Set([...last.baseline_orders, last.order_number])], window };
    }
    const fresh = { fromDate: daysAgo(1), toDate: daysAgo(0) };
    const scan = await this.scan(company, tabName, fresh);
    if (!scan.ok) return { ok: false, outcome: { status: 'BLOCKED', reason: scan.reason } };
    if (scan.paged) return { ok: false, outcome: { status: 'BLOCKED', reason: 'order_table_paged_unsupported' } };
    this.windows.set(scopeKey, fresh);
    const orders = scan.rows.map((r) => r.order).filter((o): o is string => !!o);
    return { ok: true, orders, window: fresh };
  }

  async order(manifestPath: string, key: RecordKey): Promise<Outcome> {
    const m = await manifestShow(manifestPath);
    const company = m.company;
    const period = m.period;
    const record = m.records[key];
    if (!['PLANNED', 'RETRY_ALLOWED', 'SUBMITTING'].includes(record.state)) {
      return { status: 'BLOCKED', reason: `record_state_${record.state}`, record };
    }
    const blocked = await this.guard(company);
    if (blocked) return blocked;

    const ensured = await this.ensureReport(company, key);
    if (!ensured.ok) return ensured.outcome;
    const tabName = ensured.tabName;

    // An interrupted save (tool error or restart after begin): never click
    // blind. Resolve it with the same-scope table evidence first.
    if (record.state === 'SUBMITTING') {
      const scopeKey = `${manifestPath}#${reportFor(key)}`;
      const window = this.windows.get(scopeKey) ?? { fromDate: daysAgo(1), toDate: daysAgo(0) };
      this.windows.set(scopeKey, window);
      return this.afterUnconfirmed(manifestPath, key, company, period, tabName, record.baseline_orders, window, record.attempts,
        { clicked: 'unknown', lagreDisabledSeen: false, dialogs: [], resumed: true });
    }

    const base = await this.baselineFor(manifestPath, m.records, key, company, tabName);
    if (!base.ok) return base.outcome;

    const read = await this.bridge.run<Record<string, any>>('opSetParams', {
      tabName, report: REPORTS[reportFor(key)], period, account: key === 'raw_balance' ? null : key,
    }, 90000);
    const problems = this.verifyParams(key, period, read);
    if (problems.length) return { status: 'BLOCKED', reason: 'parameters_not_committed', problems, fields: read.fields };

    return this.submit(manifestPath, key, company, period, tabName, base.orders, base.window);
  }

  private async submit(manifestPath: string, key: RecordKey, company: string, period: string, tabName: string, baseline: string[], window: { fromDate: string; toDate: string }): Promise<Outcome> {
    const begun = await manifestRequire('begin', ['--manifest', manifestPath, '--key', key, '--baseline', ...baseline]);
    const attempt: number = begun.record.attempts;

    const save = await this.bridge.run<Record<string, any>>('opLagre', { tabName, waitMs: 30000 }, 90000);
    const dialogs = (save.dialogs ?? []) as Array<{ kind: string | null; text: string }>;
    const order = parseConfirmation(dialogs);
    if (order) {
      const confirmed = await manifestRequire('confirm', ['--manifest', manifestPath, '--key', key, '--order-number', order]);
      await this.bridge.run('opAckSuccess');
      return { status: 'CONFIRMED', key, order, attempt, ms: save.ms, record: confirmed.record };
    }

    return this.afterUnconfirmed(manifestPath, key, company, period, tabName, baseline, window, attempt, save);
  }

  // No readable confirmation: compare the same-scope table with the baseline,
  // then let the manifest helper decide between one retry and UNKNOWN.
  private async afterUnconfirmed(manifestPath: string, key: RecordKey, company: string, period: string, tabName: string, baseline: string[], window: { fromDate: string; toDate: string }, attempt: number, save: Record<string, any>): Promise<Outcome> {
    const dialogs = (save.dialogs ?? []) as Array<{ kind: string | null; text: string }>;
    const submissionObserved = Boolean(save.lagreDisabledSeen || dialogs.length);
    const scan = await this.scan(company, tabName, window);
    const observed = scan.ok ? scan.rows.map((r) => r.order).filter((o): o is string => !!o) : [];
    const evidence = { dialogs, lagreDisabledSeen: save.lagreDisabledSeen, clicked: save.clicked, reason: save.reason, error: save.error, hitTarget: save.hitTarget, resumed: save.resumed, scanOk: scan.ok, paged: scan.paged };

    if (attempt >= 2 || !scan.ok || scan.paged) {
      const res = await manifestCall(['mark-unknown', '--manifest', manifestPath, '--key', key,
        '--reason', attempt >= 2 ? 'confirmation_missing_after_second_attempt' : 'order_table_unreadable', '--observed', ...observed]);
      return { status: 'UNKNOWN', key, attempt, evidence, manifest: res.payload };
    }
    const retry = await manifestCall(['retry-allowed', '--manifest', manifestPath, '--key', key,
      '--observed', ...observed, '--submission-state-observed', String(submissionObserved)]);
    if (retry.exitCode !== 0) {
      return { status: 'UNKNOWN', key, attempt, evidence, candidates: observed.filter((o) => !baseline.includes(o)), manifest: retry.payload };
    }
    // When the click never reached Unit4 (actionability failure) or the save
    // was interrupted, the cause is still present: stop with the retry granted
    // so the next unit4_order call uses it once the cause is understood.
    if (save.resumed || save.reason === 'dblclick_failed' || save.clicked === false) {
      return { status: 'RETRY_ALLOWED', key, attempt, evidence, message: 'No submission evidence; one retry is recorded as allowed. Resolve the cause, then call unit4_order again.' };
    }

    // One guarded retry: the unchanged form must still be correct and idle.
    const reread = await this.bridge.run<Record<string, any>>('opReadParams', { tabName, report: REPORTS[reportFor(key)] });
    const problems = this.verifyParams(key, period, reread);
    if (problems.length) {
      await manifestCall(['block', '--manifest', manifestPath, '--reason', 'retry_preconditions_failed']);
      return { status: 'BLOCKED', reason: 'retry_preconditions_failed', problems, key };
    }
    return this.submit(manifestPath, key, company, period, tabName, baseline, window);
  }

  // Poll the order table until every identified order is Ferdig, one fails,
  // or the timeout passes. Only exact order-number rows are considered.
  async waitOrders(manifestPath: string, timeoutS: number): Promise<Outcome> {
    let m = await manifestShow(manifestPath);
    const company = m.company;
    const blocked = await this.guard(company);
    if (blocked) return blocked;
    const deadline = Date.now() + Math.min(timeoutS, 900) * 1000;
    const window = { fromDate: daysAgo(7), toDate: daysAgo(0) };
    const fromTabName = (await this.state()).tabs.find((t) => t.name.startsWith(`${company} `) && t.name.endsWith(' : TRA015'))?.name;
    for (;;) {
      m = await manifestShow(manifestPath);
      const pending = KEY_ORDER.filter((k) => ['CONFIRMED', 'TRACKING'].includes(m.records[k].state));
      if (!pending.length) break;
      const scan = await this.scan(company, fromTabName, window);
      if (!scan.ok) return { status: 'BLOCKED', reason: scan.reason };
      if (scan.paged) return { status: 'BLOCKED', reason: 'order_table_paged_unsupported' };
      for (const key of pending) {
        const rec = m.records[key];
        const rows = scan.rows.filter((r) => r.order === rec.order_number);
        if (rows.length !== 1) continue;
        const row = rows[0];
        if (!row.report || !REPORTS[reportFor(key)].tableNames.includes(row.report)) {
          return { status: 'BLOCKED', reason: 'report_name_mismatch', key, order: rec.order_number, report: row.report };
        }
        if (row.status && /feil|error|avbrutt|failed|stoppet/i.test(row.status)) {
          return { status: 'FAILED', key, order: rec.order_number, visibleStatus: row.status };
        }
        if (row.file !== rec.filename || row.status !== rec.visible_status) {
          const args = ['--manifest', manifestPath, '--key', key];
          if (row.file) args.push('--filename', row.file, '--filename-kind', 'FULL');
          if (row.status) args.push('--visible-status', row.status);
          await manifestRequire('track', args);
        }
        if (row.status === 'Ferdig' && row.file) await manifestRequire('finish-order', ['--manifest', manifestPath, '--key', key]);
      }
      if (Date.now() > deadline) break;
      m = await manifestShow(manifestPath);
      if (!KEY_ORDER.some((k) => ['CONFIRMED', 'TRACKING'].includes(m.records[k].state))) break;
      await new Promise((r) => setTimeout(r, 10000));
    }
    m = await manifestShow(manifestPath);
    const summary = Object.fromEntries(KEY_ORDER.map((k) => [k, { state: m.records[k].state, order: m.records[k].order_number, file: m.records[k].filename, visibleStatus: m.records[k].visible_status }]));
    const allFinished = KEY_ORDER.every((k) => m.records[k].state === 'FINISHED');
    if (allFinished && m.run_state === 'ACTIVE') await manifestRequire('complete', ['--manifest', manifestPath]);
    const stillPending = KEY_ORDER.some((k) => ['CONFIRMED', 'TRACKING'].includes(m.records[k].state));
    const agm = KEY_ORDER.filter((k) => m.records[k].filename?.toLowerCase().endsWith('.agm'));
    return { status: stillPending ? 'STILL_PENDING' : allFinished ? 'COMPLETE' : 'FINISHED_SO_FAR', records: summary, needsAgmVerification: agm };
  }

  async verifyEmptyAgm(manifestPath: string, key: RecordKey): Promise<Outcome> {
    if (reportFor(key) !== 'suppliers') return { status: 'BLOCKED', reason: 'agm_only_for_supplier_reports' };
    const m = await manifestShow(manifestPath);
    const rec = m.records[key];
    if (!rec.order_number || !rec.filename?.toLowerCase().endsWith('.agm')) return { status: 'BLOCKED', reason: 'record_has_no_agm', record: rec };
    const blocked = await this.guard(m.company);
    if (blocked) return blocked;
    const scan = await this.scan(m.company, undefined, { fromDate: daysAgo(7), toDate: daysAgo(0) });
    if (!scan.ok) return { status: 'BLOCKED', reason: scan.reason };
    const pattern = logPattern(rec.order_number);
    const before = await snapshot(pattern);
    const opened = await this.bridge.run<Record<string, any>>('opOpenLog', { company: m.company, order: rec.order_number }, 60000);
    if (!opened.ok) return { status: 'BLOCKED', ...opened };
    const file = await waitForNew(before, pattern, 60000);
    await this.bridge.run('opCloseTab', { tabName: opened.logTab });
    if (file.status !== 'OK') return { status: 'BLOCKED', reason: `log_download_${file.status.toLowerCase()}`, candidates: file.candidates };
    const log = parseUnit4Log(await fs.readFile(file.path, 'utf8'));
    const result = verifyEmptyResultLog(log, { order: rec.order_number, company: m.company, period: m.period, account: key });
    return {
      status: result.verified ? 'VERIFIED_EMPTY' : 'NOT_VERIFIED',
      key, order: rec.order_number, logPath: file.path, checks: result.checks,
      parameterNames: result.parameterNames, allowEmptyAgm: result.verified ? rec.filename : null,
    };
  }

  async downloadZip(manifestPath: string): Promise<Outcome> {
    const m = await manifestShow(manifestPath);
    if (m.run_state !== 'COMPLETE') return { status: 'BLOCKED', reason: `run_state_${m.run_state}` };
    const clicks = this.downloadClicks.get(manifestPath) ?? 0;
    if (clicks >= 2 || (clicks === 1 && !this.bufferCleared)) {
      return { status: 'BLOCKED', reason: clicks >= 2 ? 'download_attempts_exhausted' : 'buffer_clear_required_before_retry' };
    }
    const blocked = await this.guard(m.company);
    if (blocked) return blocked;
    const orders = KEY_ORDER.map((k) => m.records[k].order_number!);
    const fromTabName = (await this.state()).tabs.find((t) => t.name.startsWith(`${m.company} `) && t.name.endsWith(' : TRA015'))?.name;
    let scan = await this.scan(m.company, fromTabName, { fromDate: daysAgo(30), toDate: daysAgo(0) });
    if (!scan.ok && !fromTabName) {
      const ensured = await this.ensureReport(m.company, 'raw_balance');
      if (!ensured.ok) return ensured.outcome;
      scan = await this.scan(m.company, ensured.tabName, { fromDate: daysAgo(30), toDate: daysAgo(0) });
    }
    if (!scan.ok) return { status: 'BLOCKED', reason: scan.reason };
    if (scan.paged) return { status: 'BLOCKED', reason: 'order_table_paged_unsupported' };
    for (const key of KEY_ORDER) {
      const rec = m.records[key];
      const rows = scan.rows.filter((r) => r.order === rec.order_number);
      const row = rows[0];
      if (rows.length !== 1 || row.status !== 'Ferdig' || row.file !== rec.filename || !row.report || !REPORTS[reportFor(key)].tableNames.includes(row.report)) {
        return { status: 'BLOCKED', reason: 'row_identity_mismatch', key, order: rec.order_number, row: row ?? null };
      }
    }
    const selected = await this.bridge.run<{ checked: string[] }>('opSelectRows', { tabName: scan.tabName, orders });
    const exact = selected.checked.length === orders.length && orders.every((o) => selected.checked.includes(o));
    if (!exact) return { status: 'BLOCKED', reason: 'selection_not_exact', checked: selected.checked };

    const before = await snapshot(ZIP_PATTERN);
    const clicked = await this.bridge.run<Record<string, any>>('opClickDownload', { tabName: scan.tabName, orders });
    if (!clicked.clicked) return { status: 'BLOCKED', ...clicked };
    this.downloadClicks.set(manifestPath, clicks + 1);
    const file = await waitForNew(before, ZIP_PATTERN, 180000);
    if (file.status !== 'OK') {
      return { status: 'NO_UNIQUE_ZIP', reason: file.status, candidates: file.candidates, orders, message: 'Recovery: unit4_clear_buffer with consent, then retry once.' };
    }
    const agm = KEY_ORDER.map((k) => m.records[k].filename!).filter((f) => f.toLowerCase().endsWith('.agm'));
    // Done with Unit4 for this run: free the activities (Unit4 allows 10).
    const tabs = await this.bridge.run<{ closed: string[]; failed: unknown[] }>('opCloseTabs', { tabNames: runTabNames(m.company) })
      .catch((error) => ({ closed: [], failed: [String((error as Error).message ?? error)] }));
    return { status: 'DOWNLOADED', closedTabs: tabs.closed, tabCloseFailures: tabs.failed, zip: file.path, size: file.size, orders, entries: Object.fromEntries(KEY_ORDER.map((k) => [k, m.records[k].filename])), agm };
  }

  async clearBuffer(consent: boolean): Promise<Outcome> {
    if (!consent) return { status: 'BLOCKED', reason: 'consent_required' };
    if (this.bufferCleared) return { status: 'BLOCKED', reason: 'buffer_already_cleared_this_session' };
    const s = await this.state();
    if (s.visibility !== 'visible') return { status: 'NEEDS_USER', reason: 'window_hidden' };
    const res = await this.bridge.run<Record<string, unknown>>('opClearBuffer', {}, 90000);
    this.bufferCleared = true;
    return { status: res.ok ? 'OK' : 'BLOCKED', ...res };
  }

  async closeTabs(company: string): Promise<Outcome> {
    const blocked = await this.guard();
    if (blocked) return blocked;
    const res = await this.bridge.run<{ closed: string[]; failed: unknown[] }>('opCloseTabs', { tabNames: runTabNames(company) });
    return { status: res.failed.length ? 'BLOCKED' : 'OK', ...res };
  }

  async probeLagre(tabName: string): Promise<Outcome> {
    const res = await this.bridge.run<Record<string, unknown>>('opProbeLagre', { tabName }, 60000);
    return { status: res.ok ? 'OK' : 'NOT_CLICKABLE', ...res };
  }

  async snapshot(tabName?: string, maxChars?: number): Promise<Outcome> {
    const res = await this.bridge.run<Record<string, unknown>>('opSnapshot', { tabName, maxChars });
    return { status: 'OK', ...res };
  }
}

// Map exceptions to structured outcomes so the agent never sees a stack trace.
export async function outcomeOf(fn: () => Promise<Outcome>): Promise<Outcome> {
  try {
    return await fn();
  } catch (error) {
    if (error instanceof ManifestError) return { status: 'BLOCKED', reason: 'manifest_transition_failed', exitCode: error.result.exitCode, manifest: error.result.payload };
    if (error instanceof BridgeError) {
      if (/activity_limit/.test(error.message)) return { status: 'ACTIVITY_LIMIT', message: 'Unit4 allows 10 open activities. Close unused Unit4 tabs, or clear the buffer / log out and in, then retry.' };
      return { status: error.code === 'browser_detached' ? 'NEEDS_USER' : 'ERROR', reason: error.code, detail: error.message };
    }
    return { status: 'ERROR', reason: 'unexpected', detail: String((error as Error).message ?? error).slice(0, 300) };
  }
}
