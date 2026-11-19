#!/usr/bin/env python3
import json, os, csv, sys
from collections import defaultdict, deque

BASE = os.environ.get("FACET_BASE") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_g = json.load(open(os.path.join(BASE, "hp.json")))["graphs"][0]

HPO_RELEASE_EXPECTED = os.environ.get("FACET_HPO_RELEASE", "2026-02-16")
_hpo_version = (_g.get("meta") or {}).get("version") or ""
HPO_RELEASE_LOADED = _hpo_version.split("/releases/")[-1].split("/")[0] if "/releases/" in _hpo_version else "unknown"
if HPO_RELEASE_LOADED != HPO_RELEASE_EXPECTED:
    raise RuntimeError(
        "HPO release mismatch: %s expects release %s but %s reports %r. "
        "Re-validate the CROSSWALK anchors before bumping HPO_RELEASE_EXPECTED, "
        "or set FACET_HPO_RELEASE=%s to override for this run."
        % (os.path.basename(__file__), HPO_RELEASE_EXPECTED,
           os.path.join(BASE, "hp.json"), HPO_RELEASE_LOADED, HPO_RELEASE_LOADED)
    )
def _sid(u): return u.split("/")[-1].replace("_", ":") if u else u
_parents = defaultdict(set)
for _e in _g["edges"]:
    if _e.get("pred") == "is_a":
        _parents[_sid(_e["sub"])].add(_sid(_e["obj"]))

CROSSWALK = [
    ("HP:5200230", "affective", "Negative Valence", "RATIFIED override: fear/anxiety cognitions -> affective, not HPO's judgment branch"),
    ("HP:0034434", "behavioral", "Social Processes", "RATIFIED override: communication -> social/behavioral, not HPO's cognitive branch"),
    ("HP:0012433", "behavioral", "Social Processes", "abnormal social behavior"),
    ("HP:0000738", "perceptual", "Cognitive/Perception", "hallucinations"),
    ("HP:0003474", "perceptual", "Cognitive/Perception", "RATIFIED: somatic sensory (pain, temperature) -> perceptual"),
    ("HP:0025779", "cognitive", "Cognitive Systems", "disorder of thought content (delusion)"),
    ("HP:0025769", "cognitive", "Cognitive Systems", "disordered formal thought"),
    ("HP:5200401", "cognitive", "Cognitive Systems", "abnormal judgment (non-fear)"),
    ("HP:5200430", "cognitive", "Cognitive Systems", "abnormal psychotic pattern"),
    ("HP:0025766", "affective", "Neg/Pos Valence", "abnormal affect (mood, emotion, volition)"),
    ("HP:0100543", "cognitive", "Cognitive Systems", "cognitive impairment"),
    ("HP:0001328", "cognitive", "Cognitive Systems", "specific learning disability (dyslexia, dyscalculia)"),
    ("HP:0025792", "cognitive", "Cognitive Systems", "abnormal cognitive process (fallback)"),
    ("HP:5200423", "perceptual", "Cognitive/Perception", "abnormal experience of reality (fallback)"),
    ("HP:0002360", "somatic", "Arousal/Regulatory", "sleep disturbance"),
    ("HP:0004323", "somatic", "Arousal/Regulatory", "body weight"),
    ("HP:0100738", "somatic", "Arousal/Regulatory", "eating behavior"),
    ("HP:0004396", "somatic", "Arousal/Regulatory", "poor appetite"),
    ("HP:0003388", "somatic", "Arousal/Regulatory", "easy fatigability"),
    ("HP:0100022", "sensorimotor", "Sensorimotor", "abnormality of movement"),
    ("HP:0011442", "sensorimotor", "Sensorimotor", "abnormal central motor function"),
    ("HP:0005327", "behavioral", "Social Processes", "facial expression (social-communication)"),
    ("HP:0000708", "behavioral", "Social Processes/Sensorimotor", "atypical behavior (broad residual)"),
    ("HP:0031058", "functional", "(not RDoC)", "impairment of activities of daily living (adaptive)"),
    ("HP:0033695", "functional", "(not RDoC)", "occupational disability (adaptive)"),
    ("HP:0025142", "somatic", "Arousal/Regulatory", "constitutional symptom (fatigue, asthenia, general)"),
    ("HP:0410263", "unclassified", "(modifier)", "onset / clinical modifier"),
    ("HP:0011446", "mental_unspec", "(mental, unresolved)", "mental function fallback"),
]
_ANCHOR = {a: (c, r) for a, c, r, note in CROSSWALK}
_ORDER = {a: i for i, (a, c, r, note) in enumerate(CROSSWALK)}
_ANCHOR["HP:0003674"] = ("unclassified", "(modifier)"); _ORDER["HP:0003674"] = len(_ORDER)

def classify_full(hpo_id, label=""):
    if not hpo_id:
        return ("no_hpo", "")
    dist = {hpo_id: 0}; dq = deque([hpo_id]); hits = []
    while dq:
        x = dq.popleft()
        if x in _ANCHOR:
            hits.append((dist[x], _ORDER[x], x))
        for p in _parents.get(x, ()):
            if p not in dist:
                dist[p] = dist[x] + 1; dq.append(p)
    if not hits:
        return ("unclassified", "")
    hits.sort()
    return _ANCHOR[hits[0][2]]

def classify(hpo_id, label=""):
    return classify_full(hpo_id, label)[0]

def rdoc_domain(hpo_id, label=""):
    return classify_full(hpo_id, label)[1]

if __name__ == "__main__":
    src = os.path.join(BASE, "mappability_catalog", "catalog_by_phenotype.tsv")
    rows = list(csv.DictReader(open(src), delimiter="\t"))
    from collections import Counter
    c = Counter()
    for r in rows:
        if r["role"] == "associated" or not r["hpo_id"]:
            continue
        c[classify(r["hpo_id"], r["hpo_label"])] += 1
    print(dict(c))
