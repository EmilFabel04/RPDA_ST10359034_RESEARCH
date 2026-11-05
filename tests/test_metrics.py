"""Automated metrics (Step 7): answer sections, bands, hallucination check, hedging, output files."""
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import compute_metrics as cm  # noqa: E402

from core import config  # noqa: E402
from core import metrics as m  # noqa: E402

ANSWER = """### Root cause
The most likely cause: `stg_payments` still selects `amount`, but raw.raw_payments now has `amount_cents`.

### Fix
Update models/sources.yml and models/staging/stg_payments.sql:

```sql
with source as (select * from {{ source('raw', 'raw_payments') }}),
renamed as (
    select payment_id, cast(amount_cents as decimal(18, 2)) / 100 as amount, payment_status
    from source
)
select * from renamed
```

Optionally add a new model models/staging/stg_payments_v2.sql that reads {{ ref('raw_payments') }}.
Check `fct_orders.order_total` and `fct_orders.created_at`, raise `freshness_threshold_hours`,
and never set the test to `warn`.

### Verification
Run `dbt build --select stg_payments+`.

### Assumptions
- The provider also sends `payment_status`.
- Amounts are integer cents.
"""


def sd01_known():
    truth = cm.load_truth("SD01", config.SCENARIOS_DIR)
    return m.known_entities(truth["valid_entities"], truth["manifest_nodes"], truth["context_text"])


def test_sections_and_similarity_text():
    s = m.split_sections(ANSWER)
    assert set(s) == {"preamble", "root cause", "fix", "verification", "assumptions"}
    assert s["root cause"].startswith("The most likely cause")
    assert "integer cents" not in m.similarity_text(ANSWER)        # Assumptions left out
    assert "payment_id" in m.similarity_text(ANSWER)
    # a heading-like line inside a code block is not a heading; bold and colon headings are
    other = "**Root cause:**\nx\n```\nFix\n```\nFix:\ny"
    assert m.split_sections(other) == {"preamble": "", "root cause": "x\n```\nFix\n```", "fix": "y"}


def test_bands():
    assert [m.band(x) for x in (0.9, 0.75, 0.7499, 0.69, 0.6899)] == ["high", "high", "moderate", "moderate", "low"]


def test_hallucination_check_on_sd01():
    refs, unknown, parse = m.find_refs(ANSWER, sd01_known())
    flagged = {r.entity for r in unknown}
    assert flagged == {"models/sources.yml",          # existing file, wrong folder
                       "ref('raw_payments')",          # a source, not a model
                       "fct_orders.order_total",       # no such column
                       "fct_orders.created_at",        # created_at exists, but in stg_customers only
                       "freshness_threshold_hours",    # no such dbt setting
                       "payment_status"}               # not a column (stated in Assumptions, see below)
    checked = {r.entity for r in refs}
    for ok in ("amount_cents", "stg_payments", "models/staging/stg_payments.sql",
               "models/staging/stg_payments_v2.sql"):                    # real, or a new file it proposes
        assert ok in checked and ok not in flagged
    assert "warn" not in checked and "renamed" not in flagged                # dbt word; the answer's own CTE
    assert parse["sql_parsed"] >= 1 and parse["sql_failed"] == 0


def test_assumed_names_are_not_counted_as_hallucinations():
    rec = {"run_id": "SD01-full-gpt-r1", "scenario_id": "SD01", "category": "schema_drift", "level": "full",
           "model_key": "gpt", "rep": 1, "input_tokens": 1, "output_tokens": 1, "stop_reason": "completed",
           "text": ANSWER}
    row, candidates = cm.answer_metrics(rec, cm.load_truth("SD01", config.SCENARIOS_DIR))
    assert row["refs_assumed"] == 1 and "payment_status" not in {c.entity for c in candidates}
    assert row["hallucination_candidates"] == 5 and row["hallucination_auto"] == 1
    assert row["all_headings"] == 1 and row["truncated"] == 0
    assert row["hedges_root_cause"] == 1 and row["root_cause_asserted"] == 0   # "most likely"
    assert row["n_assumptions"] == 2


