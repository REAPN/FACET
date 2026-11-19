import csv, collections, json
import numpy as np
csv.field_size_limit(10**9)
S = {r['genotype_id']: r for r in csv.DictReader(open('broad_benchmark_setup/01_all_genotype_summary.csv', encoding='utf-8'))}
FV = 'mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv'
POOL = sorted({r['genotype_id'] for r in csv.DictReader(open(FV, encoding='utf-8'), delimiter='\t') if r['disorder'] == 'ASD'})
POS = collections.defaultdict(set)
for r in csv.DictReader(open('audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv'), delimiter='\t'):
    if r['label_corrected'] == '1': POS[r['disorder']].add(r['genotype_id'])
par = collections.defaultdict(set); cur = None
for l in open('MPheno_OBO.ontology', encoding='utf-8'):
    l = l.rstrip('\n')
    if l == '[Term]': cur = None
    elif l.startswith('id: MP:'): cur = l[4:]
    elif l.startswith('is_a: ') and cur: par[cur].add(l[6:16])
memo = {}
def anc(t):
    if t not in memo:
        s = set()
        for p in par.get(t, ()): s |= {p} | anc(p)
        memo[t] = s
    return memo[t]
CLASSES = [('motor behavior', ['MP:0002066']), ('sensory behavior and reflexes', ['MP:0002067']), ('seizures', ['MP:0002064']),
           ('social and vocal', ['MP:0002557', 'MP:0001529']), ('cognition', ['MP:0014114']), ('emotion and affect', ['MP:0002572']),
           ('other behavior', ['MP:0004924']), ('nervous system morphology', ['MP:0003632']), ('nervous system physiology', ['MP:0003633']),
           ('ear and eye', ['MP:0005377', 'MP:0005391']), ('mortality and growth', ['MP:0010768', 'MP:0005378']), ('other physiology and morphology', [])]
def mpclass(t):
    a = anc(t) | {t}
    for c, roots in CLASSES:
        if not roots or any(r in a for r in roots): return c
mps = lambda g: [m.strip() for m in S[g]['mp_ids'].split('|') if m.strip()]
CL = {g: collections.Counter(mpclass(t) for t in mps(g)) for g in POOL}
BEHAV = {'motor behavior', 'sensory behavior and reflexes', 'seizures', 'social and vocal', 'cognition', 'emotion and affect', 'other behavior'}
nbeh = lambda g: sum(v for k, v in CL[g].items() if k in BEHAV)
strict_beh = lambda g: any(t == 'MP:0004924' or 'MP:0004924' in anc(t) for t in mps(g))
def prof(G):
    G = list(G); tot = collections.Counter()
    for g in G: tot.update(CL[g])
    n = sum(tot.values())
    return dict(n=len(G), n_terms=n,
        beh_landscape=int(sum(nbeh(g) > 0 for g in G)), beh_strict=int(sum(strict_beh(g) for g in G)),
        social_any=int(sum(CL[g]['social and vocal'] > 0 for g in G)), cognition_any=int(sum(CL[g]['cognition'] > 0 for g in G)),
        motor_any=int(sum(CL[g]['motor behavior'] > 0 for g in G)), emotion_any=int(sum(CL[g]['emotion and affect'] > 0 for g in G)),
        median_terms=float(np.median([len(mps(g)) for g in G])), median_beh_terms=float(np.median([nbeh(g) for g in G])),
        share={k: round(tot[k] / n, 4) for k, _ in CLASSES})
out = {'pool_n': len(POOL)}
for D in ['ASD', 'SCZ', 'IDD', 'NCD', 'MDD']:
    out[D] = prof(POS[D] & set(POOL))
out['ALL'] = prof(POOL)
allpos = set().union(*[POS[D] & set(POOL) for D in ['ASD', 'SCZ', 'IDD', 'NCD', 'MDD']])
out['labels_in_pool'] = sum(len(POS[D] & set(POOL)) for D in POS); out['labelled_genotypes_in_pool'] = len(allpos)
print(json.dumps(out, indent=0))
