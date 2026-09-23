---
name: unit4-raabalanse-gatherer
description: Gather and reconcile Knowit Unit4 Råbalanse with customer reports for accounts 1510 and 1560 and supplier reports for accounts 2440, 2444, and 2460 for a company and YYYYMM period. Ask for missing inputs; not for other accounts, timesheets, or file-only analysis.
---

# Unit4 Råbalanse Gatherer

Gather and reconcile a controlled report set from Knowit's production
Unit4/UBW environment using Codex and the user's connected Chrome profile.

## Current Validated Scope

For each run, order and download exactly:

1. One `Råbalanse` report.
2. One `Periodisert saldospesifikasjon kunder` report for account `1510`.
3. One `Periodisert saldospesifikasjon kunder` report for account `1560`.
4. One `Periodisert saldospesifikasjon leverandør` report for account `2440`.
5. One `Periodisert saldospesifikasjon leverandør` report for account `2444`.
6. One `Periodisert saldospesifikasjon leverandør` report for account `2460`.

If the user requests another account, stop and explain that the account and
correct Unit4 report type must be confirmed and added to the skill before a
future production run. Never silently expand the account set.

Finish the Råbalanse order before creating the five account-specific orders.
Do not download until all six exact orders have status `Ferdig`. Download the
six reports together as one ZIP, unpack it, and reconcile all five accounts.

## Required Inputs

Determine both values before opening or operating Unit4:

- **Company:** The exact 2-10 digit company code. A supplied name is additional
  identity evidence.
- **Period:** An accounting period in `YYYYMM` format, such as `202609`.

Ask one concise question for every missing value. Do not infer either value
from Unit4, the active browser tab, a screenshot, today's date, or a previous
run. Never encode a test company or period as a default.

A direct request to fetch, gather, order, or download the report set authorizes
the six production report orders once both inputs are known. Do not ask for a
separate confirmation before **Lagre**. Ask before ordering only if the request
is advisory, ambiguous about execution, or explicitly asks to stop before
submission.

Before the first **Lagre** action, use `scripts/run_manifest.py` as specified in
[Unit4 ordering](references/unit4-ordering.md) to create a unique private
`run-manifest.json`; never hand-edit it. Record its path in task state. It must
contain only operational identity—never customer or supplier rows or amounts—
and must be updated before and after every submission or state transition. If
Codex needs permission to create or update that exact temporary path, request
the narrow permission then. If the helper is unavailable or cannot persist the
manifest, stop before the first production order.

Use the manifest as the durable run ledger and mirror its current state in the
task. After an interruption, inspect it and reuse exact captured orders rather
than starting over. If a save may have occurred but no exact order identity
survived, stop rather than risk creating duplicate production orders. Use the
helper's guarded cleanup only after the final result is fully assembled; retain
and report the manifest path when blocked so a recoverable run can resume.

## Codex Access Preflight

Before operating Unit4:

1. Use Computer Use with the ChatGPT Chrome browser extension and the user's
   connected Chrome profile, normally through an explicitly mentioned
   `@Chrome` or Unit4 tab. The built-in `@Browser` uses a separate profile and
   is not a substitute for the user's existing Unit4 SSO session unless the
   user explicitly requests it.
2. Reuse an existing Unit4 tab when available. Otherwise open
   `https://ubw.unit4cloud.com/se_kno_prod_web/` in connected Chrome.
3. If Chrome control is not available, ask the user to install or enable the
   Computer Use plugin, connect Chrome under **Settings > Computer Use**, and
   retry with `@Chrome` or the Unit4 tab. If Codex or the operating system
   presents a browser-control, website, or app-access approval, request the
   narrow approval and wait. On macOS this can include Screen Recording and
   Accessibility; on Windows keep Chrome visible on the active desktop while
   Computer Use is operating it.
4. Do not test download-folder or workbook permissions yet. Request those
   permissions just in time, immediately before the first operation that needs
   them.

Do not enable Developer mode or use standalone Playwright, full-CDP scripts,
shell browser helpers, direct HTTP requests, or a remote-debug browser as a
fallback. The instruction not to ask for a conversational confirmation before
**Lagre** never bypasses a Codex, browser, operating-system, or Unit4 security
prompt. A denied permission is not authorization to switch profiles, bypass the
sandbox, or request broader access.

When Unit4, SSO, or MFA asks for credentials or confirmation, pause for the
user to complete it in the browser. Never request passwords or authentication
codes in chat.

## Workflow

1. Read [Unit4 ordering](references/unit4-ordering.md) completely, then use it
   to select the company, order Råbalanse, order the five account reports, and
   capture the exact order-to-account mapping. Do not continue unless the six
   exact orders are `Ferdig`.
2. Read [ZIP download and recovery](references/download-and-recovery.md)
   completely, then select only the six captured rows, download one verified
   ZIP, and extract it into a private temporary directory.
3. Read [reconciliation](references/reconciliation.md) completely, then verify
   workbook identity and reconcile accounts `1510`, `1560`, `2440`, `2444`,
   and `2460`.

Keep company, period, report name, account, order number, Unit4 filename, ZIP
entry, and extracted workbook together as one identity chain. A mismatch or
ambiguity at any link is a blocker; never substitute a nearby row or file.

## Completion

Report two independent outcomes:

- **Gathering:** `SUCCESS` only when all six exact orders finished and the
  verified ZIP contains the six corresponding workbooks. Otherwise report
  `BLOCKED` with the exact stage and known order numbers.
- **Reconciliation:** `MATCH`, `AVVIK`, or `BLOCKED`. A non-zero difference is
  `AVVIK`; it does not turn a successful gathering into a download failure.

For each account, report the periodisert sum, Råbalanse value, signed
difference, status, mapped order number, and workbook filename. Lead with a
clear human-review warning when any account is `AVVIK`. Also report company,
period, Råbalanse order and filename, and the verified ZIP path or artifact.

Do not expose customer- or supplier-level rows unless the user explicitly
asks. Treat all visible, downloaded, and extracted Unit4 data as confidential.
