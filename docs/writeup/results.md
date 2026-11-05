# Results — DRAFT (partial)

> **Draft notes for the author (delete before submission)**
> - **Final now:** everything built from automated measures. That is
>   specificity, the context-window figures and the *unreviewed*
>   hallucination candidates.
> - **Pending:**
>   - the three human-scored dimensions, misdiagnosis, false confidence and
>     agreement (needs both experts' score files, D30);
>   - confirmed hallucination rates (needs your 62 verdicts and the 27-answer
>     recall sample).
>
>   These sections are marked **PENDING**. The human-scored results will come
>   from section 8 of `report.md` (expert scores).
> - **Source of the numbers:** `results/analysis/report.md` (generated
>   26 October 2026). Re-run `python scripts/analyse.py` after each input
>   arrives and update the tables from the new report.
> - **Holm p will change.** It is computed across the four dependent
>   variables, and only specificity exists so far, so for now Holm p equals
>   raw p. Update Table R2 once the human scores are in.

## Data collected

All 405 planned calls returned an answer. The cloud answers were complete
and correctly formatted:

- no answer was truncated, empty or refused;
- every answer came from the pinned model version (D21);
- every GPT and Claude answer used all four requested headings.

Three llama answers each left out one heading. They were kept as returned
and scored like the others.

Answer length differed by model. Claude wrote the longest answers (median
about 470 words), GPT about 350–390, and llama about 230. Length did not
change much with context level.

**Context window (RQ4).** The full-context prompts were well within every
model's window (Table R7). The largest llama prompt plus the 2,048-token
output limit used 59% of llama3:8b's 8,192-token window. No prompt was
truncated, so the "lost in the middle" risk that comes from truncation
(proposal §10.2) did not occur.

## Context and specificity (RQ1, RQ2)

**More context made all three models' suggestions more specific** (Table R1,
Figure [fig3]). The context effect was significant in the two-way ANOVA for
every model (Table R2):

- **GPT:** F(2, 30) = 11.77, p < .001, partial η² = .44;
- **Claude:** F(2, 30) = 6.26, p = .005, partial η² = .29;
- **llama:** F(2, 30) = 4.64, p = .018, partial η² = .24.

The Friedman test, which accounts for the same scenarios appearing at every
level, agreed for all three:

- **GPT:** χ²(2) = 19.73, p < .001, Kendall's W = .66;
- **Claude:** χ²(2) = 14.53, p < .001, W = .48;
- **llama:** χ²(2) = 12.13, p = .002, W = .40.

Kruskal-Wallis tests agreed as well (GPT p < .001, Claude p = .001, llama
p = .038). The context effect on specificity is therefore robust by the rule
set in the Methodology.

**Assumptions.** The residuals of the ANOVA departed from normality for GPT
(Shapiro-Wilk p = .021) and Claude (p = .005), but not for llama (p = .113).
Variances were similar across cells for all three models (Brown-Forsythe
p ≥ .76). Since the rank-based tests agree, the conclusion does not depend on
the normality assumption.

**Table R1. Specificity by context level** (mean (SD) of 15 scenario
medians).

| Model | Minimal | Partial | Full |
|---|---|---|---|
| GPT | 0.763 (0.057) | 0.776 (0.046) | 0.838 (0.019) |
| Claude | 0.770 (0.069) | 0.795 (0.049) | 0.841 (0.046) |
| llama | 0.693 (0.051) | 0.726 (0.047) | 0.743 (0.044) |

**Table R2. Two-way ANOVA on specificity** (Type II; 3 values per cell;
residual df = 30).

| Model | Effect | df | F | p | Partial η² |
|---|---|---|---|---|---|
| GPT | Level | 2 | 11.77 | < .001 | .44 |
| GPT | Category | 4 | 1.47 | .235 | .16 |
| GPT | Level × category | 8 | 0.44 | .885 | .11 |
| Claude | Level | 2 | 6.26 | .005 | .29 |
| Claude | Category | 4 | 1.66 | .186 | .18 |
| Claude | Level × category | 8 | 0.62 | .756 | .14 |
| llama | Level | 2 | 4.64 | .018 | .24 |
| llama | Category | 4 | 3.28 | .024 | .30 |
| llama | Level × category | 8 | 0.22 | .984 | .06 |

