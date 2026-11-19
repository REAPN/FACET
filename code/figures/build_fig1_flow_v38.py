import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Ellipse, Polygon
plt.rcParams['font.family'] = 'DejaVu Sans'; plt.rcParams['mathtext.fontset'] = 'dejavusans'
BLUE, GREEN, CRIM, INK, OK, NO = '#2f4f80', '#2d6a4f', '#9b1b30', '#111111', '#1b7f3b', '#b02a2a'
W, H = 70, 39
fig = plt.figure(figsize=(W / 10, H / 10), dpi=300); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
def rbox(x, y, w, h, ec, fc='white', lw=1.3, r=0.9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f'round,pad=0.25,rounding_size={r}', fc=fc, ec=ec, lw=lw))
def arrow(p1, p2, color=INK, lw=1.8, ms=12):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle='-|>', mutation_scale=ms, color=color, lw=lw, shrinkA=0, shrinkB=0, zorder=6))
def chip(x, y):
    ax.add_patch(FancyBboxPatch((x - 2.1, y - 0.75), 4.2, 1.5, boxstyle='round,pad=0.1,rounding_size=0.4', fc=CRIM, ec='none', zorder=5))
    ax.text(x, y, 'LLM', ha='center', va='center', fontsize=6.5, color='white', fontweight='bold', zorder=7)
def doc(x, y, color):
    w, h, c = 5.0, 6.4, 1.3
    ax.add_patch(Polygon([(x, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h)], closed=True, fc='white', ec=color, lw=1.4))
    ax.add_patch(Polygon([(x + w - c, y + h), (x + w - c, y + h - c), (x + w, y + h - c)], closed=True, fc=color, ec=color, lw=0.8))
    for k in range(4): ax.plot([x + 0.8, x + w - (1.6 if k == 0 else 0.8)], [y + h - 1.9 - 1.1 * k] * 2, color=color, lw=1.1)
def cylinder(x, y, w, h, color):
    ax.add_patch(Rectangle((x, y), w, h, fc='white', ec='none', zorder=2)); ax.plot([x, x], [y, y + h], color=color, lw=1.4, zorder=3); ax.plot([x + w, x + w], [y, y + h], color=color, lw=1.4, zorder=3)
    ax.add_patch(Ellipse((x + w / 2, y), w, 1.6, fc='white', ec=color, lw=1.4, zorder=2)); ax.add_patch(Rectangle((x + 0.07, y), w - 0.14, 0.9, fc='white', ec='none', zorder=2.5))
    ax.add_patch(Ellipse((x + w / 2, y + h), w, 1.6, fc='white', ec=color, lw=1.4, zorder=4))

for x, t in ((6.0, 'INPUTS'), (35.0, 'FACET'), (63.5, 'OUTPUTS')):
    ax.text(x, 37.4, t, ha='center', va='center', fontsize=9.5, fontweight='bold', color=INK)

doc(3.5, 25.0, BLUE); ax.text(6.0, 23.9, 'DSM-5-TR\ncriteria', ha='center', va='top', fontsize=7.5, color=BLUE, fontweight='bold', linespacing=1.15)
doc(3.5, 11.6, GREEN); ax.text(6.0, 10.5, 'mouse phenotype\nterms (MP)', ha='center', va='top', fontsize=7.5, color=GREEN, fontweight='bold', linespacing=1.15)

rbox(15.0, 7.0, 40.0, 28.4, INK, fc='#fafafa', lw=1.1, r=1.4)
for x, t in ((21.6, '1  Anchoring'), (35.0, '2  Judgment'), (48.4, '3  Aggregation')):
    ax.text(x, 33.6, t, ha='center', va='center', fontsize=8.5, fontweight='bold', color=INK)
