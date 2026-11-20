import csv, json, random, hashlib, io, sys
from pathlib import Path

OUT = Path("_rating_pilot_2026_v9")
SEED = 20260913
N_CODES = 12
N_ANCHOR = 3
BLOCK = 4
PER_CLASS = {"ASD": 24, "SCZ": 18, "ID": 18, "NCD": 16, "MDD": 8}
N_BLOCKS = 12
K = 3
PARTITIONS = [[(0, 4, 8), (1, 5, 9), (2, 6, 10), (3, 7, 11)],
              [(0, 5, 10), (1, 6, 11), (2, 7, 8), (3, 4, 9)],
              [(0, 7, 9), (1, 4, 10), (2, 5, 11), (3, 6, 8)]]

src = io.open("_rating_criterion_map.py", encoding="utf-8").read()
exec(src)
SEED = 20260913
N_CODES = 12
N_ANCHOR = 3
BLOCK = 4
OUT = Path("_rating_pilot_2026_v9")
if "--n_codes" in sys.argv:
    N_CODES = int(sys.argv[sys.argv.index("--n_codes") + 1])
CRITMAP = criterion_map()
print("criterion map:", len(CRITMAP), "hpo_id to criterion links")


def truthy(s):
    return (s or "").strip().lower() in ("true", "1", "yes")


def stratum_of(r):
    if truthy(r.get("strict_eligible")): return "S1"
    if truthy(r.get("broad_eligible")):  return "S2"
    if (r.get("relevance_tier") or "").strip() == "1": return "S3"
    if (r.get("behavioral_analog_type") or "").strip(): return "S4"
    return "S5"


def load(d, path):
    rows, seen = [], set()
    for r in csv.DictReader(io.open(path, encoding="utf-8", errors="replace"), delimiter="\t"):
        mp, hp = (r.get("mp_id") or "").strip(), (r.get("hpo_id") or "").strip()
        if not mp.startswith("MP:") or not hp.startswith("HP:"): continue
        cm = CRITMAP.get((d, hp))
        if not cm: continue
        mpdef = (r.get("mp_definition") or "").strip()
        if not mpdef: continue
        if (r.get("retrieval_channels") or "").find("rescue") >= 0: continue
        if not (r.get("evidence_scope") or "").strip(): continue
        if (hp, mp) in seen: continue
        seen.add((hp, mp))
        cid, clabel, cgloss = cm
        crit = (clabel + ". " + cgloss.rstrip(".") + ".") if cgloss.strip() else clabel
        rows.append(dict(
            disorder=d, hpo_id=hp, hpo_label=(r.get("hpo_label") or "").strip(),
            criterion=crit, cid=cid, mp_id=mp, mp_label=(r.get("mp_label") or "").strip(),
            mp_def=mpdef,
            tier=(r.get("relevance_tier") or "").strip(),
            grade=(r.get("behavioral_analog_type") or "").strip() or "ungraded",
            scope=(r.get("evidence_scope") or "").strip(),
            comparable=truthy(r.get("comparable_observable")),
            strict=truthy(r.get("strict_eligible")), broad=truthy(r.get("broad_eligible")),
            stratum=stratum_of(r)))
    return rows


rng = random.Random(SEED)
pool = {}
for d, p in RERANK.items():
    rows = load(d, p)
    for r in rows:
        r["positive"] = (r["stratum"] == "S1")
    pos = sorted([r for r in rows if r["positive"]], key=lambda r: (r["hpo_id"], r["mp_id"]))
    neg = sorted([r for r in rows if not r["positive"]], key=lambda r: (r["hpo_id"], r["mp_id"]))
    pool[d] = dict(pos=pos, neg=neg)
    print(f"[{d}] positive(S1)={len(pos)}  negative(S2-S5)={len(neg)}")

used = set()
def key(r): return (r["hpo_id"], r["mp_id"])


NEG_TOTAL = sum(PER_CLASS.values())
_negpop = {}
for _d in RERANK:
    for _r in pool[_d]["neg"]:
        _negpop[_r["stratum"]] = _negpop.get(_r["stratum"], 0) + 1
