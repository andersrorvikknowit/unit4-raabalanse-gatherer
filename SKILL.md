---
name: unit4-raabalanse-gatherer
description: Order Råbalanse plus separate Periodisert saldospesifikasjon kunder reports for accounts 1510, 1560, 2440, 2444, and 2460 for a requested company and accounting period in Knowit's production Unit4/UBW site. Download all six workbooks together as a ZIP and reconcile every account against Råbalanse. Ask for either input when missing and track each exact order. Use for gathering and validating these accounting reports; do not use for timesheet entry or non-browser automation.
---

# Unit4 Råbalanse Gatherer

Order six reports from Knowit's production Unit4/UBW environment for the
company and accounting period requested by the user, then download them
together:

1. `Råbalanse`
2. Five separate `Periodisert saldospesifikasjon kunder` reports, one for each
   account: `1510`, `1560`, `2440`, `2444`, and `2460`

Finish the Råbalanse order before ordering the five account-specific reports.
Do not download anything until all six exact orders have status `Ferdig`; then
select only those six rows and download them together as one ZIP. Use the same
requested company and period for every report. After downloading, reconcile
each account-specific detail report against the corresponding account in
Råbalanse before reporting success.

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
all six production report orders once both required inputs are known. Do not
ask for a separate confirmation before clicking **Lagre** for any report. Ask
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

## Wait for the Matching Råbalanse Order

1. Open **Dine bestilte rapporter** from the report page.
2. Expect the table to contain multiple historical or concurrent orders. Treat
   each table row as one record and keep its **Ordrenummer**, **Rapportnavn**,
   **Status**, **Filnavn**, and row-selection checkbox together. Do not combine
   values or controls from different rows based on their visual or
   accessibility-tree position.
3. Locate the row whose **Ordrenummer** exactly matches the number captured
   from the success confirmation. Also verify **Rapportnavn** is `Råbalanse`.
   The order number is the primary identity. Use the **Ordrenummer** filter when
   helpful, but verify the resulting row after filtering.
4. If the matching row is not visible or its **Status** is not `Ferdig`, use
   the page's visible load/refresh control and check again. Wait between checks
   so Unit4 can generate the report.
5. If Unit4 reports failure, or the order does not finish after a reasonable
   bounded wait, stop and report the order number and visible status.

Do not click **Vis rapport**, select the row, or download anything yet. Retain
the exact order number and Unit4 filename for the combined download.

## Order Five Periodisert saldospesifikasjon kunder Reports

Begin these reports only after the matching Råbalanse order has status
`Ferdig`. Use the fixed account sequence `1510`, `1560`, `2440`, `2444`,
`2460`. Each account requires its own separate Unit4 order; never combine the
accounts into one parameter value or reuse one order for multiple accounts.

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
5. For the current account in the fixed sequence, set **Konto** to that one
   exact account number. Before each submission, verify that the visible value
   is the intended current account and not the value from the prior order.
6. Open the required **Periode** dropdown and select the same requested
   `YYYYMM` period used for Råbalanse. Do not rely on a typed or pre-existing
   value: verify the collapsed dropdown visibly shows the requested period.
7. Leave all other parameters at their report defaults unless the user
   explicitly requested different values. In particular, do not copy parameter
   values from Råbalanse into unrelated fields.
8. Click **Lagre** to order the current account's report; do not use
   **Eksport**. Apply the same
   bounded double-click workaround as for Råbalanse: inspect the page after the
   first click, and make exactly one additional click only when the unchanged
   form is visible, the requested values remain correct, **Lagre** is enabled,
   and no success or error appeared. Never exceed two total attempts.
9. Capture the exact order number from the success confirmation and record it
   against the current account. If no readable order number appears after the
   allowed attempts, stop rather than inferring it from the ordered-reports
   table.
10. Repeat steps 5-9 for every remaining account. Do not advance until the
    current account has a captured order number, and do not submit the same
    account twice.
11. Open **Dine bestilte rapporter**. For each account-to-order mapping, locate
    the single row whose **Ordrenummer** exactly matches the captured number and
    whose **Rapportnavn** is `Periodisert saldospesifikasjon kunder`. Keep all
    row-local values and controls together; other historical or concurrent
    orders may be present. Record the Unit4 filename for every mapped order.
12. Refresh with the visible load control until all five exact rows have status
    `Ferdig`, using a reasonable bounded wait. If any order fails or does not
    finish, report its account, order number, and visible status.
13. Do not click **Vis rapport** or download any file individually. Retain each
    account-to-order-to-filename mapping for the combined download and later
    reconciliation.

## Download All Six Reports as One ZIP

Start only when the captured Råbalanse order and all five captured periodisert
orders are visible and every one has status exactly `Ferdig`.

1. Re-read all six complete table rows and verify all of these values together:
   - The Råbalanse row has its captured order number, report name `Råbalanse`,
     and captured Unit4 filename.
   - Each periodisert row has the order number and Unit4 filename captured for
     its mapped account and report name `Periodisert saldospesifikasjon kunder`.
2. Inspect the row-selection checkboxes. Clear any selected row that is not one
   of the six captured orders. Do not use the header checkbox that selects all
   visible rows.
3. Select the row checkbox for each of the six captured orders. Re-read the
   table and verify that exactly those six rows are selected; historical or
   concurrent rows must remain unselected.
4. Before downloading, record every existing `Rapporter*.zip` file in the
   browser's download folder, including Chrome numeric-suffix variants. Record
   each path, size, and modification time; do not delete or overwrite existing
   downloads.
