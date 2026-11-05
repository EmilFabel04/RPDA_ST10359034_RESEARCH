"""The seed generator must be deterministic and produce internally consistent data."""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.seed_data import TS_FMT, build_rows, write_seeds  # noqa: E402

AS_OF = datetime(2026, 10, 13, 12, 0, 0)


def test_same_as_of_gives_identical_csvs(tmp_path):
    write_seeds(tmp_path / "a", as_of=AS_OF)
    write_seeds(tmp_path / "b", as_of=AS_OF)
    for name in ("raw_customers", "raw_orders", "raw_payments"):
        assert (tmp_path / "a" / f"{name}.csv").read_bytes() == (tmp_path / "b" / f"{name}.csv").read_bytes()


def test_referential_integrity_and_loaded_at():
    t = build_rows(AS_OF)
    customer_ids = {c["customer_id"] for c in t["raw_customers"]}
    order_ids = {o["order_id"] for o in t["raw_orders"]}
    assert all(o["customer_id"] in customer_ids for o in t["raw_orders"])
    assert all(p["order_id"] in order_ids for p in t["raw_payments"])
    for table in t.values():
        assert all(datetime.strptime(r["loaded_at"], TS_FMT) <= AS_OF for r in table)


def test_volumes_inside_row_count_test_bounds():
    t = build_rows(AS_OF)
    assert 500 <= len(t["raw_orders"]) <= 1000   # row_count_between on stg_orders / fct_orders
    assert {o["status"] for o in t["raw_orders"]} <= {"placed", "shipped", "completed", "cancelled"}