_strata_all = sorted(_negpop)
_tot = sum(_negpop.values())
_q = {s: NEG_TOTAL * _negpop[s] / _tot for s in _strata_all}
NEG_QUOTA = {s: int(_q[s]) for s in _strata_all}
while sum(NEG_QUOTA.values()) < NEG_TOTAL:
    s = max(_strata_all, key=lambda s: _q[s] - NEG_QUOTA[s])
    NEG_QUOTA[s] += 1
print("negative stratum quota, proportional to the population:", NEG_QUOTA,
      "of", NEG_TOTAL, "negatives")


def draw_spread(items, n, prng):
    if n <= 0: return []
    avail = {}
    for r in items:
        if key(r) not in used:
            avail.setdefault(r["stratum"], []).append(r)
    for s in avail:
        avail[s].sort(key=lambda r: (r["hpo_id"], r["mp_id"]))
        prng.shuffle(avail[s])
    out = []
    while len(out) < n:
        cand = [s for s in avail if avail[s] and NEG_QUOTA.get(s, 0) > 0]
        if cand:
            s = max(cand, key=lambda s: (NEG_QUOTA[s], len(avail[s]), s))
        else:
            cand = [s for s in avail if avail[s]]
            if not cand: break
            s = max(cand, key=lambda s: (len(avail[s]), s))
        r = avail[s].pop()
        NEG_QUOTA[s] = max(0, NEG_QUOTA.get(s, 0) - 1)
        used.add(key(r)); out.append(r)
    return out


def draw_plain(items, n, prng):
    avail = [r for r in items if key(r) not in used]
    prng.shuffle(avail)
    out = avail[:n]
    for r in out: used.add(key(r))
    return out


drng = random.Random(SEED + 1)
POS, NEG = [], []
for d in RERANK:
    POS += draw_plain(pool[d]["pos"], PER_CLASS[d], drng)
    NEG += draw_spread(pool[d]["neg"], PER_CLASS[d], drng)
assert len(POS) == len(NEG) == sum(PER_CLASS.values()), (len(POS), len(NEG))
print(f"\nitem set: {len(POS)} accepted + {len(NEG)} refuted = {len(POS)+len(NEG)} pairs")

def deal(rows, prng):
    by = {}
    for r in rows: by.setdefault(r["disorder"], []).append(r)
    order = []
    for d in RERANK:
        xs = by.get(d, []); prng.shuffle(xs); order += xs
    blocks = [[] for _ in range(N_BLOCKS)]
    for i, r in enumerate(order): blocks[i % N_BLOCKS].append(r)
    return blocks
brng = random.Random(SEED + 2)
BLOCKS = [p + n for p, n in zip(deal(POS, brng), deal(NEG, brng))]
for b in BLOCKS: assert sum(1 for r in b if r["stratum"] == "S1") == 7 and len(b) == 14

ANCHORS = [
 dict(disorder="ANCHOR", hpo_id="HP:0000733", hpo_label="Motor stereotypy",
      criterion="Repetitive motor movements, repetitive use of objects, or repetitive speech.",
      mp_id="MP:0001409", mp_label="increased stereotypic behavior",
      mp_def="increased frequency of repetitive, invariant motor patterns with no obvious goal or function",
      expect=True, expect_map=["direct", "close"]),
 dict(disorder="ANCHOR", hpo_id="HP:0002360", hpo_label="Sleep abnormality",
      criterion="Sleeping too little or too much on most days.",
      mp_id="MP:0002574", mp_label="increased circulating iron level",
      mp_def="greater than normal concentration of iron in the blood",
      expect=False, expect_map=["unrelated", "weak"]),
 dict(disorder="ANCHOR", hpo_id="HP:0100543", hpo_label="Cognitive impairment",
      criterion="Evidence of significant cognitive decline from a previous level of performance.",
      mp_id="MP:0002062", mp_label="impaired learning",
      mp_def="reduced ability to acquire new information or skills through experience or instruction",
      expect=True, expect_map=["direct", "close"])]


items = []
for bi, blk in enumerate(BLOCKS):
    for j, r in enumerate(blk):
        items.append(dict(r, block=f"B{bi:02d}", code="", iid=f"B{bi:02d}I{j:02d}"))
