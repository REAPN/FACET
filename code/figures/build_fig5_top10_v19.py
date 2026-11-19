import sys, pandas as pd, numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
plt.rcParams['font.family'] = 'DejaVu Sans'
FV, LAB, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
fv = pd.read_csv(FV, sep='\t', dtype=str, keep_default_na=False)
lab = pd.read_csv(LAB, sep='\t', dtype=str)
UNITS = {'ASD': ['A1','A2','A3','B1','B2','B3','B4'], 'SCZ': ['A1','A2','A3','A4','A5'], 'ID': ['A','B'], 'NCD': ['A','B'],
         'MDD': ['A1','A2','A3','A4','A5','A6','A7','A8','A9']}
GLOSS = {'ASD': ['A1 social reciprocity', 'A2 nonverbal communication (excluded)', 'A3 relationships', 'B1 stereotyped movement or speech',
                 'B2 insistence on sameness', 'B3 restricted interests', 'B4 sensory reactivity'],
         'SCZ': ['A1 delusions', 'A2 hallucinations', 'A3 disorganized speech', 'A4 disorganized or catatonic behavior', 'A5 negative symptoms'],
         'ID': ['A intellectual function', 'B adaptive function'],
         'NCD': ['A cognitive decline', 'B interference with independence'],
         'MDD': ['A1 depressed mood', 'A2 loss of interest or pleasure', 'A3 weight or appetite change', 'A4 sleep disturbance', 'A5 psychomotor change',
                 'A6 fatigue', 'A7 worthlessness or guilt', 'A8 impaired concentration', 'A9 thoughts of death']}
LABKEY = {'ASD':'ASD','SCZ':'SCZ','ID':'IDD','NCD':'NCD','MDD':'MDD'}
TITLE = {'ASD':'ASD (85 curated models)','SCZ':'SCZ (42)','ID':'IDD (121)','NCD':'NCD (71)','MDD':'MDD (8)'}
cmap = matplotlib.colors.ListedColormap(['#ebebeb', '#7fb2e5', '#1f4e79'])
CELL = 0.30; TITLEH = 0.55; FS_TICK, FS_TITLE, FS_GLOSS, FS_LEG = 10.5, 11.5, 10.5, 10.5
LABW = {'ASD': 0.80, 'SCZ': 0.70, 'ID': 0.90, 'NCD': 1.10, 'MDD': 0.65}
W, H = 9.3, 11.4
ROW1_BOT = H - 0.95 - TITLEH - 10 * CELL
ROW2_BOT = ROW1_BOT - 1.45 - 0.30 - TITLEH - 10 * CELL
LEFT = {'ASD': 0.95, 'SCZ': 4.40, 'ID': 0.95, 'NCD': 3.10, 'MDD': 6.10}
BOT = {'ASD': ROW1_BOT, 'SCZ': ROW1_BOT, 'ID': ROW2_BOT, 'NCD': ROW2_BOT, 'MDD': ROW2_BOT}
fig = plt.figure(figsize=(W, H), dpi=300)
def slot(D):
    n = len(UNITS[D]); return fig.add_axes([LEFT[D] / W, BOT[D] / H, n * CELL / W, 10 * CELL / H])
for i, D in enumerate(['ASD','SCZ','ID','NCD','MDD']):
    d = fv[fv.disorder == D].copy()
    pos = set(lab[(lab.disorder == LABKEY[D]) & (lab.label_corrected == '1') & (lab.in_k4_pool == '1')].genotype_id)
    d = d[d.genotype_id.isin(pos)].copy(); d['b'] = d.breadth.astype(int); d['dres'] = d.depth_crit.str.count(r'\.').astype(int)
    d = d.sort_values(['b', 'dres', 'gene'], ascending=[False, False, True]).head(10)
    units = [f'{D}.{u}' for u in UNITS[D]]; M = np.zeros((len(d), len(units)), dtype=int)
    for r, (_, row) in enumerate(d.iterrows()):
        bc = set(x for x in row.breadth_crit.split(';') if x); dc = set(x for x in row.depth_crit.split(';') if x)
        for c, u in enumerate(units): M[r, c] = 2 if u in dc else (1 if u in bc else 0)
    genes = d.gene.tolist(); cnt = pd.Series(genes).value_counts(); k = {}; labels = []
    for g in genes:
        if cnt[g] > 1: k[g] = k.get(g, 0) + 1; labels.append(f'{g} ({k[g]})')
        else: labels.append(g)
    ax = slot(D)
    ax.imshow(M, cmap=cmap, vmin=0, vmax=2, aspect='equal', interpolation='nearest')
    ax.set_xticks([k - 0.5 for k in range(len(units) + 1)], minor=True); ax.set_yticks([k - 0.5 for k in range(len(d) + 1)], minor=True); ax.grid(which='minor', color='white', lw=1.5); ax.tick_params(which='minor', length=0)
    ax.set_xticks(range(len(units))); ax.set_xticklabels(UNITS[D], fontsize=FS_TICK, fontweight='bold'); ax.xaxis.tick_top()
    ax.set_yticks(range(len(d))); ax.set_yticklabels(labels, fontsize=FS_TICK, style='italic')
    ax.set_title(TITLE[D], fontsize=FS_TITLE, pad=18, fontweight='bold'); ax.tick_params(length=0)
    for s in ax.spines.values(): s.set_visible(False)
    for c in range(len(units)):
        if M[:, c].max() == 0: ax.get_xticklabels()[c].set_color('#9b1b30')
    ax.set_ylim(9.5, -0.5)
    ax.text(-0.5, 10.0, '\n'.join(GLOSS[D]), ha='left', va='top', fontsize=FS_GLOSS, linespacing=1.25, color='#111111', transform=ax.transData, clip_on=False)
fig.legend(handles=[Patch(color='#1f4e79', label='credited directly (through an admitted leaf term the genotype carries)'),
                    Patch(color='#7fb2e5', label='credited indirectly (through a broader admitted term or one of its descendants)'),
                    Patch(color='#ebebeb', label='no admitted phenotype'),
                    Patch(color='white', label='red unit label: no curated model is credited with the unit')],
           loc='upper left', ncol=1, fontsize=FS_LEG, frameon=False, bbox_to_anchor=(0.0, 1.0), handlelength=1.6)
plt.savefig(OUT, bbox_inches='tight', pad_inches=0.05, dpi=300, facecolor='white'); print('wrote', OUT)
