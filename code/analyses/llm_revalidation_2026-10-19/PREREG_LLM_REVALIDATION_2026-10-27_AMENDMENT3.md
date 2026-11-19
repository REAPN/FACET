# Amendment 3 to PREREG_LLM_REVALIDATION_2026-10-19 (2026-10-27, written before any gpt-5.4 re-judgment under the designed prompt exists)

No dash-family characters. The original pre-registration, its erratum and amendment 2 stay unchanged.

## Why

SETTLEMENT_ADDENDUM_2026-08-09.md section 0 established that the production pair judgment of record ran on the depression variant of the developer prompt for every disorder, because stage2b_rerank.py dispatches on the truthiness of developer_prompt_addendum rather than on the disorder. The ruling then was code fix plus disclosure and no rerun. Part A of this pre-registration gave the independent judges "the production prompts", which rejudge_record_pairs.py builds as the frozen base plus the disorder addendum for bundle-origin pairs and the base alone for fill-origin pairs (rerank_independent_judge.dev_prompt_for). That is the designed prompt and not the prompt the record ran on. The part A contrasts therefore vary the vendor and the developer prompt together, and the SCZ difference of +0.182 (claude minus record) cannot be attributed to the vendor alone.

## Design

One additional arm, backend openai, model gpt-5.4 (the alias of record), temperature 0, seed 1, the production response schema, the same user prompt builder and bundle construction as the Claude and Gemini arms, and the same developer prompt those arms received (base plus disorder addendum for bundle pairs, base for fill pairs). Exactly the record pairs are re-judged (ASD 6,988, SCZ 6,882, IDD 4,398, NCD 2,607), only the verdict columns change, and stages 3 and 4 run with the configurations of record (run_judgeswap.sh DISORDER openai). The served model snapshot is recorded per chunk (raw.jsonl field response_model) and reported.

## Outcomes, fixed before any verdict is read

All on the headline universe (primary) and the full pool, corrected labels of 2026-10-08, strict mode, K4, paired differences in discrimination AUROC with gene-clustered 90 percent intervals (2,000 replicates, seed 20261008, clusters as in audit/geneclust_2026-10-08/common.py), margin 0.05, the same equivalent, not equivalent and inconclusive rule as part A.

1. Prompt effect, vendor held fixed: openai minus record. Primary.
2. Vendor effect, prompt held fixed: claude minus openai. Primary.
3. Reference: claude minus record, as already reported in part A.
4. Pair level, every pair of arms: percent agreement and Cohen kappa on strict_eligible and on behavioral_analog_type, and the counts of pairs admitted by one arm only.

## Reading rules

- If outcome 1 is equivalent for a disorder, the developer prompt variant did not move that disorder's discrimination and the part A result for it stands as a vendor comparison.
- If outcome 1 is not equivalent, the part A difference for that disorder is restated as the sum of a prompt effect (outcome 1) and a vendor effect (outcome 2), and the manuscript reports both.
- Outcome 1 is not a measurement of same-model re-judgment instability, because the prompt differs between the two gpt-5.4 arms. Any such instability is bounded above by outcome 1 only if the prompt effect is assumed to be zero, which this design does not assume.
- No number of record changes. The record stays the record, with the disclosure of SETTLEMENT_ADDENDUM_2026-08-09.md section 0.5 in the Methods.

## Spend guard

Unchanged from amendment 2. The openai ledger is _judgeswap/ledger/openai__A_{D}.jsonl at the price the shell supplies (OPENAI_PRICE_IN_PER_M, OPENAI_PRICE_OUT_PER_M, USD per million tokens) or, when the shell supplies none, at an assumed 2.50 in and 15.00 out per million tokens, chosen above the list price so that the projection gate and the cap err on the safe side (ledger rows then carry mode sync_assumed_price, and the real spend is read from the OpenAI dashboard). The cap is 200 USD (An, 2026-10-27 23:11). --budget_usd is required, each disorder runs a 20-chunk random pilot (seed 1) first and the full run refuses to start if the projection exceeds what is left under the cap.

## Files (md5 recorded at commit, see the end of this file)

Patched: rejudge_record_pairs.py (backend openai, ledger, pilot), llm_budget.py (gpt-5.4 price from the shell, snapshot names bill at the alias price), run_judgeswap.sh (openai case). New: openai_judge.py (the call, identical in every request field to judge_backends.call_openai, returning usage and the served model), evalA3.py (the three-way evaluation). judge_backends.py is untouched.

## md5 at commit, 2026-10-27

In audit/llm_revalidation_2026-10-19/ unless named otherwise:
  rejudge_record_pairs.py 41ed3efcf12d2b9bcb82ea3499a71142
  llm_budget.py d633bcc4acf08029f3717ba936d83296 (23:15: price optional, assumed high when absent, ledger rows tagged)
  run_judgeswap.sh 1b2e230d5aa992a7f2a3fc90659b61e4 (23:15: price no longer required)
  openai_judge.py 454b0b461311d070d2dc0ea8851fa18d
  evalA3.py bd2a66621d06397c77b3db873a0e2ca8
  permutation_null_mirrored.py (project root) dc40d16a53bc07d6aaf990a883f99c71
  run_nullmirror.sh (audit/nullmirror_2026-10-27) 95d49a924ba9c81b276ea637b352d8f1
  eval_mirror.py (audit/nullmirror_2026-10-27) 67d745b0409603b1561d15c6a7cf493e