**Where the gain comes from (RQ2).** RQ2 asks what each cumulative step adds
(Table R3).

- **Minimal → partial.** Adding model metadata did not significantly raise
  specificity for any model; the differences were +0.012 to +0.032.
- **Partial → full.** Adding lineage and history raised GPT's specificity by
  +0.062 (95% CI 0.023 to 0.101, p < .001). The same step for Claude (+0.045,
  p = .076) and llama (+0.018, p = .562) was not significant on its own.
- **Minimal → full.** Significant for all three models: GPT +0.074,
  Claude +0.071, llama +0.050.

For Claude and llama, the gain built up over the two steps rather than
coming from one of them. GPT's full-context answers were also the most
uniform: their SD fell from 0.057 to 0.019, and all 45 GPT answers at full
context were in the high band (Table R4).

**Table R3. Tukey HSD between context levels, specificity** (difference =
later minus earlier level).

| Model | Comparison | Difference | 95% CI | p (adj.) |
|---|---|---|---|---|
| GPT | Minimal → partial | +0.012 | −0.026 to 0.051 | .723 |
| GPT | Partial → full | +0.062 | 0.023 to 0.101 | < .001 |
| GPT | Minimal → full | +0.074 | 0.036 to 0.113 | < .001 |
| Claude | Minimal → partial | +0.026 | −0.024 to 0.075 | .420 |
| Claude | Partial → full | +0.045 | −0.004 to 0.095 | .076 |
| Claude | Minimal → full | +0.071 | 0.022 to 0.120 | .003 |
| llama | Minimal → partial | +0.032 | −0.010 to 0.074 | .159 |
| llama | Partial → full | +0.018 | −0.024 to 0.060 | .562 |
| llama | Minimal → full | +0.050 | 0.008 to 0.092 | .016 |

Tukey comparisons within each failure category (3 values per level) are in
`results/analysis/tukey.csv`. They have very little power and are not
interpreted.

**Table R4. Specificity bands, all 405 answers** (high ≥ 0.75, moderate
≥ 0.69, low < 0.69; descriptive only).

| Model | Level | High | Moderate | Low |
|---|---|---|---|---|
| GPT | Minimal | 31 | 9 | 5 |
| GPT | Partial | 31 | 12 | 2 |
| GPT | Full | 45 | 0 | 0 |
| Claude | Minimal | 34 | 7 | 4 |
| Claude | Partial | 37 | 7 | 1 |
| Claude | Full | 42 | 3 | 0 |
| llama | Minimal | 8 | 16 | 21 |
| llama | Partial | 15 | 19 | 11 |
| llama | Full | 21 | 16 | 8 |

**Which reference fix is closest.** For each answer, all 15 reference fixes
were ranked by similarity; ideally the answer's own fix comes first. This
rose with context:

- **GPT:** 69% at minimal context, 100% at full;
- **Claude:** 73% to 93%;
- **llama:** 64% to 73%.

**Model differences.** llama was less specific than the cloud models at every
level. Its full-context mean (0.743) was below the cloud models' minimal-context
means (0.763 and 0.770). Because llama3:8b is far smaller than the cloud
models (D1), this difference describes these three models; it is not
attributed to model size, training or provider.

**Repetitions.** At temperature 1.0 the three repetitions of a condition
differed in specificity by 0.035 on average for GPT, 0.042 for Claude and
0.057 for llama, at most 0.155 (llama).

## Failure categories (RQ3)

The failure category had no significant effect on specificity for GPT or
Claude. For llama it did: F(4, 30) = 3.28, p = .024, partial η² = .30, and
Kruskal-Wallis p = .026. No model showed a level × category interaction, so
the context effect did not depend on the type of failure (Table R2).

**Table R5. Specificity by failure category** (mean of 9 values: 3 scenarios
× 3 levels).

