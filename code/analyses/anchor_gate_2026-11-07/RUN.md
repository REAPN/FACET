# Anchor gate rerun, 2026-11-07 (needs OPENAI_API_KEY in the environment)

From the project folder, in the WSL environment of record. About 75 calls in all, gpt-5.4 for the criterion step and gpt-5.4-mini for the two domain-labeling pilots.

    python3 audit/anchor_gate_2026-11-07/build_gate_sets.py          # already run, rewrites the gate files identically

    # criterion-grounded classifier of record (prompt v4), 15 terms each, fresh outdirs
    python3 classify_mp_terms_criterion_grounded.py --spec criterion_specs/ASD.json --pilot audit/anchor_gate_2026-11-07/gate_ASD.tsv --outdir audit/anchor_gate_2026-11-07/run_ASD
    python3 classify_mp_terms_criterion_grounded.py --spec criterion_specs/ID.json  --pilot audit/anchor_gate_2026-11-07/gate_ID.tsv  --outdir audit/anchor_gate_2026-11-07/run_ID
    python3 classify_mp_terms_criterion_grounded.py --spec criterion_specs/NCD.json --pilot audit/anchor_gate_2026-11-07/gate_NCD.tsv --outdir audit/anchor_gate_2026-11-07/run_NCD
    python3 audit/anchor_gate_2026-11-07/score_gate.py

    # domain-labeling pilots (print pass/fail and exit without writing a taxonomy)
    python3 audit/anchor_gate_2026-11-07/run_scz_gate.py                 2>&1 | tee audit/anchor_gate_2026-11-07/pilot_SCZ.log
    python3 rebuild_mdd_taxonomy.py --pilot --outdir audit/anchor_gate_2026-11-07/run_MDD --cache_dir audit/anchor_gate_2026-11-07/run_MDD/cache 2>&1 | tee audit/anchor_gate_2026-11-07/pilot_MDD.log

Check the printed prompt sha of each classifier run against the record (ASD 313ec80ceb9d1caf, ID e5db1b06dfb0f3bd, NCD 550477b5aa685622 for prompt v4 of 2026-07-27, per the project memory): if it differs, the classifier prompt has drifted since the record and the result certifies the current prompt, not the record.

Then tell Claude the five results (or paste RESULT_gate.md and the two logs). Nothing here touches the record folders.
