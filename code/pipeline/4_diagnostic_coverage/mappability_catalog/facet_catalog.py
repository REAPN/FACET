#!/usr/bin/env python3
import csv, re, json, os, sys, argparse
from collections import defaultdict, Counter

_SELFDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SELFDIR)
BASE = os.environ.get("FACET_BASE") or os.path.dirname(_SELFDIR)
CATDIR = os.path.join(BASE, "mappability_catalog")
TH = 0.6
STOP = set("the a an of or and to in for with is are be by on as at from that this these those may not e g such other more one".split())

DISORDER_CONFIG = {
    "ASD": "asd.disorder.json", "SCZ": "scz.disorder.json",
    "ID": "intellectualdisability.disorder.json", "MDD": "mdd.disorder.json",
    "OCD": "ocd.disorder.json", "PTSD": "ptsd.disorder.json",
    "NCD": "neurocognitive.disorder.json",
}
CIRCULAR_HPO = {"ID": "HP:0001249", "ASD": "HP:0000717", "SCZ": "HP:0100753", "MDD": "HP:0000716"}

def norm(s):
    s = s.lower().replace('/', ' '); s = re.sub(r'[^a-z0-9 ]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
def content(s): return [t for t in norm(s).split() if t not in STOP and len(t) > 1]

def load_config(did):
    p = os.path.join(BASE, DISORDER_CONFIG[did])
    with open(p) as f: return json.load(f)

def paths(did):
    c = load_config(did)
    return dict(
        did=did,
        name=c.get("disorder", {}).get("name", did),
        pilot=c["stage1_hpo_curation"]["outdir"].rstrip("/"),
        rerank=c["stage2_rerank"]["outdir"].rstrip("/"),
        dsm5=c["stage0_dsm5_extraction"]["outdir"].rstrip("/"),
    )

def tb(x): return str(x).strip().lower() == "true"

def rd(path, delim='\t'):
    with open(os.path.join(BASE, path)) as f: return list(csv.DictReader(f, delimiter=delim))

def load_roles():
    roles = defaultdict(dict)
    fp = os.path.join(CATDIR, "criterion_roles.tsv")
    if os.path.exists(fp):
        for r in rd("mappability_catalog/criterion_roles.tsv"):
            roles[r['disorder']][r['criterion']] = r['role']
    return roles
ROLES = load_roles()

def parse_spine(did):
    dsm5 = paths(did)['dsm5']
    raw = open(os.path.join(BASE, dsm5, "01_diagnostic_criteria.txt")).read()
    LET = "ABCDEFGH"
    explicit = set(re.findall(r'(?m)^\s*([A-H])\s*\.\s+', raw))
    sentences = []; cur = None; num = None; sub = 0; prev = 0; buf = []
    def flush():
        if cur and buf: sentences.append((cur, num, ' '.join(buf).strip()))
    for ln in raw.splitlines():
        s = ln.strip()
        if not s: continue
        if s.lower().startswith('specify if'): break
        mL = re.match(r'^([A-H])\s*\.\s+(.*)$', s); mN = re.match(r'^(\d+)\.\s+(.*)$', s)
        if mL:
            flush(); buf = [mL.group(2)]; cur = mL.group(1); num = None; sub = 0; prev = 0
        elif mN and cur:
            n = int(mN.group(1)); flush()
            idx = LET.index(cur); nxt = LET[idx + 1] if idx + 1 < len(LET) else None
            if n <= prev and nxt and nxt not in explicit:
                cur = nxt; sub = 0
            sub += 1; num = str(sub); buf = [mN.group(2)]; prev = n
        else:
            buf.append(s)
    flush()
    spine = []
    for letter, n, text in sentences:
        cid = f"{did}.{letter}{n}" if n else f"{did}.{letter}"
        spine.append(dict(criterion_id=cid, letter=letter, num=n,
                          role=ROLES.get(did, {}).get(letter, 'gate'),
                          text=text, tokens=set(content(text)), norm=norm(text)))
    return spine

def align_fragment(frag, spine):
    ft = content(frag); fn = norm(frag)
    if not ft: return None, None, 0.0
    b = 0.0; bc = None
    for c in spine:
        cont = sum(1 for t in ft if t in c['tokens']) / len(ft)
        sc = 1.0 if (fn and fn in c['norm']) else cont
        if sc > b: b = sc; bc = c
    return (bc['criterion_id'], bc['role'], b) if (bc and b >= TH) else (None, None, b)

def grain(cid):
    d, rest = cid.split('.', 1)
    if d in ('ASD', 'ID') and re.match(r'^[A-H]\d', rest): return f"{d}.{rest[0]}"
    return cid

def load_domain_policy():
    pol = defaultdict(dict)
    fp = os.path.join(CATDIR, "criterion_domain_policy.tsv")
    if os.path.exists(fp):
        for r in rd("mappability_catalog/criterion_domain_policy.tsv"):
            pol[r['disorder']][r['domain']] = r['confirmed_policy']
    return pol
DOMAIN_POLICY = load_domain_policy()

def human_side(did):
    pilot = paths(did)['pilot']
    rows = []
    for r in rd(f"{pilot}/06b_llm_hpo_resolutions.csv", ','):
        resolved = r['decision_status'] == 'resolved'
        rows.append(dict(
            hpo_id=(r.get('selected_hpo_id', '') if resolved else ''),
            hpo_label=r.get('selected_label', ''),
            source_fragment=r['source_fragment'], category=r['category'],
            centrality=r['centrality'], decision_status=r['decision_status']))
    return rows

def circular_hpo(did):
    s = set()
    if did in CIRCULAR_HPO: s.add(CIRCULAR_HPO[did])
    name = norm(paths(did)['name'])
    for r in human_side(did):
        if r['hpo_id'] and r['hpo_label'] and norm(r['hpo_label']) in (name, did.lower()):
            s.add(r['hpo_id'])
    return s

def build_attribution(did):
    spine = parse_spine(did); rows = human_side(did)
    byhpo = defaultdict(list); cat = {}
    for r in rows:
        if r['hpo_id']: byhpo[r['hpo_id']].append(r)
    align = {}
    for h, rs in byhpo.items():
        cat[h] = Counter(x['category'] for x in rs).most_common(1)[0][0]
        best = None
        for x in rs:
            cid, role, sc = align_fragment(x['source_fragment'], spine)
            if cid and (best is None or sc > best[2]): best = (cid, role, sc)
        align[h] = best
    learn = defaultdict(Counter)
    for h, b in align.items():
        if b and b[1] in ('symptom', 'onset'): learn[cat[h]][(grain(b[0]), b[1])] += 1
    dommap = {k: v.most_common(1)[0][0] for k, v in learn.items()}
    pol = DOMAIN_POLICY.get(did, {})
    def assign(h, category=None):
        c = category if category is not None else cat.get(h, '')
        b = align.get(h)
        if b and b[1] in ('symptom', 'onset'): return grain(b[0]), b[1], 'aligned'
        p = pol.get(c, 'align_only')
        if p == 'extend' and c in dommap:
            dm = dommap[c]; return dm[0], dm[1], 'domain_extended'
        if p == 'specifier': return f"{did}.spec", 'specifier', 'specifier'
        if b and b[0]: return grain(b[0]), b[1], 'aligned_nonsymptom'
        return f"{did}.assoc", 'associated', 'associated'
    return assign, circular_hpo(did), dommap

def pair_verdicts(did):
    rerank = paths(did)['rerank']
    strict = defaultdict(int); broad = defaultdict(int); bestmp = {}; bestsc = {}; lab = {}; retr = set()
    for x in rd(f"{rerank}/03_reranked_pairs_filled.tsv"):
        h = x['hpo_id']; retr.add(h); lab[h] = x.get('hpo_label', '')
        try: sc = float(x.get('final_pair_score') or 0)
        except Exception: sc = 0.0
        if tb(x['strict_eligible']):
            strict[h] += 1
            if h not in bestsc or sc > bestsc[h]:
                bestsc[h] = sc; bestmp[h] = f"{x['mp_id']} {x.get('mp_label') or x.get('mp_term')}"
        if tb(x['broad_eligible']): broad[h] += 1
    out = {}
    for h in retr:
        out[h] = dict(n_strict=strict[h], n_broad=broad[h], best_strict_mp=bestmp.get(h, ''),
                      mapped_strict=strict[h] > 0, mapped_broad=broad[h] > 0, label=lab.get(h, ''))
    return out

def build_hpo_mappability(dids, write=True):
    per = defaultdict(dict)
    for did in dids:
        circ = circular_hpo(did)
        for h, v in pair_verdicts(did).items():
            if h in circ: continue
            per[h][did] = v
    rows = []; divergent = 0
    for h, pd in per.items():
        ns = sum(v['n_strict'] for v in pd.values()); nb = sum(v['n_broad'] for v in pd.values())
        verdicts = set(v['mapped_strict'] for v in pd.values())
        diverges = len(verdicts) > 1; divergent += diverges
        best = next((v['best_strict_mp'] for v in pd.values() if v['best_strict_mp']), '')
        lab = next(iter(pd.values()))['label']
        ms = any(v['mapped_strict'] for v in pd.values())
        rows.append(dict(hpo_id=h, hpo_label=lab, disorders=';'.join(pd.keys()),
                         best_strict_mp=best, n_strict=ns, n_broad=nb, mapped_strict=ms,
                         absence_bucket='' if ms else 'adjudicated_none',
                         cross_disorder_divergent=diverges))
    rows.sort(key=lambda r: (-r['n_strict'], r['hpo_label']))
    if write:
        _write_tsv(os.path.join(CATDIR, "hpo_mappability.tsv"), rows,
                   ['hpo_id', 'hpo_label', 'disorders', 'best_strict_mp', 'n_strict', 'n_broad',
                    'mapped_strict', 'absence_bucket', 'cross_disorder_divergent'])
    return rows, divergent

def load_master():
    fp = os.path.join(CATDIR, "hpo_mappability.tsv")
    return {r['hpo_id']: r for r in rd("mappability_catalog/hpo_mappability.tsv")} if os.path.exists(fp) else {}

def master_lookup(did):
    master = load_master()
    pilot = paths(did)['pilot']
    resolved = [r['hpo_id'] for r in rd(f"{pilot}/07_final_resolved_hpo_terms.tsv") if r['hpo_id']]
    free = [h for h in resolved if h in master]
    novel = [h for h in resolved if h not in master]
    return dict(resolved=len(resolved), free=free, novel=novel,
                free_verdicts={h: master[h]['mapped_strict'] for h in free})

def build_catalog(dids, write=True):
    import phenotype_class_hpo as PC
    pheno = []
    crit_text = {}
    for did in dids:
        assign, circ, dommap = build_attribution(did)
        for c in parse_spine(did):
            crit_text.setdefault((did, grain(c['criterion_id'])), c['text'][:120])
        pv = pair_verdicts(did)
        pilot = paths(did)['pilot']
        p07 = rd(f"{pilot}/07_final_resolved_hpo_terms.tsv")
        cat = {r['hpo_id']: r['category'] for r in p07}
        cen = {r['hpo_id']: r['centrality'] for r in p07}
        lab = {r['hpo_id']: r['hpo_label'] for r in p07}
        for h, c in cat.items():
            if h in circ: continue
            cid, role, prov = assign(h)
            v = pv.get(h, dict(n_strict=0, n_broad=0, best_strict_mp='', mapped_strict=False, mapped_broad=False))
            ab = '' if v['n_strict'] > 0 else ('retrieval_null' if h not in pv else 'adjudicated_none')
            pheno.append(dict(disorder=did, criterion_id=cid, role=role, attribution=prov, category=c,
                              hpo_id=h, hpo_label=lab.get(h, ''), centrality=cen.get(h, ''),
                              n_strict=v['n_strict'], n_broad=v['n_broad'],
                              mapped_strict=v['mapped_strict'], mapped_broad=v['mapped_broad'],
                              best_strict_mp=v['best_strict_mp'], absence_bucket=ab,
                              phenotype_class=PC.classify(h, lab.get(h, ''))))
        for r in rd(f"{pilot}/08_unresolved_phenotypes.csv", ','):
            if r.get('decision_status') != 'unresolved': continue
            cid, role, prov = assign(None, category=r['category'])
            pheno.append(dict(disorder=did, criterion_id=cid, role=role, attribution='unresolved',
                              category=r['category'], hpo_id='', hpo_label=r['normalized_phenotype'],
                              centrality=r['centrality'], n_strict=0, n_broad=0, mapped_strict=False,
                              mapped_broad=False, best_strict_mp='', absence_bucket='no_hpo_term',
                              phenotype_class=PC.classify('', r['normalized_phenotype'])))
    grp = defaultdict(list)
    for r in pheno: grp[(r['disorder'], r['criterion_id'])].append(r)
    crows = []
    for (did, cid), ch in grp.items():
        ns = sum(c['n_strict'] for c in ch); nb = sum(c['n_broad'] for c in ch)
        role = Counter(c['role'] for c in ch).most_common(1)[0][0]
        ab = ''
        if ns == 0:
            bk = Counter(c['absence_bucket'] for c in ch if not c['mapped_strict'] and c['absence_bucket'])
            ab = bk.most_common(1)[0][0] if bk else ''
        crows.append(dict(disorder=did, criterion_id=cid, role=role, criterion_text=crit_text.get((did, cid), ''),
                          n_child_phenotypes=len(ch), mapped_strict=ns > 0, mapped_broad=nb > 0,
                          n_strict_pairs=ns, n_broad_pairs=nb, absence_bucket=ab))
    ro = {'symptom': 0, 'onset': 1, 'impairment': 2, 'duration': 3, 'specifier': 4, 'associated': 5, 'exclusion': 6, 'gate': 7}
    crows.sort(key=lambda r: (r['disorder'], ro.get(r['role'], 9), r['criterion_id']))
    pheno.sort(key=lambda r: (r['disorder'], r['criterion_id'], -r['n_strict']))
    if write:
        _write_tsv(os.path.join(CATDIR, "catalog_by_phenotype.tsv"), pheno,
                   ['disorder', 'criterion_id', 'role', 'attribution', 'category', 'hpo_id', 'hpo_label',
                    'centrality', 'n_strict', 'n_broad', 'mapped_strict', 'mapped_broad', 'best_strict_mp',
                    'absence_bucket', 'phenotype_class'])
        _write_tsv(os.path.join(CATDIR, "catalog_by_criterion.tsv"), crows,
                   ['disorder', 'criterion_id', 'role', 'criterion_text', 'n_child_phenotypes', 'mapped_strict',
                    'mapped_broad', 'n_strict_pairs', 'n_broad_pairs', 'absence_bucket'])
    return pheno, crows

def validate_disorder(did):
    import json as _json
    spine = parse_spine(did); rep = {}
    assign, circ, dommap = build_attribution(did)
    rows = human_side(did)
    unassigned = 0
    for r in rows:
        if r['hpo_id'] and assign(r['hpo_id'])[0] is None: unassigned += 1
    rep['check1_provenance'] = dict(passed=unassigned == 0, unassigned=unassigned)
    secfp = None
    dsm5 = paths(did)['dsm5']
    sj = [f for f in os.listdir(os.path.join(BASE, dsm5)) if f.endswith("_sections.json")]
    sections = {}
    if sj:
        j = _json.load(open(os.path.join(BASE, dsm5, sj[0])))
        sections = {k: set(content(v)) for k, v in j.items()} if isinstance(j, dict) else {}
    unaligned = 0; total = 0
    for r in rows:
        ft = content(r['source_fragment'])
        if not ft or not sections: continue
        bs = 0; bn = None
        for nm, toks in sections.items():
            c = sum(1 for t in ft if t in toks) / len(ft)
            if c > bs: bs = c; bn = nm
        if bn and bn.strip().lower() == 'diagnostic criteria':
            total += 1
            _, _, sc = align_fragment(r['source_fragment'], spine)
            if sc < 0.5: unaligned += 1
    rep['check2_source_section_GATE'] = dict(passed=unaligned == 0, criteria_fragments=total, unaligned=unaligned)
    pv = pair_verdicts(did)
    dom_mp = defaultdict(set)
    for x in rd(f"{paths(did)['rerank']}/03_reranked_pairs_filled.tsv"):
        if tb(x['strict_eligible']): dom_mp[x.get('human_domain', '')].add(x['mp_id'])
    flags = []
    doms = [d for d in dom_mp if dom_mp[d]]
    for i in range(len(doms)):
        for jx in range(i + 1, len(doms)):
            a, b = dom_mp[doms[i]], dom_mp[doms[jx]]
            inter = a & b; uni = a | b
            if uni:
                jac = len(inter) / len(uni); frac = len(inter) / min(len(a), len(b))
                if jac > 0.20 or frac > 0.50:
                    flags.append(f"{doms[i]}|{doms[jx]} jaccard={jac:.2f} shared={len(inter)}")
    rep['check3_domain_redundancy'] = dict(flags=flags)
    rep['check4_circular'] = dict(rejected=sorted(circ))
    pol = Counter()
    for r in rd(f"{paths(did)['pilot']}/08_unresolved_phenotypes.csv", ','):
        pol[r.get('polarity', '')] += 1
    rep['check5_polarity'] = dict(unresolved_polarity=dict(pol))
    rep['GATE_PASS'] = rep['check1_provenance']['passed'] and rep['check2_source_section_GATE']['passed']
    return rep

def build_landscape(dids, roadmap_path):
    pheno, crows = build_catalog(dids, write=False)
    import phenotype_class_hpo as PC
    byclass = defaultdict(lambda: [0, 0])
    bydis = defaultdict(lambda: [0, 0])
    for r in pheno:
        if r['role'] in ('symptom', 'onset') and r['hpo_id']:
            byclass[r['phenotype_class']][0] += 1; bydis[r['disorder']][0] += 1
            if r['mapped_strict']:
                byclass[r['phenotype_class']][1] += 1; bydis[r['disorder']][1] += 1
    predicted = {}
    if os.path.exists(roadmap_path):
        for r in csv.DictReader(open(roadmap_path), delimiter='\t'):
            if r['config_seed']: predicted[r['config_seed'].lower()] = r['predicted_pole']
    def stem(did): return DISORDER_CONFIG[did].replace('.disorder.json', '').lower()
    land = []
    for did in dids:
        n, s = bydis[did]
        land.append(dict(disorder=did, n_criterion_hpo=n, strict_mapped=s,
                         strict_map_pct=round(100 * s / n) if n else 0,
                         predicted_pole=predicted.get(stem(did), '')))
    return dict(by_class={k: dict(n=v[0], strict=v[1], pct=round(100 * v[1] / v[0]) if v[0] else 0)
                          for k, v in byclass.items()},
                by_disorder=land)

def add_disorder(did):
    p = paths(did); log = []
    def step(msg): log.append(msg); print(msg)
    step(f"== add_disorder({did}) ==")
    spine_ok = os.path.exists(os.path.join(BASE, p['dsm5'], "01_diagnostic_criteria.txt"))
    step(f"[stage0/spine] {p['dsm5']}/01_diagnostic_criteria.txt : {'present' if spine_ok else 'MISSING -> run:'}")
    if not spine_ok:
        step(f'    place the paraphrased criterion file at {p["dsm5"]}/01_diagnostic_criteria.txt')
        return log
    res_ok = os.path.exists(os.path.join(BASE, p['pilot'], "06b_llm_hpo_resolutions.csv"))
    if not res_ok:
        step("[stage1] resolution missing -> run (API):")
        step(f'    export OPENAI_API_KEY=...; export OPENAI_MODEL=gpt-5.4')
        step(f'    python3 stage1_curate_hpo.py --config {DISORDER_CONFIG[did]} --hpo_json hp.json --core_text {p["dsm5"]}/{did}_core_phenotype_only.txt --outdir {p["pilot"]}/')
        return log
    ml = master_lookup(did)
    step(f"[master lookup] resolved={ml['resolved']} free={len(ml['free'])} novel={len(ml['novel'])}")
    pair_ok = os.path.exists(os.path.join(BASE, p['rerank'], "03_reranked_pairs_filled.tsv"))
    if not pair_ok:
        step(f"[stage2] pair table missing -> adjudicate the {len(ml['novel'])} novel terms (API):")
        step(f'    python3 stage2a_candidate_features.py --config {DISORDER_CONFIG[did]}')
        step(f'    export OPENAI_API_KEY=...; python3 stage2b_rerank.py --config {DISORDER_CONFIG[did]}')
        step(f'    python3 stage2c_score_floor_fill.py --config {DISORDER_CONFIG[did]}')
        return log
    rep = validate_disorder(did)
    step(f"[validate] check2 GATE pass={rep['check2_source_section_GATE']['passed']} "
         f"(criteria_fragments={rep['check2_source_section_GATE']['criteria_fragments']}, "
         f"unaligned={rep['check2_source_section_GATE']['unaligned']}); overall GATE_PASS={rep['GATE_PASS']}")
    if not rep['GATE_PASS']:
        step("    GATE FAILED: disorder does not enter the catalog until check 2 passes.")
        return log
    all_dids = [d for d in DISORDER_CONFIG if os.path.exists(os.path.join(BASE, paths(d)['rerank'], "03_reranked_pairs_filled.tsv"))]
    build_hpo_mappability(all_dids)
    build_catalog(all_dids)
    step(f"[catalog] rebuilt over {len(all_dids)} disorders: {','.join(all_dids)}")
    step("[registry] update DISORDER_REGISTRY.tsv row for " + did)
    return log

def _write_tsv(path, rows, cols):
    tmp = "/tmp/_facet_" + os.path.basename(path)
    with open(tmp, "w", newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter='\t'); w.writeheader()
        for r in rows: w.writerow({c: r.get(c, '') for c in cols})
    b = open(tmp, 'rb').read()
    assert b.count(b'\x00') == 0, "null bytes in " + path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f: f.write(b)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("master", "catalog", "landscape"):
        s = sub.add_parser(c); s.add_argument("--disorders", required=True)
        if c == "landscape": s.add_argument("--roadmap", default=os.path.join(CATDIR, "dsm5_sweep_roadmap.tsv"))
    for c in ("validate", "lookup", "add-disorder"):
        s = sub.add_parser(c); s.add_argument("--disorder", required=True)
    a = ap.parse_args()
    if a.cmd == "master":
        rows, div = build_hpo_mappability([d.strip().upper() for d in a.disorders.split(",")])
        print(f"hpo_mappability.tsv: {len(rows)} terms, {div} cross-disorder divergent")
    elif a.cmd == "catalog":
        ph, cr = build_catalog([d.strip().upper() for d in a.disorders.split(",")])
        print(f"catalog_by_phenotype.tsv: {len(ph)} rows; catalog_by_criterion.tsv: {len(cr)} rows")
    elif a.cmd == "landscape":
        land = build_landscape([d.strip().upper() for d in a.disorders.split(",")], a.roadmap)
        print(json.dumps(land, indent=1))
    elif a.cmd == "validate":
        print(json.dumps(validate_disorder(a.disorder.strip().upper()), indent=1))
    elif a.cmd == "lookup":
        ml = master_lookup(a.disorder.strip().upper())
        print(f"resolved={ml['resolved']} free={len(ml['free'])} novel={len(ml['novel'])}")
        print("novel:", ml['novel'])
    elif a.cmd == "add-disorder":
        add_disorder(a.disorder.strip().upper())

if __name__ == "__main__":
    main()