def test_hedges_and_assumptions():
    assert m.hedges("The most likely cause is X; it may also be Y.") == 2
    assert m.hedges("The column was renamed.\n```sql\nselect 'maybe likely' as x\n```") == 0   # code ignored
    assert m.hedges("Either the load failed or the report doesn't say which.") == 2
    assert m.n_assumptions("- a\n- b\n1. c") == 3
    assert m.n_assumptions("Nothing beyond the given data.") == 1 and m.n_assumptions("  ") == 0


def test_key_entity_recall():
    assert m.key_entity_recall("`stg_payments` reads raw_payments", ["stg_payments", "raw_payments", "amount_cents"]) \
        == pytest.approx(2 / 3)
    assert m.key_entity_recall("stg_payments_v2", ["stg_payments"]) == 0      # whole names only


def test_review_verdicts_are_kept(tmp_path, monkeypatch):
    path = tmp_path / "review.csv"
    monkeypatch.setattr(cm, "REVIEW_PATH", path)
    row = {"item_id": "SD01-01A", "entity": "x", "kind": "name", "section": "fix", "context": "",
           "verdict": "", "reviewer_note": ""}
    cm.write_csv(path, [{**row, "verdict": "h", "reviewer_note": "checked"}], cm.REVIEW_COLUMNS)
    merged = cm.merge_review([dict(row)])
    assert merged[0]["verdict"] == "H" and merged[0]["reviewer_note"] == "checked"
    cm.write_csv(path, [{**row, "verdict": "maybe"}], cm.REVIEW_COLUMNS)
    with pytest.raises(SystemExit):
        cm.merge_review([dict(row)])


@pytest.fixture(scope="module")
def embedder():
    try:
        return m.Embedder()
    except Exception as exc:   # model not downloaded and no network
        pytest.skip(f"embedding model not available: {exc}")


def test_chunks_cover_text_within_limit(embedder):
    text = "\n\n".join(f"Paragraph {i}: " + "the stg_orders model selects order_id " * 30 for i in range(6))
    chunks = embedder.chunks(text)
    assert len(chunks) > 1 and all(embedder.n_tokens(c) <= embedder.limit for c in chunks)
    assert " ".join("\n\n".join(chunks).split()) == " ".join(text.split())     # nothing lost or added


def test_short_text_embedding_matches_model(embedder):
    text = "stg_payments selects amount, which was renamed to amount_cents."
    ours = embedder.embed([text])[0]
    direct = embedder.model.encode([text], normalize_embeddings=True)[0]
    assert float(ours @ direct) == pytest.approx(1.0, abs=1e-6)


@pytest.mark.skipif(not cm.METRICS_PATH.exists(), reason="run compute_metrics.py first")
def test_output_files_are_complete_and_blinded():
    with cm.METRICS_PATH.open(newline="") as f:
        rows = list(csv.DictReader(f))
    key = json.loads(cm.KEY_PATH.read_text())["items"]
    assert len(rows) == 405 == len({r["run_id"] for r in rows})
    assert all(key[r["item_id"]]["run_id"] == r["run_id"] for r in rows)
    assert all(m.band(float(r["specificity"])) == r["specificity_band"] for r in rows)
    with cm.REVIEW_PATH.open(newline="") as f:
        review_text = f.read()
    assert review_text.splitlines()[0].split(",") == cm.REVIEW_COLUMNS
    for leak in ("-minimal-", "-partial-", "-full-", "gpt", "claude", "llama"):
        assert leak not in review_text.lower()
    with cm.RECALL_PATH.open(newline="") as f:
        recall = list(csv.DictReader(f))
    assert len(recall) == 27 and set(recall[0]) == {"item_id", "checked", "missed_entities", "reviewer_note"}
