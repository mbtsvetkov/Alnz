# Test Results, Logs & Debugging

This document summarises the data-quality tests, records the execution logs, and walks
through a deliberate debugging exercise — covering the **Testing**, **Logging**, and
**Debugging** parts of the assignment.

---

## 1. Test inventory

The project uses dbt's **built-in generic tests**, the **dbt_utils** package, and one
**custom singular test**. Tests are defined declaratively in the `_*.yml` files; the
singular test is a SQL query in `tests/`.

A deliberately **curated set of 23 high-value tests** — focused on Data Vault integrity
(identity, referential integrity, history grain) rather than exhaustively testing every
column. Low-value metadata `not_null` checks were intentionally omitted to keep the suite
fast and meaningful.

| Layer | File | Tests (23 total) |
|---|---|---|
| Staging | `models/staging/_staging.yml` | `unique` + `not_null` on each business key (`customer_id`, `product_id`, `order_id`) — early warning before the vault loads — **6** |
| Raw Vault — hubs | `models/raw_vault/_raw_vault.yml` | `unique`+`not_null` on each hub **primary hash key**; `unique` on each hub **business key** — **6** |
| Raw Vault — link | `models/raw_vault/_raw_vault.yml` | `unique`+`not_null` on the link hash key; `relationships` from `customer_hk`/`product_hk` to their hubs — **4** |
| Raw Vault — satellites | `models/raw_vault/_raw_vault.yml` | `dbt_utils.unique_combination_of_columns` (`*_hk` + `load_date`) and a `relationships` test to the parent, on each of the 3 satellites — **6** |
| Custom | `tests/assert_no_orphan_links.sql` | Asserts **no orphan links** — every link row resolves to an existing customer hub *and* product hub — **1** |

**Test categories and why they matter**

- **`not_null`** — hash keys and audit columns must always be populated; a null key breaks
  every downstream join.
- **`unique`** — a hub/link primary hash key must identify exactly one row (no duplicate
  business keys leaking in).
- **`relationships`** — referential integrity: a link/satellite can never point at a hub key
  that doesn't exist.
- **`unique_combination_of_columns`** — guards satellite grain: one version per parent key
  per load (no accidental duplicate history rows).
- **Custom `assert_no_orphan_links`** — a single readable business-rule test; a template for
  more complex assertions later.

> **23 tests** total. The exact count and pass/fail appear in the `dbt test` output below.

---

## 2. Execution logs

> Paste the dbt Cloud output here after running. Each command also writes detailed logs to
> `logs/dbt.log` (local) or the run's **Logs** tab in dbt Cloud.

### `dbt deps`
```
<paste output>
```

### `dbt seed`
```
<paste output — expect: raw_customers (8), raw_products (6), raw_orders (15)>
```

### `dbt run`
```
<paste output — expect: 3 staging views + 6 raw vault tables built, PASS>
```

### `dbt test`
```
<paste output — expect: all tests PASS>
```

### `dbt build` (one-shot)
```
<paste the final summary line, e.g. "Completed successfully ... PASS=NN">
```

### Lineage graph
After `dbt docs generate`, click **View Docs** → lineage. Save a screenshot here:

`![lineage](lineage.png)`

---

## 3. Debugging walkthrough (deliberate break → diagnose → fix)

This demonstrates the debugging workflow required by the brief.

### Step 1 — Introduce a defect
Add a duplicate customer business key to `seeds/raw_customers.csv`:
```diff
 8,Sophia,Wilson,sophia.w@example.com,Germany,2023-08-30
+8,Sophia,Wilson,sophia.w@example.com,Germany,2023-08-30
```
Re-run:
```bash
dbt seed --full-refresh && dbt build
```

### Step 2 — Observe the failure
`dbt build` fails on the customer hub's uniqueness test, with output similar to:
```
Failure in test unique_hub_customer_customer_hk (models/raw_vault/_raw_vault.yml)
  Got 1 result, configured to fail if != 0
  compiled Code at target/compiled/.../unique_hub_customer_customer_hk.sql
```
Two source rows share `customer_id = 8`, so they hash to the same `customer_hk`, and the hub
now has a duplicate primary key.

### Step 3 — Diagnose
Run the compiled failing query (dbt prints its path) to see the offending key:
```sql
select customer_hk, count(*)
from <DEV_SCHEMA>.hub_customer
group by 1 having count(*) > 1;
```
Returns the hash for `customer_id = 8` with `count = 2` → confirms a duplicate business key
in the source.

### Step 4 — Fix & verify
Remove the duplicate row from the CSV and re-run:
```bash
dbt seed --full-refresh && dbt build
```
All tests return to **PASS**. The `unique` test did exactly its job: it stopped bad data from
silently corrupting the vault.

> Takeaway: tests are the safety net. The fix wasn't in SQL logic — the test correctly
> surfaced a **data** problem at the source, which is where it was resolved.

### Other useful debugging commands
- `dbt compile -s <model>` → inspect the generated SQL in `target/compiled/...`
- `dbt run -s <model> --debug` → verbose logs incl. the exact warehouse query
- `dbt test -s <model>` → run just one model's tests
- `dbt run -s +<model>` / `<model>+` → run a model with all its parents / children
