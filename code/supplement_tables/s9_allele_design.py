import csv, collections, json, re
import numpy as np
csv.field_size_limit(10**9)
S = {r['genotype_id']: r for r in csv.DictReader(open('broad_benchmark_setup/01_all_genotype_summary.csv', encoding='utf-8'))}
F4 = 'mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv'
FM = 'mappability_catalog/genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_rescue_MDD_idd20260910.tsv'
R = collections.defaultdict(dict)
for r in csv.DictReader(open(F4, encoding='utf-8'), delimiter='\t'): R[r['disorder']][r['genotype_id']] = r
RM = {r['genotype_id']: r for r in csv.DictReader(open(FM, encoding='utf-8'), delimiter='\t') if r['disorder'] == 'MDD'}
print('MDD breadth identical in the two catalogue files:', all(RM[g]['breadth'] == R['MDD'][g]['breadth'] for g in R['MDD']))
POOL = sorted(R['ASD'])
FVD = {'ASD': 'ASD', 'SCZ': 'SCZ', 'IDD': 'ID', 'NCD': 'NCD', 'MDD': 'MDD'}
POS = collections.defaultdict(set)
for r in csv.DictReader(open('audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv'), delimiter='\t'):
    if r['label_corrected'] == '1': POS[r['disorder']].add(r['genotype_id'])
br = lambda D, g: int(R[FVD[D]][g]['breadth'] or 0)
AL = {}
for l in open('MGI_PhenotypicAllele.rpt.txt', encoding='utf-8'):
    if l.startswith('#'): continue
    f = l.rstrip('\n').split('\t')
    if len(f) > 5: AL[f[1]] = (f[3], set(f[4].split('|')) - {''})
def design(g):
    alle = [a for a in S[g]['allele_symbols'].split('|') if a and not a.endswith('<+>')]
    info = [(a, *AL.get(a, ('?', set()))) for a in alle]
    drivers = [a for a, t, at in info if 'Recombinase' in at]
    drivers += [a for a, t, at in info if re.search(r'\(cre|-cre|cre\)|cre/Esr|\(Cre', a) and a not in drivers]
    core = [(a, t, at) for a, t, at in info if a not in drivers]
    if drivers and any('Conditional ready' in at for a, t, at in core): return 'conditional (Cre plus floxed allele)'
    if drivers and not core: return 'driver or reporter only'
    ats = set().union(*[at for a, t, at in core]) if core else set()
    tys = {t for a, t, at in core}
    if 'Humanized sequence' in ats: return 'humanized sequence'
    if 'Transgenic' in tys and not ({'Targeted', 'Endonuclease-mediated'} & tys): return 'transgene (random insertion)'
    if 'Hypomorph' in ats: return 'hypomorph'
    if 'Null/knockout' in ats: return 'null or knockout'
    if 'Chemically induced (ENU)' in tys or any(t.startswith('Chemically') for t in tys): return 'chemically induced (ENU)'
    if 'Spontaneous' in tys: return 'spontaneous'
    if 'Gene trapped' in tys: return 'gene trap'
    if {'Targeted', 'Endonuclease-mediated'} & tys: return 'targeted, not null (knock-in, point, other)'
    return 'other or unresolved'
DES = {g: design(g) for g in POOL}
L = json.load(open('audit/geneclust_2026-10-08/landscape.json'))['design']
out = {}
for d in sorted(set(DES.values())):
    G = [g for g in POOL if DES[g] == d]
    row = dict(pool_n=len(G), pool_n_stored=L.get(d, {}).get('pool_n'))
    for D in FVD:
        cur = [g for g in G if g in POS[D]]
        st = L.get(d, {}).get(D, {})
        row[D] = dict(curated=len(cur),
                      curated_any=round(float(np.mean([br(D, g) > 0 for g in cur])), 3) if cur else None,
                      curated_mean_criteria=round(float(np.mean([br(D, g) for g in cur])), 3) if cur else None,
                      pool_any=round(float(np.mean([br(D, g) > 0 for g in G])), 3),
                      stored=st)
    out[d] = row
print(json.dumps(out))
