---
name: unit4-raabalanse-gatherer
description: Gather and reconcile Knowit Unit4 Råbalanse with customer reports for accounts 1510 and 1560 and supplier reports for accounts 2440, 2444, and 2460 for a company and YYYYMM period. Ask for missing inputs; not for other accounts, timesheets, or file-only analysis.
---

# Unit4 Råbalanse Gatherer

Gather and reconcile a controlled report set from Knowit's production
Unit4/UBW environment using an agent host (Codex or Claude Code) with browser
control of the user's connected Chrome profile.

## Mandatory save gate

For **every** report, verify the active company and committed parameters, then
record `begin` in the run manifest **before** touching **Lagre**. Target the
enabled **Lagre** button in the report form and send **one native
double-click**. In Codex Chrome Computer Use, use
`await tab.click(lagreIndex, { clickCount: 2 })`; in Claude in Chrome, send
one `double_click` computer action on the freshly read **Lagre** target.
Do not substitute a single click, two separate click calls, **Eksport**, or a
click on **Dine bestilte rapporter**. With the `unit4` MCP server,
`unit4_order` performs this whole gate. It verifies the parameters, calls
`begin`, sends one Playwright `dblclick()` on the **Lagre** button in the
**Handling** toolbar, and records the confirmation with `confirm`.

Read the result immediately. The order is submitted for this run only when a
readable Unit4 confirmation gives the **complete Ordrenummer** and `confirm`
records that exact number in the manifest. Do not navigate to the next report
or account before that happens. If **Lagre** becomes disabled, an order row
appears, or the page changes without a captured confirmation number, follow
the unknown-submission procedure in [Unit4 ordering](references/unit4-ordering.md)
and stop; never infer the number from the newest row or double-click again
without the guarded retry evidence.

For **Periodisert saldospesifikasjon kunder** and
**Periodisert saldospesifikasjon leverandør**, verify that the actual bottom
toolbar **Lagre** button is the double-click target immediately before saving.
Unit4 can rebuild the form after account or period changes: a previously read
accessibility index may then point to **Beløps kolonne** instead. If the index
is stale or unstable, use a fresh screenshot to target the visible **Lagre**
button with one native coordinate double-click. An opened parameter dropdown
is evidence that **Lagre** was missed; close it and apply the no-confirmation
order-table check before any retry.

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
six outputs together as one ZIP, unpack them, and reconcile all five accounts.
For a supplier order only, Unit4 may produce `su05_<order>.agm` when the
report has no rows. The product owner confirmed that this means an empty
result. Use it as a zero periodised amount only after verifying the exact
order's Unit4 log says `No rows found. Report stop` and identifies the
requested company, account, and period. For this verified empty-result case,
the user confirmed that an absent Råbalanse account row also means zero and
there is no deviation; never apply that rule to a non-empty report.

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
the agent host needs permission to create or update that exact temporary path, request
the narrow permission then. If the helper is unavailable or cannot persist the
manifest, stop before the first production order.

Use the manifest as the durable run ledger and mirror its current state in the
task. After an interruption, inspect it and reuse exact captured orders rather
than starting over. If a save may have occurred but no exact order identity
survived, stop rather than risk creating duplicate production orders. Use the
helper's guarded cleanup only after the final result is fully assembled; retain
and report the manifest path when blocked so a recoverable run can resume.

## Unit4 MCP Server (preferred)

When the `unit4` MCP server's tools (`unit4_attach` and the other `unit4_*`
tools) are available, use them instead of screenshot-driven browser control.
They run the deterministic Unit4 steps through Playwright on the user's own
Chrome tab, using the Playwright Extension. Each tool enforces the save gate,
the committed-value checks, the manifest transitions and the bounded retry
described in this skill, and returns one JSON status. Setup is in
[Unit4 MCP server](references/mcp-server.md).

