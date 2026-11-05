# Methodological decisions log

Every decision that deviates from, or makes concrete, the research proposal
(submitted 12 June 2026). Dated. Use this for the Methodology and
Limitations / Threats to Validity sections of the write-up.

Status: **Confirmed** = agreed by the researcher. **Open** = still to decide.

---

## D1 — Local model: llama3:8b instead of LLaMA 3 70B (2026-10-12, Confirmed)

**Proposal said:** LLaMA 3 70B via Ollama.
**Actual:** `llama3:8b` via Ollama 0.40.3 on a 16 GB MacBook (Apple M5).
**Why:** A 70B model needs ~40 GB RAM even quantised; it cannot run on 16 GB.
**Added 2026-11-01:** the researcher also looked at renting a cloud GPU (RunPod)
for the 70B model: an unbudgeted cost for a self-funded study, and a rented
server is not local, which was the reason for including a local model.
**Implication for write-up:** The local model is much smaller than the cloud
models, so model differences confound _size_ and _provider/training_. Report
as a limitation; the local-vs-cloud comparison is "small open-weight vs
frontier API models", not "open vs closed at equal scale".
**Re-confirmed 2026-10-23, after the SD01 run:** keep llama3:8b. The main
analysis (context effect, two-way ANOVA per model) compares llama only with
itself, which size does not affect. Between-model differences are reported
for these three specific models, not attributed to size, training or provider.
Framing: a laptop-runnable model is the realistic option for teams that cannot
send pipeline metadata to an external API. If llama scores near the floor at
every level, report that descriptively (Kruskal-Wallis, floor effect) rather
than as "no context effect". Rejected alternative: a hosted Llama 3.3 70B
(not local, new provider, contradicts the evaluator pack).
**Context-window consequence:** llama3:8b's maximum context is 8,192 tokens.
`num_ctx` is set to 8192 explicitly on every call (Ollama's default is smaller
and truncates silently). Prompt + 2,048 output tokens must fit in 8,192, so
full-context prompts are capped at ~5,500 tokens (enforced in Step 4).
**Evidence (test_connection.py check 4, re-run 2026-10-13):** a 6,350-token
prompt with a code word on line 61 of a 451-line log. With `num_ctx=2048`
Ollama read only 1,036 tokens (5,314 silently dropped, no error) and the model
could not recall the code word; with `num_ctx=8192` it read all 6,350 and
recalled it. Ollama keeps the first few tokens and the end of an over-long
prompt and drops the **middle** — which is where context parts 2–4 sit — so an
undersized window would silently turn a "full" prompt into a "minimal" one.

## D2 — Model IDs pinned (2026-10-12, Confirmed 2026-10-13)

| Role               | Proposal            | Pinned ID                                        | Version the API reported (2026-10-13)     |
| ------------------ | ------------------- | ------------------------------------------------ | ----------------------------------------- |
| OpenAI GPT-5-class | "GPT-5"             | `gpt-5.5-2026-04-23` (dated snapshot of GPT-5.5) | `gpt-5.5-2026-04-23`                      |
| Anthropic Sonnet   | "Claude 4.6 Sonnet" | `claude-sonnet-5-5` (current Sonnet)             | `claude-sonnet-5-5` ("Claude Sonnet 5.5") |
| Local              | LLaMA 3 70B         | `llama3:8b`                                      | `llama3:8b@365c0bd3c000` (Ollama digest)  |

**Why gpt-5.5 dated snapshot:** OpenAI's current flagship line is GPT-6;
of the GPT-5 family, `gpt-5.5` has an explicit dated snapshot that never
changes, which directly addresses model drift (the proposal's top validity
risk). `gpt-5.6-sol` is newer but has no dated snapshot.
**Why claude-sonnet-5-5:** current Sonnet. Anthropic publishes no dated
suffixes for current models; the ID itself is the pinned version.
**Logged per call:** the model version string each API _returned_, so any
silent change would be visible in `results/raw_outputs.jsonl`.

## D3 — Temperature 1.0 for all models, not 0.7 (2026-10-12, Confirmed 2026-10-13)

**Design said:** a fixed temperature such as 0.7, identical for all models.
**Evidence (test_connection.py check 3, 2026-10-13):**

- `gpt-5.5-2026-04-23` (reasoning off): temperature 0.7 **accepted**.
- `claude-sonnet-5-5`: temperature 0.7 **rejected** — HTTP 400
  "`temperature` is deprecated for this model."
  (request id `req_011Cfz8FhT8idRR5FkLqDeNs`). Temperature 1.0 is accepted.
  **Decision:** temperature = 1.0 for all three models — the only value every
  model accepts — so the "identical temperature" requirement still holds and
  the 3 repetitions vary naturally.
  **Implication:** 1.0 gives more run-to-run variation than 0.7; the median of
  3 repetitions (and reporting the spread) absorbs some of this.

## D4 — Reasoning / thinking set to lowest on both cloud models (2026-10-12, Confirmed 2026-10-13)

