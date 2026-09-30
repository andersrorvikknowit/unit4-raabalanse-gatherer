// Order-flow tests with a scripted browser and the real manifest helper.

import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { manifestCall, manifestRequire, manifestShow } from '../src/manifest.ts';
import { REPORTS, Unit4, outcomeOf } from '../src/unit4.ts';

type Handler = (args: any) => unknown;

class FakeBridge {
  calls: Array<{ name: string; args: any }> = [];
  handlers: Record<string, Handler | Handler[]>;
  constructor(handlers: Record<string, Handler | Handler[]>) {
    this.handlers = handlers;
  }
  async run(name: string, args: any = {}) {
    this.calls.push({ name, args });
    const h = this.handlers[name];
    if (!h) throw new Error(`unexpected op ${name}`);
    const fn = Array.isArray(h) ? h.shift() : h;
    if (!fn) throw new Error(`no more responses for ${name}`);
    return fn(args);
  }
  async close() {}
  count(name: string) {
    return this.calls.filter((c) => c.name === name).length;
  }
}

const state = (company = '312') => () => ({
  visibility: 'visible', loggedIn: true, modals: [], company: { code: company, name: 'Knowit Experience Oslo AS' },
  tabs: [{ name: `${company} Råbalanse : TRA015`, selected: true }],
});

const goodParams = (key: string, period = '202608') => () => {
  const report = REPORTS[key === 'raw_balance' ? 'raw_balance' : ['1510', '1560'].includes(key) ? 'customers' : 'suppliers'];
  const fields: Record<string, any> = {};
  for (const label of report.checkFields) fields[label] = { label, present: true, visible: report.expectVisible[label] ?? '', committed: report.expectVisible[label] ?? '' };
  fields.Periode = { label: 'Periode', present: true, visible: period, committed: period };
  if (key !== 'raw_balance') fields.Konto = { label: 'Konto', present: true, visible: key, committed: key };
  return { heading: report.heading, fields, lagreCount: 1, lagreEnabled: true, modals: [] };
};

const scan = (orders: string[]) => () => ({
  ok: true, tabName: '312 Dine bestilte rapporter : TRA003', paged: false,
  rows: orders.map((order) => ({ order, report: 'R&#229;balanse', user: 'ANDROR', file: `gl09a_${order}.xlsx`, status: 'Ferdig', checked: false })),
});

const success = (order: string) => () => ({
  clicked: true, ms: 3000, lagreDisabledSeen: true,
  dialogs: [{ kind: 'u4_messageoverlay_success', text: `Vellykket Lagring vellykket. Rapporten har ordrenummer ${order} og er tilgjengelig under Dine bestilte rapporter. OK` }],
});
const silent = () => ({ clicked: true, ms: 30000, lagreDisabledSeen: false, dialogs: [] });

async function newManifest() {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'u4m-'));
  const created = await manifestRequire('create', ['--company', '312', '--period', '202608', '--directory', path.join(dir, 'run')]);
  return { dir, manifest: created.manifest as string };
}

function unit4With(handlers: Record<string, Handler | Handler[]>) {
  const bridge = new FakeBridge({ opState: state(), opEnsureReport: () => ({ ok: true, tabName: '312 Råbalanse : TRA015' }), opAckSuccess: () => ({ ok: true }), ...handlers });
  return { bridge, unit4: new Unit4(bridge as any) };
}

test('confirmed order is recorded with its exact number', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({ opScanOrders: scan(['18567']), opSetParams: goodParams('raw_balance'), opLagre: success('18574') });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'CONFIRMED');
  assert.equal(out.order, '18574');
  const m = await manifestShow(manifest);
  assert.equal(m.records.raw_balance.state, 'CONFIRMED');
  assert.deepEqual(m.records.raw_balance.baseline_orders, ['18567']);
  assert.equal(bridge.count('opLagre'), 1);
  await fs.rm(dir, { recursive: true });
});

