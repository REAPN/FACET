# LLM revalidation, WSL commands (2026-10-19)

From the project root in WSL, in the conda environment of the run of record, with ANTHROPIC_API_KEY and GOOGLE_API_KEY exported in the same shell. Never paste a key into a file, and never `git add` from the project parent folder.

```bash
cd "<project root>"      # adjust to your WSL mount of N:
python3 -c "import anthropic, google.genai, pydantic; print('sdk ok')"   # if this fails: pip install anthropic google-genai pydantic
H=audit/llm_revalidation_2026-10-19

# 0. smoke test, 1 call per vendor (prints a JSON verdict, writes nothing to the run)
python3 $H/smoke_test.py

# 1. gate arms (no API): record verdicts through stages 3 and 4, all four in the background
for D in ASD SCZ ID NCD; do nohup bash $H/run_judgeswap.sh $D cached > /dev/null 2>&1 & done

# 2. independent judges, 8 jobs in the background (resume by re-running the same line)
for D in ASD SCZ ID NCD; do for X in claude gemini; do nohup bash $H/run_judgeswap.sh $D $X 4 > /dev/null 2>&1 & done; done

# 3. anchor reassignment, 8 short jobs
for D in ASD SCZ ID NCD; do for X in claude gemini; do M=claude-opus-4-8; [ $X = gemini ] && M=gemini-2.5-pro
  nohup python3 $H/reassign_units_independent.py --disorder $D --backend $X --model $M > _judgeswap/logs/reassign_${D}_${X}.log 2>&1 & done; done
# optional third arm for SCZ on the current prompt (your OpenAI key, production script):
# python3 decompose_targets_to_criterion_units.py --disorder SCZ --spec criterion_specs/SCZ.json --targets pilot_hpo_run_scz_v1/07_final_resolved_hpo_terms.tsv --outdir _reassign/SCZ_gpt_current

# progress
cat _judgeswap/*.status; tail -n 2 _judgeswap/logs/*_judge.log; ls _reassign/*/03_target_criterion_units.tsv
```

Scale: about 4,236 calls per judge (ASD 1,419, SCZ 1,394, IDD 890, NCD 533 chunks of 5 pairs). With 4 workers per job, expect roughly one to two hours per disorder, then several minutes of stage 4. Lower the worker count (third argument) if a vendor rate-limits. A permanent error (quota, key, model name) stops the job at once and says so in the log.

## Part C, mouse-side reclassification (8 jobs, about 7,400 single-term calls per vendor)
```bash
H=audit/llm_revalidation_2026-10-19; mkdir -p _reclass
for D in ASD SCZ ID NCD; do for X in claude gemini; do M=claude-opus-4-8; [ $X = gemini ] && M=gemini-2.5-pro
  nohup python3 $H/reclassify_mp_criterion_independent.py --disorder $D --backend $X --model $M --workers 3 > _judgeswap/logs/reclass_${D}_${X}.log 2>&1 & done; done
tail -n 2 _judgeswap/logs/reclass_*.log
```
