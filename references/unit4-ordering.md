# Unit4 Ordering

Use this procedure only after the skill's required company and period are
known. The supported account set is exactly `1510`, `1560`, `2440`, `2444`,
and `2460`.

## Durable Run Manifest

Load Codex workspace dependencies, use the returned bundled Python executable,
and resolve `scripts/run_manifest.py` relative to this skill's `SKILL.md`.
Pass every executable, script, path, and value as a separately shell-quoted
data argument. Do not hand-edit the manifest or replace the helper with an
in-memory note. On POSIX hosts the helper enforces private owner/mode checks;
on Windows it rejects reparse-point paths and relies on the current user's
temporary-directory or workspace ACL boundary.

1. Create the manifest once, before the first **Lagre**, with:

   ```text
   <bundled-python> <skill-root>/scripts/run_manifest.py create \
     --company <company-code> --period <YYYYMM>
   ```

   Require exit `0`; store the returned manifest path in task state.
2. Before each save click, call `begin` with key `raw_balance`, `1510`, `1560`,
   `2440`, `2444`, or `2460` and the complete pre-click baseline as repeated
   values after `--baseline`. The helper enforces the fixed raw_balance → 1510
   → 1560 → 2440 → 2444 → 2460 sequence and at most two attempts.
3. After a readable success dialog, call `confirm` with the exact order number.
   A confirmation that reuses a baseline or prior run order is rejected.
4. Record table evidence with `track`. Whenever a filename is supplied, also
   pass `--filename-kind FULL` or `--filename-kind PREFIX`; use `PREFIX` only
   when Unit4 truly exposes a truncated value. Pass the exact visible status
   with `--visible-status`. Call `finish-order` only after the helper has the
   filename identity and status `Ferdig`.
5. For the first no-confirmation outcome, call `retry-allowed` with the complete
   post-click order set after `--observed` and whether any submission state was
   seen. Only exit `0` authorizes one retry, followed by a second `begin` using
   the unchanged baseline. Exit `3` records an unknown outcome, any newly
   observed candidate order numbers, and blocks the run. If the second attempt
   has no readable confirmation, inspect the same table scope again and call
   `mark-unknown --reason confirmation_missing_after_second_attempt` with that
   complete set after `--observed`; never continue ordering. Candidate numbers
   are evidence for a human handoff, never an inferred confirmation.
6. For a recoverable non-submission interruption while the run is `ACTIVE`,
   call `block` with a concise machine reason. On continuation, inspect with
   `show`. Call `resume` only when the manifest is `BLOCKED`, has no `UNKNOWN`
   or in-flight record, and the original blocking condition has been resolved.
   Never call generic `block` while a submission is in flight—use
   `mark-unknown`.
7. After all six records are finished, call `complete`. If later work is
   interrupted and `show` reports `COMPLETE`, do not call `block` or `resume`;
   reuse the exact finished records and continue with ZIP download and
   reconciliation. After the final ZIP and reconciliation result has been
   assembled into task state, call the guarded `cleanup`. Never clean up a
   blocked ordering run.

Require the helper's JSON result and expected exit code at every transition.
On an unexpected result, stop and preserve the manifest path.

## Select the Company

If the requested company is already active, leave it selected. Otherwise open
the company chooser, search when needed, and select the row whose code exactly
matches the requested company. If the user supplied a company name, require
the visible name to match as well. Verify the active company after the chooser
closes. Stop rather than guessing when the company is missing or ambiguous.

## Order Råbalanse

1. Reuse an open Råbalanse page only after verifying the active company and
   report identity. Otherwise use the top-right global search `Søk (Alt+q)` and
   select the result matching:
   - Title: `Råbalanse`
   - Window ID: `TRA015`
   - Location: `Regnskap/Hovedbok/Rapporter`
2. Verify a heading, breadcrumb, or window title identifies
   `Råbalanse`/`TRA015`. Do not construct an undocumented deep link.
3. Keep the variant `Råbalanse`; do not select `Trial Balance` or
   `Råbalanse (periodeslutt)`.
4. In **Åpne parametre**, open the **Periode** dropdown and select the exact
   requested `YYYYMM`. Do not merely type or directly set the control. Re-read
   the collapsed dropdown and require the exact requested period.
5. Leave **Beløps kolonne** at `Beløp` unless the user explicitly requested
   another value.
6. Before clicking **Lagre**, update the durable run manifest with the intended
   report. While the requested company is active, take a baseline of every
   order number for the same report and current user across all result pages—or
   all order numbers across all pages when the table cannot prove either field.
   Keep the same table filters and page scope for the post-click comparison.
   Do not filter the baseline by accounting period or account because the
   ordered-reports table does not expose those parameters. Then click **Lagre**
   once. Do not use
   **Eksport**. Observe whether Unit4
   enters any loading or disabled state, wait for the confirmation, and capture
   the complete visible order number. Update the manifest immediately and
   acknowledge the confirmation only as needed to continue.

