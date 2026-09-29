// Download detection in Chrome's download folder.
//
// Playwright receives no download events over the extension bridge (Chrome
// saves files itself), so each download is identified by a scoped before/after
// snapshot of files matching one pattern. Nothing is deleted or overwritten.

import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

export const DOWNLOAD_DIR = process.env.UNIT4_DOWNLOAD_DIR ?? path.join(os.homedir(), 'Downloads');

export type Snapshot = Map<string, { size: number; mtimeMs: number }>;

export async function snapshot(pattern: RegExp, dir = DOWNLOAD_DIR): Promise<Snapshot> {
  const result: Snapshot = new Map();
  for (const name of await fs.readdir(dir)) {
    if (!pattern.test(name)) continue;
    const stat = await fs.lstat(path.join(dir, name));
    if (stat.isFile()) result.set(name, { size: stat.size, mtimeMs: stat.mtimeMs });
  }
  return result;
}

async function inProgress(dir: string): Promise<boolean> {
  return (await fs.readdir(dir)).some((name) => name.endsWith('.crdownload'));
}

// Wait for exactly one new (or changed) file matching `pattern`, with no
// partial Chrome download left in the folder.
export async function waitForNew(
  before: Snapshot,
  pattern: RegExp,
  timeoutMs: number,
  dir = DOWNLOAD_DIR,
): Promise<{ status: 'OK'; path: string; size: number } | { status: 'TIMEOUT' | 'AMBIGUOUS'; candidates: string[] }> {
  const deadline = Date.now() + timeoutMs;
  let candidates: string[] = [];
  while (Date.now() < deadline) {
    const now = await snapshot(pattern, dir);
    candidates = [...now].filter(([name, meta]) => {
      const old = before.get(name);
      return !old || old.size !== meta.size || old.mtimeMs !== meta.mtimeMs;
    }).map(([name]) => name);
    if (candidates.length > 1) return { status: 'AMBIGUOUS', candidates };
    if (candidates.length === 1 && !(await inProgress(dir))) {
      // Require a stable size across two reads before accepting the file.
      const first = now.get(candidates[0])!;
      await new Promise((r) => setTimeout(r, 750));
      const again = (await snapshot(pattern, dir)).get(candidates[0]);
      if (again && again.size === first.size) {
        return { status: 'OK', path: path.join(dir, candidates[0]), size: again.size };
      }
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  return { status: 'TIMEOUT', candidates };
}

export const ZIP_PATTERN = /^Rapporter_\d{14}( \(\d+\))?\.zip$/;

export function logPattern(order: string): RegExp {
  return new RegExp(`^[a-z0-9]+_${order}( \\(\\d+\\))?\\.log$`, 'i');
}
