# ZIP Download and Recovery

Use this procedure only after the exact Råbalanse and account `1510`, `1560`,
`2440`, `2444`, and `2460` orders are visible with status `Ferdig`.

## Just-in-Time File Access

Before downloading, determine whether the connected browser can return a
completed-download artifact path. Prefer that mechanism because it identifies
the new file without scanning unrelated downloads.

If the connector cannot expose a completed-download artifact, request the
narrowest available read access to the browser download directory and explain
that it is needed to identify the new Unit4 ZIP. Do not request general home
directory or full-disk access. If directory access cannot be surfaced or is
denied, offer the narrow fallback of having the user choose the exact newly
downloaded ZIP or move only that ZIP into an approved workspace path. Stop
before **Last ned** unless one of these paths can identify the result uniquely.

## Select and Download

1. Re-read the six complete rows and verify their captured order numbers,
   report names, statuses, and available filenames together.
2. Clear table filters that could hide selected rows. Inspect every result page
   or use a trustworthy global selected-count indicator; selection may persist
   across filters or pagination. Clear every selection that is not one of the
   six captured orders. Do not use the header checkbox.
3. Select the six exact row checkboxes. Re-read every result page or the
   global selected-count indicator and require exactly six selected rows,
   with order numbers equal to the captured set. If global selection cannot be
   proven, stop before downloading.
4. When the browser provides a completed-download artifact, arm or start its
   download wait before clicking. Otherwise take a scoped pre-click snapshot
   of only `Rapporter*.zip` metadata in the download directory: path, size, and
   modification time. Include numeric-suffix variants; do not delete or
   overwrite anything.
5. Click the bottom toolbar's **Last ned** exactly once. Do not use any row's
   **Vis rapport** control. Expect one ZIP, not six separate workbooks.
6. Accept only the connector-returned artifact or, for the fallback, one newly
   created `Rapporter*.zip` or one whose size or modification time changed
   after the click. Wait for the download to finish before reading it. Reject
   stale or ambiguous candidates.
7. Before local inspection, verify that the exact accepted ZIP can be opened
   for reading. A connector-returned artifact path identifies the download but
   does not by itself prove local filesystem access. If necessary, request
   narrow read access to that exact ZIP. If exact-file access cannot be granted,
   ask the user to move only that ZIP into an approved workspace path and stop
   until it is readable; do not request broader download-folder access when the
   exact path is already known.

## Verify and Extract

Load Codex workspace dependencies, use the returned bundled Python executable,
and resolve `scripts/extract_unit4_zip.py` relative to this skill's `SKILL.md`.
Pass every executable, script, path, and entry name as a separately shell-quoted
data argument. Never concatenate an entry name into shell syntax or execute it
unquoted. For extraction, the helper enforces private owner/mode checks on
`--output-dir` on POSIX hosts. On Windows it rejects a reparse-point
`--output-dir` and relies on the current user's temporary-directory or
approved-workspace ACL boundary. These output-directory guarantees do not
apply to `--zip`; establish the ZIP through the verified download identity and
the inspection step below.

1. Run the helper's `inspect --zip <path>` command. Exit `0` with status `SAFE`
   confirms the ZIP is readable and contains exactly six regular,
   unencrypted `.xlsx` entries within the enforced entry-name, type, size,
   collision, and compression limits. Exit `1` is invalid input; exit `3` is
   `BLOCKED`.
   Do not improvise a less strict extractor after either failure.
2. Match entries to the six captured orders using, in descending strength:
   - The full Unit4 filename captured from the row.
   - The captured unique filename prefix plus order number when Unit4 truncated
     the rendered cell.
   - The order number in the archive entry plus workbook identity checks after
     extraction.
3. If any entry cannot be mapped uniquely, report the ambiguity and do not
   reconcile it.
4. Request narrow write access when required and create a new private temporary
   directory accessible only to the current user. Never treat the ZIP itself as
   an Excel workbook. Keep the original ZIP unchanged as the deliverable.
5. Run the helper's `extract` command with the exact six entry names and
   corresponding controlled targets established by the identity mapping:

   ```text
   <bundled-python> <skill-root>/scripts/extract_unit4_zip.py extract \
     --zip <archive> --output-dir <private-directory> \
     --entry <raw-entry> --target raw-balance.xlsx \
     --entry <1510-entry> --target account-1510.xlsx \
     --entry <1560-entry> --target account-1560.xlsx \
     --entry <2440-entry> --target account-2440.xlsx \
     --entry <2444-entry> --target account-2444.xlsx \
     --entry <2460-entry> --target account-2460.xlsx
   ```

   Require exit `0` and status `EXTRACTED`. The helper refuses unsafe archives,
   existing targets, or incomplete mappings and removes partial outputs on
   failure. Preserve each original entry name in the identity mapping, but use
   only the controlled target paths for reconciliation.

## Unit4 Buffer Recovery

Use this recovery only when a verified **Last ned** click produced no unique
readable ZIP. Perform it at most once per gathering run. Because clearing the
Unit4 application buffer can refresh other Unit4 tabs and discard unsaved UI
state, tell the user why it is needed and obtain explicit consent immediately
before step 1 unless the user explicitly authorized buffer clearing for this
run.

1. Open the signed-in username menu next to the company selector.
2. Select **Om Unit4 ERP**, then **Tøm bufferen**. This is Unit4's application
   buffer; do not clear Chrome history, cookies, downloads, or profiles.
3. Wait for Unit4 to refresh. Verify authentication and the requested company.
4. Return to **Dine bestilte rapporter** and re-identify all six rows by exact
   order number. Re-verify report names, filenames, and `Ferdig` status.
5. Ensure only those rows are selected, prepare a fresh artifact wait or scoped
   download snapshot, and click **Last ned** once.
6. Repeat the ZIP checks. If the retry fails, stop and report the six existing
   order numbers. Suggesting a manual retry in another Chrome profile or
   browser is allowed, but never switch automatically and never create new
   report orders as part of recovery.
