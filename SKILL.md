---
name: unit4-raabalanse-gatherer
description: Navigate Knowit's production Unit4/UBW site to open the Råbalanse report for a requested company and accounting period using the ChatGPT browser connector. Ask for either input when missing. Use when the user wants to open or begin gathering Råbalanse data; do not use for timesheet entry or non-browser automation.
---

# Unit4 Råbalanse Gatherer

Open the Råbalanse report in Knowit's production Unit4/UBW environment. This
version stops when the report page is open and verified.

## Required Inputs

Before opening or operating Unit4, determine both:

- **Company:** Prefer the exact company code. A company name may be supplied
  alongside it for verification.
- **Period:** The accounting period in `YYYYMM` format, for example `202609`.

If either value is missing from the user's request, ask the user for every
missing value before using the browser. Ask for both in one concise question
when both are missing. Do not infer the company from the currently selected
Unit4 company, prior runs, the active browser tab, or a screenshot. Do not
infer the period from today's date or a value already present in the report.

Treat these values as inputs for the requested gathering workflow. This stage
still stops after opening and verifying the report page; it does not enter the
period or run the report.

## Browser Requirements

- Use only the ChatGPT browser connector for the user's regular browser
  profile, normally `@Chrome` or an explicitly mentioned Unit4 tab.
- Reuse an existing Unit4 tab when one is available. Otherwise open:
  `https://ubw.unit4cloud.com/se_kno_prod_web/`.
- Do not use Node.js, Playwright, CDP, shell browser helpers, direct HTTP APIs,
  or a remote-debug browser as a fallback.
- Do not use ChatGPT's isolated built-in browser unless the user explicitly
  asks for it; the normal workflow relies on the user's existing browser
  profile and SSO session.
- If no browser connector is available, stop and tell the user to open the
  ChatGPT desktop app, connect their browser under **Settings > Computer
  Use**, and start a chat with `@Chrome` or the Unit4 tab mentioned.

## Login

1. Inspect the current browser tab before navigating.
2. Reuse an authenticated Unit4 session when possible; otherwise open the
   production URL above.
3. When Unit4, SSO, or MFA asks for credentials or confirmation, pause and let
   the user complete it in the browser. Never ask the user to paste passwords
   or authentication codes into chat.
4. Continue only after the authenticated Unit4 start page is visible.

## Select the Company

Use the company supplied by the user. If that company is already selected,
leave it selected. Otherwise open the company chooser, search when needed,
and select the row whose code exactly matches the requested company code.
When the user also supplied a company name, require the visible name to match
as well. Verify the active company after the chooser closes. If the requested
company cannot be identified unambiguously, stop and report the visible
choices rather than guessing.

## Open Råbalanse

If the current tab is already on the Råbalanse report, reuse it only after
verifying both the active company and the visible report identity. Otherwise:

1. Focus the top-right global search labelled `Søk (Alt+q)`.
2. Search for `Råbalanse`.
3. Select only the result matching all available identity details:
   - Title: `Råbalanse`
   - Window ID: `TRA015`
   - Location: `Regnskap/Hovedbok/Rapporter`
4. If results are missing or ambiguous, stop and report what is visible rather
   than choosing a similarly named entry.
5. Open the result and verify that a visible page heading, breadcrumb, or
   window title identifies the report as `Råbalanse` before reporting success.

A browser-discovered shortcut or already-open report page may replace the
global-search steps only when it is visibly verified as `Råbalanse`/`TRA015`
for the requested company. Do not guess or construct an undocumented deep
link.

## Completion and Boundaries

Report the verified company, the requested period, and that the Råbalanse page
is open. Make clear that the period has not yet been entered or run. If
blocked, state whether the blocker is missing inputs, browser access, login,
company selection, search, or page verification.

For this stage, do not set report parameters, run the report, extract values,
download files, or persist Unit4 data. Treat all visible Unit4 data as
confidential.
