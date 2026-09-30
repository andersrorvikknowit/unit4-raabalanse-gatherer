#!/usr/bin/env node
// Unit4 Råbalanse MCP server: guarded, high-level Unit4 tools on Playwright
// through the Playwright Extension in the user's own Chrome profile.

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { Unit4, outcomeOf, type Outcome } from './unit4.ts';

const unit4 = new Unit4();
const server = new McpServer({ name: 'unit4-raabalanse', version: '1.0.0' });

const recordKey = z.enum(['raw_balance', '1510', '1560', '2440', '2444', '2460']);
const manifest = z.string().min(1).describe('Absolute path returned by scripts/run_manifest.py create.');

function reply(outcome: Outcome) {
  return { content: [{ type: 'text' as const, text: JSON.stringify(outcome) }] };
}

server.registerTool('unit4_attach', {
  description: 'Attach to the Unit4 tab shared through the Playwright Extension (the first call opens the extension\'s "Allow & select" page) and return window visibility, login state, active company, open activity tabs and any modal. Read-only.',
  inputSchema: {},
}, async () => reply(await outcomeOf(() => unit4.attach())));

server.registerTool('unit4_select_company', {
  description: 'Make the exact company code active (and the name, when given) via the company chooser, then re-verify. No-op when already active.',
  inputSchema: { code: z.string().regex(/^\d{2,10}$/), name: z.string().optional() },
}, async ({ code, name }) => reply(await outcomeOf(() => unit4.selectCompany(code, name))));

server.registerTool('unit4_order', {
  description: 'Place ONE production report order for a manifest record: open or reuse the report form, set Periode through its dropdown and Konto through commit, verify the committed values, record manifest begin with the complete baseline, double-click Lagre once and capture the confirmation order number (manifest confirm). Applies the bounded second-save rule and returns UNKNOWN rather than guessing. Call in the fixed order raw_balance, 1510, 1560, 2440, 2444, 2460; raw_balance must be Ferdig before account orders.',
  inputSchema: { manifest, key: recordKey },
}, async ({ manifest: m, key }) => reply(await outcomeOf(() => unit4.order(m, key))));

server.registerTool('unit4_wait_orders', {
  description: 'Poll "Dine bestilte rapporter" for every confirmed order in the manifest, recording exact filename and status (track / finish-order) until all are Ferdig, one fails, or timeout_s passes (max 900). Marks the manifest complete when all six are finished. Never selects or downloads.',
  inputSchema: { manifest, timeout_s: z.number().int().min(10).max(900).default(900) },
}, async ({ manifest: m, timeout_s }) => reply(await outcomeOf(() => unit4.waitOrders(m, timeout_s))));

server.registerTool('unit4_verify_empty_agm', {
  description: 'For a supplier order whose output is su05_<order>.agm: download its Unit4 log and verify order number, company, period, account and "No rows found. Report stop". Returns the exact --allow-empty-agm filename only when verified.',
  inputSchema: { manifest, key: z.enum(['2440', '2444', '2460']) },
}, async ({ manifest: m, key }) => reply(await outcomeOf(() => unit4.verifyEmptyAgm(m, key))));

server.registerTool('unit4_download_zip', {
  description: 'For a COMPLETE manifest: re-verify the six exact rows, tick exactly those checkboxes, click Last ned once and return the path of the single new Rapporter_*.zip in the browser download folder. At most one retry, and only after unit4_clear_buffer.',
  inputSchema: { manifest },
}, async ({ manifest: m }) => reply(await outcomeOf(() => unit4.downloadZip(m))));

server.registerTool('unit4_clear_buffer', {
  description: 'Unit4 "Om Unit4 ERP > Tøm bufferen" recovery. Requires consent=true given by the user for this run; at most once per server session.',
  inputSchema: { consent: z.boolean() },
}, async ({ consent }) => reply(await outcomeOf(() => unit4.clearBuffer(consent))));

server.registerTool('unit4_reset_activities', {
  description: 'Recovery for ACTIVITY_LIMIT ("Systemet tillater at opptil 10 aktiviteter er åpne samtidig"): user menu > log out > "Return to the application" (never "Yes"). Unit4 reloads in the same session with all activities closed; the given company is made active again. unit4_order and unit4_download_zip already do this once automatically when opening a report hits the limit. At most 3 per server session.',
  inputSchema: { company: z.string().regex(/^\d{2,10}$/).optional() },
}, async ({ company }) => reply(await outcomeOf(() => unit4.resetActivities(company))));

server.registerTool('unit4_close_tabs', {
  description: 'Close the activity tabs this skill opens for one company (the three report forms, Dine bestilte rapporter, and report log views). Other Unit4 activities are left open. unit4_download_zip already does this after a successful download.',
  inputSchema: { company: z.string().regex(/^\d{2,10}$/) },
}, async ({ company }) => reply(await outcomeOf(() => unit4.closeTabs(company))));

server.registerTool('unit4_probe_lagre', {
  description: 'Read-only diagnosis for a report tab (exact tab name): runs Playwright\'s actionability checks on Lagre as a trial (no click) and reports what element is under the button.',
  inputSchema: { tab: z.string() },
}, async ({ tab }) => reply(await outcomeOf(() => unit4.probeLagre(tab))));

server.registerTool('unit4_snapshot', {
  description: 'Debug fallback: accessibility snapshot of the whole page or one activity tab (exact tab name). Read-only; may contain confidential data, do not echo it to the user unnecessarily.',
  inputSchema: { tab: z.string().optional(), max_chars: z.number().int().min(500).max(20000).optional() },
}, async ({ tab, max_chars }) => reply(await outcomeOf(() => unit4.snapshot(tab, max_chars))));

const transport = new StdioServerTransport();
await server.connect(transport);

const shutdown = async () => {
  await unit4.bridge.close();
  process.exit(0);
};
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
transport.onclose = shutdown;
