#!/usr/bin/env python3
import hashlib, json, os, re, sys
from pathlib import Path

CACHE = "_dsm5tr_cache/dsm5tr_full.txt"
OUTDIR = "DSM5TR_definitions"
TRANSLATE = {"’": "'", "‘": "'", "“": '"', "”": '"', "­": "",
             "—": " ", "–": "-", "−": "-", "‐": "-", " ": " ", "ﬁ": "fi", "ﬂ": "fl"}


def norm(s):
    for k, v in TRANSLATE.items():
        s = s.replace(k, v)
    return re.sub(r"\s+", " ", s).strip()


def build_page_index(text):
    pages, line_to_page, printed = text.split("\f"), {}, {}
    n = 0
    for pi, pg in enumerate(pages, start=1):
        lines = pg.splitlines()
        nums = [int(x.strip()) for x in lines if re.fullmatch(r"\s*\d{2,4}\s*", x or "")]
        printed[pi] = nums[0] if nums else None
        for _ in lines:
            line_to_page[n] = pi
            n += 1
        line_to_page[n] = pi
        n += 1
    return line_to_page, printed


def cite(line_to_page, printed, idx):
    pi = line_to_page.get(idx)
    return {"pdf_page": pi, "printed_page": printed.get(pi), "line": idx}


