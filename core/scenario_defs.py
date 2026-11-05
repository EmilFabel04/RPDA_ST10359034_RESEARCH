"""The 15 failure scenarios: 5 categories x 3 genuinely different root causes.

Each scenario applies ONE fault to a fresh copy of the dbt project and carries
the researcher-written material that cannot come from dbt artefacts:
synthetic historical context and the gold-standard remediation.

Text fields are `string.Template` strings ($name placeholders; `$$` = a
literal dollar sign) filled with `facts`: numbers, dates and ids computed when
the fault is applied. Every number in the text therefore matches the data the
LLM is shown.

Root-cause types: data = upstream data/ingestion, code = dbt model SQL,
config = dbt YAML configuration.
"""
from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from core.seed_data import TS_FMT, _hourly_load, read_csv, write_csv

CATEGORIES = ["schema_drift", "null_rate_anomaly", "row_count_anomaly",
              "referential_integrity", "freshness_violation"]


@dataclass
class Scenario:
    id: str
    category: str
    title: str                     # researcher label, never shown to LLMs or evaluators
    root_cause_type: str           # data | code | config
    root_cause: str                # one-sentence ground truth
    apply: Callable[[Path, datetime], dict]   # mutates the project copy, returns facts
    expected_failures: list[str]   # short node ids, e.g. "test.not_null_stg_payments_amount"
    fix_targets: dict              # where a correct fix acts: files / models / columns / upstream
    key_entities: list[str]        # names a correct diagnosis would mention
    changes: list[tuple[int, str, str]]   # relevant (days_ago, kind, text) recent changes
    noise: tuple[int, int]         # indexes into NOISE (unrelated recent changes)
    incidents: list[str]           # previous incidents
    run_history: list[str]         # recent run metrics
    gold: dict                     # root_cause / fix / verification / notes


# Unrelated recent changes, mixed into the history so the relevant entry is not
# the only one. Each is true of the project (no false statements).
NOISE = [
    (9, "commit", "docs: add column descriptions to models/marts/schema.yml (no SQL change)"),
    (6, "deploy", "CI image upgraded dbt-duckdb 1.10 → 1.11; full build passed afterwards"),
    (12, "commit", "stg_customers: lower-case email and upper-case country code "
                   "(models/staging/stg_customers.sql)"),
    (5, "ticket", "BI-204: 'Weekly revenue' tile added to the finance revenue dashboard (reads fct_orders)"),
    (8, "deploy", "Warehouse database file moved to faster storage; no schema changes"),
    (11, "commit", "add accepted_values test on stg_payments.payment_method (models/staging/schema.yml)"),
    (13, "deploy", "CRM connector upgraded 3.1 → 3.2 (bug-fix release)"),
]


def commit_hash(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:7]


# ---------------------------------------------------------------- helpers for faults
def load(proj: Path, table: str) -> list[dict]:
    return read_csv(proj / "seeds" / f"{table}.csv")


def save(proj: Path, table: str, rows: list[dict]) -> None:
    write_csv(proj / "seeds" / f"{table}.csv", rows)


def ts(value: str) -> datetime:
    return datetime.strptime(value, TS_FMT)


