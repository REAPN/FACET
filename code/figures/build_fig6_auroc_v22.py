import math, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
plt.rcParams['font.family'] = 'DejaVu Sans'
DARK, LIGHT, RED, INK = '#1f4e79', '#8dbbe6', '#b02a2a', '#111111'

dis = ['ASD', 'SCZ', 'IDD', 'NCD']
conv = {'ASD': (0.964, 0.928, 0.990, 0.944), 'SCZ': (0.877, 0.807, 0.933, 0.732), 'IDD': (0.771, 0.729, 0.836, 0.735), 'NCD': (0.761, 0.690, 0.824, 0.604)}
disc = {'ASD': (0.956, 0.920, 0.983, 0.961, 0.936, 0.979, 0.969), 'SCZ': (0.682, 0.603, 0.761, 0.662, 0.584, 0.739, 0.709),
        'IDD': (0.751, 0.705, 0.820, 0.761, 0.710, 0.847, 0.759), 'NCD': (0.668, 0.595, 0.737, 0.636, 0.557, 0.707, 0.731)}
fig, axes = plt.subplots(2, 1, figsize=(7.5, 6.8), dpi=300, sharex=True)
titles = ['A   Coverage AUROC\n     ranking by Diagnostic Coverage', 'B   Support AUROC\n     ranking by the support score']
y = list(range(len(dis)))[::-1]
for ax, t in zip(axes, titles):
    ax.axvline(0.5, color=INK, lw=0.9, ls=':'); ax.set_xlim(0, 1); ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_title(t, fontsize=11, fontweight='bold', loc='left', linespacing=1.15); ax.tick_params(labelsize=10)
    ax.set_yticks(y); ax.set_yticklabels(dis, fontsize=11); ax.set_ylim(-0.6, len(dis) - 0.4)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
for yi, D in zip(y, dis):
    v = conv[D]; a = axes[0]
    a.plot([v[1], v[2]], [yi + 0.15] * 2, color=DARK, lw=2.0); a.plot(v[0], yi + 0.15, 'o', color=DARK, ms=7)
    a.plot(v[3], yi - 0.18, 's', color=LIGHT, ms=7, markeredgecolor=DARK)
    w = disc[D]; b = axes[1]
    b.plot([w[1], w[2]], [yi + 0.24] * 2, color=DARK, lw=2.0); b.plot(w[0], yi + 0.24, 'o', color=DARK, ms=7)
    b.plot([w[4], w[5]], [yi] * 2, color=DARK, lw=1.1); b.plot(w[3], yi, 's', color=LIGHT, ms=7, markeredgecolor=DARK)
    b.plot(w[6], yi - 0.24, '^', color=INK, ms=7)
axes[1].set_xlabel('AUROC, curated models against the background (0.5 is chance)', fontsize=10)
h = [Line2D([], [], marker='o', color=DARK, lw=2.0, ms=7, label='all genotypes,\nwith 95%\ngene-clustered\ninterval'),
     Line2D([], [], marker='s', color=LIGHT, markeredgecolor=DARK, lw=0, ms=7, label='both classes\nbehaviorally\nannotated\n(interval in B)'),
     Line2D([], [], marker='^', color=INK, lw=0, ms=7, label='full background,\nincluding genotypes\nwith zero support\n(B only)')]
fig.legend(handles=h, loc='center left', bbox_to_anchor=(0.745, 0.5), fontsize=10, frameon=False, labelspacing=1.4, handlelength=1.6)
plt.tight_layout(rect=(0, 0, 0.75, 1)); fig.savefig('fig6_auroc_2026-11-08.png', dpi=300, facecolor='white')

print('ok')