**Settings:** OpenAI `reasoning.effort = "none"`; Anthropic
`thinking = {"type": "between_tools"}` (Sonnet 5.5's lowest thinking setting).
**Why:** (a) llama3:8b has no reasoning mode, so this keeps all three models
answering directly; (b) hidden reasoning tokens count against the output
limit, so leaving it on would make "same max output tokens" unequal in
practice; (c) GPT-5-family temperature control requires reasoning off.
**Implication:** results describe the models' _direct-answer_ behaviour, not
their best reasoning-mode performance. Report as a scope limitation.

## D5 — No server-side fallbacks (2026-10-12, Confirmed)

Anthropic offers automatic fallback to another model when a request is
refused. Disabled deliberately: a fallback answer would be attributed to the
wrong model. Refusals are logged via `stop_reason` and handled in analysis.

## D6 — Expert scoring load: 135 outputs per evaluator (2026-10-13, Confirmed)

**Design said:** expert evaluators score the outputs (implicitly all 405).
**Problem:** 405 outputs at ~2 min each is ~13–20 h per evaluator; the pack
promised 4–6 h, which would have misinformed consent.
**Decision:** both experts score the same 135 outputs — one repetition of
every scenario × context level × model — so every design cell is covered and
inter-rater kappa uses all 135. The researcher scores all 405 (provisional),
which feeds the median-of-3 analysis; expert scores validate it.
**Implication:** report clearly which analyses use expert vs researcher scores.

## D7 — Evaluators blind to context level as well as model (2026-10-13, Confirmed)

Evaluators see the same full scenario details for every output, never the
prompt the LLM received, so they cannot tell the context level (the main
independent variable). Step 6 scoring tool must implement this.

## D8 — Actionability anchor example is reserved (2026-10-13, Confirmed)

The evaluator brief's anchor example is an `accepted_values` failure on
`stg_orders.status` (new value 'returned'; accepted list
'placed', 'shipped', 'completed', 'cancelled' in `models/staging/schema.yml`).
Step 2 must build the project to match; Step 3 must NOT use this failure as
one of the 15 scenarios. Replaces the proposal's Appendix A schema-drift
example, which overlapped a planned scenario and named a test dbt would
not generate.

## D9 — Evaluator pack: final terms (2026-10-13, Confirmed)

Final file: `Evaluator_Pack_RPDA8411_final.docx` (sent to the 2 evaluators).
What the evaluators were told, so the write-up matches it:

- Institution Emeris Online; supervisor [name removed] ([email removed]);
  ethics reference CSREC/st10359034/019; concerns go to the IIE's research
  ethics committee (2026-10-14, closes O2).
- Models described as "an OpenAI GPT-5-series model, Anthropic's Claude
  Sonnet and a locally run LLaMA 3 8B model".
- **Calibration:** 5 sample outputs scored jointly on a call; these come from
  a **pilot run and are excluded from the results** (scoring them together
  would inflate agreement).
- **Load:** 135 outputs, ~4–6 h (~2 min each), in batches (see D6).
- **Consistency check:** at the midpoint each evaluator re-scores ~10 earlier
  outputs without seeing their earlier scores (intra-rater reliability).
- **Withdrawal:** scores deleted if withdrawn before **11 December 2026** (end
  of scoring); after that, anonymised scores are kept.
- **Privacy:** name and signature on the consent form; experience reported
  only as ranges for the panel as a whole.
- **Retention:** "kept for as long as the IIE requires, and then securely
  deleted" (matches proposal §8.5).
- **Disagreement:** discussed; if still unresolved, **both scores are kept and
  the disagreement is reported**. There is no third evaluator.
- **Rubric rules added:** definition of "partly right" (0.5); actionability 3
  needs root cause + exact fix location with code + downstream models +
  verification step; references to non-existent models/columns are noted and
  technical accuracy scored as the fix would actually behave; the models'
  assumptions list is not scored separately.
- Evaluators agree not to use AI tools when scoring.

## D10 — Scoring tool is a self-contained HTML page (2026-10-13, Done in Step 6 — see D24)

The pack promises "runs in a browser, nothing to install". A local Streamlit
app breaks that; a hosted one can lose saved files on restart. Step 6 will
produce one HTML file per evaluator that runs offline and exports a CSV they
email back. The researcher uses `score_tool.py`.

## D11 — Repetitions and seeds (2026-10-13, Confirmed)

`GLOBAL_SEED=42` seeds all Python randomness (blinding order, shuffles) and is
sent to Ollama, so llama outputs are reproducible. The OpenAI and Anthropic
APIs take no seed, so cloud outputs cannot be reproduced exactly; this is why
each condition is run 3 times and the median used. Other fixed settings:
max output tokens 2,048 for every model; Ollama `num_ctx` 8,192.

---

## Open items

- **O1 — Timing risk:** experts check scenario realism by 23 October, but the
  LLM runs happen before that. If a scenario is judged unrealistic, its 27
  calls (3 levels × 3 models × 3 reps) must be re-run. Corrections to a
  reference (gold-standard) fix are cheap: the fix is not in the prompt, so
  only the similarity metric changes.
- **O2 — Ethics committee wording:** _Closed 2026-10-14._ The concerns
  paragraph now names "the IIE's research ethics committee" (the committee
  that issued CSREC/st10359034/019). Still no committee contact address; add
  it if the supervisor supplies one.
- **O1 status (2026-10-25):** the LLM runs are complete; the experts' scenario
  check result has not been recorded yet.
- **O1 status (2026-10-29):** no material for the check had been sent. Built
  `scenario_check.html` (15 scenarios as the scoring pages show them + reference
  fix; questions: realistic? Yes/Mostly/No; fix correct? Yes/Partly/No; comments).
  To be sent to both evaluators first; `make_scenario_check.py --summary` lists flags.
- **O1 status (2026-11-01):** Evaluator 2 returned the check. All 15 scenarios
  realistic, so no re-runs. Fixes: 9 Yes, 5 Partly (each suggests an extra
  verification or monitoring step, not a different cause or fix), 1 No (RI03:
  excluding the erased customer's payments would understate finance totals;
  retain them anonymised instead). Reference fixes kept unchanged (they are
  frozen inputs to specificity, and the RI03 fix already says "delete or
  anonymise"); both evaluators are told that a different approach that would
  work, such as keeping RI03's payments anonymised, can score as correct.
  Evaluator 1 skips the check (D35). Report in 3.3.3 and as a limitation.
- **O3 — Anonymised historical cases (proposal §7.2, §8.1):** none collected yet.
  Either add 2–3 cases (anonymisation checklist §8.1; anything not fully
  anonymised goes to llama only, §8.2) or drop them and report the loss of
  external validity as a limitation. _Researcher decided 2026-10-29: add 2–3
  cases._ Waiting for the cases; still to settle: who scores their answers.
  _Closed:_ not included. Reported as a limitation, a
  deviation, and as further research in 5.5.
- **O5 — Specificity bands (D26):** _Closed 2026-10-26:_ option A (0.75 / 0.69).
- **O4 — GitHub (proposal §7.7, §9):** _Closed 2026-10-27:_ private repo
  https://github.com/EmilFabel04/RDPA, `main` pushed with the full history.
  Before making it public for the dataset, remove the supervisor's email
  (D9) and re-check for personal data.

---

## D12 — Seeds are generated, with timestamps relative to the build time (2026-10-13, Step 2)

Source freshness compares `max(loaded_at)` with the current clock, so static
CSVs would fail freshness a day later. `core/seed_data.py` generates the three
seeds from `GLOBAL_SEED`, with every timestamp relative to `as_of` (default:
now, UTC, to the hour). The same `as_of` reproduces byte-identical CSVs
(unit-tested). The CSVs are build artefacts (git-ignored); each scenario in
Step 3 records its `as_of`. Volumes: 200 customers, 600 orders, 636 payments.

## D13 — Ingestion and transformation are separate dbt runs (2026-10-13, Step 2)

`dbt seed --full-refresh` plays the ingestion tool (loads `raw` schema);
`dbt build --exclude resource_type:seed` is the transformation job; then
`dbt source freshness`. Reason: in a real warehouse dbt does not load raw
data, so run_results.json should describe only the models and tests an
engineer would debug. Failures injected into raw data (Step 3) are applied
to the CSVs before the ingestion step.

## D14 — Custom generic tests instead of dbt packages (2026-10-13, Step 2)

The row-count test (`row_count_between`, 500–1,000 rows on stg_orders and
fct_orders) and a null-rate threshold test (`null_rate_below`, max 5% on
stg_customers.email) are small generic tests in `dbt_project/tests/generic/`
rather than dbt_utils / dbt_expectations. No `dbt deps` / network needed, and
the full test SQL is visible in the scenario artefacts.

## D15 — Two additions to the Step 2 project for Step 3 (2026-10-13)

1. fct_orders' row-count test changed from `row_count_between(500, 1000)` to
   `equal_row_count(compare_model=stg_orders)` ("grain must match stg_orders").
   A fan-out join (RC03) adds only ~80 rows, which a 500–1,000 band would not
   catch; equal row counts is also the more realistic check for a fact table.
2. `models/marts/exposures.yml`: the finance revenue dashboard and the marketing
   customer dashboard, so lineage can show the downstream business impact
   (needed for an actionability score of 3).
   Clean build re-checked: 32 nodes pass.

## D16 — How scenarios are built (2026-10-13, Step 3)

- One `as_of` for all 15 scenarios (**2026-10-13 18:00 UTC**), seed 42.
- Each scenario: copy project → baseline run on clean data (so the warehouse
  holds "yesterday's" tables, as in production) → apply ONE fault → seed, build,
  source freshness. The run is checked against the designed failures; all 15
  matched on the first full run.
- The nodes described in context parts 2–3 are derived **only from the observed
  failure** (failing test → its model(s); failing model; stale source), never
  from the known root cause, so context does not leak the answer.
- Parts 1–3 are rendered from real dbt artefacts. Part 4 (historical context)
  is synthetic: the relevant change, two unrelated but true changes, one past
  incident, and a recent-run metric. Ages quoted in part 4 and the gold
  standard are the ages measured by `dbt source freshness`, so they match part 1.
- Automated check: no prompt part contains a category name, the scenario title,
  "root cause", or a sentence from the gold-standard fix.
- Prompt size (parts 1–4, chars/4): 914–2,598 tokens; well under the 5,500 cap.
- **Frozen:** re-running the injector changes timestamps and so the prompts.
  It refuses to overwrite existing scenarios without `--force`.

## D17 — Root-cause types are unbalanced: 11 data, 3 code, 1 config (2026-10-13, Open — report)

Most real data-quality failures start upstream, and the design fixes the
categories, not the cause types. Consequence: for the 3 code faults (NR02,
RC03, RI02) the faulty SQL appears in part 2, so partial context may be enough,
while data faults need lineage/history (parts 3–4). Root-cause type is recorded
in `ground_truth.json`; report results by type descriptively as a possible
moderator, not as a tested factor.

## D18 — Gold standards are researcher-approved (2026-10-13)

Each gold standard (root cause, fix with exact files/SQL, verification,
notes) was confirmed and approved by the researcher against the actual artefacts, with every
number filled from the data. The experts' scenario check (O1) covers them; a
corrected gold standard only changes the similarity metric, not the LLM runs.

## D19 — Prompts show the build command as plain `dbt build` (2026-10-14, Step 4)

The real transformation command is `dbt build --exclude resource_type:seed`
(D13), but showing that to the models would reveal that the raw tables are
dbt seeds, i.e. that the pipeline is simulated, and invite "edit the seed
CSV" answers. In the simulated project the ingestion jobs load `raw` and the
scheduled job is plain `dbt build`, so part 1 now shows that. Done before any
LLM run: the injector renders it this way (`BUILD_AS_SHOWN`) and the one line
was replaced in the 15 frozen `scenario.json` files (nothing else changed;
token estimates recomputed). The real commands stay in `dbt_commands`. A unit
test now fails if "seed" appears in any context part.

## D20 — Prompt design (2026-10-14, Step 4)

- One user message, no system prompt, identical for all three models;
  `build_prompt(scenario, level)` has no model argument (unit-tested).
- Part 1 opens with a fixed 3-sentence intro (shop, dbt-core 1.12 + DuckDB,
  hourly ingestion from web shop / payment provider / CRM into `raw`, run
  date). It is the same for every scenario and gives no hint of the cause.
- Headings are unnumbered, so a minimal prompt does not show that parts 2–4
  exist.
- Part 5 asks for four fixed headings (Root cause / Fix / Verification /
  Assumptions), asks the model to label anything not given as an assumption,
  and allows fixes outside dbt ("say what should change and where"), since
  11 of 15 root causes are upstream (D17). Without that line, models would be
  pushed towards SQL patches over upstream data problems.
- "Keep the answer under 500 words, not counting code": keeps answers well
  inside the 2,048-token limit, so truncation cannot differ between verbose
  and terse models, and keeps the experts' reading load manageable.
- Sizes: 440–710 tokens (minimal), 606–1,963 (partial), 1,226–2,911 (full)
  by chars/4. Exact llama3 count of the largest prompt (RI01 full) is 2,780;
  plus 2,048 output = 4,828 of the 8,192 window.
- `PROMPT_VERSION = "v1"`; Step 5 logs it and a SHA-256 of every prompt.

## D21 — How the 405 calls are run (2026-10-14, Step 5)

- Run IDs `<scenario>-<level>-<model>-r<rep>`; every answer is appended to
  `results/raw_outputs.jsonl` with the prompt version + SHA-256, the model
  version the API reported, tokens, latency, stop reason, cost and settings.
  The prompt itself is not stored; it is rebuilt exactly from the scenario.
- **Order:** all calls shuffled with `GLOBAL_SEED`; each model works through
  its own calls in that order, the three models in parallel. Time of day
  (API load, model updates) is therefore not confounded with scenario or level.
- **llama seeds:** 42, 43, 44 for reps 1–3 (one seed for all reps would make
  llama's three answers identical). Cloud APIs take no seed (D11).
- **Every answer is kept as it came back,** including truncated, empty or
  refused ones; nothing is re-run because it looks bad (that would bias the
  results). Only calls that returned no answer at all (errors after 6 retries
  with backoff) are logged to `results/errors.jsonl` and tried again.
- **Version guard:** the runner refuses to continue if the results file holds
  answers made with a different prompt or pinned model ID.
- The CHECKPOINT 5 run (SD01, 27 calls) is part of the experiment data, not a
  pilot. The calibration outputs promised in the evaluator pack (D9, "from a
  pilot run, excluded from the results") are a separate run, for Step 6.

**Run log (D21).**

- 2026-10-19: SD01, 27/27 answers, $0.40.
- 2026-10-23: remaining run. Claude and llama complete (135/135 each).
  GPT stopped at 73/135 when the OpenAI account ran out of credit (HTTP 429
  `insufficient_quota`, RI01-partial-gpt-r2). Because the call order is
  shuffled, the 62 missing GPT calls are a random subset, not a block of
  scenarios or levels; they are made with the same pinned snapshot once
  credit is added. Fix: "out of credit" is no longer retried.
- 2026-10-25: credit added; the 62 GPT calls ran without errors.
  **Complete: 405/405 answers, no duplicates, no truncation, no empty
  answers, every answer from the pinned version, total cost $6.63.**
- 3 of 135 llama answers omit one of the four requested headings; kept as
  returned (format compliance is reported, not corrected).

## D22 — No LangChain; plain provider SDKs (2026-10-25, deviation from proposal §7.7)

**Proposal said:** LangChain for prompt templating, context injection and
output collection. **Actual:** the official `openai`, `anthropic` and `ollama`
Python SDKs behind one small wrapper (`core/llm_clients.py`); prompts built by
`prompts/builder.py`. **Why:** fewer moving parts and full control over exactly
what is sent (temperature, token limits, context window, no hidden retries or
fallbacks), all of which is logged per call. Nothing in the design needs
LangChain's chains or agents.

## D23 — Pilot phase reduced (2026-10-25, deviation from proposal §7.3, §7.5, §7.6)

**Proposal said:** a pilot of 5–10 scenarios across all levels and models to
check prompts, scoring and infrastructure, give early inter-rater data,
estimate score variance and confirm the specificity bands.
**Actual:**

1. Infrastructure pilot = SD01 (27 calls, 2026-10-19). Nothing changed after
   it, so its answers are kept as experiment data (D21).
2. Calibration pilot = a separate scenario **PL01** (duplicate customers after
   a CRM account merge; not one of the 15, not in any category), run once per
   model and level (9 calls, $0.15, 2026-10-25). 5 of the 9 answers are the
   calibration samples; they are excluded from the results (D9).
3. Specificity bands (0.75 / 0.5) are checked in Step 7 against the PL01
   calibration scores before the main similarity analysis.
   **Not done:** a separate variance / sample-size estimate before the main run.
   Report the reduced pilot as a limitation; the 3 repetitions and the per-cell
   spread are reported instead.

## D24 — Blinding and scoring setup (2026-10-25, Step 6)

- **Item ids:** per scenario, the 9 (level, rep) combinations get random group
  numbers 01–09; within a group the 3 models get random labels A/B/C. Item id
  e.g. `RC02-05A`. Neither part says anything about model or level (tested).
  Key: `results/blinding_key.json` (researcher only).
- **Expert set (D6):** per scenario × level one repetition drawn at random, its
  3 items to both experts: 135 items, the same for both (kappa on all 135).
- **Orders:** each rater has their own seeded order. Experts: 10 repeats of
  earlier items after item 67 (midpoint consistency check, pack: "about 10";
  earlier scores not shown). Researcher: all 405, no repeats.
- **What raters see (D7):** for every item the full scenario (failure report,
  model and source metadata, lineage, recent history), the researcher's
  reference fix, and one suggestion labelled "Model A/B/C". Never the prompt.
- **Expert pages:** `results/scoring/pages/score_expert_{1,2}.html`, one offline
  file each, no install, autosave in the browser, CSV export (and re-import
  to resume elsewhere). Rubric text copied from the final evaluator pack.
  Tested in Chrome: scoring, blocking incomplete items, reload, repeats
  banner, CSV quoting; exports pass `import_scores.py`.
- **Calibration page:** `calibration.html`, the 5 PL01 samples; the rater picks
  who is scoring; scores saved to `results/pilot/`, never to the results.
- **Researcher:** `scripts/score_tool.py` (terminal), writes
  `results/scores_researcher_provisional.csv`, status PROVISIONAL on every row.
- **Import:** `scripts/import_scores.py` accepts an expert export only if every
  row has the right rater, status EXPERT and the item at that position.

## D25 — MOCK scores until the real ratings exist (2026-10-25, Step 6)

To build Steps 7–8 before the experts finish, `scripts/make_mock_scores.py`
writes random scores to `results/mock/scores_<rater>.MOCK.csv` (status MOCK,
notes MOCK). Rules:

- Mock values never depend on model or context level, so they cannot show an
  effect; raters agree with a shared random value ~75% of the time.
- Mock files live only in `results/mock/`; real files are
  `results/scores_<rater>.csv`. `import_scores.py` refuses any row whose status
  is not EXPERT, so a mock file cannot become a real one.
- The analysis uses real files; with `--mock` it uses these and labels every
  table and figure "MOCK DATA". Nothing built from mock data goes in the report.

## D26 — Specificity: how similarity is computed, and the band check (2026-10-26, Step 7; bands Confirmed: option A)

**Proposal (§7.5):** all-mpnet-base-v2 embeddings, cosine similarity to the
gold standard; bands ≥ 0.75 high, 0.5–0.75 moderate, < 0.5 low, "to be
confirmed during the pilot phase".
**How it is computed:**

- Model `sentence-transformers/all-mpnet-base-v2`, revision
  `e8c3b32edf5434bc2275fc9bab85f82640a19130` (main branch, 2026-10-26), on CPU
  (deterministic). sentence-transformers 6.1.0, torch 2.14.1.
- **Chunking.** The model reads at most 384 tokens and silently ignores the
  rest. Every GPT and Claude answer is longer (median ~1,000 tokens) and 76% of
  llama answers are, so unchunked scores would compare only the first third of
  a cloud answer but most of a llama answer, which would bias the model
  comparison. Texts are split at paragraph, then line, then word boundaries
  into chunks of ≤ 382 tokens; the chunk vectors are averaged, weighted by
  token count (approximately the model's own mean pooling over the whole
  text). 328 of 405 answers needed more than one chunk; the gold standards
  (192–338 tokens) fit in one.
- **What is compared.** The answer without its Assumptions section, against
  the gold standard's root cause + fix + verification (not its "notes"). The
  gold has no assumptions and the rubric does not score them (D9).
- The continuous similarity is the specificity variable in the analysis
  (ANOVA); the bands are descriptive only.
  **Band check, rule set before computing (D23):** using only the 9 pilot (PL01)
  answers, compare their similarity to their own gold standard with their
  similarity to the 15 study gold standards (wrong scenario). The bands are
  confirmed if no wrong-scenario similarity reaches 0.75 and the median
  wrong-scenario similarity is below 0.5.
  **Result:** own gold median 0.810 (0.734–0.880); wrong gold median 0.517
  (0.308–0.748), 59% at or above 0.5. **Not confirmed:** 0.75 works as the
  "high" cut (nothing about a different incident reached it), but 0.5 does not
  separate anything. A typical answer about a _different_ incident scores
  "moderate". In the main run no answer is below 0.5.
  **Validity checks (main run):** specificity correlates with the share of the
  scenario's key entities an answer names (Spearman ρ = 0.64) and not with
  answer length (|ρ| ≤ 0.15 within each model); for 78% of answers the closest
  of the 15 gold standards is their own.
  **Options considered:** (A) keep 0.75 and move the lower cut to the pilot's
  wrong-scenario level; (B) keep the proposal's bands and report that the low
  band is empty; (C) drop the bands and report the continuous score and
  `own_gold_rank` only.
  **Decision (researcher, 2026-10-26): option A.** Bands: high ≥ 0.75,
  moderate ≥ 0.69, low < 0.69. 0.69 is the 95th percentile of the pilot's
  wrong-scenario similarities (0.692, rounded to two decimals), so "low" means
  "no more similar to the reference fix than a typical answer about a different
  incident". The cut comes from pilot data only, as the proposal required.
  Main run: high 264, moderate 89, low 52 (of which llama 40). The bands are
  descriptive; the ANOVA uses the continuous similarity.

## D27 — Hallucination check (2026-10-26, Step 7)

**Proposal:** hallucination rate per failure type and context level (§7.5,
§8.3); method not specified. Rubric (D9): references to non-existent models or
columns are noted.
**Definition:** a hallucination is a model, source, column, file, dbt setting
or SQL function that the answer _states as existing_ but that does not exist
in the scenario's project, in dbt, or in DuckDB.
**Automated candidates** (`core/metrics.py`), checked against each scenario's
`ground_truth.json` (models, sources, columns as in the warehouse and as
documented, tests, files):

- `ref()` / `source()` targets; names that look like models (`stg_`, `dim_`,
  `fct_`, `int_`, `raw_`); `relation.column` references; columns in the
  answer's SQL (parsed with sqlglot, DuckDB dialect; 92 of 914 statements
  could not be parsed and are skipped); columns in its YAML; file paths that
  put an existing file in the wrong folder; and identifiers in `inline code`.
- Not candidates: names the answer defines itself (aliases, CTEs, created
  tables or columns, new files it proposes); names the project's own SQL
  defines (e.g. the `total_amount` CTE column in fct*orders), generic-test
  arguments and any name in the scenario's context parts 1–4 (error messages,
  commit ids); DuckDB function and keyword names (from DuckDB 1.5.6 itself)
  and a fixed list of dbt words (`core/metrics.py: DBT_WORDS`).
  A column of a \_named* relation must exist on that relation (created_at
  exists in stg_customers, so `fct_orders.created_at` is still a candidate).
- A candidate that also appears in the answer's Assumptions section is
  counted as **assumed**, not as a candidate (the prompt asked models to label
  what is not given as an assumption).
  **Review:** the researcher gives every candidate a verdict in
  `results/hallucination_review.csv` (blinded item ids only): H hallucination,
  C conditional (hedged guess or example), N new (proposed by the answer),
  F false positive. Only H counts. Precision of the automated check = H /
  candidates. **Recall** is estimated from 27 answers (3 per model × level,
  seeded) read in full (`hallucination_recall_sample.csv`).
  **Development note:** the rules were refined after inspecting the candidate
  list (all refinements are generic, e.g. "names in the context exist"; none
  targets a model or scenario); the review and recall sample are the check.
  **First run:** 62 candidates in 46 of 405 answers (before review).
  **Report both** the share of answers with ≥ 1 hallucination and hallucinations
  per checked reference (`refs_checked`): llama names far fewer entities
  (median 4 per answer vs 10–13), so it has fewer chances to name a wrong one.
  **AI-assisted review (researcher's decision, 2026-10-29):** to save time, an AI
  assistant (Claude, the coding assistant used for this project) pre-classified the
  62 candidates and pre-read the 27 recall answers, working from blinded item ids,
  the answer text and the scenario's real names (`ground_truth.json`, `dbt --help`,
  DuckDB's function list). The suggestions with reasons are in
  `results/hallucination_suggestions.csv` (15 H, 23 C, 17 N, 7 F) and
  `results/hallucination_recall_suggestions.csv` (5 suggested misses in 5 answers).
  The researcher confirms or changes every one with `scripts/confirm_suggestions.py`;
  only confirmed answers enter the analysis, and each row's note records "accepted"
  or "changed to …", so the agreement between suggestion and researcher can be
  reported. Report as AI-assisted, researcher-confirmed. Note that the suggestions
  come from a model of the same family as one of the three models studied; the
  blinded ids hide which model wrote each answer.

## D28 — Hedging and false confidence (RQ4) (2026-10-26, Step 7)

**Proposal:** "false-confidence risk" (RQ4, §8.3); no measure specified.
**Measure:** hedge words in the Root cause section (code ignored) from a fixed
lexicon (`core/metrics.py: HEDGE`: likely, probably, may, might, could,
appears, suggests, either, unclear, "cannot confirm", "doesn't say", assume, …).
`root_cause_asserted` = the root cause is stated with no hedge at all.
Also recorded: hedges per 100 words outside the Assumptions section, and the
number of listed assumptions.
**False confidence (Step 8):** an answer whose root cause is wrong (human score 0) and asserted. Reported as the share of wrong diagnoses that are asserted,
per model and level, and as hedging when right vs. when wrong (a
well-calibrated model hedges more when it is wrong).
**Limitation:** a lexicon misses hedging without these words and counts some
non-hedging uses ("you may run…"); restricting it to the Root cause section
limits the second. Report as a proxy, not as a validated confidence measure.

## D29 — Analysis as implemented (2026-10-26, Step 8)

**Proposal (§7.3, §7.5, §8.3):** median of the 3 runs; two-way ANOVA for the
main effects and interaction of the two independent variables on the four
DVs; Tukey HSD between context levels for each failure type; the three models
analysed separately; Cohen's kappa; hallucination rate per failure type and
context level; misdiagnosis rate.
**Unit of analysis:** one value per model × scenario × level, the median of
the 3 repetitions, so 45 values per model and DV (3 per level × category
cell). Human DVs come from the researcher's scores of all 405 answers (D6);
specificity from Step 7. `scripts/analyse.py`, `core/analysis.py`.
**ANOVA:** per model and DV, `y ~ level * category`, Type II sums of squares
(the design is balanced, so Types I–III agree), partial η². Model is not a
factor (analysed separately, as proposed). **Added:** Holm correction across
the 4 DVs within each model and effect, because the four DVs test the same
hypothesis; raw p is reported next to it.
**Assumptions:** Shapiro-Wilk on residuals, Brown-Forsythe Levene over the 15
cells. Expected to fail for the human DVs: root cause is 0/1 and the median of
3 keeps technical accuracy and actionability on 3-point scales. Hence:
**Rank-based checks (added):** Kruskal-Wallis by level and by category (the
non-parametric version of the main effects; also the floor-effect check
promised in D1), and **Friedman by level with scenario as block**. The same
15 scenarios appear at all three levels, so the 45 values are repeated
measures, which the proposal's two-way ANOVA ignores. Report the level effect
as robust only where ANOVA and Friedman agree, and say so where they don't.
**Tukey HSD:** between levels on all 45 values (15 per level), and within each
category as the proposal asks (3 per level: very low power, read as
descriptive).
**RQ3:** category means per model, the ANOVA's category effect, and Kendall's
W: whether the three models rank the five categories in the same order.
**RQ4:** per answer, all 405 (not medians):

- misdiagnosis = root cause scored 0;
- false confidence = misdiagnosed and asserted (D28), reported as a rate, as a
  share of misdiagnoses, and against the asserted share of correct diagnoses;
- hallucinations: the automated candidate rate, and the confirmed rate
  (verdict H, filled only when every candidate in the group is reviewed), both
  per answer and per 100 checked references (D27); precision and recall of
  the check;
- context window: prompt and answer sizes; llama uses at most 59% of its
  8,192 tokens (largest prompt + 2,048 output); no answer truncated.
  **Agreement:** Cohen's kappa over the full scale (as proposed),
  quadratic-weighted kappa for the 3-point scales, and % agreement, for:
- expert vs expert (135 items);
- each expert vs their own 10 midpoint repeats (too few for a stable kappa);
- researcher vs each expert (validates the provisional scores).
  There is no third evaluator (D9); the expert analyses use the mean of the two
  experts, so disagreements are kept.
  **Expert replication:** the same ANOVA on the 135 expert-scored answers (one
  repetition per cell).
  **Also reported:** root-cause type × level, descriptive only (D17); the spread
  of the 3 repetitions (temperature 1.0, D3).
  **Power:** 3 values per cell, residual df 30, no pilot variance estimate
  (D23). Small interaction effects cannot be detected; report effect sizes and
  confidence intervals, not only p.
  **First results (specificity only, the one automated DV; 2026-10-26):**
- Specificity rises with context for all three models:
  - gpt F(2,30) = 11.77, p < .001, partial η² = .44;
  - claude F(2,30) = 6.26, p = .005, partial η² = .29;
  - llama F(2,30) = 4.64, p = .018, partial η² = .24.
- Friedman agrees for all three (p ≤ .002).
- **Where the gain is (Tukey):**
  - gpt: partial → full (p < .001); minimal → partial is not significant.
  - claude and llama: only minimal → full is significant.
- No level × category interaction for any model.
- A category effect only for llama (F(4,30) = 3.28, p = .024).
- The models do not clearly rank the categories alike (W = .56, p = .155).

## D30 — Expert scoring cut to 90 answers each, grouped by scenario (2026-10-29, Confirmed)

**Why:** the report is due 4 November 2026; the planned scoring window was
16 November – 11 December, and the researcher does not score the 405
answers. The experts' scores are therefore the human-scored data.
**What changed (from D6, D24):**

- The 135 expert-set answers (one repetition per scenario × level × model)
  are split. Per scenario the 3 models are put in a random order; at each
  level one model's answer is scored by **both** experts (45 shared, for
  agreement) and each expert gets one of the other two **alone** (45 each).
  Each expert scores **90** (was 135 + 10 repeats). Every one of the 135 has
  an expert score. In each part every model appears once per scenario and
  each level 15 times (unit-tested).
- **Grouped by scenario:** each expert reads a scenario once and scores its 6
  answers in a row (was fully shuffled). Scenario order and order within a
  scenario are shuffled per expert (seeded). The page shows "answer k of 6".
- **No midpoint repeats** (proposal §7.6 drift check dropped): scoring now
  takes days, not weeks.
- Estimated time per expert: about 3 hours (was 4–6).
  **Analysis:** human-scored DVs use the expert cells (mean of both experts on
  shared answers, one expert otherwise; disagreements kept, D9); agreement on
  the 45 shared answers; misdiagnosis and false confidence on the 135 expert
  answers. Specificity keeps the median of 3. Blinding key and researcher order
  unchanged; pages and mock files regenerated.
  **Report as:** a deviation (one scored repetition per cell for the human
  DVs; agreement on 45 answers; no drift check).

## D31 — Calibration by email, not on a call (2026-10-29, Confirmed)

**Proposal (§7.5) / evaluator pack (D9):** the evaluators score the same 5
sample outputs together on a call and discuss differences.
**Actual:** each evaluator scores the 5 practice answers in `calibration.html`
on their own and emails the CSV (`calibration_expert_N.csv`). The researcher
imports them (`import_scores.py expert_N <file> --calibration`), compares the
two, and emails both a short note on where they differed and how to score
such cases. Only then are the scoring files sent.
**Why:** submission on 4 November; no time to schedule a joint call.
**Report as:** a deviation; the calibration had no live discussion.

## D32 — Files exchanged by WhatsApp, not email (2026-10-29, Confirmed)

**Planned (D31, evaluator pack):** the evaluator pack, practice page, scenario
check and scoring pages are emailed, and the evaluators email their files back.
**Actual:** the evaluators' work email filters blocked the researcher's emails,
so all files go both ways over WhatsApp (end-to-end encrypted). Returned files
are saved to `results/scoring/` as before; nothing else changes.
**Why:** the emails did not arrive, and there is no time to get the senders
allowed before 4 November.
**Report as:** a note in the data storage paragraph (Section 3.9).

## D33 — Evaluator dbt experience (2026-10-30, Open until Evaluator 2's form)

**Proposal (§5, §10.5):** two independent, practising data engineers. No
minimum dbt experience was set.
**Actual:** Evaluator 2 reports 3 years as a data engineer and no professional
dbt experience (SQL transformations, data quality checks and pipeline
troubleshooting in other tools). This meets the proposal's criterion.
**Report as:** experience as ranges for the panel only, as the consent form
promises (3.6.1), and a limitation that dbt-specific details of a fix may be
judged less reliably by an evaluator without dbt experience. The reference
fix shown next to every answer reduces this.

## D34 — One evaluator is a family member of the researcher (2026-10-30, Confirmed)

**Proposal (§5):** "a panel of two independent data engineers".
**Actual:** Evaluator 2 is a family member of the researcher.
**Safeguards:** blinding to model and context level (D7, D24);
independent scoring; agreement on the 45 shared answers; and a new check of
whether either expert scores systematically higher on the shared answers
(`a.mean_difference`, Wilcoxon signed-rank; `rater_difference.csv`).
**Report as:** disclosed in 3.6.1, a limitation in 3.10, a row in the
deviations table (3.11), and the generosity check in 4.2.3. The report says
"one evaluator", never which, so scores stay unlinked to a name (consent form).

## D35 — Compressed final schedule (2026-11-01, Confirmed)

**Situation:** Evaluator 2 returned the consent form, scenario check and
practice scores on 29–31 October. Evaluator 1 has returned nothing (due 31
October). Submission is on 4 November.
**Changes:**

- _Labels._ The person first listed as Evaluator 1 chose "Evaluator 2" on the
  pages, so the labels were swapped to match the returned files (D33 and D34 now
  refer to Evaluator 2). Evaluator 1 had not started.
- _Calibration (D31)._ There is no second practice file to compare against, so
  both evaluators get the same two written rubric clarifications before scoring:
  (1) root cause = 1 only if the answer says _why_ the failure happened (PL01:
  the CRM merge job), not only _where_ (duplicates in raw_customers), following
  the rubric's "underlying cause"; (2) the reference fix is a guide, and a
  different approach that would work can score as correct. Point (1) comes from
  Evaluator 2's practice scores (root cause = 1 on PL01-01A and -01C, whose
  notes say the answer did not explain why). Practice scores of both are still
  compared and reported afterwards.
- _Scenario check and practice round._ Evaluator 1 skips both (limited time):
  one evaluator's check covers O1, and the two written rubric clarifications
  replace the practice round. Calibration is therefore reported as written
  guidance, with practice scores from Evaluator 2 only.
- _Time estimate._ Evaluator 2's practice timestamps show 1–4 minutes per
  answer (mean 2.5 for the four timed answers), longer with long notes. The 90
  answers are the same length as the practice ones (median about 475 words vs
  437; about 39,000 words per evaluator), so 90 answers take about 3.5–4 hours,
  not 1.5 as told on 29 October; both evaluators are told the corrected figure,
  and notes are optional except when unsure or when a name is made up.
- _Considered and rejected:_ showing evaluators an AI-written summary of each
  answer to save time. It would break consent item 9 (no AI tools in scoring),
  make the experts score the summary instead of the answer, and add an LLM
  judge to a study of LLM output (Section 2.7).
  **Fallback:** if Evaluator 1 cannot score by 3 November, the analysis runs on
  Evaluator 2's 90 answers alone, without an agreement measure, and the report
  says so.

## D36 — Use expert scores as far as they go (2026-11-01, Confirmed)

**Problem:** the analysis used expert scores only when both files had all 90
answers, so the D35 fallback (Evaluator 2 alone) and a half-finished file
would both have given no expert results at all.
**Change:** an expert's partly scored file is used for the answers it covers
(the page exports only fully scored answers); expert results are computed from
whichever experts returned scores, and every table and figure label states how
many of the 135 answers were scored and how many by both. When a model has no
score in some level × category cell, the interaction cannot be estimated and
the ANOVA fits the main effects only (noted per test). Friedman needs scenarios
scored at all three levels; with one evaluator there are none, so Kruskal–Wallis
remains the rank check. Agreement and the generosity check (D34) use the
answers both scored, whatever their number.
**Why not shorten the scoring instead:** the time is reading about 39,000 words
of answers per evaluator. Fewer shared answers weakens the agreement and D34
checks; fewer scenarios loses a third of the expert data and leaves two
scenarios per category. Asking evaluators to work in page order and send
whatever is finished keeps every completed scenario group usable.
**Report as:** if a file is incomplete, state the coverage in 3.6.1 and 4.1
and as a limitation; name any test that could not be run.

## D37 — Historical cases not included (2026-11-01)

**Situation:** the proposal planned a cross-check on anonymised historical cases
(§7.2, §8.1), and on 29 October the researcher decided to add 2–3 of them (O3).
None had been collected.
**Decision:** the cases are not included, because they could not be collected,
anonymised and scored in the time available. This closes O3.
**Effect:** external validity rests on the designed scenarios alone.
**Report as:** a limitation, a deviation from the proposal, and further research.

## D38 — Evaluator 2's scores in; expert results drafted from them (2026-11-02, Provisional)

Evaluator 2's export (90 of 90 suggestions, scored 1 November) passed
`import_scores.py` and is `results/scores_expert_2.csv`. `analyse.py` ran with
it alone (the D36 path): 30 suggestions per model, 8 to 12 per model and level;
GPT has one empty level × category cell, so its expert ANOVAs fit main effects
only; Friedman cannot run (no scenario has one evaluator's score at all three
levels for a model). The report's expert placeholders are filled from these
results in `src/` only (tracked insertions), marked provisional in 4.1 and
4.2.2. **Holm:** the researcher does not score the 405 (D30), so specificity is
the only dimension in the median-of-3 analysis and Holm applies in the expert
replication, where it covers the three expert dimensions plus specificity of
the same 135 suggestions. **Main result so far:** root cause correctness rises
sharply at the full level for GPT (0/20 below full, 8/10 at full) and Claude
(4/18, 10/12); llama shows no level effect on any expert dimension. **Next:**
when Evaluator 1's file arrives, import, rerun, update every number in 4.1,
4.2.2–4.5.6, 5.2 and the abstract, add 4.2.3 and the Friedman results, and
remove the provisional notes.

## D39 — All corrections accepted; hallucination review complete (2026-11-02, Confirmed)

The researcher accepted every tracked correction, so `report/src_user/` was set
equal to `report/src/` and the report rebuilt without tracked changes. The
draft AI-use statement now says the corrections were accepted (not "reviewed
one by one"). The hallucination review is complete: 62/62 verdicts (1 changed
from the suggestion: NR01-03C `amount_cents`, C to H), 16 confirmed
hallucinations (llama 14, GPT 1, Claude 1); recall sample 27/27 read, 5 missed
against 4 found (recall 44%); precision 16/62 = 26%.

## D40 — New Evaluator 1 (2026-11-02, Confirmed: consent signed 2 November 2026)

**Situation:** the person recruited as Evaluator 1 had not signed the consent
form or returned any scores. The researcher is asking another practising data
engineer to take the Evaluator 1 place instead.
**What stays the same:** the same evaluator pack (information sheet and
consent form), the same `score_expert_1.html` (the same 90 answers, 45 shared
with Evaluator 2), the same two written scoring clarifications, no scenario
check and no practice round (D35), and no AI tools. No data from the first
person exists, so there is nothing to delete. The design is unchanged, so the
ethics clearance (CSREC/st10359034/019) still covers it.
**What the new evaluator is told up front** (the pack is out of date): 90
answers, not 135; about 3.5–4 hours; no call and no midpoint check; return by
3 November. Their years of data engineering experience and dbt use are asked
for, for the panel range in 3.6.1.
**Only the new evaluator's file is imported as expert_1.** The first person is
told they no longer need to score, so no second Evaluator 1 file arrives.
**Report as (once they agree):** 3.3.3, 3.6.1 and 3.11 give "joined shortly
before submission" as the reason for the skipped scenario check and practice
round, instead of workload, and 3.6.1 drops the date on which the
clarifications were sent. The same changes go into the methodology task
document.
**Update (2026-11-02):** the new Evaluator 1 signed and dated the consent form
on 2 November 2026 and reported 4 years as a data engineer and no dbt
experience. The panel is therefore 3–4 years of data engineering experience,
and neither evaluator has used dbt professionally. The returned PDF (exported
from Google Docs) does not show the tick boxes; the signature covers the form.
Report changed as planned above (3.3.3, 3.6.1, 3.11), plus: the experience
range in 3.6.1, a new limitation "Evaluators without dbt experience" in 3.10
(as D33 planned), "full-time in demanding roles" replaced with "scored in their
own time, alongside their jobs", and the reason for using WhatsApp (both
evaluators' email filters) dropped, as it may not apply to the new evaluator.
**Update (2026-11-03):** the new Evaluator 1 sent a photo of the signed paper
form showing every consent box ticked. The photo stays with the signed form,
outside the repository.

## D41 — Evaluator 1's scores imported; final expert analysis (2026-11-03, Confirmed)

**What arrived:** Evaluator 1's export (90 of 90 assigned answers, scored on
2 November 2026, median about 2.4 minutes per answer, no notes). It passed
`import_scores.py` (right rater, right items in the right positions, valid
scores) and was saved as `results/scores_expert_1.csv`. `analyse.py` was rerun
on both files; the Evaluator 2-only outputs were replaced.
**Agreement (45 shared answers):** root cause κ = .51 (moderate), technical
accuracy κ = .27 (fair), actionability κ = .10 (slight). The differences are
systematic: Evaluator 1 scored lower on technical accuracy and actionability
and higher on root cause (Wilcoxon p ≤ .007). Evaluator 1 gave actionability 1
to 51 of 90 answers, Evaluator 2 to 2 of 90.
**Added check (not in the proposal):** because agreement was low, each
evaluator's own 90 scores were also looked at separately, descriptively (means
by level). For GPT and Claude the full-level rise appears in both; for llama
only Evaluator 1's technical accuracy rises. Reported in 4.2.2 as a check, with
no extra significance tests, to avoid more multiple testing.
**Robustness (criterion in 3.7, ANOVA and Friedman both significant):** GPT on
all three expert dimensions; Claude on root cause and actionability, not on
technical accuracy (Friedman p = .066); llama on none. H1₀ is reported as
rejected accordingly (5.2).
**Report as:** 4.1, 4.2.2, 4.2.3, 4.3, 4.4.2 and 4.5 rewritten with both
evaluators' scores; abstract, 3.10 and 5.2/5.5 adjusted; all notes to self
removed. Changes shown as tracked changes.

