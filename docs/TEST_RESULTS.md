# Tests, logs & debugging

This file covers the testing, logging and debugging parts of the assignment: what I test and
why, the run logs, the problems I hit, and a worked example of finding and fixing one.

## The tests

There are 23 tests. I kept the set small on purpose and went for the ones that actually
protect the Data Vault, instead of testing every column. The plain `not_null` checks on
metadata like `load_date` add noise without catching much, so I left them out.

Most tests are dbt's built-in generic tests declared in the `_*.yml` files. A few come from
the `dbt_utils` package, and one is a custom SQL test in `tests/`.

What's covered:

- **Staging** (`_staging.yml`): `unique` + `not_null` on each business key (`customer_id`,
  `product_id`, `order_id`). This catches bad keys early, before the vault loads.
- **Hubs** (`_raw_vault.yml`): `unique` + `not_null` on each hub's hash key, and `unique` on
  each business key. A hub key has to identify exactly one thing.
- **Link** (`_raw_vault.yml`): `unique` + `not_null` on the link hash key, plus
  `relationships` from `customer_hk` and `product_hk` back to their hubs. The link can never
  point at a hub key that doesn't exist.
- **Satellites** (`_raw_vault.yml`): `unique_combination_of_columns` on `(*_hk, load_date)`
  so there's one version per key per load, plus a `relationships` test to the parent.
- **Custom** (`assert_no_orphan_links.sql`): checks every link row resolves to a real
  customer hub and product hub. It's the same idea as the relationships tests but in one
  readable query, and a good template for harder business rules later.

## Run logs

Paste the dbt Cloud output here after running. dbt also writes full logs to `logs/dbt.log`,
or the run's Logs tab in dbt Cloud.

### `dbt deps`
```
<paste output>
```

### `dbt seed`
```
<paste output — expect raw_customers 8, raw_products 6, raw_orders 15>
```

### `dbt run`
```
<paste output — expect 3 views + 6 vault tables built, all PASS>
```

### `dbt test`
```
<paste output — expect 23 tests, all PASS>
```

### `dbt build` (everything in one go)
```
<paste the final line, e.g. Completed successfully ... PASS=NN>
```

### Lineage graph
After `dbt docs generate`, open View Docs and screenshot the lineage view:

`![lineage](lineage.png)`

## Problems I hit (and how I fixed them)

A few things went wrong setting this up. Keeping them here since the brief asks for errors
encountered, and they're the kind of thing you'd actually run into.

**1. Snowflake login stopped working.**
`Test connection` started failing with `390100 (08004): Incorrect username or password`,
even though it had worked half an hour earlier. My account had been temporarily locked from
too many attempts. Once it was unlocked the same credentials worked, so nothing in dbt
needed changing.

**2. `dbt seed` failed before loading anything.**
A batch of `DbtYamlValidationError (dbt1159)` errors pointing at `_raw_vault.yml`. This dbt
version is the 2.0 / Fusion preview, which no longer accepts the old test syntax where `to`,
`field` and `combination_of_columns` sit at the top level. The fix was to nest them under an
`arguments:` key:

```yaml
- relationships:
    arguments:
      to: ref('hub_customer')
      field: customer_hk
```

dbt parses every `.yml` before running anything, so this broke `dbt seed` even though seeds
have nothing to do with those tests.

**3. 11 tests failed with `370001` internal errors.**
These weren't real failures. A real `not_null` failure says `Got N results`, but these said
`Snowflake 370001 (08004): Internal error`, only hit a random handful of tests, and each one
took 90+ seconds on tiny 8-row tables. That's a warehouse problem, not a data one. The
queries were queueing on a shared warehouse with 6 threads. Re-running on a dedicated XS
warehouse cleared it.

## A worked debugging example

To show the workflow end to end, here's a problem I introduced on purpose, then found and
fixed using the logs.

**Break it.** Add a duplicate customer to `seeds/raw_customers.csv`:

```diff
 8,Sophia,Wilson,sophia.w@example.com,Germany,2023-08-30
+8,Sophia,Wilson,sophia.w@example.com,Germany,2023-08-30
```

Then `dbt seed --full-refresh && dbt build`.

**See it fail.** The build fails on the hub's uniqueness test:

```
Failure in test unique_hub_customer_customer_hk
  Got 1 result, configured to fail if != 0
```

Two rows share `customer_id = 8`, so they hash to the same `customer_hk`, and the hub now has
a duplicate key.

**Find it.** Run the failing check against the table to see the offender:

```sql
select customer_hk, count(*)
from <dev_schema>.hub_customer
group by 1 having count(*) > 1;
```

It returns the hash for `customer_id = 8` with a count of 2, confirming a duplicate key in
the source.

**Fix it.** Remove the duplicate row and re-run. Everything goes back to PASS. The test did
its job: it caught a data problem at the source, which is where it gets fixed, not in the SQL.

### Handy debugging commands
- `dbt compile -s <model>` — see the generated SQL in `target/compiled/`
- `dbt run -s <model> --debug` — verbose logs with the exact query sent to Snowflake
- `dbt test -s <model>` — run just one model's tests
- `dbt run -s +<model>` / `<model>+` — build a model with its parents / children
