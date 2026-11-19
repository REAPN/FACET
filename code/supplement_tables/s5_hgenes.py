import csv, json, hashlib
def col(p, c='gene_symbol'): return {r[c].upper() for r in csv.DictReader(open(p, encoding='utf-8'), delimiter='\t') if r.get(c)}
F = {'asc': 'dnv_catalogs/asc_satterstrom2020_asd_genes.tsv', 'fu': 'dnv_catalogs/fu2022_asd_genes.tsv',
     'schema': 'dnv_catalogs/schema_scz_gene_list.tsv', 'dndb_scz': 'dnv_catalogs/denovo_db_scz_genes.tsv',
     'ddg2p': 'dnv_catalogs/ddg2p_id_confirmed_dominant.tsv', 'mdd': 'rescue_line_output/mdd_t1g_REAL_human_genes.tsv'}
S = {k: col(v) for k, v in F.items()}
for k, v in F.items(): print(k, len(S[k]), hashlib.sha256(open(v, 'rb').read()).hexdigest())
print('ASD union', len(S['asc'] | S['fu']), 'overlap', len(S['asc'] & S['fu']))
print('SCZ union', len(S['schema'] | S['dndb_scz']), 'overlap', len(S['schema'] & S['dndb_scz']))
r = list(csv.DictReader(open(F['schema']), delimiter='\t'))
print('schema exome-wide yes', sum(x['schema_exome_wide_sig'] == 'yes' for x in r), 'qmeta<0.05', sum(float(x['schema_qmeta']) < 0.05 for x in r))
r = list(csv.DictReader(open(F['dndb_scz']), delimiter='\t'))
print('dndb n_dnv_total', sorted(int(x['n_dnv_total']) for x in r))
cfg = {d['name']: d for d in json.load(open('disorders_rescue_config.json'))['disorders']}
nd = set(cfg['Neurocognitive']['doids'])
G = {r['Symbol'].upper() for r in csv.DictReader(open('MGI_DO.rpt', encoding='utf-8'), delimiter='\t')
     if r['DO Disease ID'] in nd and r['Common Organism Name'].startswith('human')}
print('NCD MGI_DO human genes', len(G), 'n doids', len(nd))
