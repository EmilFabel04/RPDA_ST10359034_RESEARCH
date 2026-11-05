"""Automated metrics (Step 7): specificity, hallucinated references, hedging.

Specificity (proposal §7.5, D26): cosine similarity between an answer and its
scenario's gold-standard remediation, both embedded with all-mpnet-base-v2
(revision pinned below). The model reads at most 384 tokens and every cloud
answer is longer, so texts are embedded in chunks of at most 384 tokens and the
chunk vectors averaged, weighted by tokens. The answer's Assumptions section is
left out (the gold standard has none and the rubric does not score it).

Hallucinated references (D27): names that look like project entities (models,
sources, columns, files) but do not exist in the scenario's project
(ground_truth.json "valid_entities"), are not defined by the answer itself (an
alias, CTE, new model or file it proposes) and are not stated as an
assumption. These are candidates; the researcher confirms each one.

Hedging (D28): hedge words in the Root cause section. A wrong diagnosis stated
without any hedge counts as false confidence (RQ4), joined with the human
root-cause scores in Step 8.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import yaml

EMBED_MODEL = "sentence-transformers/all-mpnet-base-v2"
EMBED_REVISION = "e8c3b32edf5434bc2275fc9bab85f82640a19130"   # main branch on 2026-10-26
BANDS = ((0.75, "high"), (0.69, "moderate"))   # D26 option A: 0.69 = 95th pct of pilot wrong-scenario similarity

HEADINGS = ("root cause", "fix", "verification", "assumptions")
FENCE = re.compile(r"```([\w+-]*)[^\n]*\n(.*?)```", re.S)
INLINE_CODE = re.compile(r"`([^`\n]+)`")


# ---------------------------------------------------------------- answer structure
def split_sections(text: str) -> dict[str, str]:
    """{'preamble', 'root cause', 'fix', 'verification', 'assumptions'} -> text (headings removed).
    Same heading rule as the runner's format check; sections that are missing are absent."""
    sections, current = {"preamble": []}, "preamble"
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        norm = line.strip().lstrip("#*0123456789. ").rstrip(":*").strip().lower()
        if not in_code and norm in HEADINGS:
            current = norm
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def without_code(text: str) -> str:
    return FENCE.sub(" ", text)


def words(text: str) -> int:
    """Words outside code blocks (the prompt's 500-word limit does not count code)."""
    return len(without_code(text).split())


def similarity_text(answer: str) -> str:
    """The answer without its Assumptions section."""
    s = split_sections(answer)
    return "\n\n".join(s[k] for k in ("preamble", "root cause", "fix", "verification") if s.get(k))


def gold_text(scenario: dict) -> str:
    g = scenario["gold_standard_remediation"]
    return "\n\n".join(g[k] for k in ("root_cause", "fix", "verification"))


def band(similarity: float) -> str:
    for cut, name in BANDS:
        if similarity >= cut:
            return name
    return "low"


