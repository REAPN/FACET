import pandas as pd
MC = 'mappability_catalog/'
F4 = MC + 'genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_ncdB_constructfiltered_idd20260910.tsv'
FM = MC + 'genotype_face_validity_seco_criterion_strictonly_prev25_span1_k4_a2floor_rescue_MDD_idd20260910.tsv'
lab = pd.read_csv('audit/geneclust_2026-10-08/labels_corrected_2026-11-02.tsv', sep='\t', dtype=str)
pos = {D: set(lab[(lab.disorder == D) & (lab.label_corrected == '1')].genotype_id) for D in lab.disorder.unique()}
a = pd.read_csv(F4, sep='\t', dtype=str, usecols=['disorder', 'genotype_id', 'breadth_crit', 'depth_crit'])
m = pd.read_csv(FM, sep='\t', dtype=str, usecols=['disorder', 'genotype_id', 'breadth_crit', 'depth_crit'])
print('F4 disorders', a.disorder.value_counts().to_dict())
print('FM disorders', m.disorder.value_counts().to_dict())
units = lambda x: set(u.split('.', 1)[1] for u in str(x).split(';') if u and u != 'nan')
RULES = {
 'ASD': lambda s: {'A1', 'A2', 'A3'} <= s and len(s & {'B1', 'B2', 'B3', 'B4'}) >= 2,
 'SCZ': lambda s: len(s & {'A1', 'A2', 'A3', 'A4', 'A5'}) >= 2 and len(s & {'A1', 'A2', 'A3'}) >= 1,
 'ID': lambda s: {'A', 'B'} <= s,
 'NCD': lambda s: {'A', 'B'} <= s,
 'MDD': lambda s: len(s & {f'A{i}' for i in range(1, 10)}) >= 5 and len(s & {'A1', 'A2'}) >= 1,
}
LD = {'ASD': 'ASD', 'SCZ': 'SCZ', 'ID': 'IDD', 'NCD': 'NCD', 'MDD': 'MDD'}
for D, f in RULES.items():
    t = (m if D == 'MDD' else a)
    t = t[t.disorder == D]
    P = pos[LD[D]]
    for col in ('breadth_crit', 'depth_crit'):
        s = t[col].map(units)
        meet = s.map(f)
        n = int(meet.sum()); nc = int((meet & t.genotype_id.isin(P)).sum())
        mx = int(s.map(len).max())
        print(D, col, 'n_genotypes', len(t), 'meeting', n, 'curated', nc, 'max units', mx,
              'units seen', sorted(set().union(*s)))
