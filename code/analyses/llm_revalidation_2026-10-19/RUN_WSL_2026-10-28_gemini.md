# Gemini arm resume, 2026-10-28 (no API key is read, printed or logged by anything here)

## Where the Gemini arm stopped on 2026-10-20

The synchronous jobs hit the per-day request quota (429) after about 150 chunks per disorder, the Batch API chain then ran until the prepaid credits ran out (402, "prepayment credits are depleted"), after which every returned request carried "Precondition check failed" and the last batch create was refused. State in _gbatches/ (requests done, of total): A_ASD 459 of 1,261, A_SCZ 495 of 1,235, A_ID 90 of 740, A_NCD 87 of 374, C_ASD, C_SCZ, C_ID and C_NCD 20 each of 328, 367, 332 and 335. Three batches are still marked pending (A_ASD 802, A_SCZ 740, A_NCD 225 requests) and will be collected as errors and resubmitted. Part B (anchor re-attribution) finished for all four disorders on 2026-10-20 and is already in the record. Ledger so far: 10.79 USD.

Projection at the measured batch price (about 0.011 USD per part A request, 0.007 to 0.010 per part C request): about 28 USD for the 2,479 part A requests left and about 11 USD for the 1,282 part C requests left, so about 40 USD, before any retries. The chain stops by itself if a batch comes back mostly errors, and the cap below is the hard limit.

## Before pasting

1. Top up the prepaid credits in Google AI Studio (the 402 of 2026-10-20 was the balance, not the quota). 60 USD covers the projection with room for retries.
2. GOOGLE_API_KEY in the shell, as for the 2026-10-20 runs.

## Terminal 1, the resume (one line, runs unattended, hours at the Batch API's pace)

```bash
cd "<project root>"; H=audit/llm_revalidation_2026-10-19; mkdir -p _judgeswap/logs
nohup bash $H/gemini_resume.sh 100 > _judgeswap/logs/gemini_resume.log 2>&1 &
```

Monitoring, any time: `tail -n 5 _judgeswap/logs/gemini_resume.log; cat _judgeswap/*_gemini.status`

If the log ends with "run step stopped" read the lines above it: "STOP: batch create refused" with 402 again means the credits did not land, "STOP: ... came back with N errors" means a batch failed after submission (billing or quota), and in both cases the same nohup line resumes from where it stopped once the cause is fixed. Nothing done is ever resubmitted.

## When the log ends with "gemini resume finished" and all four status files say DONE

```bash
cd "<project root>"; H=audit/llm_revalidation_2026-10-19
python3 $H/evalA3.py
python3 $H/eval_partC.py claude gemini
```

Output: _judgeswap/evalA3.md (now with the gemini arm and three more contrasts: gemini minus openai under the same designed prompt, gemini minus record, gemini minus claude) and PARTC_RESULTS.md with the gemini column. Paste evalA3.md to Claude.

## What the result decides

The second independent vendor under the designed prompt. If gemini agrees with claude on SCZ (both well above the record), the SCZ dependence is a property of the record's judge and the manuscript says so; if gemini sits with gpt-5.4, the two vendors disagree and the manuscript reports SCZ as judge-dependent with no majority. Either way the "gemini-2.5-pro arms: pending" row of Table 10 is filled and [TBD ruling 1] closes.

## Files (md5 at commit, 2026-10-28)

New: gemini_resume.sh 7d9a2c57e8f2dd7cd31a1ec14c72166e. Patched: evalA3.py 79b49ebb05f179f4d7918393e0e4f23d (gemini arm and contrasts added, backup evalA3.py.bak_pre_gemini_2026-10-28). gemini_batch.py, run_judgeswap.sh, rejudge_record_pairs.py untouched.

## Afternoon of 2026-10-28: state after both resumes

Part A is complete for all four disorders and evaluated (evalA3.md, evalA3.json carry the gemini arm; the eval was run one disorder at a time, which evalA3.py now supports by merging into the existing json). Part C stopped at a second credit depletion: ASD 379 of 388 terms, SCZ 234 of 423, IDD 83 of 393, NCD 81 of 396, about 8 USD left at the batch price. To finish part C, top up the credits once more, then:

```bash
cd "<project root>"; H=audit/llm_revalidation_2026-10-19
python3 $H/gemini_batch.py run C_ASD C_SCZ C_ID C_NCD --budget_usd 100
for D in ASD SCZ ID NCD; do python3 $H/reclassify_mp_criterion_independent.py --disorder $D --backend gemini --model gemini-2.5-pro --terms_file _reclass/sample/partC_sample_$D.tsv --ingest _gbatches/C_$D/results.jsonl --no_api; done
python3 $H/eval_partC.py claude gemini
```

The first line waits for the batches itself (minutes to hours). Paste PARTC_RESULTS.md when it is done. md5 of evalA3.py after the merge change: b757e7a4a630340955c9c8fdabf1a0bc.
