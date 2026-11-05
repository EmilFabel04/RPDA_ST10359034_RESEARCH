# Limitations — DRAFT

> **Draft notes for the author (delete before submission)**
> - Follows the proposal's §10 headings first, then the limitations that came
>   from how the study was actually run (decisions log D1–D31).
> - `[square brackets]` = fill in once the expert scores and your hallucination
>   review are in.

## Synthetic scenarios

All 15 scenarios were built on a small simulated pipeline, so they are cleaner
than real incidents (proposal §10.1). Each has exactly one injected fault, the
error messages come from a real dbt run but on a project with five models,
and the history given at full context was written for the study. Real
failures often have several causes, vague errors and undocumented business
rules.

Three further points narrow what the scenarios represent:

- **Cause types are unbalanced.** 11 root causes lie in upstream data, 3 in
  dbt code and 1 in configuration (D17). The results by cause type are
  descriptive only, and the code-fault pattern rests on three scenarios.
- **The reference fixes were written by the researcher** (D18). The two
  experts checked them [outcome of the scenario check], but a different
  engineer might fix some failures differently.
- **[No anonymised real cases were included / N real cases were included]**
  (O3). [If none: this removes the cross-check against real incidents that
  the proposal planned (§7.2), so external validity rests on the scenarios
  alone.]

## Context window size

The proposal expected that large lineage graphs might not fit the models'
context windows (§10.2). In this study they did: the largest full-context
prompt plus the maximum answer used 59% of llama3:8b's 8,192-token window,
and no answer was truncated. The other side of this is that the full-context
prompts were short (at most about 2,900 tokens), so the study does not test
how the models behave with the much larger metadata of a production project,
where truncation and the "lost in the middle" effect (Liu et al., 2024) would
matter.

## Limited scope of generality

The findings apply to dbt with DuckDB, to one e-commerce-style project, to
the five failure categories, and to three models at the versions pinned for
this study (§10.3, D2). They do not show how other tools, larger projects or
other failure types behave.

## Rapidly advancing models

The models were pinned and every answer came from the pinned version (D2,
D21), but newer models will behave differently (§10.4). Three choices also
limit what the model comparison means:

- **The local model is llama3:8b, not LLaMA 3 70B** (D1). It is far smaller
  than the two cloud models, so differences between models mix size,
  training and provider. The context effect is compared within each model,
  which this does not affect.
- **Reasoning was switched to its lowest setting** on both cloud models (D4),
  so the results describe direct answers, not the models' best
  reasoning-mode performance.
- **Temperature was 1.0, not 0.7** (D3), because one model accepted no other
  value. This adds run-to-run variation; the median of three repetitions
  absorbs some of it for specificity.

## Evaluators and human scores

The proposal flagged evaluator availability as a risk (§10.5). The
submission date made the following changes necessary (D6, D30, D31):

- **One answer per condition, not the median of three.** The human-scored
  dimensions rest on one repetition of each scenario × level × model (135
  answers), whereas specificity uses the median of three. The human scores
  therefore carry more run-to-run noise.
- **Each answer was scored by one or two experts.** Each expert scored 90
  answers: 45 that both scored, and 45 alone. Agreement is measured on the
  45 shared answers, and 90 answers rest on a single expert's judgement.
- **Calibration was done by email**, without a live discussion between the
  experts (D31).
- **There was no midpoint drift check** (D30). Scoring took [n] days, which
  limits drift, but within-expert consistency was not measured.
- **There was no third evaluator** (D9). Disagreements were kept and averaged
  rather than settled.
- [Inter-rater agreement was κ = … for root cause correctness, … ; report
  any dimension where agreement was only fair or poor as a limit on that
  dimension's results.]

## Measures

- **Specificity** is the similarity between an answer and one reference fix.
  It tracks how many of the scenario's key names an answer uses (ρ = 0.64)
  and not answer length (D26), but a correct fix that differs from the
  reference scores lower. The band cut-offs come from nine pilot answers.
- **The hallucination check is incomplete.** The automated check flagged 62
  references. On review, [15] were hallucinations, so its precision was about
  [24%]. Reading 27 answers in full found [5] hallucinations it had missed,
  against [4] it caught, so it finds only about [half] of them. Confirmed
  rates are therefore a lower bound.
- **The hallucination review was AI-assisted.** An AI assistant suggested a
  verdict for every flag and pre-read the sample answers; the researcher
  confirmed or changed each one ([n] changed). The assistant belongs to the
  same model family as one of the models studied, though the blinded IDs hid
  which model wrote each answer (D27).
- **False confidence** is measured with a fixed list of hedge words in the
  root-cause section (D28). It misses hedging in other words, so it is a
  proxy, not a validated measure of confidence.
- **Quality, not time to resolution.** The study scores suggestions; it does
  not measure whether they shorten real incidents (proposal §7.6).

## Statistical power

Each model has 45 values per dependent variable, three per cell, leaving 30
residual degrees of freedom. The planned variance estimate from the pilot was
not made (D23), so the study was not powered in advance, and small
interaction effects could go undetected. The human scores take only two or
three values, so the ANOVA's normality assumption does not hold for them;
rank-based tests are reported alongside, and a context effect is called
robust only where both agree (D29). The same scenarios appear at all three
context levels; the Friedman test accounts for this, the ANOVA does not.