test('uncommitted parameters block before begin and never click Lagre', async () => {
  const { dir, manifest } = await newManifest();
  const bad = () => ({ ...goodParams('raw_balance')(), fields: { ...goodParams('raw_balance')().fields, Periode: { label: 'Periode', present: true, visible: '202608', committed: '202609' } } });
  const { bridge, unit4 } = unit4With({ opScanOrders: scan([]), opSetParams: bad });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'BLOCKED');
  assert.deepEqual(out.problems, ['Periode']);
  assert.equal(bridge.count('opLagre'), 0);
  assert.equal((await manifestShow(manifest)).records.raw_balance.state, 'PLANNED');
  await fs.rm(dir, { recursive: true });
});

test('silent first save with unchanged table allows exactly one retry', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opScanOrders: [scan(['18567']), scan(['18567'])],
    opSetParams: goodParams('raw_balance'),
    opReadParams: goodParams('raw_balance'),
    opLagre: [silent, success('18575')],
  });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'CONFIRMED');
  assert.equal(out.attempt, 2);
  assert.equal(bridge.count('opLagre'), 2);
  await fs.rm(dir, { recursive: true });
});

test('silent save with a new table row is UNKNOWN and not retried', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opScanOrders: [scan(['18567']), scan(['18567', '18580'])],
    opSetParams: goodParams('raw_balance'),
    opLagre: silent,
  });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'UNKNOWN');
  assert.deepEqual(out.candidates, ['18580']);
  assert.equal(bridge.count('opLagre'), 1);
  const m = await manifestShow(manifest);
  assert.equal(m.run_state, 'BLOCKED');
  assert.equal(m.records.raw_balance.state, 'UNKNOWN');
  await fs.rm(dir, { recursive: true });
});

test('disabled Lagre without confirmation is UNKNOWN even with an unchanged table', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opScanOrders: [scan(['18567']), scan(['18567'])],
    opSetParams: goodParams('raw_balance'),
    opLagre: () => ({ clicked: true, ms: 30000, lagreDisabledSeen: true, dialogs: [] }),
  });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'UNKNOWN');
  assert.equal(bridge.count('opLagre'), 1);
  await fs.rm(dir, { recursive: true });
});

test('second silent save is marked UNKNOWN', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opScanOrders: [scan(['18567']), scan(['18567']), scan(['18567'])],
    opSetParams: goodParams('raw_balance'),
    opReadParams: goodParams('raw_balance'),
    opLagre: [silent, silent],
  });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'UNKNOWN');
  assert.equal(bridge.count('opLagre'), 2);
  assert.equal((await manifestCall(['show', '--manifest', manifest])).payload.manifest.blocked_reason, 'confirmation_missing_after_second_attempt');
  await fs.rm(dir, { recursive: true });
});

test('account order before raw balance is Ferdig is refused by the manifest without clicking', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({ opScanOrders: scan([]), opSetParams: goodParams('1510'), opLagre: success('13930') });
  const out = await outcomeOf(() => unit4.order(manifest, '1510'));
  assert.equal(out.status, 'BLOCKED');
  assert.equal(out.reason, 'manifest_transition_failed');
  assert.equal(bridge.count('opLagre'), 0);
  await fs.rm(dir, { recursive: true });
});

test('second account in a scope reuses the cached baseline without rescanning', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opScanOrders: [scan(['18567']), scan(['13923'])],
    opSetParams: [goodParams('raw_balance'), goodParams('1510'), goodParams('1560')],
    opLagre: [success('18574'), success('13930'), success('13931')],
  });
  assert.equal((await outcomeOf(() => unit4.order(manifest, 'raw_balance'))).status, 'CONFIRMED');
  await manifestRequire('track', ['--manifest', manifest, '--key', 'raw_balance', '--filename', 'gl09a_18574.xlsx', '--filename-kind', 'FULL', '--visible-status', 'Ferdig']);
  await manifestRequire('finish-order', ['--manifest', manifest, '--key', 'raw_balance']);
  assert.equal((await outcomeOf(() => unit4.order(manifest, '1510'))).status, 'CONFIRMED');
  assert.equal((await outcomeOf(() => unit4.order(manifest, '1560'))).status, 'CONFIRMED');
  assert.equal(bridge.count('opScanOrders'), 2);
  const m = await manifestShow(manifest);
  assert.deepEqual(m.records['1560'].baseline_orders.sort(), ['13923', '13930']);
  await fs.rm(dir, { recursive: true });
});