# ---------------------------------------------------------------- embeddings
class Embedder:
    """all-mpnet-base-v2 on CPU (deterministic). Long texts: token-weighted mean of chunk embeddings."""

    def __init__(self):
        from sentence_transformers import SentenceTransformer   # slow import, only when needed
        from transformers.utils import logging
        logging.set_verbosity_error()   # silence "sequence longer than max length": we chunk ourselves
        try:    # the pinned revision from the local cache; download it only the first time
            self.model = SentenceTransformer(EMBED_MODEL, revision=EMBED_REVISION, device="cpu",
                                             local_files_only=True)
        except OSError:
            self.model = SentenceTransformer(EMBED_MODEL, revision=EMBED_REVISION, device="cpu")
        self.limit = self.model.max_seq_length - 2   # room for the start and end tokens

    def n_tokens(self, text: str) -> int:
        return len(self.model.tokenizer(text, add_special_tokens=False)["input_ids"])

    def chunks(self, text: str) -> list[str]:
        """Split at blank lines, then lines, then words, and pack the pieces into chunks <= limit tokens."""
        pieces = []
        for para in re.split(r"\n\s*\n", text.strip()):
            if self.n_tokens(para) <= self.limit:
                pieces.append(para)
                continue
            for line in para.splitlines():
                if self.n_tokens(line) <= self.limit:
                    pieces.append(line)
                    continue
                cur = []
                for w in line.split():
                    if cur and self.n_tokens(" ".join(cur + [w])) > self.limit:
                        pieces.append(" ".join(cur))
                        cur = []
                    cur.append(w)
                pieces.append(" ".join(cur))
        out, cur = [], ""
        for p in pieces:
            joined = f"{cur}\n\n{p}" if cur else p
            if cur and self.n_tokens(joined) > self.limit:
                out.append(cur)
                cur = p
            else:
                cur = joined
        return out + [cur] if cur else out

    def embed(self, texts: list[str]) -> np.ndarray:
        """One unit-length vector per text."""
        owners, parts = [], []
        for i, t in enumerate(texts):
            for c in self.chunks(t):
                owners.append(i)
                parts.append(c)
        vecs = self.model.encode(parts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)
        weights = np.array([self.n_tokens(p) for p in parts], dtype=float)
        out = np.zeros((len(texts), vecs.shape[1]))
        for owner, vec, w in zip(owners, vecs, weights):
            out[owner] += w * vec
        return out / np.linalg.norm(out, axis=1, keepdims=True)