rbox(16.6, 24.6, 10.0, 5.6, BLUE); ax.text(21.6, 28.4, 'HPO anchors', ha='center', va='center', fontsize=8, fontweight='bold', color=BLUE)
ax.text(21.6, 26.1, 'human terms', ha='center', va='center', fontsize=7, color=INK)
rbox(16.6, 11.2, 10.0, 5.6, GREEN); ax.text(21.6, 15.0, 'MP terms', ha='center', va='center', fontsize=8, fontweight='bold', color=GREEN)
ax.text(21.6, 12.7, 'by criterion', ha='center', va='center', fontsize=7, color=INK)
arrow((9.4, 28.2), (16.0, 28.2), BLUE); chip(12.6, 30.0)
arrow((9.4, 14.8), (16.0, 14.8), GREEN); chip(12.6, 16.6)
ax.plot([16.6, 26.6], [20.7, 20.7], color=INK, lw=0.8, ls=(0, (2, 2))); ax.text(21.6, 21.6, 'kept apart', ha='center', va='center', fontsize=7, color=INK, style='italic')
rbox(30.0, 13.6, 10.0, 14.2, CRIM, fc='#fdf2f4')
chip(35.0, 25.6)
ax.text(35.0, 22.2, 'analog?', ha='center', va='center', fontsize=8, fontweight='bold', color=CRIM)
ax.text(33.0, 18.8, '✓', ha='center', va='center', fontsize=13, color=OK, fontweight='bold'); ax.text(37.0, 18.8, '✗', ha='center', va='center', fontsize=13, color=NO, fontweight='bold')
ax.text(35.0, 15.4, 'blind to genes', ha='center', va='center', fontsize=7, color=CRIM, style='italic')
arrow((27.2, 27.0), (29.5, 23.4), BLUE); arrow((27.2, 14.4), (29.5, 18.0), GREEN)
cylinder(44.6, 17.2, 7.6, 7.2, INK)
ax.text(48.4, 20.4, 'genotypes\ncredited', ha='center', va='center', fontsize=7.5, color=INK, linespacing=1.15, zorder=5)
arrow((40.6, 20.7), (44.0, 20.7), OK); ax.text(42.3, 22.4, 'admitted', ha='center', va='center', fontsize=6.5, color=OK, style='italic', rotation=0)

arrow((55.6, 20.7), (58.0, 20.7), INK)
outs = [('1', 'Diagnostic\nCoverage', 'criteria a\ngenotype models'), ('2', 'Support\nscore', 'against random\nprofiles'), ('3', 'Public\ncatalogue', 'every genotype,\nper criterion')]
for i, (n, t, sub) in enumerate(outs):
    y = 30.6 - 9.4 * i
    ax.add_patch(Ellipse((59.4, y), 2.4, 2.4, fc=INK, ec='none')); ax.text(59.4, y, n, ha='center', va='center', fontsize=7.5, color='white', fontweight='bold')
    ax.text(61.2, y, t, ha='left', va='center', fontsize=8, fontweight='bold', color=INK, linespacing=1.1)
    ax.text(61.2, y - 3.5, sub, ha='left', va='center', fontsize=7, color=INK, linespacing=1.1)

rbox(1.0, 0.7, 68.0, 4.3, INK, fc='white', lw=1.0)
ax.text(2.0, 2.85, 'Example', ha='left', va='center', fontsize=7.5, fontweight='bold', color=INK)
ax.text(9.0, 2.85, 'depression, sleep criterion', ha='left', va='center', fontsize=7, color=BLUE)
ax.text(24.6, 2.85, 'Insomnia', ha='left', va='center', fontsize=7, color=BLUE, fontweight='bold')
ax.text(30.6, 2.85, 'with', ha='left', va='center', fontsize=7, color=INK)
ax.text(33.4, 2.85, 'decreased sleep duration', ha='left', va='center', fontsize=7, color=GREEN, fontweight='bold')
ax.text(48.6, 2.7, '✓', ha='center', va='center', fontsize=10, color=OK, fontweight='bold')
G = lambda g: r'$\mathit{' + g + '}$'
ax.text(50.4, 2.85, 'credits ' + G('Clock') + ', ' + G('Per2') + ' and others', ha='left', va='center', fontsize=7, color=INK)
fig.savefig('fig1_flow_2026-11-19.png', dpi=300, facecolor='white'); print('ok')
