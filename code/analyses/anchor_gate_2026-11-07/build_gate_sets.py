import csv, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); os.chdir(ROOT)
HERE = 'audit/anchor_gate_2026-11-07'
defs = {}
for d in ('ASD', 'ID', 'NCD', 'SCZ'):
    for r in csv.DictReader(open(f'taxonomy_v2_full/scope_main_{d}.tsv', encoding='utf-8'), delimiter='\t'):
        defs.setdefault(r['mp_id'], r)
for r in csv.DictReader(open('mp_term_taxonomy_mdd_v1/03_mp_term_taxonomy.tsv', encoding='utf-8'), delimiter='\t'):
    defs.setdefault(r['mp_id'], r)
GATES = {
 'ASD': [
  ('MP:0001360', 'EXPECT_ADMIT', 'A1', 'social investigation'), ('MP:0001361', 'EXPECT_ADMIT', 'A1', 'social withdrawal'),
  ('MP:0021111', 'EXPECT_ADMIT', 'A1', 'decreased social investigation'), ('MP:0001529', 'EXPECT_ADMIT', 'A1', 'vocalization routes to A1 not A2 (A2 construct floor)'),
  ('MP:0020396', 'EXPECT_ADMIT', 'A3', 'social recognition'), ('MP:0021112', 'EXPECT_ADMIT', 'A3', 'impaired social recognition'),
  ('MP:0001400', 'EXPECT_ADMIT', 'B1', 'increased stereotypic behavior'), ('MP:0001441', 'EXPECT_ADMIT', 'B1', 'increased grooming (grooming rule)'),
  ('MP:0001440', 'EXPECT_ADMIT', 'B2', 'abnormal grooming behavior, review flag expected'),
  ('MP:0002733', 'EXPECT_ADMIT', 'B4', 'thermal nociception'), ('MP:0003998', 'EXPECT_ADMIT', 'B4', 'decreased thermal nociceptive threshold'),
  ('MP:0001486', 'EXPECT_ADMIT', 'B4', 'abnormal startle reflex, sensory reactivity'),
  ('MP:0002064', 'EXPECT_BLOCK', 'none', 'seizures, involuntary motor sign'), ('MP:0000745', 'EXPECT_BLOCK', 'none', 'tremors, involuntary motor sign'),
  ('MP:0002135', 'EXPECT_BLOCK', 'none', 'kidney morphology, non-neurological control')],
 'ID': [
  ('MP:0008428', 'EXPECT_ADMIT', 'A', ''), ('MP:0002062', 'EXPECT_ADMIT', 'A', ''), ('MP:0001458', 'EXPECT_ADMIT', 'A', ''), ('MP:0001463', 'EXPECT_ADMIT', 'A', ''), ('MP:0001469', 'EXPECT_ADMIT', 'A', ''),
  ('MP:0001360', 'EXPECT_ADMIT', 'B', ''), ('MP:0001447', 'EXPECT_ADMIT', 'B', ''), ('MP:0001440', 'EXPECT_ADMIT', 'B', 'soft, self-care'),
  ('MP:0000003', 'EXPECT_BLOCK', 'none', ''), ('MP:0002135', 'EXPECT_BLOCK', 'none', ''), ('MP:0004859', 'EXPECT_BLOCK', 'none', ''), ('MP:0001905', 'EXPECT_BLOCK', 'none', ''),
  ('MP:0003861', 'EXPECT_BLOCK', 'none', ''), ('MP:0000060', 'EXPECT_BLOCK', 'none', 'embryonic, not a milestone'), ('MP:0002174', 'EXPECT_BLOCK', 'none', 'embryonic, not a milestone')],
 'NCD': [
  ('MP:0001463', 'EXPECT_ADMIT', 'A', ''), ('MP:0001458', 'EXPECT_ADMIT', 'A', ''), ('MP:0002062', 'EXPECT_ADMIT', 'A', ''), ('MP:0001469', 'EXPECT_ADMIT', 'A', ''), ('MP:0008428', 'EXPECT_ADMIT', 'A', 'added 2026-11-07'),
  ('MP:0001516', 'EXPECT_ADMIT', 'A', 'perceptual-motor'), ('MP:0001406', 'EXPECT_ADMIT', 'A', 'perceptual-motor'), ('MP:0001393', 'EXPECT_ADMIT', 'A', 'perceptual-motor'),
  ('MP:0021112', 'EXPECT_ADMIT', 'A', 'social cognition'), ('MP:0020396', 'EXPECT_ADMIT', 'A', 'social cognition'),
  ('MP:0001447', 'EXPECT_ADMIT', 'B', 'ADL proxy'), ('MP:0001440', 'EXPECT_ADMIT', 'B', 'soft, self-care'),
  ('MP:0001900', 'EXPECT_BLOCK', 'none', ''), ('MP:0001905', 'EXPECT_BLOCK', 'none', ''), ('MP:0002135', 'EXPECT_BLOCK', 'none', '')],
}
SCZ_EXTRA = [
  {"mp_id": "MP:0002572", "label_hint": "abnormal emotion/affect behavior", "expected_domain": "negative_symptoms", "expected_strict": True, "expected_direction": "bidirectional"},
  {"mp_id": "MP:0002064", "label_hint": "seizures", "expected_domain": "mechanistic_neurobiology", "expected_strict": False, "expected_direction": "n/a"},
]
for d, rows in GATES.items():
    assert len(rows) == 15, d
    with open(f'{HERE}/gate_{d}.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['mp_id', 'mp_label', 'mp_definition', 'parent_label', 'ancestor_label', 'expected', 'expected_item', 'expected_direction', 'expect_review', 'pilot_note'])
        for mp, exp, item, note in rows:
            r = defs.get(mp)
            if r is None: sys.exit(f'{d}: {mp} not in the scope tables, give its label and definition by hand')
            w.writerow([mp, r['mp_label'], r.get('mp_definition', ''), '', '', exp, item, '', 'yes' if 'review' in note else '', note])
    print(d, 'gate written, 15 terms,', sum(1 for r in rows if r[1] == 'EXPECT_ADMIT'), 'expected admissible')
json.dump(SCZ_EXTRA, open(f'{HERE}/gate_SCZ_extra.json', 'w'), indent=1)
print('SCZ: 13 of record + 2 extra written to gate_SCZ_extra.json; MDD: the 15-term set of record, unchanged')