for j, a in enumerate(ANCHORS):
    items.append(dict(a, block="anchor", code="", stratum="", cid="", tier="", grade="",
                      scope="", comparable=None, strict=None, broad=None, positive=None,
                      iid=f"A{j:02d}"))
for x in items: x["positive"] = (x.get("stratum") == "S1") if x["block"] != "anchor" else None
pmap = {}
for x in items:
    x["pid"] = "P" + hashlib.sha256(f"{SEED}:{x['iid']}".encode()).hexdigest()[:6]
    if x["pid"] in pmap: sys.exit("screen id collision, change SEED")
    pmap[x["pid"]] = x["iid"]
byiid = {x["iid"]: x for x in items}
anchor_iids = [x["iid"] for x in items if x["block"] == "anchor"]

def rater_blocks(k):
    part, slot = divmod(k, 4)
    return PARTITIONS[part][slot]

def balanced_order(iids, prng):
    pos = [i for i in iids if byiid[i]["positive"]]; neg = [i for i in iids if not byiid[i]["positive"]]
    prng.shuffle(pos); prng.shuffle(neg)
    H = BLOCK // 2; order = []
    nb = min(len(pos), len(neg)) // H
    for b in range(nb):
        blk = pos[H*b:H*b+H] + neg[H*b:H*b+H]; prng.shuffle(blk); order += blk
    rest = pos[H*nb:] + neg[H*nb:]; prng.shuffle(rest)
    return order + rest

def weave_anchors(order, prng):
    anc = anchor_iids[:]; prng.shuffle(anc)
    seq = list(order); taken = []
    step = (len(order) + 1) / (len(anc) + 1.0)
    for j, a in enumerate(anc):
        pos = min(len(seq), max(2, int(round((j + 1) * step)) + j))
        while pos in taken or (pos - 1) in taken or (pos + 1) in taken:
            pos += 1
            if pos > len(seq): pos = len(seq); break
        taken.append(pos); seq.insert(pos, a)
    return seq

runs = {}
for k in range(N_CODES):
    cd = chr(65 + k)
    prng = random.Random(SEED * 1000 + ord(cd))
    mine = [x["iid"] for x in items if x["block"] in {f"B{b:02d}" for b in rater_blocks(k)}]
    pos = [i for i in mine if byiid[i]["positive"]]; neg = [i for i in mine if not byiid[i]["positive"]]
    prng.shuffle(pos); prng.shuffle(neg)
    part1 = weave_anchors(balanced_order(pos[:11] + neg[:11], prng), prng)
    part2 = balanced_order(pos[11:] + neg[11:], prng)
    runs[cd] = dict(core=part1, ext=part2)
    print(f"  code {cd}: blocks {rater_blocks(k)}, part one {len(part1)} screens (incl {N_ANCHOR} anchors), part two {len(part2)}")

cov = {}
for cd, r in runs.items():
    for i in r["core"] + r["ext"]:
        if byiid[i]["block"] != "anchor": cov.setdefault(i, []).append(cd)
