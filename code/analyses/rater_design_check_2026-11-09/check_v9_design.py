#!/usr/bin/env python3
import json, re, sys, collections
from pathlib import Path
R = Path.cwd(); V = R / "_rating_pilot_2026_v9"
PART = [[(0, 4, 8), (1, 5, 9), (2, 6, 10), (3, 7, 11)], [(0, 5, 10), (1, 6, 11), (2, 7, 8), (3, 4, 9)], [(0, 7, 9), (1, 4, 10), (2, 5, 11), (3, 6, 8)]]
CODES = "ABCDEFGHIJKL"
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name + (f"  [{detail}]" if detail else ""))
pages = {c: R / f"FACET_SEND_PACKAGE_2026-09-10/rater_packages_2026-10-19/FACET_rater_{c}/FACET_rating_page_v9_4.html" for c in "ABCDEFGHJKL"}
pages = {c: p for c, p in pages.items() if p.exists()}
def runs_in(html):
    i = html.find('{"A": {"core"'); assert i >= 0
    return json.JSONDecoder().raw_decode(html[i:])[0]
txt = {c: p.read_text(encoding="utf-8") for c, p in pages.items()}
same = len({t for t in txt.values()}) == 1
check("every rater package carries the identical page", same, f"{len(pages)} packages: {''.join(sorted(pages))}")
page = runs_in(txt["L"])
blind = json.loads((V / "runs_blinded.json").read_text())
key = json.loads((V / "SEALED_KEY_do_not_open.json").read_text())
check("page assignments for A to L equal runs_blinded.json", all(page[c] == blind[c] for c in CODES), "extra page code(s) outside the design: " + ",".join(sorted(set(page) - set(CODES))))
if "X" in page: print("NOTE X carries the same 42 pairs and anchors as A in another order:", set(page["X"]["core"] + page["X"]["ext"]) == set(page["A"]["core"] + page["A"]["ext"]))
check("page assignments equal the sealed key's runs", page == key["runs"] or all(set(page[c]["core"]) | set(page[c]["ext"]) == set(key["runs"][c]["core"] if isinstance(key["runs"][c], dict) else key["runs"][c]) | (set(key["runs"][c]["ext"]) if isinstance(key["runs"][c], dict) else set()) for c in CODES))
items = {x["pid"]: x for x in json.loads((V / "items_blinded.json").read_text())}
p2i = key["pid_to_iid"]; meta = {x["iid"]: x for x in key["items"]}
blk = {pid: meta[p2i[pid]]["block"] for pid in p2i}; pos = {pid: meta[p2i[pid]]["positive"] for pid in p2i}
anchors = {pid for pid, b in blk.items() if b == "anchor"}
check("171 items: 168 pairs and 3 anchors", len(items) == 171 and len(anchors) == 3, f"{len(items)} items, {len(anchors)} anchors")
cover = collections.defaultdict(set)
for c in CODES:
    allp = page[c]["core"] + page[c]["ext"]
    s = set(allp); mine = s - anchors
    check(f"{c}: 45 screens, no duplicates, 3 anchors in part one, 42 pairs", len(allp) == 45 and len(s) == 45 and anchors <= set(page[c]["core"]) and len(mine) == 42,
          f"{len(page[c]['core'])}+{len(page[c]['ext'])} screens")
    part, slot = divmod(CODES.index(c), 4)
    want = {f"B{b:02d}" for b in PART[part][slot]}
    got = collections.Counter(blk[p] for p in mine)
    check(f"{c}: blocks {sorted(want)}, 14 pairs each", set(got) == want and all(v == 14 for v in got.values()))
    npos = sum(1 for p in mine if pos[p])
    check(f"{c}: 21 accepted and 21 refuted", npos == 21, f"{npos} accepted")
    pc = sum(1 for p in page[c]["core"] if p not in anchors and pos[p])
    check(f"{c}: part one balanced", pc == (len(page[c]["core"]) - 3) // 2, f"{pc} of {len(page[c]['core']) - 3}")
    for p in mine: cover[p].add(c)
pairs = set(blk) - anchors
check("all 168 pairs covered", set(cover) == pairs, f"{len(cover)} covered")
k3 = sum(1 for p in pairs if len(cover[p]) == 3 and {CODES.index(c) // 4 for c in cover[p]} == {0, 1, 2})
check("every pair rated by exactly three codes, one per partition", k3 == 168, f"{k3} of 168")
bpos = collections.Counter(blk[p] for p in pairs if pos[p]); bn = collections.Counter(blk[p] for p in pairs)
check("12 blocks of 14, 7 accepted and 7 refuted", len(bn) == 12 and all(v == 14 for v in bn.values()) and all(v == 7 for v in bpos.values()))
share = [len((set(page[a]["core"] + page[a]["ext"]) - anchors) & (set(page[b]["core"] + page[b]["ext"]) - anchors)) for i, a in enumerate(CODES) for b in CODES[i + 1:] if CODES.index(a) // 4 != CODES.index(b) // 4]
check("raters in different partitions share at most one block", max(share) <= 14, f"max shared {max(share)}")
ret = set("ABCDEGH"); pend = {"J", "K", "L", "I", "F"}
def n_rated(codes): return collections.Counter(len(cover[p] & codes) for p in pairs)
print("pairs by number of ratings, returned A B C D E G H:", dict(sorted(n_rated(ret).items())))
print("  plus J K L:", dict(sorted(n_rated(ret | {"J", "K", "L"}).items())))
print("  plus I J K L:", dict(sorted(n_rated(ret | {"I", "J", "K", "L"}).items())))
print("  all twelve:", dict(sorted(n_rated(set(CODES)).items())))
print("OVERALL", "PASS" if ok else "FAIL")
