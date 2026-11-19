import csv, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.chdir(ROOT)
HERE = 'audit/anchor_gate_2026-11-07'; out = ['# Anchor gate rerun (2026-11-07)', '']
for d in ('ASD', 'ID', 'NCD'):
    p = f'{HERE}/run_{d}/03_taxonomy.tsv'
    if not os.path.exists(p): out.append(f'{d}: no run output yet'); continue
    gate = {r['mp_id']: r for r in csv.DictReader(open(f'{HERE}/gate_{d}.tsv', encoding='utf-8'), delimiter='\t')}
    got = {r['mp_id']: r for r in csv.DictReader(open(p, encoding='utf-8'), delimiter='\t')}
    ok = 0; lines = [f'## {d}', '', '| MP term | expected | item | admitted | item of rerun | verdict |', '|---|---|---|---|---|---|']
    for mp, g in gate.items():
        r = got.get(mp)
        if r is None: lines.append(f'| {mp} {g["mp_label"]} | {g["expected"]} | {g["expected_item"]} | missing | | FAIL |'); continue
        adm = r.get('admissible', '').lower() in ('true', '1', 'yes')
        item = r.get('item_id', '')
        exp_adm = g['expected'] == 'EXPECT_ADMIT'
        passed = (adm == exp_adm) and (not exp_adm or item == g['expected_item'])
        ok += passed
        lines.append(f'| {mp} {g["mp_label"]} | {g["expected"]} | {g["expected_item"]} | {"yes" if adm else "no"} | {item} | {"pass" if passed else "FAIL"} |')
    lines.insert(1, f'{ok} of {len(gate)} pass'); out += lines + ['']
    print(d, ok, 'of', len(gate))
open(f'{HERE}/RESULT_gate.md', 'w', encoding='utf-8').write('\n'.join(out) + '\n'); print('written', f'{HERE}/RESULT_gate.md')