assert all(len(v) == K for v in cov.values()) and len(cov) == 2 * sum(PER_CLASS.values())
assert all(len({(ord(c) - 65) // 4 for c in v}) == K for v in cov.values())
viol = 0
for cd, r in runs.items():
    for part in (r["core"], r["ext"]):
        scored = [i for i in part if byiid[i]["block"] != "anchor"]
        for b in range(len(scored) // BLOCK):
            blk = scored[BLOCK*b:BLOCK*(b+1)]
            if sum(1 for i in blk if byiid[i]["positive"]) != BLOCK // 2: viol += 1
print("coverage: every pair rated by", K, "raters from three partitions; block-balance violations:", viol)
edges = {cd: set() for cd in runs}
for a in runs:
    for b in runs:
        if a < b and set(rater_blocks(ord(a) - 65)) & set(rater_blocks(ord(b) - 65)):
            edges[a].add(b); edges[b].add(a)
seen, stack = set(), [next(iter(runs))]
while stack:
    c = stack.pop()
    if c in seen: continue
    seen.add(c); stack.extend(edges[c] - seen)
assert len(seen) == len(runs), "rater graph is not connected"
deg = sorted(len(v) for v in edges.values())
print(f"connectivity: rater graph connected, {sum(deg)//2} linked dyads of {len(runs)*(len(runs)-1)//2}, "
      f"each rater linked to {deg[0]} to {deg[-1]} others through a shared block of 14")

OUT.mkdir(exist_ok=True)
KEYF = OUT / "SEALED_KEY_do_not_open.json"
if KEYF.exists(): KEYF.replace(OUT / "SEALED_KEY_do_not_open.json.bak_prev")
iid2pid = {x["iid"]: x["pid"] for x in items}
key_items = [{f: x.get(f) for f in ("pid", "iid", "block", "code", "positive", "stratum",
             "disorder", "cid", "hpo_id", "mp_id", "tier", "grade", "scope", "comparable",
             "strict", "broad", "expect", "expect_map")} for x in items]
BUILD = f"v9_k3_168pairs_n{N_CODES}_judged"
KEYF.write_text(json.dumps(dict(
    build=BUILD, seed=SEED, n_codes=N_CODES, n_anchor=N_ANCHOR, k_per_pair=K,
    core_size=0, unique_size_per_code=0, pairs=2 * sum(PER_CLASS.values()),
    partitions=PARTITIONS, rater_blocks={chr(65+k): rater_blocks(k) for k in range(N_CODES)},
    class_map="positive = strict-gate analog (close or direct); negative = everything else",
    pid_to_iid=pmap,
    runs={cd: {"core": [iid2pid[i] for i in runs[cd]["core"]],
               "ext":  [iid2pid[i] for i in runs[cd]["ext"]]} for cd in runs},
    items=key_items), indent=1))
blind = [{"pid": x["pid"],
          "disorder": "" if x["block"] == "anchor" else DNAME[x["disorder"]],
          "criterion": x["criterion"], "hpo_id": x["hpo_id"], "hpo_label": x["hpo_label"],
          "mp_id": x["mp_id"], "mp_label": x["mp_label"], "mp_def": x["mp_def"]} for x in items]
(OUT / "items_blinded.json").write_text(json.dumps(blind, indent=1))
(OUT / "runs_blinded.json").write_text(json.dumps(
    {cd: {"core": [iid2pid[i] for i in runs[cd]["core"]],
          "ext":  [iid2pid[i] for i in runs[cd]["ext"]]} for cd in runs}, indent=1))
per_d = {}
for d in RERANK:
    s = {k: 0 for k in ("S1", "S2", "S3", "S4", "S5")}
    for r in pool[d]["pos"] + pool[d]["neg"]: s[r["stratum"]] += 1
    per_d[d] = dict(positive=len(pool[d]["pos"]), negative=len(pool[d]["neg"]),
                    rateable=len(pool[d]["pos"]) + len(pool[d]["neg"]), strata=s,
                    drawn_positive=PER_CLASS[d], drawn_negative=PER_CLASS[d])
pos_pop = sum(per_d[d]["positive"] for d in per_d); neg_pop = sum(per_d[d]["negative"] for d in per_d)
(OUT / "population.json").write_text(json.dumps(dict(
    note=("binary sampling frame for the v9 instrument (judged pairs on scored criteria), 168 pairs in 12 blocks of 14, "
          "every pair rated by three raters from three orthogonal partitions. positive = strict-gate analog; "
          "negative = everything else. population-weighted agreement reweights each disorder and class by its population count over its drawn count."),
    build=BUILD, seed=SEED, positive_population=pos_pop, negative_population=neg_pop,
    rateable=pos_pop + neg_pop, positive_prevalence=round(pos_pop / (pos_pop + neg_pop), 4),
    core_positive=sum(PER_CLASS.values()), core_negative=sum(PER_CLASS.values()),
    per_disorder=per_d), indent=1))
print(f"\nbuilt {len(items)} items: {2*sum(PER_CLASS.values())} pairs in {N_BLOCKS} blocks, {len(ANCHORS)} anchors, {N_CODES} codes")
print("sha256 of blinded items:", hashlib.sha256(json.dumps(blind).encode()).hexdigest()[:16])
