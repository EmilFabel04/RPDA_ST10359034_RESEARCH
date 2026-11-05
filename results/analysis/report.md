# Step 8 — analysis report

Generated 2026-11-03T04:21:15+00:00 by `scripts/analyse.py`. Methods: decisions log D29.

## Inputs

| input | status |
|---|---|
| researcher scores (all 405) | not yet (results/scores_researcher_provisional.csv missing) |
| expert_1 scores (90: 45 shared + 45 own) | complete (90 rows) |
| expert_2 scores (90: 45 shared + 45 own) | complete (90 rows) |
| hallucination review | 62/62 verdicts |
| recall sample | 27/27 read |


## 1. Context effect (RQ1, RQ2) — descriptives by level

Mean (SD) of the 45 scenario × level values per model (each the median of 3 repetitions).

| model_key | dv | minimal | partial | full |
|---|---|---|---|---|
| gpt | specificity | 0.763 (0.057) | 0.776 (0.046) | 0.838 (0.019) |
| claude | specificity | 0.770 (0.069) | 0.795 (0.049) | 0.841 (0.046) |
| llama | specificity | 0.693 (0.051) | 0.726 (0.047) | 0.743 (0.044) |


## 2. Two-way ANOVA per model: level × category (median of 3 repetitions)

Type II sums of squares; 3 values per cell, residual df 30. p_holm: Holm correction over the 4 DVs for each model and effect.

| model_key | dv | effect | df | df_resid | F | p | p_holm | partial_eta2 | note |
|---|---|---|---|---|---|---|---|---|---|
| gpt | specificity | level | 2 | 30 | 11.774 | < .001 | < .001 | 0.440 |  |
| gpt | specificity | category | 4 | 30 | 1.474 | 0.235 | 0.235 | 0.164 |  |
| gpt | specificity | level x category | 8 | 30 | 0.444 | 0.885 | 0.885 | 0.106 |  |
| claude | specificity | level | 2 | 30 | 6.264 | 0.005 | 0.005 | 0.295 |  |
| claude | specificity | category | 4 | 30 | 1.659 | 0.186 | 0.186 | 0.181 |  |
| claude | specificity | level x category | 8 | 30 | 0.618 | 0.756 | 0.756 | 0.142 |  |
| llama | specificity | level | 2 | 30 | 4.635 | 0.018 | 0.018 | 0.236 |  |
| llama | specificity | category | 4 | 30 | 3.279 | 0.024 | 0.024 | 0.304 |  |
| llama | specificity | level x category | 8 | 30 | 0.221 | 0.984 | 0.984 | 0.056 |  |


**Assumption checks** (Shapiro-Wilk on residuals; Brown-Forsythe Levene over the 15 cells):

| model_key | dv | shapiro_W | shapiro_p | levene_W | levene_p |
|---|---|---|---|---|---|
| gpt | specificity | 0.940 | 0.021 | 0.556 | 0.877 |
| claude | specificity | 0.922 | 0.005 | 0.690 | 0.766 |
| llama | specificity | 0.959 | 0.113 | 0.216 | 0.998 |


## 3. Tukey HSD between context levels (all categories)

Difference = later level minus earlier. Within-category comparisons (n = 3 per level) are in `tukey.csv`.

| model_key | dv | from | to | mean_diff | ci_low | ci_high | p_adj |
|---|---|---|---|---|---|---|---|
| gpt | specificity | minimal | partial | 0.012 | -0.026 | 0.051 | 0.723 |
| gpt | specificity | partial | full | 0.062 | 0.023 | 0.101 | < .001 |
| gpt | specificity | minimal | full | 0.074 | 0.036 | 0.113 | < .001 |
| claude | specificity | minimal | partial | 0.026 | -0.024 | 0.075 | 0.420 |
| claude | specificity | partial | full | 0.045 | -0.004 | 0.095 | 0.076 |
| claude | specificity | minimal | full | 0.071 | 0.022 | 0.120 | 0.003 |
| llama | specificity | minimal | partial | 0.032 | -0.010 | 0.074 | 0.159 |
| llama | specificity | partial | full | 0.018 | -0.024 | 0.060 | 0.562 |
| llama | specificity | minimal | full | 0.050 | 0.008 | 0.092 | 0.016 |


## 4. Rank-based checks

Kruskal-Wallis treats the 45 values as independent, like the ANOVA. Friedman blocks on scenario: each scenario appears at all three levels, which the ANOVA does not model.