## D42 — Scope of D38, D39 and D41 (2026-11-05, Confirmed)

These entries refer to the working draft Claude produced in `report/src/` during
the study. The submitted report is a separate document written by the
researcher, and those corrections were not applied to it. Decisions about the
method and results in those entries still apply to the submitted report.

## D43 — Repeated-measures analysis and evaluator offsets (recorded 2026-11-05, Confirmed)

**Decision (researcher):** the main analysis treats scenario as the subject. The
same 15 scenarios appear at all three context levels, so the 45 values per model
are repeated measures, which the two-way ANOVA and Tukey HSD of D29 treat as
independent.

- **Main test:** repeated-measures (split-plot) ANOVA per model and dependent
  variable: context level and level × category within scenarios (error df 20),
  failure category between scenarios (error df 10), Greenhouse–Geisser correction
  for the within-scenario effects, partial η².
- **Follow-up:** paired t-tests between context levels across the 15 scenarios,
  Holm-adjusted within each model and dimension, instead of Tukey HSD.
- **Kept from D29:** Friedman as the rank-based check; Holm across the four
  dependent variables of the expert-scored sample.
- **Evaluator sensitivity:** the 90 single-scored answers are not split evenly
  between the evaluators within each model and level (D30), so each evaluator's
  mean offset on the 45 shared answers is subtracted from all of their scores and
  the within-scenario test of context level is repeated.

**Where:** calculated by the researcher in `RPDA_stats_analysis.xlsx` (repository
root). The two-way ANOVA, Tukey, Kruskal–Wallis and Kendall's W outputs in
`results/analysis/` come from the AI assistant's earlier analysis
(`scripts/analyse.py`) and are not reported; only its figures are used, for
illustration.
**Report as:** 3.7, the deviations table (3.11), Tables 7, 8, 11 and 12, and the
sensitivity results in 4.2.2.
