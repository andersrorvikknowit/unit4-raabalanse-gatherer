// Connection to the user's Chrome through the Playwright Extension.
//
// @playwright/mcp's library entry point (createConnection) cannot be used in
// extension mode: its backend reads browser.contexts()[0] before the user has
// shared a tab and fails with "Cannot read properties of undefined". The CLI
// server handles that case, so we run it as a stdio child and only ever call
// its browser_run_code_unsafe tool with code composed from ./page/ops.js.

import { createRequire } from 'node:module';
import path from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { constants, helpers, ops } from './page/ops.js';

const require = createRequire(import.meta.url);

export type OpName = keyof typeof ops;

export class BridgeError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

// Build a self-contained `async (page) => ...` expression. Arguments are
// embedded as a JSON literal, so no caller value is ever parsed as code.
export function composeOp(name: OpName, args: unknown): string {
  const lines = [
    'async (page) => {',
    `const ACTIVITY_LIMIT_TEXT = ${JSON.stringify(constants.ACTIVITY_LIMIT_TEXT)};`,
    ...helpers.map((fn) => fn.toString()),
    ...Object.values(ops).map((fn) => fn.toString()),
    `return JSON.stringify(await ${ops[name].name}(page, ${JSON.stringify(args ?? {})}));`,
    '}',
  ];
  return lines.join('\n');
}

// Playwright MCP returns markdown with "### Result" / "### Error" sections.
export function parseRunCodeResult(text: string): { ok: true; value: unknown } | { ok: false; error: string } {
  const section = (title: string) => {
    const match = new RegExp(`^### ${title}\\n([\\s\\S]*?)(?=^### |(?![\\s\\S]))`, 'm').exec(text);
    return match ? match[1].trim() : null;
  };
  const error = section('Error');
  if (error !== null) return { ok: false, error: error.split('\n')[0].slice(0, 500) };
  const result = section('Result');
  if (result === null) return { ok: false, error: 'no_result_section' };
  try {
    const outer = JSON.parse(result);
    return { ok: true, value: typeof outer === 'string' ? JSON.parse(outer) : outer };
  } catch {
    return { ok: false, error: 'unparseable_result' };
  }
}

export class Bridge {
  private client: Client | null = null;
  private connecting: Promise<Client> | null = null;

  private async connect(): Promise<Client> {
    const cli = path.join(path.dirname(require.resolve('@playwright/mcp/package.json')), 'cli.js');
    const transport = new StdioClientTransport({
      command: process.execPath,
      args: [cli, '--extension'],
      env: { ...process.env } as Record<string, string>,
      stderr: 'ignore',
    });
    const client = new Client({ name: 'unit4-raabalanse', version: '1' });
    transport.onclose = () => {
      if (this.client === client) this.client = null;
    };
    await client.connect(transport);
    return client;
  }

  private async getClient(): Promise<Client> {
    if (this.client) return this.client;
    this.connecting ??= this.connect().finally(() => { this.connecting = null; });
    this.client = await this.connecting;
    return this.client;
  }

  // The first call waits for the user to approve the extension's connect page.
  async run<T = Record<string, unknown>>(name: OpName, args: unknown = {}, timeoutMs = 120000): Promise<T> {
    // Allow time for the user to approve the connect page on first use.
    if (!this.client) timeoutMs = Math.max(timeoutMs, 600000);
    const client = await this.getClient();
    let text: string;
    try {
      const response = await client.callTool(
        { name: 'browser_run_code_unsafe', arguments: { code: composeOp(name, args) } },
        undefined,
        { timeout: timeoutMs },
      );
      text = (response.content as Array<{ type: string; text?: string }>).map((c) => c.text ?? '').join('\n');
    } catch (error) {
      throw new BridgeError('bridge_call_failed', String((error as Error).message ?? error));
    }
    const parsed = parseRunCodeResult(text);
    if (!parsed.ok) {
      if (/closed|detached|disconnected/i.test(parsed.error)) {
        await this.close();
        throw new BridgeError('browser_detached', parsed.error);
      }
      throw new BridgeError('page_error', parsed.error);
    }
    return parsed.value as T;
  }

  async close(): Promise<void> {
    const client = this.client;
    this.client = null;
    await client?.close().catch(() => {});
  }
}
