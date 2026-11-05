"""Deterministic synthetic e-commerce data for the dbt seeds.

    from core.seed_data import write_seeds
    info = write_seeds(seeds_dir)            # as_of = now (UTC, to the hour)
    info = write_seeds(seeds_dir, as_of=dt)  # reproduce an earlier run exactly

Source freshness compares `max(loaded_at)` with the current time, so fixed
timestamps would go stale within a day. Every timestamp is therefore relative
to `as_of`: the same `as_of` + seed gives byte-identical CSVs, and a build run
shortly after generation always passes freshness.

Story the data tells (used later for scenario descriptions):
- raw_customers: CRM accounts, loaded hourly (incremental) after creation.
- raw_orders: shop orders over the last 180 days, loaded hourly at :05.
- raw_payments: 1 payment per non-cancelled order (15% split into 2),
  amount in integer cents, loaded hourly at :05.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import config

N_CUSTOMERS = 200
N_ORDERS = 600
TS_FMT = "%Y-%m-%d %H:%M:%S"

FIRST_NAMES = ["Thabo", "Lerato", "Sipho", "Aisha", "James", "Emma", "Liam", "Olivia",
               "Noah", "Mia", "Pieter", "Anika", "Ravi", "Priya", "Chen", "Mei",
               "Lukas", "Sofia", "Daniel", "Zanele", "Kagiso", "Hannah", "Tariq", "Nina"]
LAST_NAMES = ["Nkosi", "Dlamini", "Smith", "Jones", "Botha", "Patel", "Naidoo", "Schmidt",
              "Brown", "Williams", "Wang", "Khumalo", "Mokoena", "Jansen", "Okafor", "Taylor"]
COUNTRIES = ["ZA"] * 5 + ["GB"] * 2 + ["US"] * 2 + ["DE", "NL", "AU"]
PAYMENT_METHODS = ["credit_card", "bank_transfer", "voucher", "gift_card"]
PAYMENT_WEIGHTS = [55, 20, 15, 10]


def default_as_of() -> datetime:
    """Now in UTC, truncated to the hour, as a naive datetime (dbt treats naive as UTC)."""
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0, tzinfo=None)


def _hourly_load(ts: datetime) -> datetime:
    """The hourly loader runs at :05 and picks up rows created before it."""
    return ts.replace(minute=5, second=0) + timedelta(hours=1)


def _spread(rng: random.Random, start: datetime, end: datetime, n: int) -> list[datetime]:
    """n sorted random timestamps in [start, end], the last one exactly `end`."""
    span = (end - start).total_seconds()
    points = sorted(start + timedelta(seconds=rng.uniform(0, span)) for _ in range(n - 1))
    return [p.replace(microsecond=0) for p in points] + [end]


def build_rows(as_of: datetime, seed: int = config.GLOBAL_SEED) -> dict[str, list[dict]]:
    rng = random.Random(seed)

    # ---- customers: created over the last year, newest 5 hours ago
    created = _spread(rng, as_of - timedelta(days=365), as_of - timedelta(hours=5), N_CUSTOMERS)
    customers = []
    for cid, ts in enumerate(created, start=1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        customers.append({
            "customer_id": cid,
            "first_name": first,
            "last_name": last,
            "email": f"{first}.{last}{cid}@example.com".lower(),
            "country": rng.choice(COUNTRIES),
            "created_at": ts.strftime(TS_FMT),
            "loaded_at": (ts + timedelta(minutes=rng.randint(30, 90))).strftime(TS_FMT),
        })

    # ---- orders: last 180 days, newest 90 minutes ago, placed by existing customers
    placed = _spread(rng, as_of - timedelta(days=180), as_of - timedelta(minutes=90), N_ORDERS)
    orders, order_ts = [], {}
    for oid, ts in enumerate(placed, start=1):
        eligible = sum(1 for c in created if c < ts)  # customers created before this order
        age_days = (as_of - ts).total_seconds() / 86400
        if rng.random() < 0.08:
            status = "cancelled"
        elif age_days < 2:
            status = "placed"
        elif age_days < 5:
            status = "shipped"
        else:
            status = "completed"
        orders.append({
            "order_id": oid,
            "customer_id": rng.randint(1, eligible),
            "order_date": ts.date().isoformat(),
            "status": status,
            "loaded_at": _hourly_load(ts).strftime(TS_FMT),
        })
        order_ts[oid] = ts

    # ---- payments: paid at checkout; cancelled orders have none
    payments = []
    for order in orders:
        if order["status"] == "cancelled":
            continue
        paid_at = order_ts[order["order_id"]] + timedelta(minutes=rng.randint(1, 20))
        if rng.random() < 0.15:  # split payment: voucher/gift card + card
            parts = [(rng.choice(["voucher", "gift_card"]), rng.randint(500, 5000)),
                     ("credit_card", rng.randint(1500, 25000))]
        else:
            parts = [(rng.choices(PAYMENT_METHODS, PAYMENT_WEIGHTS)[0], rng.randint(1500, 25000))]
        for method, cents in parts:
            payments.append({
                "payment_id": len(payments) + 1,
                "order_id": order["order_id"],
                "payment_method": method,
                "amount": cents,
                "loaded_at": _hourly_load(paid_at).strftime(TS_FMT),
            })

    return {"raw_customers": customers, "raw_orders": orders, "raw_payments": payments}


def read_csv(path: Path) -> list[dict]:
    """Rows as dicts of strings (empty string = NULL once loaded by dbt seed)."""
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_seeds(seeds_dir: Path, as_of: datetime | None = None,
                seed: int = config.GLOBAL_SEED) -> dict:
    """Write the three raw_*.csv seeds. Returns as_of and row counts for logging."""
    as_of = as_of or default_as_of()
    seeds_dir.mkdir(parents=True, exist_ok=True)
    tables = build_rows(as_of, seed)
    for name, rows in tables.items():
        write_csv(seeds_dir / f"{name}.csv", rows)
    return {"as_of": as_of.strftime(TS_FMT), "seed": seed,
            "row_counts": {name: len(rows) for name, rows in tables.items()}}
