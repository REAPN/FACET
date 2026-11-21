import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, Rectangle, Ellipse, Polygon, ArrowStyle
plt.rcParams['font.family'] = 'DejaVu Sans'; plt.rcParams['mathtext.fontset'] = 'dejavusans'
BLUE, GREEN, CRIM, INK, OK, NO, PALE = '#2f4f80', '#2d6a4f', '#9b1b30', '#111111', '#1b7f3b', '#b02a2a', '#b9c7dd'
W, H = 70, 39
fig = plt.figure(figsize=(W / 10, H / 10), dpi=300); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis('off')
def box(x, y, w, h, ec, fc='white', lw=1.3, z=1):
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=lw, joinstyle='miter', zorder=z))
def arrow(p1, p2, color=INK, lw=1.5, ms=9):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle=ArrowStyle('-|>', head_length=0.9, head_width=0.32), mutation_scale=ms, color=color, lw=lw,
                                 shrinkA=0, shrinkB=0, joinstyle='miter', capstyle='butt', zorder=6))
def chip(x, y):
    ax.add_patch(Rectangle((x - 1.7, y - 0.65), 3.4, 1.3, fc=CRIM, ec='none', zorder=5))
    ax.text(x, y, 'LLM', ha='center', va='center', fontsize=6, color='white', fontweight='bold', zorder=7)
def doc(x, y, color):
    w, h, c = 5.0, 6.4, 1.3
    ax.add_patch(Polygon([(x, y), (x + w, y), (x + w, y + h - c), (x + w - c, y + h), (x, y + h)], closed=True, fc='white', ec=color, lw=1.4, joinstyle='miter'))
    ax.add_patch(Polygon([(x + w - c, y + h), (x + w - c, y + h - c), (x + w, y + h - c)], closed=True, fc=color, ec=color, lw=0.8, joinstyle='miter'))
    for k in range(4): ax.plot([x + 0.8, x + w - (1.6 if k == 0 else 0.8)], [y + h - 1.9 - 1.1 * k] * 2, color=color, lw=1.1, solid_capstyle='butt')

for x, t in ((5.5, 'INPUTS'), (32.0, 'FACET'), (61.5, 'OUTPUTS')):
    ax.text(x, 37.4, t, ha='center', va='center', fontsize=9.5, fontweight='bold', color=INK)

doc(3.0, 24.2, BLUE); ax.text(5.5, 23.1, 'DSM-5-TR\ncriteria', ha='center', va='top', fontsize=7.5, color=BLUE, fontweight='bold', linespacing=1.15)
doc(3.0, 10.8, GREEN); ax.text(5.5, 9.7, 'mouse phenotype\nterms (MP)', ha='center', va='top', fontsize=7.5, color=GREEN, fontweight='bold', linespacing=1.15)

box(13.4, 6.9, 37.4, 28.6, INK, fc='#fafafa', lw=1.1, z=0)
for x, t in ((19.6, '1  Anchoring'), (32.5, '2  Judgment'), (44.4, '3  Aggregation')):
    ax.text(x, 33.6, t, ha='center', va='center', fontsize=8.5, fontweight='bold', color=INK)
box(14.8, 24.2, 9.6, 6.6, BLUE); chip(17.0, 29.7)
ax.text(19.6, 27.6, 'HPO anchors', ha='center', va='center', fontsize=8, fontweight='bold', color=BLUE)
ax.text(19.6, 25.6, 'human terms', ha='center', va='center', fontsize=7, color=INK)
box(14.8, 10.8, 9.6, 6.6, GREEN); chip(17.0, 16.3)
ax.text(19.6, 14.2, 'MP terms', ha='center', va='center', fontsize=8, fontweight='bold', color=GREEN)
ax.text(19.6, 12.2, 'by criterion', ha='center', va='center', fontsize=7, color=INK)
arrow((8.6, 27.4), (12.9, 27.4), BLUE); arrow((8.6, 14.0), (12.9, 14.0), GREEN)
ax.plot([14.8, 24.4], [20.4, 20.4], color=INK, lw=0.8, ls=(0, (2, 2))); ax.text(19.6, 21.4, 'kept apart', ha='center', va='center', fontsize=7, color=INK, style='italic')
box(27.6, 13.6, 9.8, 14.2, CRIM, fc='#fdf2f4')
chip(32.5, 25.8)
ax.text(32.5, 22.4, 'analog?', ha='center', va='center', fontsize=8, fontweight='bold', color=CRIM)
ax.text(30.5, 19.0, '✓', ha='center', va='center', fontsize=13, color=OK, fontweight='bold'); ax.text(34.5, 19.0, '✗', ha='center', va='center', fontsize=13, color=NO, fontweight='bold')
ax.text(32.5, 15.5, 'blind to genes', ha='center', va='center', fontsize=7, color=CRIM, style='italic')
arrow((24.8, 26.4), (27.2, 23.2), BLUE); arrow((24.8, 15.0), (27.2, 18.2), GREEN)
arrow((37.8, 20.7), (41.3, 20.7), OK); ax.text(39.5, 21.9, 'admitted', ha='center', va='center', fontsize=5.6, color=OK, style='italic')
gx, gy, cs = 41.9, 18.0, 1.15
FILL = [(0, 0), (0, 1), (0, 3), (1, 1), (2, 0), (2, 2), (2, 3), (2, 5), (3, 4), (4, 1), (4, 2)]
for r in range(5):
    for c in range(6):
        ax.add_patch(Rectangle((gx + c * cs, gy + (4 - r) * cs), cs, cs, fc=(INK if (r, c) in FILL else 'white'), ec=INK, lw=0.6, joinstyle='miter', zorder=3))
