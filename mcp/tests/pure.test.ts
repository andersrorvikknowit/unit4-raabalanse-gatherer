import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { composeOp, parseRunCodeResult } from '../src/bridge.ts';
import { snapshot, waitForNew, ZIP_PATTERN, logPattern } from '../src/downloads.ts';
import { parseUnit4Log, verifyEmptyResultLog } from '../src/logparse.ts';
import { formatDate, parseConfirmation } from '../src/unit4.ts';

test('composeOp builds a valid function expression with JSON-embedded args', () => {
  const hostile = "'); process.exit(1); ('";
  const code = composeOp('opSelectCompany', { code: hostile });
  // Parses as a single expression; the hostile value stays a string literal.
  assert.doesNotThrow(() => new Function(`return (${code});`));
  assert.ok(code.includes(JSON.stringify({ code: hostile })));
  assert.ok(code.trimEnd().endsWith('}'));
});

test('parseRunCodeResult reads Result and Error sections', () => {
  assert.deepEqual(parseRunCodeResult('### Result\n"{\\"a\\":1}"\n### Ran Playwright code\n```js\nx\n```'), { ok: true, value: { a: 1 } });
  assert.deepEqual(parseRunCodeResult('### Error\nError: tab_missing:x\nstack'), { ok: false, error: 'Error: tab_missing:x' });
  assert.equal(parseRunCodeResult('nothing').ok, false);
});

test('parseConfirmation requires exactly one success overlay with a full order number', () => {
  const ok = { kind: 'u4_messageoverlay_success', text: 'Vellykket Lagring vellykket. Rapporten har ordrenummer 18574 og er tilgjengelig under Dine bestilte rapporter. OK' };
  assert.equal(parseConfirmation([ok]), '18574');
  assert.equal(parseConfirmation([]), null);
  assert.equal(parseConfirmation([{ kind: 'u4_messageoverlay_error', text: 'Feil' }]), null);
  assert.equal(parseConfirmation([ok, { kind: 'u4_messageoverlay_error', text: 'Feil' }]), null);
  assert.equal(parseConfirmation([{ ...ok, text: 'Lagring vellykket.' }]), null);
});

test('formatDate uses dd.MM.yyyy', () => {
  assert.equal(formatDate(new Date(2026, 8, 3)), '03.09.2026');
});

const LOG = [
  '﻿9:55:03 AM 20260929 SU05/20001 [PID 1] started.',
  '9:55:03 AM PROGRAM .........: SU05',
  '9:55:03 AM     Orderno .....: 20001',
  '9:55:03 AM     Client ......: 312',
  '9:55:03 AM PARAMETERS:',
  '9:55:03 AM     Konto (account) = 2440',
  '9:55:03 AM     Periode (period) = 202608',
  '9:55:03 AM     Beløps kolonne (amount_col) = amount',
  '9:55:03 AM -------------------------------------------------------------------------------',
  '9:55:04 AM No rows found. Report stop',
].join('\r\n');

test('parseUnit4Log extracts header and parameters', () => {
  const log = parseUnit4Log(LOG);
  assert.equal(log.orderno, '20001');
  assert.equal(log.client, '312');
  assert.equal(log.program, 'SU05');
  assert.deepEqual(log.parameters.map((p) => p.name), ['account', 'period', 'amount_col']);
  assert.equal(log.noRowsFound, true);
});

test('verifyEmptyResultLog checks every identity field', () => {
  const log = parseUnit4Log(LOG);
  assert.equal(verifyEmptyResultLog(log, { order: '20001', company: '312', period: '202608', account: '2440' }).verified, true);
  for (const wrong of [{ order: '20002' }, { company: '332' }, { period: '202609' }, { account: '2444' }]) {
    const want = { order: '20001', company: '312', period: '202608', account: '2440', ...wrong };
    assert.equal(verifyEmptyResultLog(log, want).verified, false, JSON.stringify(wrong));
  }
  assert.equal(verifyEmptyResultLog(parseUnit4Log(LOG.replace('No rows found. Report stop', 'Report ended')), { order: '20001', company: '312', period: '202608', account: '2440' }).verified, false);
});

test('download patterns', () => {
  assert.ok(ZIP_PATTERN.test('Rapporter_20260929144949.zip'));
  assert.ok(ZIP_PATTERN.test('Rapporter_20260929144949 (1).zip'));
  assert.ok(!ZIP_PATTERN.test('Rapporter_20260929144949.zip.crdownload'));
  assert.ok(logPattern('18574').test('gl09_18574.log'));
  assert.ok(!logPattern('18574').test('gl09_185741.log'));
});

test('waitForNew accepts one new file and rejects ambiguity', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'u4dl-'));
  await fs.writeFile(path.join(dir, 'Rapporter_20260101000000.zip'), 'old');
  const before = await snapshot(ZIP_PATTERN, dir);
  setTimeout(() => void fs.writeFile(path.join(dir, 'Rapporter_20260929144949.zip'), 'new'), 200);
  const one = await waitForNew(before, ZIP_PATTERN, 5000, dir);
  assert.equal(one.status, 'OK');
  assert.equal(one.status === 'OK' && path.basename(one.path), 'Rapporter_20260929144949.zip');

  const before2 = await snapshot(ZIP_PATTERN, dir);
  await fs.writeFile(path.join(dir, 'Rapporter_20260929150000.zip'), 'a');
  await fs.writeFile(path.join(dir, 'Rapporter_20260929150001.zip'), 'b');
  assert.equal((await waitForNew(before2, ZIP_PATTERN, 2000, dir)).status, 'AMBIGUOUS');

  const before3 = await snapshot(ZIP_PATTERN, dir);
  assert.equal((await waitForNew(before3, ZIP_PATTERN, 1200, dir)).status, 'TIMEOUT');
  await fs.rm(dir, { recursive: true });
});
