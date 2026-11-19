#!/usr/bin/env python3
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

import rerank_ambiguous_pairs_api_v3 as R
import judge_backends as JB

BASE_DEV_PROMPT = """
You are reranking ambiguous cross-species phenotype candidate pairs.

Important constraints:
- You are not the primary scorer.
- Transparent non-LLM signals have already identified a small ambiguous bundle.
- Your job is only to promote, keep, demote, or abstain on those candidates.
- Ignore any hidden prior about disease genes or disorder labels; you are not given them.
- Do not use any hand-built tier or relevance hierarchy; judge only behavioral/sensory/developmental analog quality.

Definitions:
- comparable_observable=true only if the mouse term is an organism-level or developmentally interpretable observable that could plausibly support the human target.
- evidence_scope=cellular_or_circuit_only if the term is primarily mechanistic physiology or cellular/circuit description rather than a behavioral/sensory/developmental organism-level phenotype.
- strict_eligible=true only for high-quality organism-level analogs suitable for strict domain support; the disorder-specific construct-validity criteria are appended by the wrapper as a developer_prompt_addendum.
- broad_eligible=true for weaker but still meaningful support.
- abstain if none of the candidates are suitable organism-level analogs.

Do not invent new candidates. Evaluate only the listed bundle.
""".strip()

DISORDER_ALIAS = {"asd": "asd", "scz": "scz", "id": "intellectualdisability",
                  "intellectualdisability": "intellectualdisability", "mdd": "mdd", "anxiety": "anxiety"}

RERANK_RESULT_COLS = ["candidate_index", "rerank_action", "comparable_observable", "evidence_scope",
                      "behavioral_analog_type", "strict_eligible", "broad_eligible", "reason",
                      "rerank_delta", "final_pair_score"]


def find_addendum(obj) -> str:
    if isinstance(obj, dict):
        v = obj.get("developer_prompt_addendum")
        if isinstance(v, str) and v.strip():
            return v
        for s in obj.values():
            r = find_addendum(s)
            if r:
                return r
    elif isinstance(obj, list):
        for s in obj:
            r = find_addendum(s)
            if r:
                return r
    return ""


def mdd_developer_prompt(src_dir: Path) -> str:
    import ast
    p = src_dir / "rerank_ambiguous_pairs_api_v3_mdd.py"
    tree = ast.parse(p.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "developer_prompt" for t in node.targets):
            v = node.value
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and isinstance(v.func.value, ast.Constant):
                return v.func.value.value.strip()
            if isinstance(v, ast.Constant):
                return v.value.strip()
    raise RuntimeError(f"MDD developer_prompt not found in {p}")


def dev_prompt_for(disorder: str, config_dir: Path) -> str:
    d = disorder.strip().lower()
    if d == "mdd":
        return mdd_developer_prompt(config_dir)
    stem = DISORDER_ALIAS.get(d, d)
    cfg = config_dir / f"{stem}.disorder.json"
    add = find_addendum(json.loads(cfg.read_text(encoding="utf-8"))) if cfg.exists() else ""
    if not add:
        print(f"WARNING: no developer_prompt_addendum for '{disorder}' ({cfg}); base prompt only.")
    return BASE_DEV_PROMPT if not add else BASE_DEV_PROMPT + "\n\n" + add.strip()


def build_user_prompt(target_id, hpo_label, target_text, domain, bundle: pd.DataFrame) -> str:
    cand_lines = []
    for i, (_, r) in enumerate(bundle.iterrows(), start=1):
        pieces = [
            f"[{i}] mp_id={r['mp_id']}",
            f"mp_term={r['mp_term']}",
            f"mp_definition={R.clean(r.get('mp_definition',''))}",
            f"mouse_domain={r['mouse_domain']}",
            f"transparent_score={float(r['transparent_score']):.3f}",
            f"embed={R.fmt_opt(r.get('embed_norm'))}",
            f"lexical={R.fmt_opt(r.get('lexical_norm'))}",
            f"resnik={R.fmt_opt(r.get('resnik_norm'))}",
            f"jaccard={R.fmt_opt(r.get('jaccard_norm'))}",
            f"available_channels={int(r.get('n_available_channels',0))}",
            f"structural_missing={bool(r.get('structural_missing', False))}",
        ]
        cand_lines.append(" | ".join(pieces))
    return f"""
Target ID: {target_id}
Human target label: {hpo_label}
Human target text: {target_text}
Domain: {domain}

Ambiguous candidate bundle:
{chr(10).join(cand_lines)}

Return evaluations for the listed candidates only. Use candidate_index values 1..{len(bundle)}.
""".strip()