### Bounded second-save workaround

Unit4 sometimes ignores the first **Lagre** click. If no confirmation appears,
wait at least 30 seconds, then inspect **Dine bestilte rapporter** or refresh it
once and compare candidate rows with the pre-click baseline. Any new matching
row means the submission may have succeeded: record that candidate and stop
rather than retrying or guessing its identity.

Retry exactly once only when no new candidate exists and all of these are true
after re-reading the page:

- The unchanged form is visible.
- The requested parameters remain correct.
- **Lagre** is enabled.
- No success or error message appeared.
- No loading, disabled-button, navigation, or other submission state was
  observed at any time after the click.

If any dialog, candidate row, or submission state appeared, or the response is
otherwise ambiguous, mark the intended order `UNKNOWN` in the manifest and do
not click again. Never exceed two **Lagre** attempts for one intended order.
After the retry, require a readable confirmation order number; otherwise mark
the order `UNKNOWN` and stop. The table may prove that a submission happened,
but never use it to guess which new row belongs to an ambiguous request.

## Track the Råbalanse Order

1. Open **Dine bestilte rapporter**.
2. Treat each table row as one record. Keep its order number, report name,
   status, filename, and row checkbox together; historical and concurrent rows
   may be present.
3. Locate the row whose **Ordrenummer** exactly matches the captured number and
   verify **Rapportnavn** is `Råbalanse`. The order number is the primary key.
4. Capture the full Unit4 filename from the cell's accessible value, title, or
   tooltip when the rendered cell is truncated. If Unit4 exposes only a
   truncated prefix, record that fact and defer final file identity to the ZIP
   entry and workbook checks.
5. Refresh using the page's visible load control and wait between checks until
   this exact row is `Ferdig`, Unit4 displays an explicit failure, the user
   cancels, or 15 minutes have elapsed since the first pending check. At the
   time limit, report its exact status and ask whether to keep waiting; do not
   label it failed. Do not select it or download yet.

## Order the Account Reports

Begin only after the exact Råbalanse row is `Ferdig`. Use this fixed mapping
and order:

| Accounts | Exact Unit4 report title |
| --- | --- |
| `1510`, `1560` | `Periodisert saldospesifikasjon kunder` |
| `2440`, `2444`, `2460` | `Periodisert saldospesifikasjon leverandør` |

1. Confirm the requested company remains active.
2. For each report title in the table, search globally for that exact title.
   Select only an unambiguous exact match and record any visible window ID,
   breadcrumb, or navigation path so the same identity can be reused for every
   account mapped to it. Verify the opened page heading or window title. If
   multiple exact matches exist or the result cannot be distinguished safely,
   stop and report the visible identities rather than guessing.
3. For each mapped account, in the fixed order `1510`, `1560`, `2440`, `2444`,
   then `2460`, create a separate order:
   1. Set **Konto** using the report's lookup/ellipsis control and select the
      exact account when that control is available.
   2. If text entry is the only usable path, clear the field, type the exact
      account, and commit it with the UI's normal Enter, Tab, or suggestion
      selection. Move focus away and then re-read the control.
   3. Require the committed value to remain the exact account and verify any
      visible account description or resolved-value indicator. A value that is
      merely painted in the input is not sufficient; do not directly set DOM
      state or hidden values.
   4. Select the same requested **Periode** from its dropdown and re-read the
      collapsed value. Leave all other fields at the report defaults unless the
      user explicitly requested otherwise.
   5. Apply the complete submission procedure from Råbalanse step 6: update the
      durable manifest, capture the pre-click matching-order baseline, click
      **Lagre** once, and observe all submission state. Then apply the bounded
      second-save workaround when, and only when, its evidence requirements are
      met. Capture the complete confirmation order number and map it
      immediately to the current account. Do not proceed without that mapping
      and never submit the same account twice.
4. Open **Dine bestilte rapporter**. For each captured account/order pair,
   locate the exact order-number row and verify its report name matches the
   fixed mapping above. Capture its filename using the same full-name or
   explicitly truncated-name rule as Råbalanse.

## Wait for the Exact Orders

Use the visible load/refresh control and wait between checks. Continue until
all six captured rows are `Ferdig`, Unit4 displays an explicit failure, the
user cancels, or 15 minutes have elapsed since the first pending check. Do not
label a still-pending order as failed at the time limit; report its exact
status and ask whether to keep waiting.

Do not click **Vis rapport**, select any row, or download any file during this
stage. Preserve the exact mappings for the combined download.
