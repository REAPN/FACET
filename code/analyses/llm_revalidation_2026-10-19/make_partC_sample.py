#!/usr/bin/env python3
import csv, hashlib, random
from pathlib import Path
RUNS = {"ASD": "taxonomy_v2_full/run_ASD", "SCZ": "taxonomy_v2_full/prod_SCZ_2026-07-28",
        "ID": "taxonomy_v2_full/run_ID", "NCD": "taxonomy_v2_full/prod_NCD_2026-07-28"}
N_NEG, SEED = 300, 20261020
out = Path("_reclass/sample"); out.mkdir(parents=True, exist_ok=True)
for D, run in RUNS.items():
    rows = list(csv.DictReader(open(f"{run}/03_taxonomy.tsv", encoding="utf-8"), delimiter="\t"))
    labels = [r["mp_label"] for r in rows]; assert len(labels) == len(set(labels)), D
    pos = [r for r in rows if str(r["admissible_directionaware"]).lower() == "true"]
    neg = [r for r in rows if str(r["admissible_directionaware"]).lower() != "true"]
    pick = random.Random(SEED).sample(range(len(neg)), N_NEG)
    chosen = [(r, "record_admitted") for r in pos] + [(neg[i], "record_not_admitted") for i in sorted(pick)]
    f = out / f"partC_sample_{D}.tsv"
    with f.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t"); w.writerow(["mp_id", "mp_label", "stratum", "stratum_N", "stratum_n"])
        for r, s in chosen:
            w.writerow([r["mp_id"], r["mp_label"], s, len(pos) if s == "record_admitted" else len(neg),
                        len(pos) if s == "record_admitted" else N_NEG])
    print(f"{D}: {len(pos)} admitted (all) + {N_NEG} of {len(neg)} not admitted = {len(chosen)}; md5 {hashlib.md5(f.read_bytes()).hexdigest()}")