5. Click the bottom toolbar's **Last ned** button exactly once. Do not click
   any row's **Vis rapport** control.
6. Prefer a browser-connector-provided artifact path. Otherwise compare the
   download folder with the pre-click snapshot and accept only a newly created
   `Rapporter*.zip` path or one whose size or modification time changed after
   the click. If no unique changed archive appears, use the bounded Unit4
   buffer recovery below before stopping.
7. Verify that the ZIP is readable and that its entries include all six exact
   Unit4 filenames captured from the matching rows. Reject a stale archive or
   an archive missing any expected workbook. If it contains an unexpected
   additional report file, report that extra selection rather than claiming
   clean success.
8. Treat the archive and all six workbooks as confidential. Extract them only to
   a private temporary local directory for the required reconciliation below.
   Do not upload, share, or transmit their contents unless the user explicitly
   asks.

## Reconcile All Five Accounts

Perform this local read-only check after verifying the ZIP. Do not modify any
source workbook. Use workbook-aware spreadsheet tooling and identify fields by
their visible labels and report structure rather than assuming fixed sheet
names, row numbers, or column letters.

1. Open the six exact workbook entries from the verified ZIP. Confirm every
   workbook's visible client/company and period match the requested inputs. For
   each periodisert workbook, also confirm that its visible account or its
   account-level detail identifies exactly the account mapped to that order. If
   any identity differs or cannot be read safely, stop and report the mismatch
   or ambiguity.
2. In each `Periodisert saldospesifikasjon kunder` workbook, locate the detail
   table by its semantic headers, including **Account** and **Remaining Amount**
   (or their clearly equivalent localized labels).
3. For each account in `1510`, `1560`, `2440`, `2444`, `2460`, select only
   detail rows in that account's mapped workbook whose **Account** value is
   exactly that account. Exclude headers, blank rows, and the displayed
   **Total** or other subtotal rows. Sum their numeric **Remaining Amount**
   values independently. Also compare each calculated sum with that workbook's
   displayed total when present; a disagreement is a report-integrity failure
   that must be reported for that account.
4. In `Råbalanse`, locate the exact row for each of the five accounts and read
   its numeric **Beløp**/balance value for the requested period. Do not match an
   account merely because its text contains the account number. If more than
   one candidate row or balance column could apply for an account, mark that
   account as blocked and report the ambiguity rather than guessing or adding
   unrelated values.
5. For each account, preserve the signs from both reports. Do not compare
   absolute values or silently reverse a sign. Compare monetary values using
   decimal arithmetic,
   rounded to two decimal places. Always calculate the signed difference and
   classify the result explicitly. The reconciliation is **MATCH** only when:

   `periodisert detail sum for account - Råbalanse value for account = 0.00`

6. Produce one reconciliation result per account. If any difference is
   non-zero, classify that account as **AVVIK** and classify the overall run as
   **AVVIK**. Do not report the gathering workflow as successful. Prominently
   warn the human running the skill which account or accounts do not reconcile
   and require human review. For every account, report the periodisert sum,
   Råbalanse value, signed difference, status, mapped order number, and workbook
   filename. Also report company, period, and the Råbalanse order and filename.
   Do not expose individual customer rows unless the user asks. Never silently
   accept, hide, round away, or merely imply a mismatch. The overall run is
   **MATCH** only when all five account results are **MATCH**.
7. Remove temporary extracted copies after the check when they are no longer
   needed. Keep the downloaded ZIP unchanged as the verified deliverable.

## Recover from Unit4 Buffer Errors

Use this recovery only when the combined **Last ned** action fails to produce a
unique readable ZIP. Do not use it routinely, and perform it at most once per
gathering run.

1. Open the user menu labelled with the signed-in username, for example
   **ANDROR**, next to the company selector.
2. Select **Om Unit4 ERP**.
3. Click **Tøm bufferen**. This is Unit4's application buffer control; do not
   clear Chrome history, cookies, downloads, or the browser profile.
4. Wait for Unit4 to finish refreshing. Verify that the session is still
   authenticated and that the requested company is active.
5. Return to **Dine bestilte rapporter** and locate all six existing rows using
   their exact captured order numbers. Verify every report name, filename, and
   `Ferdig` status again.
6. Ensure only those six row checkboxes are selected, take a fresh
   `Rapporter*.zip` snapshot, and click the bottom **Last ned** button once.
   Do not create or submit new report orders and do not use **Vis rapport**.
7. Re-run the ZIP and archive-entry checks above. If the retry still produces
   no unique readable archive containing all six expected workbooks, stop and
   report all six existing order numbers and the failed download. A different
   Chrome profile or browser may be suggested for a manual retry, but do not
   switch profiles or browsers automatically. If the retry succeeds, perform
   all five account reconciliations before reporting success.

## Completion and Boundaries

Report the verified company and requested period plus each report's captured
order number, final status, and Unit4 filename. Also report the verified ZIP
filename or artifact path and a five-row reconciliation summary containing
account, periodisert sum, Råbalanse value, signed difference, and explicit
status **MATCH** or **AVVIK**. Report the overall status as **MATCH** only when
all five rows match. For any **AVVIK**, lead with a clear warning that identifies
the affected accounts and states that human review is required. If blocked,
state whether the blocker is missing inputs, browser access, login, company
selection, search, report ordering, report generation, download access,
workbook identity, or reconciliation.

Do not report customer-level detail unless the user asks. Treat all visible,
downloaded, and extracted Unit4 data as confidential.
