// Parse a Unit4 report-server log (e.g. gl09_18567.log). The header has fixed
// "Key ....: value" lines and a PARAMETERS block of "Label (name) = value".

export interface ParsedLog {
  orderno: string | null;
  client: string | null;
  program: string | null;
  parameters: Array<{ label: string; name: string; value: string }>;
  noRowsFound: boolean;
}

export function parseUnit4Log(raw: string): ParsedLog {
  const text = raw.replace(/^﻿/, '');
  const lines = text.split(/\r?\n/).map((l) => l.replace(/^\d{1,2}:\d{2}:\d{2} [AP]M /, ''));
  const header = (key: string) => {
    const line = lines.find((l) => new RegExp(`^\\s*${key}\\s*\\.*:\\s*`).test(l));
    return line ? line.replace(/^[^:]*:\s*/, '').trim() : null;
  };
  const parameters: ParsedLog['parameters'] = [];
  const start = lines.findIndex((l) => l.trim() === 'PARAMETERS:');
  if (start >= 0) {
    for (const line of lines.slice(start + 1)) {
      const match = /^\s+(.+?) \(([^)]+)\) = (.*)$/.exec(line);
      if (!match) break;
      parameters.push({ label: match[1].trim(), name: match[2].trim(), value: match[3].trim() });
    }
  }
  return {
    orderno: header('Orderno'),
    client: header('Client'),
    program: header('PROGRAM'),
    parameters,
    noRowsFound: /No rows found\. Report stop/.test(text),
  };
}

// Verify that a log proves an empty supplier result for the exact request.
export function verifyEmptyResultLog(log: ParsedLog, want: { order: string; company: string; period: string; account: string }) {
  const param = (pred: (p: ParsedLog['parameters'][number]) => boolean) => log.parameters.find(pred)?.value ?? null;
  const period = param((p) => p.name === 'period');
  const account = param((p) => /account/i.test(p.name) || /^konto$/i.test(p.label));
  const checks = {
    orderno: log.orderno === want.order,
    client: log.client === want.company,
    period: period === want.period,
    account: account === want.account,
    noRowsFound: log.noRowsFound,
  };
  return {
    verified: Object.values(checks).every(Boolean),
    checks,
    parameterNames: log.parameters.map((p) => p.name),
  };
}
