import math, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
plt.rcParams['font.family'] = 'DejaVu Sans'
DARK, LIGHT, RED, INK = '#1f4e79', '#8dbbe6', '#b02a2a', '#111111'

def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - hw, c + hw

fig, axes = plt.subplots(2, 1, figsize=(7.5, 7.6), dpi=300, gridspec_kw={'hspace': 0.55})
ax = axes[0]
labels = ['composite,\nadmitted pairs', 'composite,\nrefused pairs', 'criterion match,\npairs grounded\nto the criterion', 'criterion match,\npairs not grounded\nto it']
rate = [0.662, 0.884, 0.788, 0.733]; lo = [0.551, 0.793, 0.682, 0.625]; hi = [0.758, 0.939, 0.866, 0.818]; cols = [DARK, RED, DARK, RED]
ax.bar(range(4), rate, color=cols, width=0.62)
ax.errorbar(range(4), rate, yerr=[[r - l for r, l in zip(rate, lo)], [hh - r for r, hh in zip(rate, hi)]], fmt='none', ecolor=INK, capsize=4, lw=1.2)
for i, r in enumerate(rate): ax.text(i, 0.05, f'{r:.2f}', ha='center', color='white', fontsize=10, fontweight='bold')
ax.axhline(0.70, color=INK, ls=':', lw=1.1); ax.axhline(0.85, color=INK, ls='--', lw=1.1)
ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=9.5); ax.set_ylim(0, 1.05); ax.set_ylabel('agreement with the pipeline', fontsize=10)
ax.set_title('A   Agreement with the pipeline by outcome', fontsize=11, fontweight='bold', loc='left')

ax = axes[1]
dis = ['ASD', 'IDD', 'MDD', 'NCD', 'SCZ']
ka = [29, 23, 9, 16, 14]; na = [43, 30, 12, 26, 27]
kr = [35, 23, 8, 21, 29]; nr = [36, 28, 12, 25, 29]
w = 0.36; x = list(range(5))
for off, k, n, col in ((-w / 2, ka, na, DARK), (w / 2, kr, nr, RED)):
    r = [a / b for a, b in zip(k, n)]; ci = [wilson(a, b) for a, b in zip(k, n)]
    xs = [xi + off for xi in x]
    ax.bar(xs, r, color=col, width=w)
    ax.errorbar(xs, r, yerr=[[c - l for c, (l, u) in zip(r, ci)], [u - c for c, (l, u) in zip(r, ci)]], fmt='none', ecolor=INK, capsize=3, lw=1.1)
    for xi, a, b in zip(xs, k, n): ax.text(xi, 0.04, f'{a}\nof\n{b}', ha='center', fontsize=8.5, color='white', fontweight='bold', linespacing=1.0)
ax.axhline(0.70, color=INK, ls=':', lw=1.1); ax.axhline(0.85, color=INK, ls='--', lw=1.1)
ax.set_xticks(x); ax.set_xticklabels(dis, fontsize=10.5); ax.set_ylim(0, 1.05); ax.set_ylabel('agreement with the pipeline', fontsize=10)
ax.set_title('B   Agreement by disorder, admitted and refused pairs', fontsize=11, fontweight='bold', loc='left')
for a in axes:
    for s in ('top', 'right'): a.spines[s].set_visible(False)
    a.tick_params(axis='y', labelsize=9.5)
fig.legend(handles=[Patch(color=DARK, label='admitted pairs\nconfirmed, or\npairs grounded'), Patch(color=RED, label='refused pairs\nagreed, or pairs\nnot grounded'),
                    Line2D([], [], color=INK, ls=':', lw=1.1, label='floor 0.70'), Line2D([], [], color=INK, ls='--', lw=1.1, label='bar 0.85')],
           loc='center left', bbox_to_anchor=(0.79, 0.5), fontsize=9.5, frameon=False, labelspacing=1.3, handlelength=1.6)
fig.subplots_adjust(left=0.10, right=0.77, top=0.95, bottom=0.07); fig.savefig('fig7_raters_2026-11-17.png', dpi=300, facecolor='white'); print('ok')
