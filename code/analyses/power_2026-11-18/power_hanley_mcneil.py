import math
N = 32535; POS = {'ASD': 85, 'SCZ': 42, 'IDD': 121, 'NCD': 71, 'MDD': 8}
def se(a, n1, n2):
    q1 = a / (2 - a); q2 = 2 * a * a / (1 + a)
    return math.sqrt((a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n2 - 1) * (q2 - a * a)) / (n1 * n2))
def mda(n1, n2, za=1.959964, zb=0.841621):
    lo, hi = 0.5, 0.999
    for _ in range(60):
        m = (lo + hi) / 2
        if m - 0.5 > za * se(0.5, n1, n2) + zb * se(m, n1, n2): hi = m
        else: lo = m
    return hi
print('| Curated models | Background | Half-width of the 95% interval at AUROC 0.5 | At AUROC 0.7 | Smallest AUROC detected with 80% power |'); print('|---|---|---|---|---|')
for d, n1 in list(POS.items()) + [('threshold', 30)]:
    n2 = N - n1
    print(f'| {d} ({n1}) | {n2:,} | {1.959964 * se(0.5, n1, n2):.3f} | {1.959964 * se(0.7, n1, n2):.3f} | {mda(n1, n2):.3f} |')
