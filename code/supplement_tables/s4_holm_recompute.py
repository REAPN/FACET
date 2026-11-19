import json, math
fam = json.load(open('audit/open_items_2026-10-13/item5c_abstract_family.json'))['family']
w = json.load(open('audit/geneclust_2026-10-08/ncd_wpw_removed_2026-11-02.json'))
lad = json.load(open('audit/geneclust_2026-10-08/ncd_wpw_removed_phenodigm_ladder_2026-11-02.json'))
def p_ci(est, lo, hi, null):
    se = (hi - lo) / 3.92
    return math.erfc(abs(est - null) / se / math.sqrt(2)) if se > 0 else 0.0
new = [dict(f) for f in fam]
for f in new:
    if f['claim'] == 'discrimination AUROC > 0.5, NCD':
        h = w['headline']; f['estimate'] = round(h['auroc'], 4); f['p'] = p_ci(h['auroc'], *h['ci_gene'], 0.5)
    if f['claim'] == 'convergent AUROC > 0.5, NCD':
        c = w['convergent']; f['estimate'] = round(c['auroc'], 4); f['p'] = p_ci(c['auroc'], *c['ci_gene'], 0.5)
    if f['claim'] == 'FACET minus PhenoDigm arm 4, NCD':
        a = lad['arm4_behavioral']; f['estimate'] = a['delta']; f['p'] = max(a['p'], 1 / 2001)
def adjust(F):
    m = len(F); order = sorted(range(m), key=lambda i: F[i]['p'])
    holm = [None] * m; run = 0
    for r, i in enumerate(order):
        run = max(run, min(1, (m - r) * F[i]['p'])); holm[i] = run
    bh = [None] * m; prev = 1
    for r in range(m - 1, -1, -1):
        i = order[r]; prev = min(prev, F[i]['p'] * m / (r + 1)); bh[i] = prev
    return holm, bh
h0, b0 = adjust(fam); h1, b1 = adjust(new)
for i, (a, b) in enumerate(zip(fam, new)):
    print(json.dumps(dict(claim=a['claim'], finding=a['finding'], kind=a['p_kind'],
        est_stored=a['estimate'], p_stored=a['p'], holm_stored=a['p_holm'], holm_check=h0[i],
        est_new=b['estimate'], p_new=b['p'], holm_new=h1[i], bh_new=b1[i])))
print('survive stored', sum(x < 0.05 for x in h0), 'survive new', sum(x < 0.05 for x in h1))