# ---------------------------------------------------------------- hallucinated references
RELATION = re.compile(r"(?<![\w/-])((?:stg|dim|fct|int|raw)_[a-z0-9_]+)\b")
DOTTED = re.compile(r"(?<![\w/.-])([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)+)\b")
PATH = re.compile(r"(?<![\w/.-])((?:models|tests|macros|seeds|snapshots|analyses)/[\w./-]+?\.(?:sql|yml|yaml|csv))\b")
FILE_NAME = re.compile(r"(?<![\w.-])([\w-]+)\.(?:sql|yml|yaml)\b")
REF = re.compile(r"ref\(\s*['\"]([^'\"]+)['\"]\s*\)")
SOURCE = re.compile(r"source\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)")
ALIAS = re.compile(r"\bas\s+\"?([a-z_][a-z0-9_]*)")
CTE = re.compile(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(")
CREATED = re.compile(r"\b(?:create|alter)\s+(?:or\s+replace\s+)?(?:temp(?:orary)?\s+)?(?:table|view)\s+"
                     r"(?:if\s+not\s+exists\s+)?([\w.\"]+)")
ADDED = re.compile(r"\b(?:add\s+column|rename\s+(?:column\s+)?\w+\s+to)\s+\"?([a-z_][a-z0-9_]*)")
FILE_EXT = {"sql", "yml", "yaml", "csv", "md", "json", "py", "txt", "log"}
INFO_SCHEMA = {"column_name", "data_type", "table_name", "table_schema", "table_catalog", "is_nullable",
               "ordinal_position", "column_default", "character_maximum_length", "rowid"}
IDENT = re.compile(r"[a-z_][a-z0-9_]{2,}")
# Words in `inline code` that are dbt vocabulary, not project entities. Together with DuckDB's own
# function and keyword names (sql_vocabulary) these are skipped by the prose check.
DBT_WORDS = {
    # node configs and properties
    "materialized", "unique_key", "incremental_strategy", "on_schema_change", "full_refresh", "pre_hook",
    "post_hook", "enabled", "tags", "meta", "schema", "database", "alias", "persist_docs", "contract",
    "enforced", "constraints", "data_type", "columns", "tests", "data_tests", "description", "docs", "quoting",
    "identifier", "loader", "loaded_at_field", "freshness", "warn_after", "error_after", "count", "period",
    "filter", "severity", "warn_if", "error_if", "store_failures", "where", "limit", "fail_calc", "config",
    "sources", "models", "seeds", "snapshots", "exposures", "macros", "version", "versions", "access",
    "owner", "maturity", "depends_on", "sql_header", "grants", "column_types",
    # Jinja context
    "ref", "source", "var", "env_var", "this", "target", "is_incremental", "run_query", "adapter", "log",
    "exceptions", "execute", "graph", "model", "modules",
    # tests and their arguments
    "unique", "not_null", "accepted_values", "relationships", "column_name", "values", "field", "quote",
    "arguments", "compare_model", "max_rate", "min_value", "max_value",
    # commands, selectors, artefacts
    "select", "exclude", "selector", "state", "defer", "threads", "vars", "fail_fast", "resource_type",
    "run_results", "manifest", "catalog",
    # schemas and database of this project; run results and severities
    "raw", "main", "ecommerce", "pass", "warn", "error", "fail", "skip", "skipped", "success",
    # DuckDB functions that are parsed specially and so are missing from duckdb_functions()
    "ifnull", "nullif", "try_cast",
    # packages: suggesting one is a recommendation, not a reference to a project entity
    "dbt_utils", "dbt_expectations", "elementary", "audit_helper",
}


@dataclass(frozen=True)
class Ref:
    entity: str      # as shown in the review file, e.g. "fct_orders.order_status", "ref('x')"
    name: str        # the bare name that must appear in Assumptions to count as assumed
    kind: str        # relation | ref | source | column | sql_column | yaml_column | file | name
    pos: int         # first position in the answer (for the context snippet)


def known_entities(valid: dict, manifest_nodes: dict | None = None, context_text: str = "") -> dict:
    """Lookup sets from ground_truth.json["valid_entities"], plus the names the project's own code
    defines (CTEs and aliases in the model SQL, generic-test arguments) from manifest_nodes.json,
    plus every name in the scenario's context material (parts 1-4: error messages, commit ids, ...)."""
    rel_cols: dict[str, set[str]] = {}
    for key, cols in valid["columns"].items():          # "main.dim_customers" / "raw.raw_orders"
        rel_cols.setdefault(key.split(".")[-1], set()).update(c.lower() for c in cols)
    for name, cols in valid["documented_columns"].items():
        rel_cols.setdefault(name, set()).update(c.lower() for c in cols)
    code_names: set[str] = set()
    for node in (manifest_nodes or {}).get("nodes", {}).values():
        code = (node.get("raw_code") or "").lower()
        code_names |= set(ALIAS.findall(code)) | set(CTE.findall(code))
        code_names |= {k.lower() for k in (node.get("test_metadata") or {}).get("kwargs", {})}
    return {
        "models": set(valid["models"]),
        "sources": set(valid["sources"]),                  # "raw.raw_orders"
        "relations": set(valid["models"]) | {s.split(".")[-1] for s in valid["sources"]}
                     | set(valid["exposures"]),
        "rel_cols": rel_cols,
        "all_cols": set().union(*rel_cols.values()),
        "code_names": code_names,
        "context_names": set(IDENT.findall(context_text.lower())),
        "tests": set(valid["tests"]),
        "files": set(valid["files"]),
        "basenames": {f.rsplit("/", 1)[-1] for f in valid["files"]},
    }


@lru_cache(maxsize=1)
def sql_vocabulary() -> frozenset[str]:
    """DuckDB's function and keyword names (the warehouse this project runs on)."""
    import duckdb
    rows = duckdb.sql("select function_name from duckdb_functions() "
                      "union select keyword_name from duckdb_keywords()").fetchall()
    return frozenset(r[0].lower() for r in rows)


def code_text(text: str) -> str:
    """Everything the answer writes as code: fenced blocks and inline `code`."""
    return "\n".join([b for _, b in FENCE.findall(text)] + INLINE_CODE.findall(text))


def defined_names(text: str, known: dict) -> set[str]:
    """Names the answer introduces itself: aliases, CTEs, created tables, added or renamed
    columns, and new files (the stem of any .sql/.yml name that is not an existing file)."""
    code = code_text(text).lower()
    names = set(ALIAS.findall(code)) | set(CTE.findall(code)) | set(ADDED.findall(code))
    names |= {c.replace('"', "").split(".")[-1] for c in CREATED.findall(code)}
    for m in FILE_NAME.finditer(text.lower()):
        if f"{m.group(1)}.{m.group(0).rsplit('.', 1)[-1]}" not in known["basenames"]:
            names.add(m.group(1))
    return names


def _dejinja(sql: str) -> str:
    sql = re.sub(r"\{\{\s*ref\(\s*['\"](\w+)['\"]\s*\)\s*\}\}", r"\1", sql)
    sql = re.sub(r"\{\{\s*source\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)\s*\}\}", r"\1.\2", sql)
    sql = re.sub(r"\{\{\s*this\s*\}\}", "this", sql)
    sql = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", " ", sql, flags=re.S)
    sql = re.sub(r"\{%.*?%\}", " ", sql, flags=re.S)
    sql = re.sub(r"\{\{.*?\}\}", "NULL", sql, flags=re.S)
    sql = re.sub(r"\{#.*?#\}", " ", sql, flags=re.S)
    return "\n".join(ln for ln in sql.splitlines() if not re.match(r"\s*(\$\s*)?dbt\s", ln))


def sql_columns(text: str) -> tuple[list[tuple[str | None, str]], set[str], int, int]:
    """(table or None, column) for every column reference in the answer's SQL blocks, the columns
    the answer declares itself (create table), and counts of statements parsed / not parsed."""
    import sqlglot
    from sqlglot import exp
    found, declared, parsed, failed = [], set(), 0, 0
    for lang, body in FENCE.findall(text):
        lang = lang.lower()
        if not ("sql" in lang or "jinja" in lang or (lang == "" and re.search(r"\bselect\b", body, re.I))):
            continue
        for stmt in re.split(r";\s*(?:\n|$)", _dejinja(body)):
            if not stmt.strip():
                continue
            try:
                trees = [t for t in sqlglot.parse(stmt, read="duckdb") if t is not None]
            except Exception:   # LLM SQL is not always valid; count it and move on
                failed += 1
                continue
            parsed += 1
            for tree in trees:
                declared |= {d.name.lower() for d in tree.find_all(exp.ColumnDef)}
                aliases = {t.alias_or_name.lower(): t.name.lower() for t in tree.find_all(exp.Table)}
                for col in tree.find_all(exp.Column):
                    if col.name and col.name != "*":
                        table = col.table.lower() if col.table else None
                        found.append((aliases.get(table, table) if table else None, col.name.lower()))
    return found, declared, parsed, failed


def yaml_columns(text: str) -> list[tuple[str, str]]:
    """(model or source table, column) declared in the answer's YAML blocks."""
    found = []
    for lang, body in FENCE.findall(text):
        if lang.lower() not in ("yml", "yaml"):
            continue
        try:
            doc = yaml.safe_load(_dejinja(body))
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        nodes = list(doc.get("models") or [])
        for src in doc.get("sources") or []:
            if isinstance(src, dict):
                nodes += list(src.get("tables") or [])
        for node in nodes:
            if isinstance(node, dict) and isinstance(node.get("columns"), list):
                for col in node["columns"]:
                    if isinstance(col, dict) and col.get("name"):
                        found.append((str(node.get("name", "")).lower(), str(col["name"]).lower()))
    return found


def find_refs(text: str, known: dict) -> tuple[list[Ref], list[Ref], dict]:
    """(all entity references checked, the ones that do not exist and are not defined by the
    answer, parse counts). Each entity is listed once per answer."""
    low = text.lower()
    cols, declared, parsed, failed = sql_columns(text)
    defined = defined_names(text, known) | declared          # introduced by the answer itself
    loose = defined | known["code_names"] | known["context_names"]

    checked: dict[str, tuple[Ref, bool]] = {}

    def add(entity, name, kind, pos, ok, qualified=False):
        """qualified: a column of a named relation, or a ref()/source() target, which must exist exactly;
        a name the project's code or the scenario context uses elsewhere does not count there
        (created_at exists in stg_customers, not in fct_orders; raw_orders is a source, not a model)."""
        if entity not in checked:
            checked[entity] = (Ref(entity, name, kind, pos), ok or name in (defined if qualified else loose))

    for m in REF.finditer(low):
        add(f"ref('{m.group(1)}')", m.group(1), "ref", m.start(), m.group(1) in known["models"], qualified=True)
    for m in SOURCE.finditer(low):
        name = f"{m.group(1)}.{m.group(2)}"
        add(f"source('{m.group(1)}', '{m.group(2)}')", m.group(2), "source", m.start(),
            name in known["sources"], qualified=True)
    for m in RELATION.finditer(low):
        name = m.group(1)
        ok = (name in known["relations"] or name in known["all_cols"]
              or any(name in t for t in known["tests"]))   # part of a test name
        add(name, name, "relation", m.start(), ok)
    for m in DOTTED.finditer(low):
        parts = m.group(1).split(".")
        for rel, col in zip(parts, parts[1:]):
            if rel in known["rel_cols"] and col not in FILE_EXT and col not in known["relations"]:
                add(f"{rel}.{col}", col, "column", m.start(), col in known["rel_cols"][rel], qualified=True)
    for table, col in cols:
        if col in INFO_SCHEMA:
            continue
        if table in known["rel_cols"]:
            add(f"{table}.{col}", col, "sql_column", low.find(col), col in known["rel_cols"][table], qualified=True)
        else:
            add(col, col, "sql_column", low.find(col), col in known["all_cols"] or col in known["relations"])
    for rel, col in yaml_columns(text):
        if rel in known["rel_cols"]:
            add(f"{rel}.{col}", col, "yaml_column", low.find(col), col in known["rel_cols"][rel], qualified=True)
    for m in PATH.finditer(low):
        path = m.group(1)
        if "..." in path or path in known["files"]:
            add(path, path, "file", m.start(), True)
        else:   # only a misplaced existing file counts; any other new path is a file the answer proposes
            add(path, path, "file", m.start(), path.rsplit("/", 1)[-1] not in known["basenames"])
    vocab = sql_vocabulary() | DBT_WORDS
    for m in INLINE_CODE.finditer(FENCE.sub(lambda f: " " * len(f.group(0)), low)):   # `names` in prose
        tok = m.group(1).strip()
        if IDENT.fullmatch(tok) and tok not in vocab:
            ok = tok in known["all_cols"] or tok in known["relations"] or any(tok in t for t in known["tests"])
            add(tok, tok, "name", m.start(), ok)

    refs = [r for r, _ in checked.values()]
    unknown = [r for r, ok in checked.values() if not ok]
    return refs, unknown, {"sql_parsed": parsed, "sql_failed": failed}


def mentions(text: str, name: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(name.lower())}(?![\w])", text.lower()) is not None


def context(text: str, pos: int, width: int = 110) -> str:
    pos = max(pos, 0)
    return " ".join(text[max(0, pos - width): pos + width].split())


# ---------------------------------------------------------------- hedging / confidence
HEDGE = re.compile(
    r"\b(?:most likely|likely|probabl[ey]|possibl[ey]|perhaps|may|might|could|appears?|seems?|"
    r"suggests?|presumably|apparently|unclear|uncertain|unknown|either|not (?:sure|certain|clear|known)|"
    r"(?:cannot|can't|unable to) (?:confirm|tell|verify|determine)|(?:does|did)(?:n't| not) (?:say|show|state)|"
    r"assum(?:e|es|ed|ing)|potentially|suspect(?:ed)?|plausibl[ey]|hypothes[ie]s)\b", re.I)
BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+", re.M)


def hedges(text: str) -> int:
    return len(HEDGE.findall(without_code(text)))


def n_assumptions(section: str) -> int:
    if not section.strip():
        return 0
    return len(BULLET.findall(section)) or 1


def key_entity_recall(text: str, key_entities: list[str]) -> float:
    return sum(mentions(text, e) for e in key_entities) / len(key_entities)
