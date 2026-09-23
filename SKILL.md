---
name: unit4-raabalanse-gatherer
description: Order and download both Råbalanse and Periodisert saldospesifikasjon kunder for a requested company and accounting period in Knowit's production Unit4/UBW site using the ChatGPT browser connector. Ask for either input when missing, complete Råbalanse first, then fetch the matching customer specification. Use for gathering these accounting reports; do not use for timesheet entry or non-browser automation.
---

# Unit4 Råbalanse Gatherer

Order and download two reports in sequence from Knowit's production Unit4/UBW
environment for the company and accounting period requested by the user:

1. `Råbalanse`
2. `Periodisert saldospesifikasjon kunder`, using account `1510`

Finish and verify the Råbalanse download before ordering the second report.
Use the same requested company and period for both reports.

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

Treat these values as inputs for the requested gathering workflow. Never add a
company code or period as a default in this skill based on a test run.

A direct request to fetch, gather, order, or download the report set authorizes
both production report orders once both required inputs are known. Do not ask
for a separate confirmation before clicking **Lagre** for either report. Ask
before ordering only when the user's request is advisory or ambiguous about
whether a report should actually be ordered, or when the user has explicitly
asked to stop before submission.

## Browser Requirements

- Use only the ChatGPT browser connector for the user's regular browser
  profile, normally `@Chrome` or an explicitly mentioned Unit4 tab.
- Reuse an existing Unit4 tab when one is available. Otherwise open:
  `https://ubw.unit4cloud.com/se_kno_prod_web/`.
- Do not use Node.js, standalone Playwright, CDP, shell browser helpers, direct
  HTTP APIs, or a remote-debug browser as a fallback. Browser-connector-native
  download waiting and page inspection are allowed.
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

## Configure and Order the Report

1. Keep the report variant set to `Råbalanse`. Do not select `Trial Balance`
   or `Råbalanse (periodeslutt)`.
2. In **Åpne parametre**, open the required **Periode** dropdown and select the
   exact requested `YYYYMM` option. Directly setting or typing the value may
   appear correct without committing it in Unit4. Verify the collapsed control
   visibly shows the requested period.
3. Leave **Beløps kolonne** at `Beløp` unless the user explicitly requests a
   different value.
4. Click **Lagre** to order the report. The user's direct request to gather the
   report is sufficient authorization; do not pause for another confirmation.
   Do not use **Eksport** as a substitute.
5. Wait briefly for the success confirmation. Record the visible order number
   from the message that says the report is available under **Dine bestilte
   rapporter**.
6. Unit4 has a known intermittent fault where the first **Lagre** click does
   not submit the order. If no success confirmation or order number appears,
   re-read the page state before retrying:
   - If Unit4 is still loading, the **Lagre** control is disabled, or any
     success/error dialog is present, wait and inspect that state; do not click
     again.
   - If the unchanged report form is visible, the requested parameters are
     still correct, **Lagre** is enabled, and no confirmation or error appeared,
     click **Lagre** exactly one more time.
   - Never make more than two total **Lagre** attempts for one requested order.
7. After the second attempt, wait for the confirmation and capture its exact
   order number. If no readable order number appears, stop and report that the
   order cannot be identified safely. Do not click **Lagre** again and do not
   infer the order from the ordered-reports table.
8. Acknowledge the confirmation only as needed to continue.

## Wait for the Matching Ordered Report

1. Open **Dine bestilte rapporter** from the report page.
2. Expect the table to contain multiple historical or concurrent orders. Treat
   each table row as one record and keep its **Ordrenummer**, **Rapportnavn**,
   **Status**, **Filnavn**, and row-local **Vis rapport** control together. Do
   not combine values or buttons from different rows based on their visual or
   accessibility-tree position.
3. Locate the row whose **Ordrenummer** exactly matches the number captured
   from the success confirmation. Also verify **Rapportnavn** is `Råbalanse`.
   The order number is the primary identity. Use the **Ordrenummer** filter when
   helpful, but verify the resulting row after filtering.
4. If the matching row is not visible or its **Status** is not `Ferdig`, use
   the page's visible load/refresh control and check again. Wait between checks
   so Unit4 can generate the report. Do not click **Vis rapport** while the
   status is queued, running, blank, failed, or otherwise not exactly
   `Ferdig`.
5. If Unit4 reports failure, or the order does not finish after a reasonable
   bounded wait, stop and report the order number and visible status.

## Download and Verify

1. In the matching `Ferdig` row, click that same row's control in the **Vis
   rapport** column. Re-read the row immediately before clicking and verify its
   order number and status again. Do not use a control from another row.
2. Before clicking, record the existing files in the browser's download folder
   that match either the Unit4 filename or Chrome's numeric-suffix form, such
   as `report.xlsx`, `report (1).xlsx`, and `report (2).xlsx`. Record each
   matching path, size, and modification time; do not delete or overwrite an
   existing download.
