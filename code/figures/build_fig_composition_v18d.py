import json, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
plt.rcParams['font.family'] = 'DejaVu Sans'
d = json.load(open(__import__("os").environ.get("FACET_ROOT", ".") + '/audit/composition_2026-11-06/composition.json'))
INK = '#111111'; DARK = '#1f4e79'; LIGHT = '#9dc3e6'
ORDER = ['ASD', 'SCZ', 'IDD', 'NCD', 'MDD']
CLS = [c for c, _ in d['classes']]
COL = {'social and vocal': '#5b9bd5', 'cognition': '#7fb2e0', 'emotion and affect': '#a3c8ea', 'motor behavior': '#c6ddf2', 'other behavior': '#e3eef8',
       'nervous system morphology': '#c9a227', 'nervous system physiology': '#dcbb5c', 'mortality and growth': '#ead394', 'other physiology and morphology': '#f5ead0'}
SHORT = {'other physiology and morphology': 'other physiology\nand morphology', 'nervous system morphology': 'nervous system\nmorphology', 'nervous system physiology': 'nervous system\nphysiology'}
fig = plt.figure(figsize=(7.5, 7.6), dpi=300)

axA = fig.add_axes([0.25, 0.70, 0.44, 0.25])
rows = [(f'{D} models ({d["curated"][D]["n"]})', d['curated'][D]['share']) for D in ORDER] + [('all genotypes (32,535)', d['pool']['share'])]
for i, (lab, sh) in enumerate(rows):
    left = 0
    for c in CLS:
        w = 100 * sh[c]
        axA.barh(i, w, left=left, color=COL[c], edgecolor='white', linewidth=0.4, height=0.72)
        if w >= 9: axA.text(left + w / 2, i, f'{w:.0f}', ha='center', va='center', fontsize=7, color=INK)
        left += w
axA.set_yticks(range(len(rows))); axA.set_yticklabels([r[0] for r in rows], fontsize=8.5); axA.invert_yaxis()
axA.set_xlim(0, 100); axA.set_xticks([0, 25, 50, 75, 100]); axA.tick_params(axis='x', labelsize=8); axA.tick_params(axis='y', length=0)
axA.set_xlabel('percent of the annotations of the set', fontsize=8.5)
for s in ('top', 'right'): axA.spines[s].set_visible(False)
fig.text(0.01, 0.975, 'A', fontsize=13, fontweight='bold', va='top')
fig.text(0.05, 0.973, 'Phenotype class breakdown of curated models\' annotations', fontsize=10, va='top', color=INK)
axA.legend(handles=[Patch(color=COL[c], label=SHORT.get(c, c)) for c in CLS], loc='center left', bbox_to_anchor=(1.01, 0.5), fontsize=7.5, frameon=False, title='phenotype class', title_fontsize=8)

import numpy as np
from matplotlib.lines import Line2D
axB = fig.add_axes([0.25, 0.05, 0.58, 0.48])
ncl = len(CLS); nd = len(ORDER)
cu = np.array([[100 * d['curated'][D]['carries'][c] for D in ORDER] for c in CLS])
bg = np.array([[100 * d['background'][D]['carries'][c] for D in ORDER] for c in CLS])
cmap = matplotlib.colors.LinearSegmentedColormap.from_list('b', ['#ffffff', '#c9ddf0', '#8fb8e0'])
for i, c in enumerate(CLS):
    for j, D in enumerate(ORDER):
        for k, (val, x0) in enumerate([(cu[i, j], j * 2.0), (bg[i, j], j * 2.0 + 0.95)]):
            axB.add_patch(plt.Rectangle((x0, i), 0.95, 0.92, color=cmap(val / 100)))
            axB.text(x0 + 0.475, i + 0.5, f'{val:.0f}', ha='center', va='center', fontsize=9.5, color=INK)
        if d['admitted_terms_by_class'][D][c]: axB.plot(j * 2.0 + 0.8, i + 0.2, marker='o', ms=5, color='#b02a2a', mec='white', mew=0.6)
axB.set_xlim(-0.05, nd * 2.0 - 0.05); axB.set_ylim(ncl, 0); axB.axis('off')
for j, D in enumerate(ORDER): axB.text(j * 2.0 + 0.95, -1.25, D, ha='center', va='center', fontsize=10, fontweight='bold', color=INK)
for j in range(nd):
    axB.text(j * 2.0 + 0.475, -0.12, 'curated', ha='left', va='bottom', fontsize=8, color=INK, rotation=45)
    axB.text(j * 2.0 + 1.425, -0.12, 'others', ha='left', va='bottom', fontsize=8, color=INK, rotation=45)
for i, c in enumerate(CLS): axB.text(-0.15, i + 0.5, SHORT.get(c, c), ha='right', va='center', fontsize=9.5, color=INK)
fig.text(0.01, 0.63, 'B', fontsize=13, fontweight='bold', va='top')
fig.text(0.05, 0.628, 'Percent of genotypes with at least one annotation in the class', fontsize=10, va='top', color=INK)
cax = fig.add_axes([0.86, 0.24, 0.02, 0.2])
cb = matplotlib.colorbar.ColorbarBase(cax, cmap=cmap, norm=matplotlib.colors.Normalize(0, 100), ticks=[0, 50, 100])
cb.ax.tick_params(labelsize=8); cb.outline.set_linewidth(0.5)
fig.text(0.855, 0.455, 'percent of\ngenotypes with\na term of\nthe class', fontsize=8, va='bottom', color=INK, linespacing=1.2)
fig.legend(handles=[Line2D([0], [0], marker='o', color='w', markerfacecolor='#b02a2a', markeredgecolor='white', markersize=6, label='admitted term\nin the class')], loc='upper left', bbox_to_anchor=(0.835, 0.21), fontsize=8, frameon=False, handletextpad=0.3)
fig.savefig('fig_composition_2026-11-06d.png', dpi=300, facecolor='white'); print('ok')