| Category | GPT | Claude | llama |
|---|---|---|---|
| Schema drift | 0.807 | 0.822 | 0.752 |
| Null rate anomaly | 0.789 | 0.803 | 0.728 |
| Row count anomaly | 0.796 | 0.806 | 0.706 |
| Referential integrity | 0.806 | 0.816 | 0.681 |
| Freshness violation | 0.762 | 0.761 | 0.737 |

The models did not reliably rank the categories in the same order (Kendall's
W = .56, χ²(4) = 6.67, p = .155):

- **GPT and Claude** were least specific on freshness violations, and close
  to each other on the other four categories.
- **llama** was least specific on referential integrity and row count
  anomalies, and did comparatively well on freshness violations.

## Root-cause type (descriptive)

As expected from the scenario design (D17), the two cloud models gained at a
different step depending on where the fault lay (Table R6):

- **Code faults (3 scenarios).** The faulty SQL is visible from the partial
  level onwards, and most of the gain came at partial.
- **Data faults (11 scenarios).** The cause lies upstream, and the gain came
  only at full context, which adds lineage and history.

With three code-fault scenarios this pattern is descriptive, not a tested
effect.

**Table R6. Specificity by root-cause type and level** (mean of scenario
medians; FV03, the single configuration fault, not shown).

| Model | Cause type (n) | Minimal | Partial | Full |
|---|---|---|---|---|
| GPT | Code (3) | 0.732 | 0.812 | 0.853 |
| GPT | Data (11) | 0.772 | 0.763 | 0.834 |
| Claude | Code (3) | 0.723 | 0.837 | 0.865 |
| Claude | Data (11) | 0.783 | 0.789 | 0.833 |
| llama | Code (3) | 0.666 | 0.721 | 0.757 |
| llama | Data (11) | 0.695 | 0.721 | 0.737 |

## Reliability (RQ4)

**Table R7. Prompt and answer sizes** (tokens as counted by each model; full
context).

| Model | Prompt median | Prompt max | Answer median | Answer max | Window used (max) |
|---|---|---|---|---|---|
| GPT | 1,634 | 2,810 | 935 | 1,123 | — |
| Claude | 2,528 | 4,586 | 1,362 | 1,633 | — |
| llama | 1,630 | 2,780 | 402 | 676 | 59% of 8,192 |

**Hallucination candidates (not yet reviewed).** The automated check flagged
62 references in 46 of the 405 answers:

| Model | References flagged | Answers with a flag |
|---|---|---|
| GPT | 30 | 21 |
| Claude | 11 | 9 |
| llama | 21 | 16 |

These are candidates only. Some will turn out to be hedged guesses, newly
proposed objects or false positives. **No hallucination rate is reported
until every candidate has been reviewed.** [PENDING: table of confirmed
hallucination rates by model × level and by category, per answer and per
100 checked references; precision and recall of the check.]

[PENDING — Provisional researcher scores — expert evaluation pending:
misdiagnosis rate and false confidence by model × level and by category;
hedging when wrong vs. when right.]

## Human-scored dimensions (RQ1, RQ2) — PENDING

[PENDING — Provisional researcher scores — expert evaluation pending.

For technical accuracy, root cause correctness and actionability, in the same
format as specificity above:

- descriptives by level;
- two-way ANOVA with Holm-corrected p;
- Friedman and Kruskal-Wallis tests;
- Tukey HSD;
- category means and Kendall's W.

Expect the ANOVA's normality assumption to fail on these 2–3-point scales,
and lead with the rank-based tests where they disagree with the ANOVA.]

## Agreement — PENDING

[PENDING: Cohen's kappa, quadratic-weighted kappa and % agreement for expert
1 vs expert 2 (135 answers), each expert vs their midpoint repeats, and the
researcher vs each expert, interpreted with Landis and Koch (1977).]

## Expert replication — PENDING

[PENDING: the two-way ANOVA on the 135 expert-scored answers (mean of the two
experts), compared with the researcher-score results.]
