# Reconciliation

Reconcile locally and read-only after verifying and extracting the Unit4 ZIP.
Never modify a source workbook. Use the deterministic
`scripts/reconcile_unit4.py` validator described below; do not replace it with
visual arithmetic or ad-hoc spreadsheet formulas.

## Establish Workbook Identity

For each extracted workbook, verify the visible client/company and period
match the request. Identify exactly one Råbalanse workbook and exactly one
periodisert output for each account `1510`, `1560`, `2440`, `2444`, and
`2460`. Require `Periodisert saldospesifikasjon kunder` for `1510` and `1560`,
and `Periodisert saldospesifikasjon leverandør` for `2440`, `2444`, and `2460`.

For an account workbook, require at least one of these identity proofs:

- A visible report parameter or heading identifies the exact account, and any
  populated detail rows agree.
- Every populated detail row's **Account** value equals the exact requested
  account.

Reject a wildcard report that contains another account. An empty detail report
without a visible exact-account parameter is ambiguous and must be `BLOCKED`,
not assumed to represent a zero balance.

For a supplier `.agm`, use a zero periodised sum only when its order number
matches the captured supplier order, the exact Unit4 log identifies the
requested company, account, and period, and the log says
`No rows found. Report stop`. The product owner confirmed this is an empty
result. Pass `--empty-supplier <account>=<order>` to the validator along with
the extracted `account-<account>.agm` path. This flag attests to the log check;
never set it from the filename or `Ferdig` status alone. For this verified
empty-result case, the user confirmed that an absent Råbalanse account row
also means zero and produces no deviation. Do not treat missing raw rows as
zero for ordinary XLSX reports or for an AGM without the exact log evidence.

## Parse Monetary Values Safely

Prefer the workbook's underlying numeric values. Unit4 can store a
two-decimal Excel amount with tiny binary-float residue; the validator accepts
only a residual within two floating-point ULPs of an exact-cent value. When a
value is stored as
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
   for the requested period. In Unit4's Trial Balance export, **Year To Date**
   is the closing balance column. Ignore hidden template sheets such as
   `_control` when establishing report identity. Do not use substring matches.
   If multiple rows or
   balance columns could apply, mark the account `BLOCKED`.
5. Calculate the signed difference:

   `periodisert detail sum - Råbalanse value`

6. Classify the account `MATCH` only when the exact-cent difference is `0.00`.
   Any non-zero difference is `AVVIK` and requires human review. Never compare
   absolute values, reverse signs silently, or round away a discrepancy.

## Report and Clean Up

For each account, return the periodisert sum, Råbalanse value, signed
difference, `MATCH`/`AVVIK`/`BLOCKED`, account-order number, and workbook
filename. Do not expose individual customer or supplier rows unless explicitly
requested.

The overall reconciliation is:

- `MATCH` only when all five accounts are `MATCH`.
- `AVVIK` when at least one account is `AVVIK` and neither is `BLOCKED`.
- `BLOCKED` when any account cannot be verified or calculated safely; still
  report any completed account results separately.

When there is `AVVIK`, make the account comparison the center of the answer:
show the signed difference, both source totals, the account order and workbook,
and whether the periodised workbook's displayed total agrees with its detail
sum. Explain which checks passed and suggest the next human review based on
the verified evidence. Keep possible causes clearly labeled as hypotheses;
do not claim a specific customer or supplier caused the difference without
transaction-level evidence or expose those rows without an explicit request.

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
  --periodised 2440=<2440.xlsx> \
  --periodised 2444=<2444.xlsx> \
  --periodised 2460=<2460.xlsx> \
  --company <company-code> \
  --period <YYYYMM>
```

For an attested empty supplier result, use
`--periodised <account>=<account.agm>` and add
`--empty-supplier <account>=<order>` to the same invocation. The user
confirmed that a missing Råbalanse row also represents zero only for this
verified empty supplier case.

Interpret exit code `0` as all `MATCH`, `2` as at least one `AVVIK`, `3` as
`BLOCKED`, and `1` as invalid invocation. Preserve the JSON output in task
state, but do not publish customer- or supplier-level detail; the validator
intentionally returns only aggregate identity and reconciliation results.
