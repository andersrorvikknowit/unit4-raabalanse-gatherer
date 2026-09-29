// Thin wrapper around scripts/run_manifest.py, the single source of truth for
// run state. Arguments go to execFile as separate argv entries (no shell).

import { execFile } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../scripts/run_manifest.py');
const PYTHON = process.env.UNIT4_PYTHON ?? 'python3';

export type RecordKey = 'raw_balance' | '1510' | '1560' | '2440' | '2444' | '2460';

export interface ManifestRecord {
  state: string;
  attempts: number;
  baseline_orders: string[];
  candidate_orders: string[];
  order_number: string | null;
  filename: string | null;
  filename_kind: string;
  visible_status: string | null;
}

export interface ManifestResult {
  exitCode: number;
  payload: Record<string, any>;
}

export class ManifestError extends Error {
  readonly result: ManifestResult;
  constructor(command: string, result: ManifestResult) {
    super(`manifest ${command} exited ${result.exitCode}: ${result.payload.error ?? 'unexpected'}`);
    this.result = result;
  }
}

export function manifestCall(args: string[]): Promise<ManifestResult> {
  return new Promise((resolve) => {
    execFile(PYTHON, [SCRIPT, ...args], { timeout: 30000 }, (error, stdout) => {
      const exitCode = error ? (typeof error.code === 'number' ? error.code : 3) : 0;
      let payload: Record<string, any>;
      try {
        payload = JSON.parse(stdout.trim().split('\n').pop() ?? '{}');
      } catch {
        payload = { ok: false, error: 'unparseable_manifest_output' };
      }
      resolve({ exitCode, payload });
    });
  });
}

// Run a transition that must succeed with exit 0; anything else is a hard stop.
export async function manifestRequire(command: string, args: string[]): Promise<Record<string, any>> {
  const result = await manifestCall([command, ...args]);
  if (result.exitCode !== 0 || result.payload.ok !== true) throw new ManifestError(command, result);
  return result.payload;
}

export async function manifestShow(manifest: string): Promise<{ run_state: string; company: string; period: string; records: Record<RecordKey, ManifestRecord> }> {
  const payload = await manifestRequire('show', ['--manifest', manifest]);
  return payload.manifest ?? payload;
}