test('hidden window returns NEEDS_USER without touching the form', async () => {
  const { dir, manifest } = await newManifest();
  const bridge = new FakeBridge({ opState: () => ({ ...state()(), visibility: 'hidden' }) });
  const out = await outcomeOf(() => new Unit4(bridge as any).order(manifest, 'raw_balance'));
  assert.equal(out.status, 'NEEDS_USER');
  assert.equal(out.reason, 'window_hidden');
  assert.deepEqual(bridge.calls.map((c) => c.name), ['opState']);
  await fs.rm(dir, { recursive: true });
});

test('failed double-click grants a retry without clicking again, and the next call retries once', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opScanOrders: [scan(['18567']), scan(['18567'])],
    opSetParams: [goodParams('raw_balance'), goodParams('raw_balance')],
    opLagre: [() => ({ clicked: false, reason: 'dblclick_failed', error: 'TimeoutError', lagreDisabledSeen: false, dialogs: [] }), success('18576')],
  });
  const first = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(first.status, 'RETRY_ALLOWED');
  assert.equal(bridge.count('opLagre'), 1);
  assert.equal((await manifestShow(manifest)).records.raw_balance.state, 'RETRY_ALLOWED');
  const second = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(second.status, 'CONFIRMED');
  assert.equal(second.attempt, 2);
  assert.equal(bridge.count('opLagre'), 2);
  await fs.rm(dir, { recursive: true });
});

test('record left SUBMITTING is resolved by table evidence, never by a blind click', async () => {
  const { dir, manifest } = await newManifest();
  await manifestRequire('begin', ['--manifest', manifest, '--key', 'raw_balance', '--baseline', '18567']);
  const { bridge, unit4 } = unit4With({ opScanOrders: scan(['18567', '18590']) });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'UNKNOWN');
  assert.deepEqual(out.candidates, ['18590']);
  assert.equal(bridge.count('opLagre'), 0);
  await fs.rm(dir, { recursive: true });
});

test('activity limit is cleared by log out > return, restoring the company, then the order proceeds', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opEnsureReport: [() => ({ ok: false, reason: 'activity_limit' }), () => ({ ok: true, tabName: '312 Råbalanse : TRA015' })],
    opLogoutReturn: () => ({ ok: true, company: { code: '100', name: 'Knowit AS' }, tabs: [] }),
    opSelectCompany: (args) => ({ ok: args.code === '312', changed: true, company: { code: '312', name: 'Knowit Experience Oslo AS' } }),
    opScanOrders: scan(['18567']), opSetParams: goodParams('raw_balance'), opLagre: success('18574'),
  });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'CONFIRMED');
  assert.equal(bridge.count('opLogoutReturn'), 1);
  assert.equal(bridge.count('opSelectCompany'), 1);
  assert.equal(bridge.count('opEnsureReport'), 2);
  await fs.rm(dir, { recursive: true });
});

test('activity limit that survives the reset stops before begin', async () => {
  const { dir, manifest } = await newManifest();
  const { bridge, unit4 } = unit4With({
    opEnsureReport: () => ({ ok: false, reason: 'activity_limit' }),
    opLogoutReturn: () => ({ ok: true, company: { code: '312', name: 'Knowit Experience Oslo AS' }, tabs: [] }),
  });
  const out = await outcomeOf(() => unit4.order(manifest, 'raw_balance'));
  assert.equal(out.status, 'ACTIVITY_LIMIT');
  assert.equal(bridge.count('opLogoutReturn'), 1);
  assert.equal(bridge.count('opLagre'), 0);
  assert.equal((await manifestShow(manifest)).records.raw_balance.state, 'PLANNED');
  await fs.rm(dir, { recursive: true });
});