3. Use the browser connector's native download handling when available. The
   click may instead open a report viewer or a new browser tab; inspect the
   resulting visible state and use its normal download control if needed.
4. Verify that a download completed. Prefer the connector-provided artifact
   path. When the connector signals a download but does not expose its path,
   compare the post-click matching files with the pre-click snapshot. Accept
   only a newly created matching path or an existing matching path whose size
   or modification time changed after the click. This permits Chrome's numeric
   suffixes without accepting a stale workbook. If no unique changed candidate
   exists because the report viewer hangs, keeps showing a loading indicator,
   or Unit4 shows an unexplained error, use the bounded Unit4 buffer recovery
   below before stopping.
5. Verify that the selected candidate is a readable `.xlsx` workbook before
   reporting success. Do not claim the file is accessible unless the actual
   local file or connector artifact was verified.
6. Treat the downloaded report and its contents as confidential. Do not upload,
   share, or transmit it elsewhere unless the user explicitly requests that.

## Order Periodisert saldospesifikasjon kunder

Begin this report only after the Råbalanse download has been verified as a
readable workbook.

1. Confirm that the requested company is still active.
2. Use the top-right global search labelled `Søk (Alt+q)` and search for the
   exact title `Periodisert saldospesifikasjon kunder`.
3. Select only the search result whose visible title exactly matches
   `Periodisert saldospesifikasjon kunder`. If more than one exact match is
   visible and no additional identity details distinguish them, stop and report
   the ambiguity rather than guessing. Do not construct an undocumented deep
   link.
4. After opening it, verify that a visible heading, breadcrumb, or window title
   identifies `Periodisert saldospesifikasjon kunder`.
5. In **Åpne parametre**, set **Konto** to exactly `1510`.
6. Open the required **Periode** dropdown and select the same requested
   `YYYYMM` period used for Råbalanse. Do not rely on a typed or pre-existing
   value: verify the collapsed dropdown visibly shows the requested period.
7. Leave all other parameters at their report defaults unless the user
   explicitly requested different values. In particular, do not copy parameter
   values from Råbalanse into unrelated fields.
8. Click **Lagre** to order the report; do not use **Eksport**. Apply the same
   bounded double-click workaround as for Råbalanse: inspect the page after the
   first click, and make exactly one additional click only when the unchanged
   form is visible, the requested values remain correct, **Lagre** is enabled,
   and no success or error appeared. Never exceed two total attempts.
9. Capture the exact order number from the success confirmation. If no readable
   order number appears after the allowed attempts, stop rather than inferring
   it from the ordered-reports table.
10. Open **Dine bestilte rapporter**. Locate the single row whose
    **Ordrenummer** exactly matches the captured number and whose
    **Rapportnavn** is `Periodisert saldospesifikasjon kunder`. Keep all
    row-local values and controls together; other historical or concurrent
    orders may be present.
11. Refresh with the visible load control until that exact row has status
    `Ferdig`, using a reasonable bounded wait. Do not click **Vis rapport** for
    any other row or before the status is exactly `Ferdig`.
12. Re-read the matching row, take a fresh pre-download filename snapshot, and
    click that row's **Vis rapport** control. Apply the same connector-native
    download handling, Chrome numeric-suffix acceptance, changed-file
    detection, and readable-`.xlsx` verification used for Råbalanse.

Treat the two downloads as separate artifacts. A verified Råbalanse file does
not prove that the customer specification downloaded successfully.

## Recover from Unit4 Buffer Errors

Use this recovery only after a matching `Ferdig` report failed to download or
the report viewer visibly hung. Do not use it routinely, and perform it at most
once per gathering run.

1. Open the user menu labelled with the signed-in username, for example
   **ANDROR**, next to the company selector.
2. Select **Om Unit4 ERP**.
3. Click **Tøm bufferen**. This is Unit4's application buffer control; do not
   clear Chrome history, cookies, downloads, or the browser profile.
4. Wait for Unit4 to finish refreshing. Verify that the session is still
   authenticated and that the requested company is active.
5. Return to **Dine bestilte rapporter** and locate the existing row using the
   exact captured order number. Verify again that **Rapportnavn** matches the
   report currently being downloaded (`Råbalanse` or
   `Periodisert saldospesifikasjon kunder`) and **Status** is `Ferdig`.
6. Take a fresh pre-download filename snapshot and retry that row's **Vis
   rapport** control once. Do not create or submit a new report order.
7. Re-run the download and workbook checks above. If the retry still produces
   no unique readable workbook, stop and report the existing order number and
   the failed download. A different Chrome profile or browser may be suggested
   for a manual retry, but do not switch profiles or browsers automatically.

## Completion and Boundaries

Report the verified company and requested period plus each report's captured
order number, final status, and downloaded filename or artifact path when
available. If blocked,
state whether the blocker is missing inputs, browser access, login, company
selection, search, report ordering, report generation, or download access.

Do not extract or summarize report values unless the user asks. Treat all
visible and downloaded Unit4 data as confidential.
