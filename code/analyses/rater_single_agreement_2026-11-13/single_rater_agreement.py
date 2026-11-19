import sys, glob, random
from itertools import combinations
sys.path.insert(0, '.')
import _rating_analysis_v9 as R
files = sorted(glob.glob('FACET_SEND_PACKAGE_2026-09-10/rater_returns/facet_rating_*.json'))
key, pop, meta, runs = R.load('_rating_pilot_2026_v9', files)
del key
P = {}
for run in runs:
    for r in R.first_pass(run['rows']):
        if r['q1'] == R.CANNOT: continue
        P.setdefault(r['iid'], [bool(r['positive']), []])[1].append(R.rater_composite(r))
BOOT, rng = 2000, random.Random(20261113)
def rr(keys):
    t = c = 0
    for k in keys:
        for x, y in combinations(P[k][1], 2): t += (x == y); c += 1
    return t / c, c
def lr(keys):
    t = c = 0
    for k in keys:
        for v in P[k][1]: t += (v == P[k][0]); c += 1
    return t / c, c
def boot(keys, f):
    bs = sorted(f([keys[rng.randrange(len(keys))] for _ in keys]) for _ in range(BOOT))
    return bs[int(0.025 * BOOT)], bs[int(0.975 * BOOT) - 1]
allk = sorted(P); two = [k for k in allk if len(P[k][1]) >= 2]
print('runs', len(runs), '| pairs with a definite rating', len(allk), '| pairs with two or more', len(two),
      '| of which admitted by the LLM', sum(P[k][0] for k in two))
for name, keys in (('all rated pairs', allk), ('pairs with two or more raters', two)):
    a, n = lr(keys); lo, hi = boot(keys, lambda ks: lr(ks)[0])
    print(f'LLM against a single rater, {name}: {a:.3f} ({n} ratings on {len(keys)} pairs), 95 percent {lo:.3f} to {hi:.3f}')
    for cls, lab in ((True, 'admitted'), (False, 'refused')):
        kk = [k for k in keys if P[k][0] == cls]; a2, n2 = lr(kk); print(f'   {lab}: {a2:.3f} ({n2} ratings on {len(kk)} pairs)')
a, n = rr(two); lo, hi = boot(two, lambda ks: rr(ks)[0])
print(f'two raters on the same pair: {a:.3f} ({n} dyads on {len(two)} pairs), 95 percent {lo:.3f} to {hi:.3f}')
for cls, lab in ((True, 'admitted by the LLM'), (False, 'refused by the LLM')):
    kk = [k for k in two if P[k][0] == cls]; a2, n2 = rr(kk); print(f'   {lab}: {a2:.3f} ({n2} dyads on {len(kk)} pairs)')
d = lr(two)[0] - rr(two)[0]; lo, hi = boot(two, lambda ks: lr(ks)[0] - rr(ks)[0])
print(f'difference on the same pairs, LLM-rater minus rater-rater: {d:+.3f}, 95 percent {lo:+.3f} to {hi:+.3f}')
maj = [k for k in allk if sum(P[k][1]) * 2 != len(P[k][1])]
print('LLM against the rater majority (ties dropped):', f'{sum((sum(P[k][1]) * 2 > len(P[k][1])) == P[k][0] for k in maj) / len(maj):.3f}', 'on', len(maj), 'pairs')