| model_key | dv | test | factor | statistic | p | effect_size | effect_measure | note |
|---|---|---|---|---|---|---|---|---|
| gpt | specificity | Kruskal-Wallis | level | 21.206 | < .001 | 0.482 | epsilon2 |  |
| gpt | specificity | Kruskal-Wallis | category | 5.675 | 0.225 | 0.129 | epsilon2 |  |
| gpt | specificity | Friedman (blocks: scenario) | level | 19.733 | < .001 | 0.658 | Kendall W |  |
| claude | specificity | Kruskal-Wallis | level | 13.149 | 0.001 | 0.299 | epsilon2 |  |
| claude | specificity | Kruskal-Wallis | category | 8.653 | 0.070 | 0.197 | epsilon2 |  |
| claude | specificity | Friedman (blocks: scenario) | level | 14.533 | < .001 | 0.484 | Kendall W |  |
| llama | specificity | Kruskal-Wallis | level | 6.524 | 0.038 | 0.148 | epsilon2 |  |
| llama | specificity | Kruskal-Wallis | category | 11.028 | 0.026 | 0.251 | epsilon2 |  |
| llama | specificity | Friedman (blocks: scenario) | level | 12.133 | 0.002 | 0.404 | Kendall W |  |


## 5. Failure categories (RQ3)

Mean per category (9 values: 3 scenarios × 3 levels).

| dv | category | gpt | claude | llama |
|---|---|---|---|---|
| specificity | schema_drift | 0.807 | 0.822 | 0.752 |
| specificity | null_rate_anomaly | 0.789 | 0.803 | 0.728 |
| specificity | row_count_anomaly | 0.796 | 0.806 | 0.706 |
| specificity | referential_integrity | 0.806 | 0.816 | 0.681 |
| specificity | freshness_violation | 0.762 | 0.761 | 0.737 |


Do the models rank the categories alike? Kendall's W (1 = same order, 0 = no agreement):

| unit | dv | models | W | chi2 | df | p |
|---|---|---|---|---|---|---|
| median3 | specificity | 3 | 0.556 | 6.667 | 4 | 0.155 |
| experts | technical_accuracy | 3 | 0.156 | 1.867 | 4 | 0.760 |
| experts | root_cause_correctness | 3 | 0.509 | 6.105 | 4 | 0.191 |
| experts | actionability | 3 | 0.152 | 1.825 | 4 | 0.768 |
| experts | specificity | 3 | 0.333 | 4.000 | 4 | 0.406 |


## 6. Reliability (RQ4)

Per answer, all 3 repetitions (45 answers per model × level, 27 per model × category).

**Misdiagnosis and false confidence.** Misdiagnosis = root cause scored 0. False confidence = misdiagnosed and stated without any hedge word; `wrong_asserted_share` is its share of the misdiagnoses, `right_asserted_share` the same for correct diagnoses (a well-calibrated model asserts more when it is right).

| model_key | level | answers | misdiagnosis_rate | false_confidence_rate | wrong_asserted_share | right_asserted_share | hedges_when_wrong | hedges_when_right |
|---|---|---|---|---|---|---|---|---|
| gpt | minimal | 45 |  |  |  |  |  |  |
| gpt | partial | 45 |  |  |  |  |  |  |
| gpt | full | 45 |  |  |  |  |  |  |
| gpt | all | 135 |  |  |  |  |  |  |
| claude | minimal | 45 |  |  |  |  |  |  |
| claude | partial | 45 |  |  |  |  |  |  |
| claude | full | 45 |  |  |  |  |  |  |
| claude | all | 135 |  |  |  |  |  |  |
| llama | minimal | 45 |  |  |  |  |  |  |
| llama | partial | 45 |  |  |  |  |  |  |
| llama | full | 45 |  |  |  |  |  |  |
| llama | all | 135 |  |  |  |  |  |  |


| model_key | category | answers | misdiagnosis_rate | false_confidence_rate | wrong_asserted_share | right_asserted_share | hedges_when_wrong | hedges_when_right |
|---|---|---|---|---|---|---|---|---|
| gpt | schema_drift | 27 |  |  |  |  |  |  |
| gpt | null_rate_anomaly | 27 |  |  |  |  |  |  |
| gpt | row_count_anomaly | 27 |  |  |  |  |  |  |
| gpt | referential_integrity | 27 |  |  |  |  |  |  |
| gpt | freshness_violation | 27 |  |  |  |  |  |  |
| claude | schema_drift | 27 |  |  |  |  |  |  |
| claude | null_rate_anomaly | 27 |  |  |  |  |  |  |
| claude | row_count_anomaly | 27 |  |  |  |  |  |  |
| claude | referential_integrity | 27 |  |  |  |  |  |  |
| claude | freshness_violation | 27 |  |  |  |  |  |  |
| llama | schema_drift | 27 |  |  |  |  |  |  |
| llama | null_rate_anomaly | 27 |  |  |  |  |  |  |
| llama | row_count_anomaly | 27 |  |  |  |  |  |  |
| llama | referential_integrity | 27 |  |  |  |  |  |  |
| llama | freshness_violation | 27 |  |  |  |  |  |  |


**Hallucinations.** Candidates are automated (Step 7); confirmed rates count reviewed verdicts H only and stay empty until every candidate has a verdict. Per 100 checked references corrects for how many entities an answer names.