def stub_bundle(target_id, bundle: pd.DataFrame) -> dict:
    return {"target_id": target_id, "selected_candidates": [
        {"candidate_index": i, "rerank_action": "keep", "comparable_observable": True,
         "evidence_scope": "organism_behavior", "behavioral_analog_type": "close_support",
         "strict_eligible": False, "broad_eligible": True, "reason": "stub"}
        for i in range(1, len(bundle) + 1)]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--disorder", required=True, help="asd | scz | id | mdd | anxiety")
    ap.add_argument("--reference_rerank_dir", required=True,
                    help="the gpt-5.4 run dir, e.g. asd_pair_rerank_v3 (provides 03_reranked_pairs.tsv + 01_ambiguous_bundles.tsv)")
    ap.add_argument("--backend", required=True, choices=["openai", "gemini", "claude", "stub"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--config_dir", default=".")
    ap.add_argument("--top_n_bundle", type=int, default=5)
    ap.add_argument("--promote_bonus", type=float, default=0.10)
    ap.add_argument("--demote_penalty", type=float, default=0.10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    ref = Path(args.reference_rerank_dir)
    outdir = Path(args.outdir); outdir.mkdir(parents=True, exist_ok=True)

    full = R.read_table(ref / "03_reranked_pairs.tsv")
    all_ranked = full.drop(columns=[c for c in RERANK_RESULT_COLS if c in full.columns]).copy()

    raw_path_ref = ref / "02_rerank_raw.jsonl"
    if raw_path_ref.exists():
        amb, seen = [], set()
        for line in raw_path_ref.open("r", encoding="utf-8"):
            if line.strip():
                t = json.loads(line).get("target_id")
                if t is not None and t not in seen:
                    seen.add(t); amb.append(t)
    else:
        bundles = R.read_table(ref / "01_ambiguous_bundles.tsv")
        amb_mask = bundles["ambiguous"].astype(str).str.lower().isin(["true", "1"])
        amb = bundles[amb_mask]["target_id"].tolist()

    system = dev_prompt_for(args.disorder, Path(args.config_dir))

    raw_path = outdir / "02_rerank_raw.jsonl"
    done = set()
    if args.resume and raw_path.exists():
        for line in raw_path.open("r", encoding="utf-8"):
            if line.strip():
                try:
                    done.add(json.loads(line).get("target_id"))
                except Exception:
                    pass

    if not args.resume and raw_path.exists():
        raw_path.unlink()

    with raw_path.open("a", encoding="utf-8") as fout:
        for target_id in amb:
            if target_id in done:
                continue
            g = all_ranked[all_ranked["target_id"] == target_id].sort_values("transparent_rank").head(args.top_n_bundle).copy()
            if g.empty:
                continue
            user = build_user_prompt(
                target_id=target_id,
                hpo_label=str(g.iloc[0].get("hpo_label", "")),
                target_text=str(g.iloc[0].get("target_text", "")),
                domain=str(g.iloc[0].get("human_domain", "")),
                bundle=g,
            )
            if args.backend == "stub":
                obj = stub_bundle(target_id, g)
            else:
                obj = JB.bundle_judgment(args.backend, args.model, system, user, seed=args.seed, schema=R.RERANK_SCHEMA)
            obj["target_id"] = target_id
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")

    rerank_rows = []
    for line in raw_path.open("r", encoding="utf-8"):
        if not line.strip():
            continue
        obj = json.loads(line)
        tid = obj["target_id"]
        for rec in obj.get("selected_candidates", []):
            rerank_rows.append({"target_id": tid, **rec})
    rr = pd.DataFrame(rerank_rows)

    merged = all_ranked.copy()
    if not rr.empty:
        merged["candidate_index"] = merged.groupby("target_id").cumcount() + 1
        merged = merged.merge(rr, on=["target_id", "candidate_index"], how="left")
    else:
        for c in ["rerank_action", "comparable_observable", "evidence_scope",
                  "behavioral_analog_type", "strict_eligible", "broad_eligible", "reason"]:
            merged[c] = np.nan

    action_delta = {"promote": args.promote_bonus, "keep": 0.0,
                    "demote": -args.demote_penalty, "abstain": -0.25}
    merged["rerank_delta"] = merged["rerank_action"].map(action_delta).fillna(0.0)
    merged["final_pair_score"] = (merged["transparent_score"] + merged["rerank_delta"]).clip(lower=0.0, upper=1.0)
    merged.to_csv(outdir / "03_reranked_pairs.tsv", sep="\t", index=False)

    (outdir / "07_run_config.json").write_text(json.dumps(
        {"disorder": args.disorder, "reference_rerank_dir": str(ref), "backend": args.backend,
         "model": args.model, "top_n_bundle": args.top_n_bundle, "seed": args.seed,
         "promote_bonus": args.promote_bonus, "demote_penalty": args.demote_penalty,
         "prompt_mode": ("mdd_wholesale" if args.disorder.strip().lower() == "mdd" else "base+addendum"),
         "mode": "faithful bundle replay; only the model call differs from gpt-5.4"}, indent=2),
        encoding="utf-8")

    n_amb = len(amb)
    n_strict = int(pd.to_numeric(merged.get("strict_eligible"), errors="coerce").fillna(0).astype(bool).sum()) if "strict_eligible" in merged.columns else 0
    print(f"Done [{args.backend}/{args.disorder}]. ambiguous targets re-judged: {n_amb} | "
          f"rows: {len(merged)} | strict_eligible pairs: {n_strict} | out -> {outdir.resolve()}")


if __name__ == "__main__":
    main()