def utc(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def edit(path: Path, old: str, new: str) -> None:
    """Replace exactly one occurrence (fails loudly if the anchor text moved)."""
    text = path.read_text()
    assert text.count(old) == 1, f"{path.name}: anchor text not found exactly once"
    path.write_text(text.replace(old, new))


def base_facts(proj: Path, as_of: datetime) -> dict:
    """Facts from the clean data, before any fault (dates, volumes, history)."""
    customers, orders = load(proj, "raw_customers"), load(proj, "raw_orders")
    facts = {f"d{n}": (as_of - timedelta(days=n)).date().isoformat() for n in range(0, 181)}
    day = lambda n: (as_of - timedelta(days=n)).date().isoformat()  # noqa: E731
    facts.update({
        "as_of": utc(as_of),
        "n_customers": len(customers),
        "n_orders": len(orders),
        "n_payments": len(load(proj, "raw_payments")),
        # row counts of earlier daily runs (days 6..1 ago), for run histories
        "hist_orders": ", ".join(str(sum(o["order_date"] <= day(n) for o in orders)) for n in range(6, 0, -1)),
        "hist_customers": ", ".join(str(sum(c["created_at"][:10] <= day(n) for c in customers))
                                    for n in range(6, 0, -1)),
    })
    return facts


# ---------------------------------------------------------------- faults: schema drift
def sd01(proj, as_of):
    rows = load(proj, "raw_payments")
    save(proj, "raw_payments", [{("amount_cents" if k == "amount" else k): v for k, v in r.items()} for r in rows])
    return {}


def sd02(proj, as_of):
    since = (as_of - timedelta(days=3)).date()
    rows = load(proj, "raw_orders")
    example_old = rows[0]["order_date"]
    n = 0
    for r in rows:
        d = date.fromisoformat(r["order_date"])
        if d >= since:
            r["order_date"] = d.strftime("%d/%m/%Y")
            n += 1
    assert n > 0
    save(proj, "raw_orders", rows)
    return {"n_reformatted": n, "since": since.isoformat(),
            "example_old": example_old, "example_new": rows[-1]["order_date"]}


def sd03(proj, as_of):
    rows = load(proj, "raw_customers")
    for r in rows:
        r["customer_id"] = f"CUST-{int(r['customer_id']):05d}"
    save(proj, "raw_customers", rows)
    return {"example_key": rows[41]["customer_id"]}


# ---------------------------------------------------------------- faults: null rate
def nr01(proj, as_of):
    reload_at = as_of - timedelta(hours=3) + timedelta(minutes=5)
    window = as_of - timedelta(days=30)
    rows = load(proj, "raw_payments")
    hit = 0
    for r in rows:
        if r["payment_method"] == "gift_card" and ts(r["loaded_at"]) >= window:
            r["amount"] = ""
            r["loaded_at"] = reload_at.strftime(TS_FMT)
            hit += 1
    assert hit >= 5, f"only {hit} gift-card payments in the window"
    save(proj, "raw_payments", rows)
    return {"n_null": hit, "reload_at": utc(reload_at)}


def nr02(proj, as_of):
    edit(proj / "models/marts/fct_orders.sql",
         "coalesce(order_payments.total_amount, 0) as amount",
         "order_payments.total_amount as amount")
    paid = {p["order_id"] for p in load(proj, "raw_payments")}
    return {"n_null": sum(o["order_id"] not in paid for o in load(proj, "raw_orders"))}


def nr03(proj, as_of):
    rows = load(proj, "raw_customers")
    n = 0
    for r in rows:
        if r["country"] in ("DE", "NL"):
            r["email"] = ""
            n += 1
    save(proj, "raw_customers", rows)
    return {"n_null": n, "null_pct": f"{n / len(rows):.1%}"}


# ---------------------------------------------------------------- faults: row count
def rc01(proj, as_of):
    rows = load(proj, "raw_orders")
    latest = max(r["loaded_at"] for r in rows)
    save(proj, "raw_orders", rows + [{**r, "loaded_at": latest} for r in rows])
    return {"n_rows": 2 * len(rows), "n_distinct": len(rows), "latest_load": utc(ts(latest))}


def rc02(proj, as_of):
    since = as_of.date() - timedelta(days=60)
    orders = load(proj, "raw_orders")
    kept = [o for o in orders if date.fromisoformat(o["order_date"]) >= since]
    save(proj, "raw_orders", kept)
    kept_ids = {o["order_id"] for o in kept}
    orphans = sum(p["order_id"] not in kept_ids for p in load(proj, "raw_payments"))
    return {"n_kept": len(kept), "n_before": len(orders), "since": since.isoformat(),
            "n_orphan_payments": orphans}


FCT_ORDERS_FANOUT = """with orders as (

    select * from {{ ref('stg_orders') }}

),

payments as (

    select * from {{ ref('stg_payments') }}

),

final as (

    select
        orders.order_id,
        orders.customer_id,
        orders.order_date,
        orders.status,
        case when payments.payment_method = 'credit_card' then payments.amount else 0 end as credit_card_amount,
        case when payments.payment_method = 'bank_transfer' then payments.amount else 0 end as bank_transfer_amount,
        case when payments.payment_method = 'voucher' then payments.amount else 0 end as voucher_amount,
        case when payments.payment_method = 'gift_card' then payments.amount else 0 end as gift_card_amount,
        coalesce(payments.amount, 0) as amount
    from orders
    left join payments on orders.order_id = payments.order_id

)

select * from final
"""


def rc03(proj, as_of):
    path = proj / "models/marts/fct_orders.sql"
    assert "order_payments as (" in path.read_text()
    path.write_text(FCT_ORDERS_FANOUT)
    per_order = Counter(p["order_id"] for p in load(proj, "raw_payments"))
    orders = load(proj, "raw_orders")
    n_rows = sum(max(1, per_order[o["order_id"]]) for o in orders)
    return {"n_rows": n_rows, "n_split": sum(c > 1 for c in per_order.values())}


# ---------------------------------------------------------------- faults: referential integrity
NEW_SIGNUPS = [("Ayanda", "Mthembu", "ZA", 30, 4599), ("Grace", "Evans", "GB", 26, 12950),
               ("Jonas", "Weber", "DE", 20, 2300), ("Lindiwe", "Zulu", "ZA", 14, 8875),
               ("Ethan", "Clark", "US", 8, 15420)]


def ri01(proj, as_of):
    customers, orders, payments = (load(proj, t) for t in ("raw_customers", "raw_orders", "raw_payments"))
    # The world: 5 customers signed up in the last 30 h and each placed an order ...
    for i, (first, last, country, hours_ago, cents) in enumerate(NEW_SIGNUPS):
        cid, oid = len(customers) + 1, len(orders) + 1
        created = as_of - timedelta(hours=hours_ago)
        placed = created + timedelta(hours=2)
        customers.append({"customer_id": str(cid), "first_name": first, "last_name": last,
                          "email": f"{first}.{last}{cid}@example.com".lower(), "country": country,
                          "created_at": created.strftime(TS_FMT),
                          "loaded_at": (created + timedelta(minutes=45)).strftime(TS_FMT)})
        orders.append({"customer_id": str(cid), "order_id": str(oid), "order_date": placed.date().isoformat(),
                       "status": "placed", "loaded_at": _hourly_load(placed).strftime(TS_FMT)})
        payments.append({"payment_id": str(len(payments) + 1), "order_id": str(oid),
                         "payment_method": "credit_card", "amount": str(cents),
                         "loaded_at": _hourly_load(placed + timedelta(minutes=5)).strftime(TS_FMT)})
    orders = [{k: o[k] for k in ("order_id", "customer_id", "order_date", "status", "loaded_at")} for o in orders]
    # ... THE FAULT: the CRM extract stalled 36 h ago, so recent customers never loaded
    cutoff = as_of - timedelta(hours=36)
    kept = [c for c in customers if ts(c["loaded_at"]) <= cutoff]
    missing = [c["customer_id"] for c in customers if ts(c["loaded_at"]) > cutoff]
    save(proj, "raw_customers", kept)
    save(proj, "raw_orders", orders)
    save(proj, "raw_payments", payments)
    last_load = max(ts(c["loaded_at"]) for c in kept)
    return {"missing_ids": ", ".join(missing), "n_missing": len(missing),
            "n_orphan_orders": sum(o["customer_id"] in missing for o in orders),
            "crm_last_load": utc(last_load),
            "crm_hours": round((as_of - last_load).total_seconds() / 3600)}


def ri02(proj, as_of):
    anchor = "    left join customer_payments on customers.customer_id = customer_payments.customer_id\n"
    edit(proj / "models/marts/dim_customers.sql", anchor,
         anchor + "    -- marketing dashboard only covers launch markets (MKT-12)\n"
                  "    where customers.country_code in ('ZA', 'GB', 'US')\n")
    customers = load(proj, "raw_customers")
    excluded = {c["customer_id"] for c in customers if c["country"] not in ("ZA", "GB", "US")}
    return {"n_excluded": len(excluded), "n_dim_rows": len(customers) - len(excluded),
            "n_orphan_orders": sum(o["customer_id"] in excluded for o in load(proj, "raw_orders"))}


def ri03(proj, as_of):
    customers, orders, payments = (load(proj, t) for t in ("raw_customers", "raw_orders", "raw_payments"))
    by_customer: dict[str, list[dict]] = {}
    for o in orders:
        by_customer.setdefault(o["customer_id"], []).append(o)
    erased = min((cid for cid, os in by_customer.items()
                  if 4 <= len(os) <= 6 and all(o["status"] != "cancelled" for o in os)), key=int)
    erased_orders = [o["order_id"] for o in by_customer[erased]]
    save(proj, "raw_customers", [c for c in customers if c["customer_id"] != erased])
    save(proj, "raw_orders", [o for o in orders if o["customer_id"] != erased])
    return {"erased_customer": erased, "erased_orders": ", ".join(erased_orders),
            "n_orphan_payments": sum(p["order_id"] in erased_orders for p in payments)}


# ---------------------------------------------------------------- faults: freshness
def fv01(proj, as_of):
    cutoff = as_of - timedelta(hours=20)
    out = {}
    for table in ("raw_orders", "raw_payments"):
        rows = load(proj, table)
        kept = [r for r in rows if ts(r["loaded_at"]) <= cutoff]
        save(proj, table, kept)
        out[f"n_missing_{table}"] = len(rows) - len(kept)
        if table == "raw_orders":
            last = max(ts(r["loaded_at"]) for r in kept)
    out.update({"last_load": utc(last), "hours_stale": round((as_of - last).total_seconds() / 3600)})
    return out


def fv02(proj, as_of):
    stuck = (as_of - timedelta(hours=30)).replace(minute=5)
    rows = load(proj, "raw_orders")
    n = 0
    for r in rows:
        if ts(r["loaded_at"]) > stuck:
            r["loaded_at"] = stuck.strftime(TS_FMT)
            n += 1
    save(proj, "raw_orders", rows)
    return {"stuck": utc(stuck), "n_orders_recent": n,
            "latest_order_date": max(r["order_date"] for r in rows),
            "stuck_hours": round((as_of - stuck).total_seconds() / 3600)}


def fv03(proj, as_of):
    edit(proj / "models/staging/sources.yml",
         "            warn_after: {count: 24, period: hour}\n            error_after: {count: 48, period: hour}\n",
         "            warn_after: {count: 1, period: hour}\n            error_after: {count: 2, period: hour}\n")
    last = max(ts(c["loaded_at"]) for c in load(proj, "raw_customers"))
    return {"customers_last_load": utc(last),
            "customers_hours": round((as_of - last).total_seconds() / 3600)}


# ---------------------------------------------------------------- the 15 scenarios
REL_FCT = "test.relationships_fct_orders_customer_id__customer_id__ref_dim_customers_"
REL_PAY = "test.relationships_stg_payments_order_id__order_id__ref_stg_orders_"
ROWS_STG = "test.row_count_between_stg_orders_1000__500"

SCENARIOS: list[Scenario] = [
    # ------------------------------------------------------------ schema drift
    Scenario(
        id="SD01", category="schema_drift",
        title="Payment provider renamed raw_payments.amount to amount_cents",
        root_cause_type="data",
        root_cause="The payment provider's export v2 renamed raw_payments.amount to amount_cents; "
                   "stg_payments still selects amount.",
        apply=sd01,
        expected_failures=["model.stg_payments"],
        fix_targets={"files": ["models/staging/stg_payments.sql", "models/staging/sources.yml"],
                     "models": ["stg_payments"], "columns": ["raw_payments.amount_cents", "stg_payments.amount"]},
        key_entities=["stg_payments", "raw_payments", "amount_cents"],
        changes=[(1, "vendor", "Payment provider notice: settlement export v2 is live from $d1. Field names "
                               "now follow the provider's API v2 naming.")],
        noise=(0, 1),
        incidents=["INC-0388 ($d41): stg_payments build warnings after the provider added a `currency` column. "
                   "Resolution: no change needed; staging ignores the new column."],
        run_history=["stg_payments model status, last 7 daily runs: success ×6, error today ($d0)."],
        gold={
            "root_cause": "raw.raw_payments no longer has an `amount` column: the provider's export v2 (live "
                          "$d1) renamed it to `amount_cents` (still integer cents). stg_payments.sql still "
                          "selects `amount`, so the view fails with a Binder Error and dim_customers, fct_orders "
                          "and their tests are skipped.",
            "fix": "In models/staging/stg_payments.sql change `cast(amount as decimal(18, 2)) / 100 as amount` to "
                   "`cast(amount_cents as decimal(18, 2)) / 100 as amount`. Keep the output column name "
                   "`amount` so dim_customers and fct_orders need no change. In models/staging/sources.yml "
                   "rename the raw_payments column `amount` to `amount_cents` (payment amount in integer cents).",
            "verification": "Run `dbt build --select stg_payments+`: stg_payments, dim_customers, fct_orders and "
                            "all their tests pass. Check the unit is unchanged: `select min(amount), max(amount) "
                            "from stg_payments` should be roughly 5 to 250 (currency units), and the fct_orders "
                            "revenue total should match the previous run.",
            "notes": "Prevention: enforce a model contract (or a column-presence check) on stg_payments' source "
                     "columns and follow the provider's changelog.",
        },
    ),
    Scenario(
        id="SD02", category="schema_drift",
        title="Shop export switched recent order_date values to DD/MM/YYYY",
        root_cause_type="data",
        root_cause="Since a store locale change the shop exports order_date as DD/MM/YYYY, so raw_orders.order_date "
                   "loads as VARCHAR with mixed formats and the cast to date in stg_orders fails.",
        apply=sd02,
        expected_failures=["test.not_null_stg_orders_order_date"],
        fix_targets={"files": ["models/staging/stg_orders.sql"], "models": ["stg_orders"],
                     "columns": ["raw_orders.order_date", "stg_orders.order_date"],
                     "upstream": ["shop order export date format"]},
        key_entities=["stg_orders", "raw_orders", "order_date"],
        changes=[(3, "ticket", "SHOP-219: web shop store locale switched from en-US to en-ZA (currency display "
                               "and date formats).")],
        noise=(2, 4),
        incidents=["INC-0351 ($d70): order_date was null for 12 orders after a shop export timeout. Resolution: "
                   "export re-run, no code change."],
        run_history=["stg_orders tests, last 7 daily runs: all pass ×6; today ($d0) the test that reads "
                     "order_date errors.",
                     "New orders per day: 2–5 (normal) for the last 7 days."],
        gold={
            "root_cause": "From $since the shop writes order_date as DD/MM/YYYY (e.g. '$example_new') instead of "
                          "ISO 'YYYY-MM-DD' (e.g. '$example_old'), after the SHOP-219 locale change. Because the "
                          "column now mixes formats, raw_orders.order_date loads as VARCHAR and "
                          "`cast(order_date as date)` in stg_orders raises a Conversion Error on the "
                          "$n_reformatted new rows. Tests that read order_date error, and the marts are skipped.",
            "fix": "Root fix: ask the shop team to restore ISO 8601 dates in the export (or set the export date "
                   "format explicitly). Make staging robust in models/staging/stg_orders.sql: "
                   "`coalesce(try_strptime(cast(order_date as varchar), '%Y-%m-%d'), "
                   "try_strptime(cast(order_date as varchar), '%d/%m/%Y'))::date as order_date`. Keep the "
                   "not_null test on stg_orders.order_date so any value matching neither format still fails.",
            "verification": "`dbt build --select stg_orders+` passes. `select count(*) from stg_orders where "
                            "order_date is null` returns 0 and `select max(order_date) from stg_orders` is "
                            "today's date, which shows the new rows were parsed and not dropped.",
            "notes": "Do not read the new values as MM/DD: dates such as 05/10 are ambiguous, so the format must "
                     "be stated explicitly.",
        },
    ),
    Scenario(
        id="SD03", category="schema_drift",
        title="CRM migration changed customer_id to prefixed string keys",
        root_cause_type="data",
        root_cause="After a CRM migration raw_customers.customer_id is a string key like 'CUST-00042' while "
                   "orders still use the integer id; the type mismatch fails the join in dim_customers.",
        apply=sd03,
        expected_failures=["model.dim_customers"],
        fix_targets={"files": ["models/staging/stg_customers.sql", "models/staging/sources.yml"],
                     "models": ["stg_customers"],
                     "columns": ["raw_customers.customer_id", "stg_customers.customer_id"]},
        key_entities=["stg_customers", "raw_customers", "customer_id", "dim_customers"],
        changes=[(1, "ticket", "CRM-77: CRM migrated to a new tenant; customer export regenerated with the "
                               "tenant's external reference keys.")],
        noise=(0, 5),
        incidents=["INC-0297 ($d120): duplicate customers after a CRM re-sync. Resolution: duplicates removed at "
                   "source and the CRM export re-run."],
        run_history=["dim_customers model status, last 7 daily runs: success ×6, error today ($d0). "
                     "stg_customers and its tests passed today."],
        gold={
            "root_cause": "raw_customers.customer_id changed from an integer to a prefixed string ('$example_key') "
                          "when the CRM was migrated (CRM-77). stg_customers passes the column through unchanged, "
                          "so its own unique/not_null tests still pass. The failure only appears in dim_customers, "
                          "which joins stg_customers.customer_id (VARCHAR) to stg_orders.customer_id (INTEGER) and "
                          "fails with a Conversion Error. fct_orders' relationships test is skipped.",
            "fix": "Normalise the key in models/staging/stg_customers.sql: "
                   "`cast(regexp_extract(cast(customer_id as varchar), '(\\d+)$$', 1) as integer) as customer_id`, "
                   "and keep the original as `cast(customer_id as varchar) as crm_customer_ref` for traceability. "
                   "First confirm with the CRM owner that the numeric part matches the shop's customer_id "
                   "(CUST-00042 = 42). Update the raw_customers.customer_id description in "
                   "models/staging/sources.yml.",
            "verification": "`dbt build --select stg_customers+` passes, including the relationships test on "
                            "fct_orders.customer_id. dim_customers has $n_customers rows and "
                            "`select typeof(customer_id) from dim_customers limit 1` returns INTEGER.",
            "notes": "Prevention: a model contract with data types on stg_customers would make a key type change "
                     "fail in staging, where the cause is.",
        },
    ),
    # ------------------------------------------------------------ null rate anomaly
    Scenario(
        id="NR01", category="null_rate_anomaly",
        title="Provider re-sync loaded gift-card payments with null amounts",
        root_cause_type="data",
        root_cause="A gift-card settlement re-sync by the payment provider reloaded the last 30 days of gift-card "
                   "payments with an empty amount; stg_payments passes the nulls through.",
        apply=nr01,
        expected_failures=["test.not_null_stg_payments_amount"],
        fix_targets={"files": [], "models": ["stg_payments"],
                     "columns": ["raw_payments.amount", "stg_payments.amount"],
                     "upstream": ["payment provider gift-card re-sync"]},
        key_entities=["raw_payments", "gift_card", "amount", "stg_payments"],
        changes=[(0, "vendor", "Payment provider notice: gift-card settlement re-sync for the last 30 days runs "
                               "today ($d0), early morning UTC.")],
        noise=(1, 3),
        incidents=["INC-0402 ($d30): voucher amounts doubled after a provider file resend. Resolution: provider "
                   "sent a corrected file; payments re-ingested."],
        run_history=["not_null_stg_payments_amount, last 7 daily runs: pass ×6, fail today ($d0) with "
                     "$n_null rows.",
                     "Gift-card payments per day: 0–2 (normal)."],
        gold={
            "root_cause": "All $n_null null amounts in raw.raw_payments are payment_method = 'gift_card' rows from "
                          "the last 30 days, and all share the same loaded_at ($reload_at). The provider's "
                          "gift-card re-sync reloaded them without the amount value. stg_payments passes amount "
                          "straight through, so not_null_stg_payments_amount fails and the marts are skipped. dbt "
                          "is working as intended; the data is wrong at the source.",
            "fix": "Confirm the pattern: `select payment_method, loaded_at, count(*) from raw.raw_payments where "
                   "amount is null group by 1, 2`. Ask the payment provider to resend the re-sync with amounts, "
                   "then re-run ingestion and `dbt build`. Do not coalesce the nulls to 0: that would understate "
                   "gift-card revenue on the finance dashboard. If the marts must refresh before the provider "
                   "fixes it, temporarily set the not_null test on stg_payments.amount to `severity: warn` and "
                   "tell Finance that gift-card revenue for the last 30 days is incomplete.",
            "verification": "After re-ingestion, `select count(*) from raw.raw_payments where amount is null` "
                            "returns 0, `dbt build --select stg_payments+` passes, and fct_orders.gift_card_amount "
                            "for the last 30 days is back to its earlier level.",
            "notes": "",
        },
    ),
    Scenario(
        id="NR02", category="null_rate_anomaly",
        title="Refactor removed coalesce on fct_orders.amount",
        root_cause_type="code",
        root_cause="A refactor commit removed coalesce(..., 0) from fct_orders.amount, so orders without payments "
                   "(cancelled orders) now have a NULL amount.",
        apply=nr02,
        expected_failures=["test.not_null_fct_orders_amount"],
        fix_targets={"files": ["models/marts/fct_orders.sql"], "models": ["fct_orders"],
                     "columns": ["fct_orders.amount"]},
        key_entities=["fct_orders", "amount", "coalesce"],
        changes=[(1, "commit", "refactor(fct_orders): simplify amount column (models/marts/fct_orders.sql)")],
        noise=(0, 4),
        incidents=["INC-0365 ($d55): fct_orders.amount was null for orders awaiting payment. Resolution: added "
                   "coalesce(..., 0) to the amount column in fct_orders (PR #41)."],
        run_history=["not_null_fct_orders_amount, last 7 daily runs: pass ×6, fail today ($d0) with "
                     "$n_null rows."],
        gold={
            "root_cause": "Yesterday's refactor commit changed `coalesce(order_payments.total_amount, 0) as amount` "
                          "to `order_payments.total_amount as amount` in models/marts/fct_orders.sql. Orders with "
                          "no payments (the $n_null cancelled orders) get NULL from the left join, so "
                          "not_null_fct_orders_amount fails. This undoes the fix from INC-0365.",
            "fix": "Restore the coalesce in models/marts/fct_orders.sql: "
                   "`coalesce(order_payments.total_amount, 0) as amount`. The source data is correct and needs no "
                   "change.",
            "verification": "`dbt build --select fct_orders` passes. `select count(*) from fct_orders where amount "
                            "is null` returns 0, and `select count(*) from fct_orders where amount = 0` returns "
                            "$n_null.",
            "notes": "Prevention: a unit test, or a code-review check for nullable aggregates after left joins.",
        },
    ),
    Scenario(
        id="NR03", category="null_rate_anomaly",
        title="CRM privacy mode blanks emails for DE and NL customers",
        root_cause_type="data",
        root_cause="A new 'EU privacy mode' in the CRM export blanks the email of German and Dutch customers, "
                   "pushing the stg_customers.email null rate above the 5% threshold.",
        apply=nr03,
        expected_failures=["test.null_rate_below_stg_customers_email__0_05"],
        fix_targets={"files": ["models/staging/schema.yml"], "models": ["stg_customers"],
                     "columns": ["stg_customers.email", "raw_customers.email"],
                     "upstream": ["CRM export privacy mode"]},
        key_entities=["stg_customers", "email", "DE", "NL"],
        changes=[(2, "ticket", "PRIV-31: CRM admin enabled 'EU privacy mode' on the customer export integration.")],
        noise=(2, 6),
        incidents=["INC-0377 ($d48): email null rate reached 3.1% after bulk sign-ups without email. "
                   "Resolution: null-rate threshold for stg_customers.email set to 5%."],
        run_history=["Email null rate in stg_customers, last 7 daily runs: 0.0%, 0.0%, 0.5%, 0.0%, 0.0%, 0.0%, "
                     "$null_pct today ($d0)."],
        gold={
            "root_cause": "All $n_null null emails ($null_pct of $n_customers customers) belong to customers "
                          "with country_code DE or NL. That matches the 'EU privacy mode' enabled on the CRM "
                          "export two days ago (PRIV-31): the export now blanks email for these customers. This is "
                          "a deliberate upstream change, not a dbt bug, so null_rate_below on stg_customers.email "
                          "(max 5%) now fails.",
            "fix": "Confirm the pattern: `select country_code, count(*) filter (where email is null) as "
                   "null_emails, count(*) from stg_customers group by 1`. Check with the CRM admin and the "
                   "data-protection owner that suppressing these emails is intended. If it is, scope the test in "
                   "models/staging/schema.yml to the unaffected countries: add "
                   "`config: {where: \"country_code not in ('DE', 'NL')\"}` to the null_rate_below test, and "
                   "document in the email column description that DE/NL emails are suppressed. Tell the marketing "
                   "dashboard owners. If it is not intended, ask the CRM admin to switch privacy mode off and "
                   "re-run the export. Do not backfill emails from another system.",
            "verification": "`dbt build --select stg_customers+` passes, the scoped null rate is at most 5%, and "
                            "every remaining null email belongs to a DE or NL customer.",
            "notes": "",
        },
    ),
    # ------------------------------------------------------------ row count anomaly
    Scenario(
        id="RC01", category="row_count_anomaly",
        title="Orders loader appended a full extract instead of replacing it",
        root_cause_type="data",
        root_cause="After a loader upgrade changed the write mode, the orders connector appended the latest full "
                   "extract to raw_orders instead of replacing it, so every order appears twice.",
        apply=rc01,
        expected_failures=[ROWS_STG, "test.unique_stg_orders_order_id"],
        fix_targets={"files": ["models/staging/stg_orders.sql"], "models": ["stg_orders"],
                     "columns": ["raw_orders.order_id"], "upstream": ["orders loader write mode"]},
        key_entities=["raw_orders", "order_id", "stg_orders", "loaded_at"],
        changes=[(0, "deploy", "Ingestion: orders connector upgraded to loader v2.4 (new default write settings).")],
        noise=(1, 5),
        incidents=["INC-0333 ($d90): duplicate payments after a loader retry. Resolution: duplicates deleted in "
                   "raw_payments; retry logic fixed."],
        run_history=["stg_orders row count, last 7 daily runs: $hist_orders, $n_rows today ($d0)."],
        gold={
            "root_cause": "raw.raw_orders has $n_rows rows but only $n_distinct distinct order_id values: every "
                          "order appears twice, and all the second copies share the latest loaded_at "
                          "($latest_load). The orders loader, upgraded to v2.4 today, appended a full extract "
                          "instead of replacing the table. That fails both row_count_between (max 1,000) and "
                          "unique on stg_orders.order_id.",
            "fix": "Set the orders connector back to replace mode, or merge on order_id, and reload raw_orders "
                   "once (full refresh). Also make staging tolerate future duplicate loads: in "
                   "models/staging/stg_orders.sql add "
                   "`qualify row_number() over (partition by order_id order by loaded_at desc) = 1` to the final "
                   "select.",
            "verification": "`select count(*), count(distinct order_id) from raw.raw_orders` returns two equal "
                            "numbers (about $n_distinct). `dbt build --select stg_orders+` passes, and fct_orders "
                            "revenue is not doubled.",
            "notes": "",
        },
    ),
    Scenario(
        id="RC02", category="row_count_anomaly",
        title="Orders extract limited to a 60-day lookback on a full-replace load",
        root_cause_type="data",
        root_cause="An ingestion config change set the orders extract lookback to 60 days while the load still "
                   "replaces the whole table, so raw_orders now holds only the last 60 days of orders.",
        apply=rc02,
        expected_failures=[ROWS_STG, REL_PAY],
        fix_targets={"files": [], "models": ["stg_orders"], "columns": ["raw_orders.order_date"],
                     "upstream": ["orders extract lookback_days (PR #88)"]},
        key_entities=["raw_orders", "stg_orders", "lookback"],
        changes=[(0, "commit", "ingestion-config repo: set orders extract `lookback_days: 60` to speed up hourly "
                               "loads (PR #88)")],
        noise=(0, 3),
        incidents=["INC-0320 ($d95): payments extract missed one hour after a connector restart. Resolution: "
                   "hour re-extracted."],
        run_history=["stg_orders row count, last 7 daily runs: $hist_orders, $n_kept today ($d0).",
                     "raw_payments row count: stable ($n_payments today)."],
        gold={
            "root_cause": "raw.raw_orders now holds only $n_kept orders, all with order_date on or after $since. "
                          "That is exactly a 60-day window, set this morning by PR #88 (`lookback_days: 60`). The "
                          "orders load replaces the table, so all older orders disappeared. stg_orders falls "
                          "below the 500-row minimum. Payments still cover the full history, so "
                          "$n_orphan_payments payments now reference missing orders and the relationships test on "
                          "stg_payments.order_id fails too.",
            "fix": "Revert PR #88, or switch the orders load to incremental merge on order_id so a short lookback "
                   "no longer deletes history. Then run a one-off full-history extract to restore raw_orders and "
                   "re-run `dbt build`. Do not lower the row-count threshold or remove the relationships test: "
                   "both caught a real data loss.",
            "verification": "`select count(*), min(order_date) from raw.raw_orders` returns about $n_before rows, "
                            "starting about 180 days ago. `dbt build --select stg_orders+` passes, including the "
                            "relationships test on stg_payments.order_id.",
            "notes": "",
        },
    ),
    Scenario(
        id="RC03", category="row_count_anomaly",
        title="fct_orders joins payments without aggregating (fan-out)",
        root_cause_type="code",
        root_cause="A performance refactor removed the order_payments aggregation in fct_orders and joined "
                   "stg_payments directly, so orders with split payments appear once per payment.",
        apply=rc03,
        expected_failures=["test.equal_row_count_fct_orders_ref_stg_orders_", "test.unique_fct_orders_order_id"],
        fix_targets={"files": ["models/marts/fct_orders.sql"], "models": ["fct_orders"],
                     "columns": ["fct_orders.order_id"]},
        key_entities=["fct_orders", "stg_payments", "order_payments"],
        changes=[(1, "commit", "perf(fct_orders): remove order_payments CTE and join payments directly "
                               "(models/marts/fct_orders.sql)")],
        noise=(2, 4),
        incidents=["INC-0309 ($d100): dim_customers lifetime_value doubled after a join change. Resolution: "
                   "payments aggregated per order before joining."],
        run_history=["fct_orders vs stg_orders row count, last 7 daily runs: equal ×6; today ($d0) fct_orders "
                     "has $n_rows rows vs $n_orders in stg_orders."],
        gold={
            "root_cause": "Yesterday's perf commit removed the `order_payments` CTE in models/marts/fct_orders.sql, "
                          "which aggregated stg_payments to one row per order, and left-joined stg_payments "
                          "directly. stg_payments has one row per payment, so the $n_split orders with split "
                          "payments now appear twice. fct_orders has $n_rows rows against $n_orders in "
                          "stg_orders, so equal_row_count and unique on fct_orders.order_id fail. The finance "
                          "dashboard would also show those orders as separate lines.",
            "fix": "Restore the pre-aggregation in models/marts/fct_orders.sql. Add back a CTE "
                   "`order_payments as (select order_id, sum(case when payment_method = 'credit_card' then amount "
                   "else 0 end) as credit_card_amount, ... the same for bank_transfer, voucher and gift_card ..., "
                   "sum(amount) as total_amount from payments group by order_id)`. Then "
                   "`left join order_payments on orders.order_id = order_payments.order_id` and select "
                   "`coalesce(order_payments.<column>, 0)` for each amount column.",
            "verification": "`dbt build --select fct_orders` passes: equal_row_count and unique order_id both "
                            "pass. `select sum(amount) from fct_orders` equals "
                            "`select sum(amount) from stg_payments`.",
            "notes": "",
        },
    ),
    # ------------------------------------------------------------ referential integrity
    Scenario(
        id="RI01", category="referential_integrity",
        title="CRM extract stalled; new customers' orders have no customer record",
        root_cause_type="data",
        root_cause="The CRM customer extract has stalled for more than a day, so customers who signed up since "
                   "then are missing from raw_customers while their orders are present.",
        apply=ri01,
        expected_failures=[REL_FCT, "source.raw.raw_customers"],
        fix_targets={"files": [], "models": [], "columns": ["fct_orders.customer_id", "dim_customers.customer_id"],
                     "upstream": ["CRM customer sync"]},
        key_entities=["raw_customers", "dim_customers", "customer_id", "fct_orders"],
        changes=[(1, "log", "CRM connector: API rate-limit errors (HTTP 429) on the customer sync since "
                            "$crm_last_load; retries exhausted.")],
        noise=(1, 4),
        incidents=["INC-0391 ($d35): orphan customer_ids in fct_orders during a CRM outage. Resolution: resolved "
                   "once the CRM sync caught up; no code change."],
        run_history=["relationships test on fct_orders.customer_id, last 7 daily runs: pass ×6, fail today "
                     "($d0) with $n_orphan_orders rows.",
                     "raw_customers freshness age at run time on previous days: 3–30 h (rows arrive as customers "
                     "sign up); about $age_raw_customers h today."],
        gold={
            "root_cause": "raw.raw_customers has not received new rows since $crm_last_load, about $age_raw_customers h "
                          "ago, because the CRM connector is failing on rate limits. raw_customers freshness is "
                          "already at warn. Customers who signed up after that (customer_id $missing_ids) are "
                          "missing from raw_customers and dim_customers, but their $n_orphan_orders orders loaded "
                          "normally, which breaks the relationships test on fct_orders.customer_id. The data is "
                          "late, not wrong.",
            "fix": "Fix the CRM sync: resolve the 429 rate-limit errors, for example by lowering the sync frequency "
                   "or batch size, or asking the vendor for more quota. Re-run the customer extract, then "
                   "`dbt build`. Do not delete the orphan orders or drop the relationships test. Prevention: make "
                   "raw_customers freshness error after 24 h (currently 48 h) so a stalled extract fails before "
                   "orphans appear. If late-arriving customers are normal, add "
                   "`config: {where: \"order_date < current_date - 1\"}` to the relationships test.",
            "verification": "`dbt source freshness --select source:raw.raw_customers` passes, and this orphan "
                            "check returns 0 rows: `select f.customer_id from fct_orders f left join dim_customers "
                            "d on f.customer_id = d.customer_id where d.customer_id is null`.",
            "notes": "",
        },
    ),
    Scenario(
        id="RI02", category="referential_integrity",
        title="dim_customers filtered to launch markets, orphaning other orders",
        root_cause_type="code",
        root_cause="A change to dim_customers keeps only ZA, GB and US customers, so fct_orders rows for DE, NL and "
                   "AU customers no longer have a matching customer.",
        apply=ri02,
        expected_failures=[REL_FCT],
        fix_targets={"files": ["models/marts/dim_customers.sql"], "models": ["dim_customers"],
                     "columns": ["dim_customers.customer_id", "dim_customers.country_code"]},
        key_entities=["dim_customers", "country_code", "fct_orders"],
        changes=[(1, "commit", "dim_customers: only include launch markets (ZA, GB, US) for the marketing "
                               "dashboard, MKT-12 (models/marts/dim_customers.sql)")],
        noise=(0, 1),
        incidents=["INC-0344 ($d80): marketing dashboard showed test accounts. Resolution: test accounts flagged "
                   "in the CRM and filtered in the dashboard."],
        run_history=["dim_customers row count, last 7 daily runs: $hist_customers, $n_dim_rows today ($d0)."],
        gold={
            "root_cause": "Yesterday's MKT-12 commit added `where customers.country_code in ('ZA', 'GB', 'US')` to "
                          "models/marts/dim_customers.sql. That removes $n_excluded DE, NL and AU customers from "
                          "the dimension, but fct_orders still has their $n_orphan_orders orders, so the "
                          "relationships test on fct_orders.customer_id fails. The finance revenue dashboard also "
                          "reads dim_customers and would lose those customers.",
            "fix": "Remove the where filter from models/marts/dim_customers.sql so the dimension again holds every "
                   "customer. Meet the marketing need without changing the grain: add a column "
                   "`customers.country_code in ('ZA', 'GB', 'US') as is_launch_market` and filter on it in the "
                   "marketing dashboard, or build a separate model for the marketing view.",
            "verification": "`dbt build --select dim_customers+` passes. dim_customers has $n_customers rows and "
                            "the relationships test from fct_orders passes.",
            "notes": "",
        },
    ),
    Scenario(
        id="RI03", category="referential_integrity",
        title="Customer erasure not propagated to payments",
        root_cause_type="data",
        root_cause="An erasure request deleted a customer and their orders from the CRM and shop data, but the "
                   "payment data was not purged, leaving payments that reference deleted orders.",
        apply=ri03,
        expected_failures=[REL_PAY],
        fix_targets={"files": ["models/staging/stg_payments.sql"], "models": ["stg_payments"],
                     "columns": ["stg_payments.order_id", "raw_payments.order_id"],
                     "upstream": ["erasure request DPR-1093 not applied to payments"]},
        key_entities=["stg_payments", "raw_payments", "order_id"],
        changes=[(1, "ticket", "DPR-1093: customer erasure request executed in the CRM and the shop database.")],
        noise=(3, 5),
        incidents=["INC-0371 ($d50): payments arrived before their orders for 1 hour after a shop outage. "
                   "Resolution: resolved on the next hourly load."],
        run_history=["relationships test on stg_payments.order_id, last 7 daily runs: pass ×6, fail today "
                     "($d0) with $n_orphan_payments rows."],
        gold={
            "root_cause": "The $n_orphan_payments payments that fail the relationships test on stg_payments.order_id "
                          "all belong to orders $erased_orders. Those orders, and customer $erased_customer, were "
                          "deleted from the shop and CRM data under erasure request DPR-1093. The payment data was "
                          "not included in the erasure, so raw.raw_payments still holds those payments. This is "
                          "not late-arriving data: the orders will never arrive.",
            "fix": "Complete the erasure: ask the data-protection owner and the payment provider to delete or "
                   "anonymise those payments, as the retention policy allows. Meanwhile, keep the orphan payments "
                   "out of the models explicitly: add a seed `erased_orders` (order_id) and exclude its order_ids "
                   "in models/staging/stg_payments.sql "
                   "(`where order_id not in (select order_id from {{ ref('erased_orders') }})`), so the exclusion "
                   "is auditable. Don't relax the relationships test.",
            "verification": "`dbt build --select stg_payments+` passes. `select count(*) from stg_payments where "
                            "order_id in ($erased_orders)` returns 0.",
            "notes": "",
        },
    ),
    # ------------------------------------------------------------ freshness violation
    Scenario(
        id="FV01", category="freshness_violation",
        title="Shop database connector failing since a credential rotation",
        root_cause_type="data",
        root_cause="The shop database connector has been failing since a credential rotation, so neither raw_orders "
                   "nor raw_payments has received new rows since then.",
        apply=fv01,
        expected_failures=["source.raw.raw_orders", "source.raw.raw_payments"],
        fix_targets={"files": [], "models": [], "columns": [],
                     "upstream": ["shop database connector credentials (SEC-58)"]},
        key_entities=["raw_orders", "raw_payments", "connector"],
        changes=[(1, "ticket", "SEC-58: rotated the database credentials of the shop read replica.")],
        noise=(2, 3),
        incidents=["INC-0359 ($d60): orders stale for 14 h while the connector was paused for maintenance. "
                   "Resolution: connector resumed; missing hours backfilled automatically."],
        run_history=["raw_orders and raw_payments freshness age at run time, last 7 daily runs: 0.5–1.5 h; today "
                     "($d0) about $age_raw_orders h."],
        gold={
            "root_cause": "raw_orders and raw_payments both stopped receiving rows at $last_load, about "
                          "$age_raw_orders h ago, and both come through the shop database connector. raw_customers "
                          "comes from the CRM and is still fresh. The timing matches the SEC-58 credential "
                          "rotation on the shop replica: the connector is still using the old credentials. The dbt "
                          "models and tests are fine; dbt build passes on stale data.",
            "fix": "Update the shop connector with the new SEC-58 credentials and re-run the sync. Its incremental "
                   "extract should backfill the missing hours. Then re-run `dbt build` and "
                   "`dbt source freshness`. Prevention: add credential rotation to the connector's runbook and "
                   "alert on connector failures, not only on freshness.",
            "verification": "`dbt source freshness` passes for raw_orders and raw_payments, and "
                            "`select max(loaded_at) from raw.raw_orders` is within the last hour. Orders placed "
                            "after $last_load, during the outage, are present.",
            "notes": "",
        },
    ),
    Scenario(
        id="FV02", category="freshness_violation",
        title="Orders loader stamps loaded_at with a stuck watermark",
        root_cause_type="data",
        root_cause="Since a loader upgrade the orders loader stamps loaded_at with its extraction watermark, which is "
                   "stuck, instead of the load time; new orders keep arriving but look stale.",
        apply=fv02,
        expected_failures=["source.raw.raw_orders"],
        fix_targets={"files": [], "models": [], "columns": ["raw_orders.loaded_at"],
                     "upstream": ["orders loader v2.3 loaded_at stamping"]},
        key_entities=["raw_orders", "loaded_at", "loader"],
        changes=[(2, "deploy", "Ingestion: orders loader upgraded to v2.3 (watermark-based incremental extraction).")],
        noise=(0, 6),
        incidents=["INC-0359 ($d60): orders stale for 14 h while the connector was paused for maintenance. "
                   "Resolution: connector resumed; missing hours backfilled automatically."],
        run_history=["raw_orders freshness age at run time, last 7 daily runs: 0.5–1.5 h on previous days; about "
                     "$age_raw_orders h today ($d0).",
                     "New rows in raw_orders: normal volume, including $n_orders_recent rows in the last 30 h."],
        gold={
            "root_cause": "raw_orders is not really stale. Orders placed in the last 30 h are present "
                          "($n_orders_recent rows, latest order_date $latest_order_date), but every one of them has "
                          "the same loaded_at, $stuck, which for some is earlier than when the order was placed. "
                          "The orders loader upgraded to v2.3 two days ago stamps loaded_at with its extraction "
                          "watermark, which is stuck, instead of the load time. The freshness check reads "
                          "loaded_at, so it reports the source as about $age_raw_orders h stale.",
            "fix": "Ask the ingestion team to fix or roll back loader v2.3 so loaded_at records the actual load "
                   "time and the watermark advances. Then reload the affected rows so their loaded_at is correct. "
                   "Do not raise the freshness threshold to make the error go away: a real outage would then go "
                   "unnoticed.",
            "verification": "`select loaded_at, count(*) from raw.raw_orders group by 1 order by 1 desc limit 5` "
                            "shows separate hourly load times again, and "
                            "`dbt source freshness --select source:raw.raw_orders` passes.",
            "notes": "",
        },
    ),
    Scenario(
        id="FV03", category="freshness_violation",
        title="raw_customers freshness threshold tightened below its load pattern",
        root_cause_type="config",
        root_cause="A config change tightened raw_customers freshness to error after 2 hours, but raw_customers only "
                   "gets new rows when customers sign up, so a healthy source fails freshness.",
        apply=fv03,
        expected_failures=["source.raw.raw_customers"],
        fix_targets={"files": ["models/staging/sources.yml"], "models": [],
                     "columns": ["raw_customers.loaded_at"]},
        key_entities=["raw_customers", "sources.yml", "error_after"],
        changes=[(1, "commit", "sources.yml: align raw_customers freshness with orders/payments since all loaders "
                               "run hourly, DATA-140 (models/staging/sources.yml)")],
        noise=(1, 5),
        incidents=["INC-0318 ($d97): CRM sync paused for 2 days during a vendor upgrade; raw_customers freshness "
                   "errored at 48 h. Resolution: sync resumed."],
        run_history=["raw_customers freshness age at run time, last 7 daily runs: 3 h, 19 h, 7 h, 30 h, 11 h, 5 h; "
                     "about $age_raw_customers h today ($d0).",
                     "Customer sign-ups per day: 0–2."],
        gold={
            "root_cause": "Yesterday's DATA-140 commit changed raw_customers freshness in models/staging/sources.yml "
                          "from warn 24 h / error 48 h to warn 1 h / error 2 h. Freshness is measured on "
                          "max(loaded_at), and raw_customers only gets a row when a customer signs up, at most a "
                          "couple a day. So max(loaded_at) is usually hours old even when the loader is healthy "
                          "(now about $age_raw_customers h). The CRM loader is working: the source is quiet, not "
                          "stale.",
            "fix": "Revert the raw_customers freshness override in models/staging/sources.yml to "
                   "`warn_after: {count: 24, period: hour}` and `error_after: {count: 48, period: hour}`. If "
                   "hourly monitoring of the CRM loader is needed, check the loader's own run log or heartbeat "
                   "instead of row timestamps.",
            "verification": "`dbt source freshness --select source:raw.raw_customers` passes, and its age falls "
                            "within the historical range of 3–30 h.",
            "notes": "",
        },
    ),
]

assert len(SCENARIOS) == 15 and len({s.id for s in SCENARIOS}) == 15
assert Counter(s.category for s in SCENARIOS) == {c: 3 for c in CATEGORIES}


# ---------------------------------------------------------------- pilot (calibration only)
# Not one of the 15 study scenarios and not in any category: its outputs are the
# calibration samples the evaluators score together (D9), excluded from results.
def pl01(proj, as_of):
    rows = load(proj, "raw_customers")
    merged_at = as_of - timedelta(hours=3, minutes=10)
    picks = [rows[i] for i in (16, 57, 120)]
    dupes = [{**r, "email": r["email"].replace("@example.com", ".merged@example.com"),
              "loaded_at": merged_at.strftime(TS_FMT)} for r in picks]
    save(proj, "raw_customers", rows + dupes)
    return {"n_dupes": len(dupes), "dupe_ids": ", ".join(r["customer_id"] for r in picks),
            "merge_load": utc(merged_at), "n_rows": len(rows) + len(dupes)}


PILOT_SCENARIOS: list[Scenario] = [
    Scenario(
        id="PL01", category="pilot",
        title="CRM account-merge job re-inserts merged customers as new rows",
        root_cause_type="data",
        root_cause="A new CRM account-merge job writes each merged account as a new row with the same "
                   "customer_id instead of updating the existing row, so raw_customers holds duplicate ids.",
        apply=pl01,
        expected_failures=["test.unique_stg_customers_customer_id"],   # dim_customers is then skipped
        fix_targets={"files": ["models/staging/stg_customers.sql"], "models": ["stg_customers", "dim_customers"],
                     "columns": ["raw_customers.customer_id", "stg_customers.customer_id"],
                     "upstream": ["CRM account-merge job"]},
        key_entities=["raw_customers", "customer_id", "stg_customers", "dim_customers", "loaded_at"],
        changes=[(1, "deploy", "CRM: nightly account-merge job enabled (merges duplicate sign-ups into one account).")],
        noise=(0, 4),
        incidents=["INC-0341 ($d75): duplicate customers after a CRM re-sync. Resolution: duplicate rows "
                   "deleted from raw_customers by hand."],
        run_history=["stg_customers row count, last 7 daily runs: $hist_customers, $n_rows today ($d0)."],
        gold={
            "root_cause": "raw.raw_customers has $n_dupes customer_ids that appear twice ($dupe_ids): the "
                          "original row and a second row with a different email, loaded at $merge_load. The CRM "
                          "account-merge job enabled yesterday writes the merged account as a new row with the "
                          "same customer_id instead of updating the existing one. stg_customers passes both rows "
                          "through, so unique fails on stg_customers.customer_id and dim_customers and its tests are "
                          "skipped.",
            "fix": "Ask the CRM team to make the merge job update the existing account (upsert on customer_id) "
                   "and remove the extra rows. Until then, keep one row per customer in "
                   "models/staging/stg_customers.sql: add `qualify row_number() over (partition by customer_id "
                   "order by loaded_at desc) = 1`, so the most recently loaded (merged) version wins.",
            "verification": "`select customer_id, count(*) from stg_customers group by 1 having count(*) > 1` "
                            "returns no rows, and `dbt build --select stg_customers+` passes with dim_customers "
                            "back to $n_customers rows.",
            "notes": "",
        },
    ),
]
assert not {s.id for s in PILOT_SCENARIOS} & {s.id for s in SCENARIOS}