ax.text(gx + 3 * cs, gy + 5 * cs + 0.9, 'criteria', ha='center', va='center', fontsize=6.3, color=INK)
ax.text(gx + 3 * cs, gy - 2.1, 'genotypes credited\nwith criteria', ha='center', va='center', fontsize=7, color=INK, linespacing=1.15)
ax.text(gx + 3 * cs, gy - 5.2, 'one row per genotype', ha='center', va='center', fontsize=6.3, color=INK, style='italic')

arrow((51.3, 20.7), (53.3, 20.7), INK)
OX, TX = 54.9, 56.7
def head(y, n, t):
    ax.add_patch(Ellipse((OX, y), 2.4, 2.4, fc=INK, ec='none')); ax.text(OX, y, n, ha='center', va='center', fontsize=7.5, color='white', fontweight='bold')
    ax.text(TX, y, t, ha='left', va='center', fontsize=8, fontweight='bold', color=INK, linespacing=1.1)
head(32.2, '1', 'Diagnostic\nCoverage')
for k in range(7): ax.add_patch(Rectangle((TX + k * 1.05, 28.6), 0.85, 0.85, fc=(INK if k in (0, 2, 3, 5) else 'white'), ec=INK, lw=0.6, joinstyle='miter'))
ax.text(TX + 7.8, 29.0, '4 of 7', ha='left', va='center', fontsize=6.5, color=INK)
ax.text(TX, 26.8, 'how many criteria a\ngenotype models', ha='left', va='center', fontsize=6.8, color=INK, linespacing=1.1)
head(22.4, '2', 'Support\nscore')
HB = [0.5, 1.1, 1.9, 2.3, 1.8, 1.2, 0.7, 0.35]
for k, hgt in enumerate(HB): ax.add_patch(Rectangle((TX + k * 0.8, 17.6), 0.68, hgt, fc=PALE, ec='none'))
ax.plot([TX - 0.2, TX + 9.6], [17.6, 17.6], color=INK, lw=0.7, solid_capstyle='butt')
ax.plot([TX + 8.6, TX + 8.6], [17.6, 20.0], color=CRIM, lw=1.3, solid_capstyle='butt')
ax.text(TX + 3.2, 16.9, 'random', ha='center', va='center', fontsize=5.8, color=INK); ax.text(TX + 8.6, 20.6, 'genotype', ha='center', va='center', fontsize=5.8, color=CRIM)
ax.text(TX, 14.6, 'how unusual its match is\namong random profiles\nof the same size', ha='left', va='center', fontsize=6.8, color=INK, linespacing=1.1)
head(10.4, '3', 'Public\ncatalogue')
ax.text(TX, 7.5, 'every genotype,\nper criterion', ha='left', va='center', fontsize=6.8, color=INK, linespacing=1.1)

box(1.0, 0.7, 68.0, 4.3, INK, fc='white', lw=1.0)
ax.text(2.0, 2.85, 'Example', ha='left', va='center', fontsize=7.5, fontweight='bold', color=INK)
ax.text(9.0, 2.85, 'depression, sleep criterion', ha='left', va='center', fontsize=7, color=BLUE)
ax.text(24.6, 2.85, 'Insomnia', ha='left', va='center', fontsize=7, color=BLUE, fontweight='bold')
ax.text(30.6, 2.85, 'with', ha='left', va='center', fontsize=7, color=INK)
ax.text(33.4, 2.85, 'decreased sleep duration', ha='left', va='center', fontsize=7, color=GREEN, fontweight='bold')
ax.text(48.6, 2.7, '✓', ha='center', va='center', fontsize=10, color=OK, fontweight='bold')
G = lambda g: r'$\mathit{' + g + '}$'
ax.text(50.4, 2.85, 'credits ' + G('Clock') + ', ' + G('Per2') + ' and others', ha='left', va='center', fontsize=7, color=INK)
fig.savefig('fig1_flow_2026-11-20.png', dpi=300, facecolor='white'); print('ok')
