import pandas as pd
SC = {'ASD': ['A1','A2','A3','B1','B2','B3','B4'], 'SCZ': ['A1','A2','A3','A4','A5'],
      'ID': ['A','B'], 'NCD': ['A','B'], 'MDD': ['A%d' % i for i in range(1, 10)]}
NAME = {'ASD': 'ASD', 'SCZ': 'SCZ', 'ID': 'IDD', 'NCD': 'NCD', 'MDD': 'MDD'}
tot_all = tot_attr = tot_scored = 0
for D in SC:
    t = pd.read_csv(f'target_units_{D}/03_target_criterion_units.tsv', sep='\t', dtype=str)
    a = t[t.attributable == 'True'].copy()
    a['ord'] = a.item_id.map({u: i for i, u in enumerate(SC[D] + ['B'])}).fillna(99)
    a = a.sort_values(['ord', 'hpo_id'])
    scored = a[a.item_id.isin(SC[D])]
    tot_all += len(t); tot_attr += len(a); tot_scored += len(scored)
    print(f'\n### {NAME[D]}\n')
    print(f'Count: {len(a)} attributable of {len(t)} anchors ({len(scored)} on scored units'
          + (f', {len(a)-len(scored)} on unscored criterion B' if len(a) > len(scored) else '') + ').\n')
    print('| HPO id | HPO label | Criterion unit | Second unit | Category | Centrality |')
    print('|---|---|---|---|---|---|')
    for _, r in a.iterrows():
        u = NAME[D] + ' ' + r.item_id + ('' if r.item_id in SC[D] else ' (not scored)')
        s = '' if r.second_item_id in ('none', '', None) else r.second_item_id
        print(f'| {r.hpo_id} | {r.hpo_label} | {u} | {s} | {r.category.replace("_"," ")} | {r.centrality} |')
print(f'\nTOTAL anchors {tot_all}, attributable {tot_attr}, attributable to scored units {tot_scored}')
