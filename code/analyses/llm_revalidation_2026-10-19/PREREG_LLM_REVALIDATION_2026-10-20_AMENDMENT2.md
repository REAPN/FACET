# Amendment 2 to PREREG_LLM_REVALIDATION_2026-10-19 (2026-10-20, before any part C output exists and before any partial part A Claude verdict was read)

No dash-family characters. The original pre-registration and its erratum stay unchanged.

## Why
The Claude arm of part A ran at the synchronous price without a spend cap and stopped at 01:18Z when the account credit ran out (NCD complete; ASD 647 of 1,419, SCZ 655 of 1,394, IDD 661 of 890 chunks). Nothing in the design changes except transport, sampling of part C and a spend guard.

## Spend guard (all parts, both vendors)
1. No API job runs without an explicit cap (--budget_usd). There is no default.
2. Every response's token usage is written to _judgeswap/ledger/{backend}__{job}.jsonl. The cap is per backend across jobs. A job stops at the cap (exit 5) and resumes on re-run.
3. Every job first runs a random pilot of 20 calls (seed 1) that measures the real cost per call. A full run refuses to start if measured cost times calls left exceeds what is left under the cap.
4. Claude runs only through the Message Batches API (claude_batch.py). The job scripts refuse a synchronous Claude call. A request that is done or inside an uncollected batch is never resubmitted.

## Part A, Claude arm
The remaining chunks are judged through the Message Batches API with the same model (claude-opus-4-8), system prompt, user prompt, tool schema and max_tokens as the synchronous calls. The transport is recorded per chunk (raw.jsonl field transport). The 2,496 chunks judged synchronously on 2026-10-20 are kept. An end-to-end test with record verdicts fed through the batch path reproduced the ASD gate table byte for byte. Outcomes and decision rules are unchanged.

## Part A, Gemini arm
Unchanged design (all record pairs). If the pilots project a cost above the first author's cap, the first author decides between the full run and a documented reduction before any Gemini part A verdict is read.

## Part C, sampled design (replaces the all-terms design)
Per disorder: every term the record admits (admissible_directionaware true: ASD 88, SCZ 123, IDD 93, NCD 96) plus a simple random sample of 300 of the terms the record does not admit (seed 20261020; make_partC_sample.py). 1,600 terms per judge.
Outcomes per disorder and judge, within each stratum: agreement with the record on admissible_directionaware (percent, Wilson 95 percent interval) and on item_id among terms admitted by either. Whole-taxonomy agreement and Cohen kappa are estimated by weighting each stratum by N over n. The list of terms the record admits and neither judge admits is complete (every admitted term is judged). The count of terms both judges admit and the record does not is estimated from the sample with weight N over n, and the sampled terms are listed for An.

## Files (md5)
Sample files:
  _reclass/sample/partC_sample_ASD.tsv 473bb7826a8b919b5b58682218d30462
  _reclass/sample/partC_sample_ID.tsv ac4a54e518177de9218452b6d1e3d4af
  _reclass/sample/partC_sample_NCD.tsv 6e4d4c0f17f9f5ae5f902ea3de68fea4
  _reclass/sample/partC_sample_SCZ.tsv 0c24e164dfcf029da56cf68c10311ba5
Scripts:
  llm_budget.py 55bca6b4f0f24f2e694f80f2373a7095
  claude_batch.py cee3284b8ff5d114025704c030ae4ddc
  rejudge_record_pairs.py fd47512d364b4c112c60c04b1d490cb1
  reclassify_mp_criterion_independent.py 685d340a80ef4325970b8600ea1de388
  reassign_units_independent.py 585612ebedd015428c2ae17c58536f61
  run_judgeswap.sh e5ab6966e6bb444150c0d00e61f3cfe8
  make_partC_sample.py af527d1123e89c081f2e2c40c76e2fbd

## Note 2026-10-20 02:05Z (code fix, no design change)
The Gemini calls of reassign_units_independent.py and reclassify_mp_criterion_independent.py built a temporary genai.Client, which the SDK closes before the request is sent ("Cannot send a request, as the client has been closed"). No Gemini part B or C request reached the API (ledger 0 dollars). Fixed by keeping a reference to the client; the request itself is unchanged. errpolicy.py now treats that error as permanent so a code defect stops a job at once instead of retrying. judge_backends.py (part A) was not affected. New md5:
  reassign_units_independent.py 628a95b66c40cb3a4674db304ddf6ede
  reclassify_mp_criterion_independent.py 5fe8dad23a72d1732ceee683f53f4b59
  errpolicy.py 228b5e29baec90561a105f9a7b3c9651

## Note 2026-10-20 04:15Z (transport change for the Gemini arm, no design change)
The synchronous Gemini jobs stopped at 03:01Z on Google's per-day request quota for gemini-2.5-pro (HTTP 429, not the spend cap). The remaining Gemini requests run through the Gemini Batch API (gemini_batch.py), built with the same GenerateContentConfig objects as the synchronous calls (same model, system instruction, user prompt, temperature 0, seed 1, response schema). Transport is recorded per chunk. A stub end-to-end test with record verdicts fed through the batch path reproduced the ASD gate table byte for byte. The spend guard applies unchanged (pilot, projection gate, cap, ledger at the batch price of 0.625 and 5.00 USD per million tokens). md5:
  gemini_batch.py de924e6f9b717a72fc994b3ce3aba749
  llm_budget.py 9f09a83f6f9786bbf4d41afbbcfa8535
  run_judgeswap.sh 4c82bbfdbc3c03f95831b8b9d6476ba8
