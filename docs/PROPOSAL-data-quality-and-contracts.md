# Proposal: Data Quality & Data Contracts for our dbt Platform

**Author:** Martin Tsvetkov
**Date:** 22 July 2026
**Status:** For review
**Audience:** Data / Analytics Engineering management

---

## 1. Summary (the ask)

We are adding dbt models faster than we are adding the guardrails that keep them
trustworthy. I'd like us to adopt a lightweight, standard framework for **data
quality** and **data contracts**, applied in tiers so the effort scales with how
important each model is.

I've already built a working reference implementation on top of our Data Vault
proof-of-concept (Snowflake + dbt Cloud), so this proposal isn't theoretical — the
patterns below are running code we can copy into other projects.

**What I'm asking for:** agreement to make this the default standard for new dbt
work, and ~2–3 days to document it and wire the coverage gate into CI.

---

## 2. Why now

Three problems are already visible, and they get more expensive the longer we wait:

1. **Tests are ad-hoc.** There's no agreed "minimum bar" per layer, so coverage
   depends on who wrote the model and how busy they were that week.
2. **Downstream things break silently.** When a column is renamed or its type
   changes, the first we hear about it is a broken dashboard — after it's shipped.
3. **No single definition of "done."** We can't point a new hire (or an auditor) at
   one document that says what a trustworthy model looks like here.

None of these are crises today. All of them become one at scale, and the fix is
much cheaper to put in now, while the project is small.

---

## 3. What I'm proposing

Two connected things:

- **A data-quality bar** — a standard set of tests every model must pass, scaled by
  layer, plus source freshness checks.
- **Data contracts** — enforced schema guarantees, constraints and versioning on
  the models other people and tools actually consume.

Two principles keep it from becoming bureaucracy:

- **Tiered, not uniform.** Cheap internal models get key checks; public models that
  feed reporting get the full treatment. We don't gold-plate throwaway data.
- **Contracts only at the interface.** Only the public "marts" layer is put under
  contract. Internal staging and vault models stay flexible so day-to-day work
  isn't slowed down.

---

## 4. The data-quality bar (per layer)

This is the minimum every model must meet before it's considered done. It uses only
native dbt tests plus `dbt_utils`, which we already have — no new dependencies.

| Layer | What it is | Minimum bar |
|---|---|---|
| **Sources** | raw landing tables | Freshness (is the data current?) + unique/not-null on natural keys |
| **Staging** | cleaned views | Unique + not-null on business keys; correct types |
| **Raw Vault** | hubs / links / satellites | Key uniqueness; referential integrity between them; correct history grain |
| **Marts** | public dim/fact tables | All of the above **plus a data contract** (see §5) |

Two supporting mechanisms worth calling out:

- **Severity levels.** Critical checks (duplicate keys, broken relationships)
  *block* the pipeline. Sanity checks (a negative price, an odd quantity) only
  *warn*, so we're alerted without halting everything. This keeps the signal useful
  instead of everyone learning to ignore red builds.
- **Stored failures.** When a test fails, the actual offending rows are saved to a
  table. So instead of "a uniqueness test failed somewhere," an analyst can query
  the exact three customers causing it. That's the difference between a five-minute
  fix and an afternoon.

Advanced tooling (anomaly detection, richer assertions via `dbt_expectations` /
`elementary`) is designed in but left **off behind a feature flag** — we can switch
it on later without re-architecting anything, and only pay for it when we decide we
need it.

---

## 5. Data contracts (the part that prevents outages)

A data contract is a written, enforced promise about a public table: *"this table
will always have exactly these columns, with these types and these guarantees."*
The build fails if the model's output ever drifts from that promise.

**Business value:** downstream dashboards and consuming teams stop breaking by
surprise. A schema change can no longer slip out silently — either the producer
updates the contract deliberately (a reviewed decision), or the build goes red
before it ships.

Three capabilities make this real:

- **Enforced schema.** Every public column has a declared type. If a model starts
  producing a different shape, the build stops.
- **Versioning.** We can evolve a table without a hard break. For example, our
  customer dimension ships as **v1 and v2** — v2 adds an `email_domain` column.
  Anything still on v1 keeps working, with a published deprecation date to migrate
  by. No "we changed the table and three dashboards went blank Monday morning."
- **Ownership & visibility.** Each public table has a named owner, and we declare
  which dashboards depend on it — so before changing anything, we can see exactly
  what's at risk.

### Technical example

Declaring the contract (the "warranty"):

```yaml
models:
  - name: dim_customer
    latest_version: 2
    columns:
      - name: customer_hk
        data_type: varchar
        constraints: [{type: primary_key}, {type: not_null}]
    versions:
      - v: 1
        deprecation_date: 2026-12-31   # consumers have a deadline to move to v2
      - v: 2                            # adds email_domain (additive = minor change)
```

If someone changes a column type in the SQL but not the contract, the build fails
clearly instead of shipping the drift:

```
Compilation Error in model fact_orders
  This model has an enforced contract that failed.
  | column       | model output | contract     | reason         |
  | total_amount | FLOAT        | NUMBER(38,2) | data type mismatch |
```

---

## 6. Making the standard stick

A standard nobody enforces quietly rots. Two things keep this one honest:

- **A coverage gate.** An automated check fails the build if any model is missing
  its required tests, or a public model is missing its contract. This turns "please
  remember to add tests" into a rule that can't be skipped under deadline pressure.
- **Runs in CI on every change.** The full set — models, tests, contracts, coverage
  gate — runs on each pull request and blocks merge on failure. Quality stops
  depending on individual diligence.

---

## 7. Honest caveats

I want to be straight about the limits so there are no surprises:

- **Snowflake only enforces `not_null` at the database level.** Primary/foreign key
  constraints are stored as documentation, and check constraints aren't supported at
  all. We cover those cases with dbt tests instead, which run regardless — so the
  guarantee holds, it's just enforced by our pipeline rather than by Snowflake.
- **This is preventative work.** It won't produce a new dashboard next week. Its
  value shows up as problems that *don't* happen: fewer broken reports, less rework,
  faster and safer scaling. That's a real trade-off worth stating plainly.

---

## 8. Effort and rollout

Because the reference implementation already exists, the remaining work is small:

| Step | Effort |
|---|---|
| Finalise the playbook doc (the standard, written down once) | ~0.5 day |
| Wire the coverage gate + contract checks into CI | ~1 day |
| Apply the bar to one existing project as the template | ~1 day |
| **Total** | **~2–3 days** |

Rollout to other projects is then copy-and-adapt — realistically an afternoon per
project, since the artifacts are reusable.

---

## 9. Recommendation

I recommend we adopt this as the default for new dbt work now, while the footprint
is small, and apply it to existing projects opportunistically as we touch them. The
cost is modest and mostly already spent; the downside of waiting is that every model
we add without it is one more we'll have to retrofit later.

Happy to walk through the running implementation in a short session if that's
useful.