def main():
    root = Path(os.environ.get("FACET_ROOT", "."))
    p = root / CACHE
    if not p.exists():
        sys.exit(f"missing {p}. Run verify_criteria_provenance.py once to build the cache.")
    text = p.read_text(encoding="utf-8", errors="replace")
    cache_sha = hashlib.sha256(p.read_bytes()).hexdigest()
    lines = text.splitlines()
    full = norm(text)
    low = full.lower()
    l2p, printed = build_page_index(text)

    def span(start, n):
        return norm(" ".join(x.strip() for x in lines[start:start + n] if x.strip()))

    ABBR = re.compile(r"(?:e\.g|i\.e|etc|cf|vs|Dr|Mr|approx|Fig|No)\.$", re.I)

    def trim_to_sentence(s):
        best = -1
        for m in re.finditer(r"[.!?](?=\s|$)", s):
            if ABBR.search(s[:m.end()]):
                continue
            best = m.end()
        return s[:best].strip() if best > 0 else s.strip()

    def after(blob, head, chars):
        i = blob.find(head)
        return trim_to_sentence(norm(blob[i:i + chars])) if i >= 0 else ""

    out = {}

    i = next(k for k, l in enumerate(lines) if "Key Features That Define the Psychotic Disorders" in l)
    blob = span(i, 130)
    heads = {"A1": "Delusions are fixed beliefs",
             "A2": "Hallucinations are perception-like",
             "A3": "Disorganized thinking (formal thought disorder)",
             "A4": "Grossly disorganized or abnormal motor",
             "A5": "Two negative symptoms are particularly prominent"}
    by = {}
    for unit, h in heads.items():
        txt = after(blob, h, 560 if unit == "A4" else 520)
        frag = h.split("(")[0].strip()[:40]
        anchor = next((k for k in range(i, i + 130) if frag in lines[k]), i)
        by[unit] = {"text": txt, "citation": cite(l2p, printed, anchor)}
    out["SCZ"] = {"source": "DSM-5-TR, Key Features That Define the Psychotic Disorders",
                  "kind": "definitional", "contiguous": True, "by_item": by}

    j = next(k for k, l in enumerate(lines) if re.search(r"conceptual \(academic\) domain", l, re.I))
    idb = after(span(j - 6, 30), "Adaptive functioning involves adaptive reasoning", 980)
    out["ID"] = {"source": "DSM-5-TR, Intellectual Developmental Disorder, Diagnostic Features",
                 "kind": "definitional", "contiguous": True,
                 "by_item": {"B": {"text": idb, "citation": cite(l2p, printed, j)}}}

    start = next(k for k, l in enumerate(lines) if re.match(r"^\s*Complex attention\b", l) and k > 37900)
    raw = []
    for k in range(start - 4, start + 162):
        frag = lines[k][:24].rstrip()
        if not frag.strip() or re.fullmatch(r"\s*\d{3}\s*", frag):
            continue
        raw.append(frag.strip())
    col = re.sub(r"\s+", " ", " ".join(raw)).strip()
    col = re.sub(r"(\w+)-\s+(\w+)",
                 lambda m: m.group(1) + m.group(2) if (m.group(1) + m.group(2)).lower() in low
                 else m.group(1) + "-" + m.group(2), col)
    DOM = ["Complex attention", "Executive function", "Learning and memory", "Language",
           "Perceptual-motor", "Social cognition"]
    defs = []
    for n, d in enumerate(DOM):
        a = col.index(d)
        b = col.index(DOM[n + 1]) if n + 1 < len(DOM) else len(col)
        seg = col[a:b].strip()
        m = re.match(r"^(.*?\))(?:\s|$)", seg)
        defs.append((m.group(1) if m else seg).strip())
    out["NCD"] = {"source": "DSM-5-TR, Table 1, Neurocognitive Domains",
                  "kind": "definitional", "contiguous": False,
                  "reconstruction_note": "Three-column table; definitions reconstructed from the left "
                                         "column and verified token by token, NOT contiguous prose.",
                  "by_item": {"A": {"text": "\n".join(defs), "citation": cite(l2p, printed, start)}}}

    a = next(k for k, l in enumerate(lines)
             if re.match(r"^\s*Diagnostic Features\s*$", l) and 6100 < k < 6600)
    asd = trim_to_sentence(span(a, 22)[:900])
    out["ASD"] = {"source": "DSM-5-TR, Autism Spectrum Disorder, Diagnostic Features",
                  "kind": "ELABORATION, NOT DEFINITIONAL", "contiguous": True,
                  "control_note": "ASD has no definitional section. Included ONLY as a negative control: "
                                  "the prediction is that adding elaboration changes little, because "
                                  "ASD's items already carry their definitions inline. If it moves as "
                                  "much as NCD's Table 1, the effect is prose volume rather than DSM "
                                  "definition and the design rationale fails.",
                  "by_item": {"A1": {"text": asd, "citation": cite(l2p, printed, a)},
                              "B1": {"text": asd, "citation": cite(l2p, printed, a)}}}

    print(f"source: DSM 5 TR-APA 2022.pdf via {CACHE}")
    print(f"cache sha256: {cache_sha[:32]}...\n")
    print(f"  {'disorder':8s} {'unit':5s} {'chars':>6s}  {'pdf pg':>7s} {'printed':>8s}  verification")
    ok = True
    for D, blk in out.items():
        for unit, ent in blk["by_item"].items():
            txt = ent["text"]
            if blk["contiguous"]:
                good, how = txt in full, "contiguous substring"
            else:
                toks = [t for t in re.findall(r"[a-z]{4,}", txt.lower())
                        if t not in ("including", "under", "terms", "abilities", "subsumed")]
                miss = [t for t in toks if t not in low]
                good, how = not miss, f"{len(toks)-len(miss)}/{len(toks)} tokens"
            ok = ok and good and bool(txt)
            c = ent["citation"]
            print(f"  {D:8s} {unit:5s} {len(txt):6d}  {str(c['pdf_page']):>7s} {str(c['printed_page']):>8s}"
                  f"  {how:22s} {'OK' if good else '*** FAIL'}")

    od = root / OUTDIR
    od.mkdir(exist_ok=True)
    for D, blk in out.items():
        f = od / f"{D}_definitions.txt"
        body = [f"DSM-5-TR definitions used by FACET for {D}",
                f"source   : {blk['source']}",
                f"kind     : {blk['kind']}",
                f"extracted: DSM 5 TR-APA 2022.pdf, cache sha256 {cache_sha[:32]}",
                f"contiguous verbatim: {blk['contiguous']}", ""]
        if blk.get("reconstruction_note"):
            body += [f"NOTE: {blk['reconstruction_note']}", ""]
        if blk.get("control_note"):
            body += [f"NOTE: {blk['control_note']}", ""]
        for unit, ent in blk["by_item"].items():
            c = ent["citation"]
            body += [f"--- unit {unit}   PDF page {c['pdf_page']}, printed page {c['printed_page']} ---",
                     ent["text"], ""]
        f.write_text("\n".join(body), encoding="utf-8")
    (root / "_dsm_definitions.json").write_text(
        json.dumps({"cache_sha256": cache_sha, "pdf": "DSM 5 TR-APA 2022.pdf", "disorders": out},
                   indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {od}/ ({len(out)} files) and _dsm_definitions.json")
    print("ALL VERIFIED:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