| Stage | Tool call |
| --- | --- |
| Preflight | `unit4_attach`, then `unit4_select_company` with the requested code |
| Råbalanse | `unit4_order` with key `raw_balance`, then `unit4_wait_orders` until it is `Ferdig` |
| Accounts | `unit4_order` for `1510`, `1560`, `2440`, `2444`, `2460` in that order |
| Wait | `unit4_wait_orders`; for each supplier key it lists as AGM, `unit4_verify_empty_agm` |
| Download | `unit4_download_zip` (closes this run's Unit4 tabs afterwards), then the ZIP `inspect`/`extract` helpers and reconciliation |

Continue only on the documented success status (`OK`, `CONFIRMED`,
`COMPLETE`, `VERIFIED_EMPTY`, `DOWNLOADED`, and `FINISHED_SO_FAR` from
`unit4_wait_orders` while account orders are still to be placed). Treat
every other status as a stop:
- `RETRY_ALLOWED`: the save never reached Unit4 and the table shows no new
  order, so the manifest grants the one retry. Find the cause first. Run
  `unit4_probe_lagre` on the report tab (a read-only trial click), fix what it
  reports, then call `unit4_order` again for the same key. Don't use the last
  attempt while the probe still fails. After a successful save, the probe
  reports Lagre as locked (`element is not enabled`) until `unit4_order`
  changes a parameter; that is normal.
- `NEEDS_USER`: tell the user what the tool's `message` or `reason` asks for,
  then retry the same call once they confirm.
- `ACTIVITY_LIMIT`: Unit4 allows 10 open activities. Ask the user to close
  unused Unit4 tabs, or log out and back in.
- `STILL_PENDING`: report the exact statuses and ask whether to keep waiting.
- `UNKNOWN`, `BLOCKED`, `FAILED`, `NOT_VERIFIED`, `NO_UNIQUE_ZIP` or `ERROR`:
  follow this skill's stop and handoff rules for that stage.

After a successful download, `unit4_download_zip` closes the activities this
run opened for the company: the three report forms, **Dine bestilte
rapporter**, and log views. Use `unit4_close_tabs` with the company code for
tabs left over from an earlier or interrupted run, but never while that
company's run is still ordering or waiting.

Never retry `unit4_order` after `UNKNOWN`. Call `unit4_clear_buffer` only for
the buffer recovery in [ZIP download and recovery](references/download-and-recovery.md).
The user's consent is required, and the call must pass `consent: true`.

While the tools run, the user may work in other apps and other Chrome windows.
Tell them to keep the shared Unit4 tab's window open, not minimized, and tall
enough (preferably maximized, with DevTools closed) that the bottom toolbar
**Lagre** of the long supplier form is inside the visible area.
Chrome stops rendering a hidden tab, and every tool then returns
`NEEDS_USER` with reason `window_hidden`. They must also leave the shared tab
and any other Unit4 tabs alone until the run is finished.

## Browser Access Preflight

Before operating Unit4, obtain control of the user's connected Chrome profile
so the existing Unit4 SSO session is reused:

0. Prefer the `unit4` MCP server above. The first `unit4_attach` opens the
   Playwright Extension's "Allow & select" page; ask the user to choose the
   Unit4 tab there. Use the host integrations below only when the server is
   unavailable.
1. Use the host's Chrome integration:
   - **Codex:** Computer Use with the ChatGPT Chrome browser extension,
     normally through an explicitly mentioned `@Chrome` or Unit4 tab. The
     built-in `@Browser` uses a separate profile and is not a substitute for
     the user's existing Unit4 SSO session unless the user explicitly
     requests it.
   - **Claude Code:** the Claude in Chrome extension, available when Claude
     Code was started with `claude --chrome` or after `/chrome` in the
     session. It operates the user's normal Chrome profile.
2. Reuse an existing Unit4 tab when available. Otherwise open
   `https://ubw.unit4cloud.com/se_kno_prod_web/` in connected Chrome.
3. If Chrome control is not available, stop and ask the user to enable it:
   - **Codex:** install or enable the Computer Use plugin, connect Chrome
     under **Settings > Computer Use**, and retry with `@Chrome` or the Unit4
     tab.
   - **Claude Code:** install the Claude in Chrome extension, then restart
     with `claude --chrome` or run `/chrome`.

   If the agent host or the operating system presents a browser-control,
   website, or app-access approval, request the narrow approval and wait. On
   macOS this can include Screen Recording and Accessibility; on Windows keep
   Chrome visible on the active desktop while it is being operated.
4. Do not test download-folder or workbook permissions yet. Request those
   permissions just in time, immediately before the first operation that needs
   them.

The bundled `unit4` MCP server is the only permitted Playwright path. It
attaches through the Playwright Extension in the user's own profile, with the
tab the user approved. Do not enable Developer mode, and do not use
standalone Playwright scripts, `browser_run_code` from a generic Playwright
MCP, full-CDP scripts, shell browser helpers, direct HTTP requests, a
remote-debug browser, or another browser profile as a fallback. The instruction not to ask for a conversational confirmation before
**Lagre** never bypasses an agent-host, browser, operating-system, or Unit4 security
prompt. A denied permission is not authorization to switch profiles, bypass the
sandbox, or request broader access.

When Unit4, SSO, or MFA asks for credentials or confirmation, pause for the
user to complete it in the browser. Never request passwords or authentication
codes in chat.

## Efficient UI Operation

The `unit4_*` tools already batch each phase into one call. The guidance
below applies to the fallback host browser control.

Use the host's browser control (Codex Computer Use or Claude in Chrome) to
group deterministic actions on a verified Unit4 page, preferring one
interaction for each verified form or table phase. When the host can batch
actions, such as a persistent Codex Computer Use REPL, batch the deterministic
clicks and typing after a fresh state read, then return only the relevant committed form
or order-row state. Read the UI after each meaningful
decision boundary rather than after every click: active company and report,
committed account and period, the result of each **Lagre**, and exact order
rows before download. Use the native double-click procedure for **Lagre**
and its confirmation safeguards in [Unit4 ordering](references/unit4-ordering.md).
Keep the account check especially strict: a previous
Unit4 run showed `1510` in the form while the generated workbook included
`1560`. Do not group a **Lagre** click with a later account submission, or
assume that a painted account value was committed. Reuse the verified customer
or supplier report page for its next account and use the reusable order-table
baseline described in [Unit4 ordering](references/unit4-ordering.md).
For supplier reports, ignore **Leverandørgruppe**: leave its default `*` value
unchanged and use **Konto** and **Periode** for the requested selection.

## Python Helpers

The `scripts/` helpers need only the Python 3 standard library. Choose the
interpreter by host and refer to it as `<python>` in the reference commands:

- **Codex:** load Codex workspace dependencies and use the returned bundled
  Python executable.
- **Claude Code:** use `python3` from `PATH`.

`scripts/reconcile_unit4.py` also needs `openpyxl`. When the chosen
interpreter lacks it (`openpyxl_dependency_missing`), use the skill's `.venv`
(`make validate` creates it; `.venv/bin/python -m pip install openpyxl`).

Resolve each script relative to this `SKILL.md`, not the current working
directory.

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
  verified ZIP contains the six corresponding outputs, each an XLSX workbook
  or an explicitly verified empty supplier AGM. Otherwise report
  `BLOCKED` with the exact stage and known order numbers.
- **Reconciliation:** `MATCH`, `AVVIK`, or `BLOCKED`. A non-zero difference is
  `AVVIK`; it does not turn a successful gathering into a download failure.

For each account, report the periodisert sum, Råbalanse value, signed
difference, status, mapped order number, and workbook filename. Lead with a
clear human-review warning when any account is `AVVIK`. Also report company,
period, Råbalanse order and filename, and the verified ZIP path or artifact.

Do not expose customer- or supplier-level rows unless the user explicitly
asks. Treat all visible, downloaded, and extracted Unit4 data as confidential.