| model_key | level | answers | candidate_answer_rate | hallucination_answer_rate | candidates_per_100_refs | hallucinations_per_100_refs | refs_checked_median |
|---|---|---|---|---|---|---|---|
| gpt | minimal | 45 | 0.289 | 0.000 | 2.671 | 0.000 | 15 |
| gpt | partial | 45 | 0.022 | 0.022 | 0.148 | 0.148 | 14 |
| gpt | full | 45 | 0.156 | 0.000 | 1.423 | 0.000 | 16 |
| gpt | all | 135 | 0.156 | 0.007 | 1.412 | 0.047 | 15 |
| claude | minimal | 45 | 0.089 | 0.022 | 0.990 | 0.198 | 12 |
| claude | partial | 45 | 0.000 | 0.000 | 0.000 | 0.000 | 13 |
| claude | full | 45 | 0.111 | 0.000 | 1.034 | 0.000 | 12 |
| claude | all | 135 | 0.067 | 0.007 | 0.663 | 0.060 | 12 |
| llama | minimal | 45 | 0.200 | 0.156 | 6.091 | 3.553 | 5.000 |
| llama | partial | 45 | 0.111 | 0.111 | 2.414 | 2.069 | 6.000 |
| llama | full | 45 | 0.044 | 0.022 | 0.660 | 0.330 | 7.000 |
| llama | all | 135 | 0.119 | 0.096 | 2.658 | 1.772 | 5.000 |


| model_key | category | answers | candidate_answer_rate | hallucination_answer_rate | candidates_per_100_refs | hallucinations_per_100_refs | refs_checked_median |
|---|---|---|---|---|---|---|---|
| gpt | schema_drift | 27 | 0.259 | 0.000 | 1.807 | 0.000 | 17 |
| gpt | null_rate_anomaly | 27 | 0.111 | 0.037 | 0.990 | 0.248 | 15 |
| gpt | row_count_anomaly | 27 | 0.074 | 0.000 | 0.725 | 0.000 | 21 |
| gpt | referential_integrity | 27 | 0.148 | 0.000 | 1.208 | 0.000 | 14 |
| gpt | freshness_violation | 27 | 0.185 | 0.000 | 3.125 | 0.000 | 9.000 |
| claude | schema_drift | 27 | 0.074 | 0.000 | 0.563 | 0.000 | 13 |
| claude | null_rate_anomaly | 27 | 0.074 | 0.037 | 0.567 | 0.283 | 13 |
| claude | row_count_anomaly | 27 | 0.037 | 0.000 | 0.229 | 0.000 | 14 |
| claude | referential_integrity | 27 | 0.074 | 0.000 | 0.852 | 0.000 | 13 |
| claude | freshness_violation | 27 | 0.074 | 0.000 | 1.852 | 0.000 | 5.000 |
| llama | schema_drift | 27 | 0.111 | 0.111 | 2.410 | 1.807 | 6.000 |
| llama | null_rate_anomaly | 27 | 0.074 | 0.074 | 1.136 | 1.136 | 7.000 |
| llama | row_count_anomaly | 27 | 0.074 | 0.000 | 2.874 | 0.000 | 5.000 |
| llama | referential_integrity | 27 | 0.111 | 0.074 | 1.485 | 0.990 | 6.000 |
| llama | freshness_violation | 27 | 0.222 | 0.222 | 9.722 | 9.722 | 2.000 |


Model × level × category: `rates.csv`.

**Hallucination check quality** (precision = H / candidates; recall from the sample read in full):

| candidates | reviewed | verdict_H | verdict_C | verdict_N | verdict_F | precision | recall_sample | recall_read | recall_found_H | recall_missed | recall | data_label |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 62 | 62 | 16 | 22 | 17 | 7 | 0.258 | 27 | 27 | 4.000 | 5 | 0.444 | researcher review (D27) |


