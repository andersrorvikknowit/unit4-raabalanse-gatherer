# Reconciliation

Reconcile locally and read-only after verifying and extracting the Unit4 ZIP.
Never modify a source workbook. Use the deterministic
`scripts/reconcile_unit4.py` validator described below; do not replace it with
visual arithmetic or ad-hoc spreadsheet formulas.

## Establish Workbook Identity

For each extracted workbook, verify the visible client/company and period
match the request. Identify exactly one Råbalanse workbook and exactly one
periodisert workbook for each account `1510` and `1560`.

For an account workbook, require at least one of these identity proofs:

- A visible report parameter or heading identifies the exact account, and any
  populated detail rows agree.
- Every populated detail row's **Account** value equals the exact requested
  account.

Reject a wildcard report that contains another account. An empty detail report
without a visible exact-account parameter is ambiguous and must be `BLOCKED`,
not assumed to represent a zero balance.

## Parse Monetary Values Safely

Prefer the workbook's underlying numeric values. When a value is stored as
localized text, normalize Norwegian formatting deliberately: ordinary,
non-breaking, or thin spaces may be thousands separators; comma may be the
decimal separator; parentheses or a trailing minus may indicate a negative
value. Do not discard a sign. Use decimal arithmetic rather than binary
floating point. Every monetary source value must already be representable to
two decimal places; unexpected sub-cent precision is `BLOCKED`, not silently
rounded. Compare exact cents.

If a value cannot be parsed unambiguously, mark that account `BLOCKED` and
report the validator's privacy-safe reason and cell coordinate. Do not reopen
the workbook merely to expose the raw cell content.

## Calculate Each Account

For each account independently:

1. Locate the periodisert detail table through semantic headers including
   **Account** and **Remaining Amount**, or clearly equivalent localized labels.
2. Include only detail rows whose **Account** equals the requested account.
   Exclude headings, blanks, displayed totals, and subtotals.
3. Sum the numeric **Remaining Amount** values. Compare the calculated sum with
   the workbook's displayed total when present. A difference is a report
   integrity failure and makes this account `BLOCKED`.
4. In Råbalanse, locate the exact account row and the **Beløp**/balance value
   for the requested period. Do not use substring matches. If multiple rows or
   balance columns could apply, mark the account `BLOCKED`.
5. Calculate the signed difference:

   `periodisert detail sum - Råbalanse value`

6. Classify the account `MATCH` only when the exact-cent difference is `0.00`.
   Any non-zero difference is `AVVIK` and requires human review. Never compare
   absolute values, reverse signs silently, or round away a discrepancy.

## Report and Clean Up

For each account, return the periodisert sum, Råbalanse value, signed
difference, `MATCH`/`AVVIK`/`BLOCKED`, account-order number, and workbook
filename. Do not expose individual customer rows unless explicitly requested.

The overall reconciliation is:

- `MATCH` only when both accounts are `MATCH`.
- `AVVIK` when at least one account is `AVVIK` and neither is `BLOCKED`.
- `BLOCKED` when any account cannot be verified or calculated safely; still
  report any completed account results separately.

Remove only the temporary extracted copies created for this run after the
check. Keep the original verified ZIP unchanged.

## Run the Validator

Load Codex workspace dependencies, use the returned bundled Python executable,
and resolve `scripts/reconcile_unit4.py` relative to this skill's `SKILL.md`
rather than the user's current working directory. Invoke it once with the
verified identity chain and controlled extracted paths. Pass every executable,
script, and file path as a separately shell-quoted argument; never interpolate
raw ZIP entry names or other untrusted text into a shell command:

```text
<bundled-python> <skill-root>/scripts/reconcile_unit4.py \
  --raw-balance <råbalanse.xlsx> \
  --periodised 1510=<1510.xlsx> \
  --periodised 1560=<1560.xlsx> \
  --company <company-code> \
  --period <YYYYMM>
```

Interpret exit code `0` as all `MATCH`, `2` as at least one `AVVIK`, `3` as
`BLOCKED`, and `1` as invalid invocation. Preserve the JSON output in task
state, but do not publish customer-level detail; the validator intentionally
returns only aggregate identity and reconciliation results.
