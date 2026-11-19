import matplotlib
matplotlib.use('Agg')
import matplotlib.ticker
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
plt.rcParams['font.family'] = 'DejaVu Sans'
DARK, LIGHT, RED, INK = '#1f4e79', '#8dbbe6', '#b02a2a', '#111111'
N = {'ASD': (85, 32450), 'SCZ': (42, 32493), 'IDD': (121, 32414), 'NCD': (71, 32464), 'MDD': (8, 32527)}
U = {'ASD': [('A1', 'social reciprocity', 76, 637), ('A2', 'nonverbal communication', 0, 0), ('A3', 'relationships', 74, 607),
             ('B1', 'stereotyped movement', 25, 556), ('B2', 'insistence on sameness', 66, 1354), ('B3', 'restricted interests', 2, 9),
             ('B4', 'sensory reactivity', 53, 2590)],
     'SCZ': [('A1', 'delusions', 0, 0), ('A2', 'hallucinations', 0, 0), ('A3', 'disorganized speech', 0, 0),
             ('A4', 'disorganized behavior', 30, 5035), ('A5', 'negative symptoms', 31, 1834)],
     'IDD': [('A', 'intellectual function', 60, 1545), ('B', 'adaptive function', 40, 1438)],
     'NCD': [('A', 'cognitive decline', 47, 4290), ('B', 'loss of independence', 0, 251)],
     'MDD': [('A1', 'depressed mood', 8, 87), ('A2', 'loss of interest', 8, 160), ('A3', 'weight or appetite change', 1, 1259),
             ('A4', 'sleep disturbance', 1, 80), ('A5', 'psychomotor change', 0, 1859), ('A6', 'fatigue', 0, 132),
             ('A7', 'worthlessness or guilt', 0, 0), ('A8', 'impaired concentration', 0, 207), ('A9', 'thoughts of death', 0, 0)]}
HIST = {'ASD': [4, 1, 14, 18, 28, 19, 1, 0], 'SCZ': [6, 11, 25, 0, 0, 0], 'IDD': [47, 48, 26], 'NCD': [24, 47, 0], 'MDD': [0, 0, 7, 0, 1, 0, 0, 0, 0, 0]}
ORDER = ['ASD', 'SCZ', 'IDD', 'NCD', 'MDD']

fig = plt.figure(figsize=(7.5, 11.0), dpi=300)
fig.text(0.01, 0.99, 'A', fontsize=14, fontweight='bold', va='top')
fig.text(0.05, 0.988, 'Curated models by the number of criterion units credited (red: none)', fontsize=11, va='top', color=INK)
POS = {'ASD': [0.08, 0.875, 0.25, 0.085], 'SCZ': [0.41, 0.875, 0.19, 0.085], 'IDD': [0.70, 0.875, 0.14, 0.085],
       'NCD': [0.08, 0.735, 0.14, 0.085], 'MDD': [0.30, 0.735, 0.34, 0.085]}
for D in ORDER:
    ax = fig.add_axes(POS[D]); ys = HIST[D]; xs = list(range(len(ys)))
    ax.bar(xs, ys, color=[RED if x == 0 else DARK for x in xs], width=0.72)
    for x, y in zip(xs, ys):
        if y: ax.text(x, y + max(ys) * 0.04, str(y), ha='center', va='bottom', fontsize=9, color=INK)
    ax.set_ylim(0, max(ys) * 1.38); ax.set_xticks(xs); ax.set_xticklabels([str(x) for x in xs], fontsize=9)
    ax.tick_params(axis='y', labelsize=9, length=2); ax.tick_params(axis='x', length=0)
    for s in ('top', 'right'): ax.spines[s].set_visible(False)
    ax.set_title(f'{D} ({N[D][0]} curated)', fontsize=10, fontweight='bold', pad=3)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True, nbins=4))
    if D in ('ASD', 'NCD'): ax.set_ylabel('models', fontsize=9.5)
    ax.set_xlabel('criterion units credited', fontsize=9.5)

fig.text(0.01, 0.675, 'B', fontsize=14, fontweight='bold', va='top')
fig.text(0.05, 0.673, 'Percent of curated models and of background genotypes credited with each criterion unit', fontsize=11, va='top', color=INK)
axB = fig.add_axes([0.47, 0.04, 0.51, 0.6])
rows = []; y = 0; ticks = []; labels = []; colors = []; groups = []
STEP = 1.3
for D in ORDER:
    y0 = y
    for code, gloss, c, b in U[D]:
        rows.append((y, D, code, gloss, 100 * c / N[D][0], 100 * b / N[D][1], c)); ticks.append(y)
        labels.append(f'{code}  {gloss}'); colors.append(RED if c == 0 else INK); y += STEP
    groups.append((D, y0, y - STEP)); y += 0.9
bh = 0.48
KIND = {('SCZ','A1'):'no admitted analog', ('SCZ','A2'):'no admitted analog', ('SCZ','A3'):'no admitted analog', ('MDD','A7'):'no admitted analog', ('MDD','A9'):'no admitted analog', ('ASD','A2'):'no mouse term', ('MDD','A5'):'phenotyping gap', ('MDD','A6'):'phenotyping gap', ('MDD','A8'):'phenotyping gap', ('NCD','B'):'phenotyping gap'}
for yy, D, code, gloss, cp, bp, c in rows:
    axB.barh(yy - bh / 2, cp, height=bh, color=DARK); axB.barh(yy + bh / 2, bp, height=bh, color=LIGHT)
    kind = KIND.get((D, code))
    if c == 0 and bp == 0:
        axB.text(1.5, yy, kind, va='center', fontsize=9.5, color=RED, style='italic'); continue
    if c == 0 and kind:
        axB.text(bp + 1.5, yy + bh / 2, f'{bp:.1f}', va='center', fontsize=9, color='#2a6db0')
        axB.text(max(bp + 12, 30), yy - bh / 2, kind, va='center', fontsize=9.5, color=RED, style='italic'); continue
    axB.text(cp + 1.5, yy - bh / 2, f'{cp:.0f}', va='center', fontsize=9, color=DARK)
    axB.text(bp + 1.5, yy + bh / 2, f'{bp:.1f}', va='center', fontsize=9, color='#2a6db0')
axB.set_yticks(ticks); axB.set_yticklabels(labels, fontsize=9.5)
for t, c in zip(axB.get_yticklabels(), colors): t.set_color(c)
axB.set_ylim(y - 0.9 - 0.3, -0.8); axB.set_xlim(0, 114); axB.set_xticks([0, 25, 50, 75, 100]); axB.tick_params(axis='x', labelsize=9); axB.tick_params(axis='y', length=0)
axB.set_xlabel('percent credited with the unit', fontsize=10)
for s_ in ('top', 'right'): axB.spines[s_].set_visible(False)
XB = -72
for D, ya, yb in groups:
    axB.plot([XB + 2, XB, XB, XB + 2], [ya - 0.45, ya - 0.45, yb + 0.45, yb + 0.45], color=INK, lw=1.1, clip_on=False)
    axB.text(XB - 2.5, (ya + yb) / 2, f'{D}\n({N[D][0]})', ha='right', va='center', fontsize=10, fontweight='bold', color=INK, clip_on=False, linespacing=1.1)
axB.legend(handles=[Patch(color=DARK, label='curated models'), Patch(color=LIGHT, label='background genotypes')], loc='upper right', bbox_to_anchor=(1.0, 0.75), fontsize=9.5, frameon=False)
fig.savefig('fig3_units_2026-11-08.png', dpi=300, facecolor='white'); print('ok')
