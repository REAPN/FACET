import json, numpy as np, matplotlib
matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams['font.family'] = 'DejaVu Sans'
COV = json.loads('{"ASD-SCZ": [429, 1181, 186, 15.6, 11.9, 167.7, 1.11], "ASD-IDD": [417, 264, 155, 3.4, 45.53, 55.7, 2.78], "ASD-NCD": [437, 63, 11, 0.9, 12.94, 10.8, 1.02], "ASD-MDD": [439, 46, 12, 0.6, 19.28, 10.2, 1.18], "SCZ-IDD": [1191, 292, 186, 10.7, 17.31, 127.0, 1.47], "SCZ-NCD": [1215, 66, 21, 2.5, 8.49, 23.8, 0.88], "SCZ-MDD": [1228, 43, 35, 1.6, 21.53, 18.7, 1.87], "IDD-NCD": [306, 66, 8, 0.6, 12.81, 9.8, 0.82], "IDD-MDD": [304, 46, 8, 0.4, 18.54, 8.1, 0.99], "NCD-MDD": [65, 46, 3, 0.1, 32.57, 1.3, 2.36]}')
SUP = json.loads('{"ASD-SCZ": [560, 578, 173, 10.0, 17.32, 58.9, 2.94], "ASD-IDD": [546, 548, 172, 9.3, 18.59, 58.7, 2.93], "ASD-NCD": [573, 652, 143, 11.5, 12.39, 58.8, 2.43], "SCZ-IDD": [604, 592, 152, 11.0, 13.76, 71.4, 2.13], "SCZ-NCD": [638, 681, 129, 13.4, 9.63, 70.8, 1.82], "IDD-NCD": [600, 644, 312, 11.9, 26.12, 63.6, 4.91]}')
json.dump({"COV": COV, "SUP": SUP}, open('s1fig_values.json', 'w'), indent=1)
fig, axes = plt.subplots(1, 2, figsize=(6.5, 3.4), dpi=300, gridspec_kw={'width_ratios': [5, 4]})
cmap = matplotlib.colors.LinearSegmentedColormap.from_list('b', ['#ffffff', '#8dbbe6', '#1f4e79'])
for ax, data, Ds, title in [(axes[0], COV, ['ASD', 'SCZ', 'IDD', 'NCD', 'MDD'], 'A   Coverage top tiers'), (axes[1], SUP, ['ASD', 'SCZ', 'IDD', 'NCD'], 'B   Support score, top 2 percent')]:
    n = len(Ds); M = np.full((n, n), np.nan)
    for k, v in data.items():
        a, b = k.split('-'); i, j = Ds.index(a), Ds.index(b); M[j, i] = v[6]
    Msub = M[1:, :-1]
    ax.imshow(np.ma.masked_invalid(Msub), cmap=cmap, vmin=0, vmax=5)
    for i in range(n - 1):
        for j in range(n - 1):
            v = Msub[j, i]
            if not np.isnan(v):
                k = f"{Ds[i]}-{Ds[j + 1]}"; ov = data[k][2]
                ax.text(i, j, f"{v:.2f}\n({ov})", ha='center', va='center', fontsize=8, color='white' if v > 3 else '#111111')
    ax.set_xticks(range(n - 1)); ax.set_xticklabels(Ds[:-1], fontsize=9); ax.set_yticks(range(n - 1)); ax.set_yticklabels(Ds[1:], fontsize=9)
    ax.set_title(title, fontsize=9.5, fontweight='bold', loc='left')
    for s in ax.spines.values(): s.set_visible(False)
    ax.tick_params(length=0)
fig.text(0.5, 0.03, 'observed over expected overlap, behavioral depth held fixed (observed count in parentheses)', ha='center', fontsize=8)
plt.tight_layout(rect=(0, 0.06, 1, 1)); fig.savefig('S1_Fig_overlap.png', dpi=300, facecolor='white'); print('ok')