**Context window** (prompt + answer sizes; llama's window is 8,192 tokens):

| model_key | level | answers | input_tokens_median | input_tokens_max | output_tokens_median | output_tokens_max | words_median | truncated | all_headings_share | window_used_max | data_label |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpt | minimal | 45 | 616 | 759 | 860 | 1021 | 354 | 0 | 1.000 |  | Automated metric |
| gpt | partial | 45 | 966 | 1863 | 842 | 993 | 350 | 0 | 1.000 |  | Automated metric |
| gpt | full | 45 | 1634 | 2810 | 935 | 1123 | 391 | 0 | 1.000 |  | Automated metric |
| claude | minimal | 45 | 909 | 1098 | 1312 | 1476 | 469 | 0 | 1.000 |  | Automated metric |
| claude | partial | 45 | 1437 | 2987 | 1295 | 1486 | 461 | 0 | 1.000 |  | Automated metric |
| claude | full | 45 | 2528 | 4586 | 1362 | 1633 | 486 | 0 | 1.000 |  | Automated metric |
| llama | minimal | 45 | 621 | 760 | 405 | 599 | 237 | 0 | 1.000 | 0.343 | Automated metric |
| llama | partial | 45 | 968 | 1854 | 414 | 586 | 232 | 0 | 0.978 | 0.476 | Automated metric |
| llama | full | 45 | 1630 | 2780 | 402 | 676 | 228 | 0 | 0.956 | 0.589 | Automated metric |


## 7. Agreement

Cohen's kappa over the full scale (proposal §7.5); quadratic-weighted kappa for the 3-point scales; % exact agreement. The two experts are compared on the answers both scored (45 when both files are complete, D30).

| comparison | dimension | n | pct_agree | kappa | kappa_quadratic | interpretation | data_label |
|---|---|---|---|---|---|---|---|
| expert_1 vs expert_2 (45 shared items) | technical_accuracy | 45 | 0.489 | 0.269 | 0.488 | fair | Expert scores |
| expert_1 vs expert_2 (45 shared items) | root_cause_correctness | 45 | 0.756 | 0.506 |  | moderate | Expert scores |
| expert_1 vs expert_2 (45 shared items) | actionability | 45 | 0.267 | 0.095 | 0.259 | slight | Expert scores |


**Is one expert more generous?** Mean score of each on the shared answers; difference = expert_1 − expert_2; Wilcoxon signed-rank test of the paired differences (D34).

| comparison | dimension | n | mean_a | mean_b | difference | a_higher | b_higher | wilcoxon_p | data_label |
|---|---|---|---|---|---|---|---|---|---|
| expert_1 vs expert_2 (45 shared items) | technical_accuracy | 45 | 0.444 | 0.622 | -0.178 | 5 | 18 | 0.005 | Expert scores |
| expert_1 vs expert_2 (45 shared items) | root_cause_correctness | 45 | 0.489 | 0.289 | 0.200 | 10 | 1 | 0.007 | Expert scores |
| expert_1 vs expert_2 (45 shared items) | actionability | 45 | 1.800 | 2.378 | -0.578 | 6 | 27 | < .001 | Expert scores |


## 8. Expert scores (RQ1–RQ4): one repetition per cell

Expert scores (one repetition per cell; mean of 2 experts on 45 shared answers, 1 expert on 90). Up to 45 values per model (3 per level × category cell); n in each table shows how many were scored.

**Means (SD) by level:**

| model_key | dv | minimal | partial | full |
|---|---|---|---|---|
| gpt | technical_accuracy | 0.517 (0.347) | 0.500 (0.327) | 0.900 (0.184) |
| gpt | root_cause_correctness | 0.167 (0.362) | 0.300 (0.414) | 0.833 (0.362) |
| gpt | actionability | 1.700 (0.528) | 2.067 (0.651) | 2.633 (0.481) |
| gpt | specificity | 0.760 (0.065) | 0.779 (0.045) | 0.838 (0.024) |
| claude | technical_accuracy | 0.567 (0.334) | 0.667 (0.397) | 0.900 (0.184) |
| claude | root_cause_correctness | 0.267 (0.458) | 0.367 (0.442) | 0.833 (0.362) |
| claude | actionability | 1.900 (0.712) | 2.100 (0.870) | 2.800 (0.368) |
| claude | specificity | 0.771 (0.061) | 0.798 (0.046) | 0.830 (0.047) |
| llama | technical_accuracy | 0.167 (0.225) | 0.283 (0.364) | 0.267 (0.306) |
| llama | root_cause_correctness | 0.067 (0.258) | 0.167 (0.362) | 0.300 (0.455) |
| llama | actionability | 1.467 (0.399) | 1.767 (0.753) | 1.700 (0.561) |
| llama | specificity | 0.704 (0.065) | 0.726 (0.047) | 0.741 (0.039) |


**Two-way ANOVA** (p_holm over the 4 DVs):

| model_key | dv | effect | df | df_resid | F | p | p_holm | partial_eta2 | note |
|---|---|---|---|---|---|---|---|---|---|
| gpt | technical_accuracy | level | 2 | 30 | 7.900 | 0.002 | 0.002 | 0.345 |  |
| gpt | technical_accuracy | category | 4 | 30 | 1.214 | 0.325 | 1.000 | 0.139 |  |
| gpt | technical_accuracy | level x category | 8 | 30 | 0.346 | 0.940 | 1.000 | 0.085 |  |
| gpt | root_cause_correctness | level | 2 | 30 | 15.273 | < .001 | < .001 | 0.505 |  |
| gpt | root_cause_correctness | category | 4 | 30 | 1.068 | 0.389 | 1.000 | 0.125 |  |
| gpt | root_cause_correctness | level x category | 8 | 30 | 1.920 | 0.094 | 0.375 | 0.339 |  |
| gpt | actionability | level | 2 | 30 | 9.328 | < .001 | 0.001 | 0.383 |  |
| gpt | actionability | category | 4 | 30 | 0.805 | 0.532 | 1.000 | 0.097 |  |
| gpt | actionability | level x category | 8 | 30 | 0.441 | 0.886 | 1.000 | 0.105 |  |
| gpt | specificity | level | 2 | 30 | 10.102 | < .001 | 0.001 | 0.402 |  |
| gpt | specificity | category | 4 | 30 | 1.194 | 0.334 | 1.000 | 0.137 |  |
| gpt | specificity | level x category | 8 | 30 | 0.606 | 0.765 | 1.000 | 0.139 |  |
| claude | technical_accuracy | level | 2 | 30 | 3.674 | 0.037 | 0.037 | 0.197 |  |
| claude | technical_accuracy | category | 4 | 30 | 0.424 | 0.790 | 0.790 | 0.054 |  |
| claude | technical_accuracy | level x category | 8 | 30 | 0.477 | 0.863 | 1.000 | 0.113 |  |
| claude | root_cause_correctness | level | 2 | 30 | 7.719 | 0.002 | 0.008 | 0.340 |  |
| claude | root_cause_correctness | category | 4 | 30 | 1.984 | 0.122 | 0.489 | 0.209 |  |
| claude | root_cause_correctness | level x category | 8 | 30 | 0.531 | 0.823 | 1.000 | 0.124 |  |
| claude | actionability | level | 2 | 30 | 7.094 | 0.003 | 0.009 | 0.321 |  |
| claude | actionability | category | 4 | 30 | 1.365 | 0.270 | 0.720 | 0.154 |  |
| claude | actionability | level x category | 8 | 30 | 0.756 | 0.643 | 1.000 | 0.168 |  |
| claude | specificity | level | 2 | 30 | 4.939 | 0.014 | 0.028 | 0.248 |  |
| claude | specificity | category | 4 | 30 | 1.457 | 0.240 | 0.720 | 0.163 |  |
| claude | specificity | level x category | 8 | 30 | 0.684 | 0.702 | 1.000 | 0.154 |  |
| llama | technical_accuracy | level | 2 | 30 | 1.229 | 0.307 | 0.609 | 0.076 |  |
| llama | technical_accuracy | category | 4 | 30 | 3.329 | 0.023 | 0.068 | 0.307 |  |
| llama | technical_accuracy | level x category | 8 | 30 | 4.550 | 0.001 | 0.004 | 0.548 |  |
| llama | root_cause_correctness | level | 2 | 30 | 1.682 | 0.203 | 0.609 | 0.101 |  |
| llama | root_cause_correctness | category | 4 | 30 | 0.386 | 0.817 | 0.817 | 0.049 |  |
| llama | root_cause_correctness | level x category | 8 | 30 | 1.852 | 0.106 | 0.304 | 0.331 |  |
| llama | actionability | level | 2 | 30 | 1.264 | 0.297 | 0.609 | 0.078 |  |
| llama | actionability | category | 4 | 30 | 1.113 | 0.369 | 0.737 | 0.129 |  |
| llama | actionability | level x category | 8 | 30 | 1.877 | 0.101 | 0.304 | 0.334 |  |
| llama | specificity | level | 2 | 30 | 2.297 | 0.118 | 0.472 | 0.133 |  |
| llama | specificity | category | 4 | 30 | 3.735 | 0.014 | 0.056 | 0.332 |  |
| llama | specificity | level x category | 8 | 30 | 0.616 | 0.757 | 0.757 | 0.141 |  |


**Assumption checks:**

| model_key | dv | shapiro_W | shapiro_p | levene_W | levene_p |
|---|---|---|---|---|---|
| gpt | technical_accuracy | 0.955 | 0.082 | 0.594 | 0.848 |
| gpt | root_cause_correctness | 0.896 | < .001 | 0.629 | 0.820 |
| gpt | actionability | 0.968 | 0.247 | 0.394 | 0.966 |
| gpt | specificity | 0.941 | 0.024 | 0.648 | 0.803 |
| claude | technical_accuracy | 0.951 | 0.057 | 0.450 | 0.942 |
| claude | root_cause_correctness | 0.933 | 0.012 | 0.474 | 0.929 |
| claude | actionability | 0.973 | 0.374 | 0.358 | 0.977 |
| claude | specificity | 0.946 | 0.037 | 0.965 | 0.509 |
| llama | technical_accuracy | 0.932 | 0.011 | 0.593 | 0.849 |
| llama | root_cause_correctness | 0.812 | < .001 | 0.857 | 0.608 |
| llama | actionability | 0.978 | 0.544 | 0.298 | 0.990 |
| llama | specificity | 0.954 | 0.072 | 0.157 | 1.000 |


**Tukey HSD between levels (all categories):**

| model_key | dv | from | to | mean_diff | ci_low | ci_high | p_adj |
|---|---|---|---|---|---|---|---|
| gpt | technical_accuracy | minimal | partial | -0.017 | -0.278 | 0.245 | 0.987 |
| gpt | technical_accuracy | partial | full | 0.400 | 0.138 | 0.662 | 0.002 |
| gpt | technical_accuracy | minimal | full | 0.383 | 0.122 | 0.645 | 0.003 |
| gpt | root_cause_correctness | minimal | partial | 0.133 | -0.204 | 0.470 | 0.605 |
| gpt | root_cause_correctness | partial | full | 0.533 | 0.196 | 0.870 | 0.001 |
| gpt | root_cause_correctness | minimal | full | 0.667 | 0.330 | 1.004 | < .001 |
| gpt | actionability | minimal | partial | 0.367 | -0.128 | 0.861 | 0.182 |
| gpt | actionability | partial | full | 0.567 | 0.072 | 1.061 | 0.022 |
| gpt | actionability | minimal | full | 0.933 | 0.439 | 1.428 | < .001 |
| gpt | specificity | minimal | partial | 0.019 | -0.024 | 0.061 | 0.539 |
| gpt | specificity | partial | full | 0.059 | 0.016 | 0.101 | 0.005 |
| gpt | specificity | minimal | full | 0.078 | 0.035 | 0.120 | < .001 |
| claude | technical_accuracy | minimal | partial | 0.100 | -0.182 | 0.382 | 0.667 |
| claude | technical_accuracy | partial | full | 0.233 | -0.049 | 0.515 | 0.122 |
| claude | technical_accuracy | minimal | full | 0.333 | 0.051 | 0.615 | 0.017 |
| claude | root_cause_correctness | minimal | partial | 0.100 | -0.275 | 0.475 | 0.794 |
| claude | root_cause_correctness | partial | full | 0.467 | 0.092 | 0.842 | 0.012 |
| claude | root_cause_correctness | minimal | full | 0.567 | 0.192 | 0.942 | 0.002 |
| claude | actionability | minimal | partial | 0.200 | -0.406 | 0.806 | 0.704 |
| claude | actionability | partial | full | 0.700 | 0.094 | 1.306 | 0.020 |
| claude | actionability | minimal | full | 0.900 | 0.294 | 1.506 | 0.002 |
| claude | specificity | minimal | partial | 0.027 | -0.018 | 0.073 | 0.326 |
| claude | specificity | partial | full | 0.032 | -0.013 | 0.078 | 0.211 |
| claude | specificity | minimal | full | 0.060 | 0.014 | 0.105 | 0.008 |
| llama | technical_accuracy | minimal | partial | 0.117 | -0.153 | 0.386 | 0.549 |
| llama | technical_accuracy | partial | full | -0.017 | -0.286 | 0.253 | 0.988 |
| llama | technical_accuracy | minimal | full | 0.100 | -0.169 | 0.369 | 0.642 |
| llama | root_cause_correctness | minimal | partial | 0.100 | -0.226 | 0.426 | 0.738 |
| llama | root_cause_correctness | partial | full | 0.133 | -0.193 | 0.459 | 0.585 |
| llama | root_cause_correctness | minimal | full | 0.233 | -0.093 | 0.559 | 0.203 |
| llama | actionability | minimal | partial | 0.300 | -0.222 | 0.822 | 0.353 |
| llama | actionability | partial | full | -0.067 | -0.589 | 0.456 | 0.948 |
| llama | actionability | minimal | full | 0.233 | -0.289 | 0.756 | 0.529 |
| llama | specificity | minimal | partial | 0.022 | -0.023 | 0.068 | 0.469 |
| llama | specificity | partial | full | 0.014 | -0.031 | 0.060 | 0.725 |
| llama | specificity | minimal | full | 0.037 | -0.009 | 0.082 | 0.137 |


**Rank-based checks:**

| model_key | dv | test | factor | statistic | p | effect_size | effect_measure | note |
|---|---|---|---|---|---|---|---|---|
| gpt | technical_accuracy | Kruskal-Wallis | level | 13.244 | 0.001 | 0.301 | epsilon2 |  |
| gpt | technical_accuracy | Kruskal-Wallis | category | 4.295 | 0.368 | 0.098 | epsilon2 |  |
| gpt | technical_accuracy | Friedman (blocks: scenario) | level | 10.360 | 0.006 | 0.345 | Kendall W |  |
| gpt | root_cause_correctness | Kruskal-Wallis | level | 16.527 | < .001 | 0.376 | epsilon2 |  |
| gpt | root_cause_correctness | Kruskal-Wallis | category | 2.335 | 0.674 | 0.053 | epsilon2 |  |
| gpt | root_cause_correctness | Friedman (blocks: scenario) | level | 12.043 | 0.002 | 0.401 | Kendall W |  |
| gpt | actionability | Kruskal-Wallis | level | 15.297 | < .001 | 0.348 | epsilon2 |  |
| gpt | actionability | Kruskal-Wallis | category | 2.815 | 0.589 | 0.064 | epsilon2 |  |
| gpt | actionability | Friedman (blocks: scenario) | level | 14.604 | < .001 | 0.487 | Kendall W |  |
| gpt | specificity | Kruskal-Wallis | level | 19.033 | < .001 | 0.433 | epsilon2 |  |
| gpt | specificity | Kruskal-Wallis | category | 6.600 | 0.159 | 0.150 | epsilon2 |  |
| gpt | specificity | Friedman (blocks: scenario) | level | 19.733 | < .001 | 0.658 | Kendall W |  |
| claude | technical_accuracy | Kruskal-Wallis | level | 8.076 | 0.018 | 0.184 | epsilon2 |  |
| claude | technical_accuracy | Kruskal-Wallis | category | 2.361 | 0.670 | 0.054 | epsilon2 |  |
| claude | technical_accuracy | Friedman (blocks: scenario) | level | 5.442 | 0.066 | 0.181 | Kendall W |  |
| claude | root_cause_correctness | Kruskal-Wallis | level | 11.784 | 0.003 | 0.268 | epsilon2 |  |
| claude | root_cause_correctness | Kruskal-Wallis | category | 6.093 | 0.192 | 0.138 | epsilon2 |  |
| claude | root_cause_correctness | Friedman (blocks: scenario) | level | 10.432 | 0.005 | 0.348 | Kendall W |  |
| claude | actionability | Kruskal-Wallis | level | 11.786 | 0.003 | 0.268 | epsilon2 |  |
| claude | actionability | Kruskal-Wallis | category | 4.679 | 0.322 | 0.106 | epsilon2 |  |
| claude | actionability | Friedman (blocks: scenario) | level | 9.522 | 0.009 | 0.317 | Kendall W |  |
| claude | specificity | Kruskal-Wallis | level | 9.603 | 0.008 | 0.218 | epsilon2 |  |
| claude | specificity | Kruskal-Wallis | category | 6.869 | 0.143 | 0.156 | epsilon2 |  |
| claude | specificity | Friedman (blocks: scenario) | level | 6.933 | 0.031 | 0.231 | Kendall W |  |
| llama | technical_accuracy | Kruskal-Wallis | level | 0.848 | 0.654 | 0.019 | epsilon2 |  |
| llama | technical_accuracy | Kruskal-Wallis | category | 8.858 | 0.065 | 0.201 | epsilon2 |  |
| llama | technical_accuracy | Friedman (blocks: scenario) | level | 1.000 | 0.607 | 0.033 | Kendall W |  |
| llama | root_cause_correctness | Kruskal-Wallis | level | 3.198 | 0.202 | 0.073 | epsilon2 |  |
| llama | root_cause_correctness | Kruskal-Wallis | category | 1.695 | 0.792 | 0.039 | epsilon2 |  |
| llama | root_cause_correctness | Friedman (blocks: scenario) | level | 3.000 | 0.223 | 0.100 | Kendall W |  |
| llama | actionability | Kruskal-Wallis | level | 1.504 | 0.471 | 0.034 | epsilon2 |  |
| llama | actionability | Kruskal-Wallis | category | 3.397 | 0.494 | 0.077 | epsilon2 |  |
| llama | actionability | Friedman (blocks: scenario) | level | 1.240 | 0.538 | 0.041 | Kendall W |  |
| llama | specificity | Kruskal-Wallis | level | 2.180 | 0.336 | 0.050 | epsilon2 |  |
| llama | specificity | Kruskal-Wallis | category | 11.230 | 0.024 | 0.255 | epsilon2 |  |
| llama | specificity | Friedman (blocks: scenario) | level | 5.200 | 0.074 | 0.173 | Kendall W |  |


**Means by category:**

| dv | category | gpt | claude | llama |
|---|---|---|---|---|
| technical_accuracy | schema_drift | 0.639 | 0.667 | 0.333 |
| technical_accuracy | null_rate_anomaly | 0.778 | 0.750 | 0.194 |
| technical_accuracy | row_count_anomaly | 0.722 | 0.806 | 0.028 |
| technical_accuracy | referential_integrity | 0.556 | 0.611 | 0.278 |
| technical_accuracy | freshness_violation | 0.500 | 0.722 | 0.361 |
| root_cause_correctness | schema_drift | 0.556 | 0.444 | 0.278 |
| root_cause_correctness | null_rate_anomaly | 0.389 | 0.278 | 0.111 |
| root_cause_correctness | row_count_anomaly | 0.556 | 0.722 | 0.111 |
| root_cause_correctness | referential_integrity | 0.278 | 0.333 | 0.167 |
| root_cause_correctness | freshness_violation | 0.389 | 0.667 | 0.222 |
| actionability | schema_drift | 2.222 | 2.111 | 1.833 |
| actionability | null_rate_anomaly | 2.111 | 2.111 | 1.500 |
| actionability | row_count_anomaly | 2.278 | 2.556 | 1.389 |
| actionability | referential_integrity | 2.222 | 2.000 | 1.778 |
| actionability | freshness_violation | 1.833 | 2.556 | 1.722 |
| specificity | schema_drift | 0.807 | 0.816 | 0.756 |
| specificity | null_rate_anomaly | 0.779 | 0.797 | 0.721 |
| specificity | row_count_anomaly | 0.795 | 0.819 | 0.711 |
| specificity | referential_integrity | 0.812 | 0.801 | 0.681 |
| specificity | freshness_violation | 0.770 | 0.766 | 0.749 |


**Misdiagnosis and false confidence on the expert scores** (135 answers; root cause 0.5 = the experts disagree, counted as neither wrong nor right):

| model_key | level | answers | misdiagnosis_rate | false_confidence_rate | wrong_asserted_share | right_asserted_share | hedges_when_wrong | hedges_when_right |
|---|---|---|---|---|---|---|---|---|
| gpt | minimal | 15 | 0.800 | 0.133 | 0.167 | 0.500 | 0.917 | 0.500 |
| gpt | partial | 15 | 0.600 | 0.200 | 0.333 | 0.667 | 0.778 | 0.333 |
| gpt | full | 15 | 0.133 | 0.000 | 0.000 | 0.250 | 1.500 | 1.167 |
| gpt | all | 45 | 0.511 | 0.111 | 0.217 | 0.353 | 0.913 | 0.941 |
| claude | minimal | 15 | 0.733 | 0.200 | 0.273 | 0.000 | 1.545 | 2.250 |
| claude | partial | 15 | 0.533 | 0.267 | 0.500 | 0.500 | 1.000 | 0.750 |
| claude | full | 15 | 0.133 | 0.000 | 0.000 | 0.500 | 1.500 | 0.917 |
| claude | all | 45 | 0.467 | 0.156 | 0.333 | 0.400 | 1.333 | 1.150 |
| llama | minimal | 15 | 0.933 | 0.533 | 0.571 | 1.000 | 0.571 | 0.000 |
| llama | partial | 15 | 0.800 | 0.200 | 0.250 | 1.000 | 0.833 | 0.000 |
| llama | full | 15 | 0.667 | 0.400 | 0.600 | 0.500 | 0.500 | 0.750 |
| llama | all | 45 | 0.800 | 0.378 | 0.472 | 0.714 | 0.639 | 0.429 |


| model_key | category | answers | misdiagnosis_rate | false_confidence_rate | wrong_asserted_share | right_asserted_share | hedges_when_wrong | hedges_when_right |
|---|---|---|---|---|---|---|---|---|
| gpt | schema_drift | 9 | 0.333 | 0.111 | 0.333 | 0.500 | 1.000 | 0.500 |
| gpt | null_rate_anomaly | 9 | 0.556 | 0.333 | 0.600 | 0.000 | 0.600 | 1.667 |
| gpt | row_count_anomaly | 9 | 0.444 | 0.000 | 0.000 | 0.600 | 1.250 | 0.600 |
| gpt | referential_integrity | 9 | 0.667 | 0.000 | 0.000 | 0.500 | 1.000 | 0.500 |
| gpt | freshness_violation | 9 | 0.556 | 0.111 | 0.200 | 0.000 | 0.800 | 1.667 |
| claude | schema_drift | 9 | 0.556 | 0.333 | 0.600 | 0.500 | 0.800 | 0.750 |
| claude | null_rate_anomaly | 9 | 0.667 | 0.111 | 0.167 | 0.000 | 1.833 | 2.500 |
| claude | row_count_anomaly | 9 | 0.222 | 0.111 | 0.500 | 0.333 | 2.000 | 1.833 |
| claude | referential_integrity | 9 | 0.667 | 0.222 | 0.333 | 0.667 | 1.000 | 0.333 |
| claude | freshness_violation | 9 | 0.222 | 0.000 | 0.000 | 0.400 | 1.500 | 0.600 |
| llama | schema_drift | 9 | 0.667 | 0.222 | 0.333 | 1.000 | 0.667 | 0.000 |
| llama | null_rate_anomaly | 9 | 0.889 | 0.444 | 0.500 | 1.000 | 0.625 | 0.000 |
| llama | row_count_anomaly | 9 | 0.889 | 0.444 | 0.500 | 0.000 | 0.625 | 2.000 |
| llama | referential_integrity | 9 | 0.778 | 0.222 | 0.286 | 1.000 | 1.000 | 0.000 |
| llama | freshness_violation | 9 | 0.778 | 0.556 | 0.714 | 0.500 | 0.286 | 0.500 |


## Files

Tables (CSV, every row has `data_label`): `agreement.csv`, `anova.csv`, `anova_experts.csv`, `assumptions.csv`, `assumptions_experts.csv`, `cells.csv`, `cells_experts.csv`, `consistency.csv`, `context.csv`, `descriptives_category.csv`, `descriptives_category_experts.csv`, `descriptives_cells.csv`, `descriptives_level.csv`, `descriptives_level_experts.csv`, `descriptives_root_cause_type.csv`, `hallucination_check.csv`, `nonparametric.csv`, `nonparametric_experts.csv`, `rater_difference.csv`, `rates.csv`, `rates_experts.csv`, `rep_spread.csv`, `tukey.csv`, `tukey_experts.csv`

Figures: `results/figures/fig1_context_effect.png`, `results/figures/fig2_category_level_heatmaps.png`, `results/figures/fig3_specificity.png`, `results/figures/fig4_reliability.png`
