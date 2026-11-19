import argparse, collections, csv, gzip, hashlib, io, json, os, re, sys, time

CANDIDATES = {
    "ASD": ["D000067877", "D001321", "D020817"],
    "IDD": ["D008607"],
    "SCZ": ["D012559"],
    "NCD": ["D003704", "D060825"],
}
DISORDER_TEXT = re.compile(
    r"autis|asperger|pervasive development|schizo|psychos|intellectual disab|intellectual development|"
    r"mental retard|developmental delay|dementia|cognitive impair|cognitive decline|cognitive deficit|neurocognitive",
    re.I)
MOUSE = "10090"


class HashReader(io.RawIOBase):
    def __init__(self, f):
        self.f, self.h, self.n = f, hashlib.sha256(), 0
    def readable(self):
        return True
    def readinto(self, b):
        chunk = self.f.read(len(b))
        self.h.update(chunk); self.n += len(chunk)
        b[:len(chunk)] = chunk
        return len(chunk)


def rows(path, manifest):
    raw = open(path, "rb"); hr = HashReader(raw)
    gz = gzip.GzipFile(fileobj=io.BufferedReader(hr, 1 << 20))
    t0 = time.time(); bad = 0
    for i, line in enumerate(io.TextIOWrapper(gz, encoding="utf-8", errors="replace")):
        f = line.rstrip("\n").split("\t")
        if i < 3:
            print(f"  {os.path.basename(path)} row {i + 1}: {f[:4]}", flush=True)
        if len(f) < 4:
            bad += 1
            if i < 1000 and bad > 50:
                sys.exit(f"STOP: {path} does not have the expected 5 tab-separated columns")
            continue
        if i and i % 20_000_000 == 0:
            print(f"  {os.path.basename(path)}: {i:,} rows, {time.time() - t0:.0f} s", flush=True)
        yield f
    while hr.readinto(bytearray(1 << 20)):
        pass
    manifest[os.path.basename(path)] = dict(bytes=hr.n, sha256=hr.h.hexdigest(),
                                            mtime=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(os.path.getmtime(path))),
                                            short_rows=bad, seconds=round(time.time() - t0))


def ids(field):
    return [x.strip().replace("MESH:", "") for x in re.split(r"[;,|]", field) if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pubtator_dir", required=True)
    ap.add_argument("--gene_ids", required=True)
    ap.add_argument("--line_pmids", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    need = ["gene2pubtator3.gz", "species2pubtator3.gz", "disease2pubtator3.gz"]
    missing = [n for n in need if not os.path.exists(os.path.join(a.pubtator_dir, n))]
    if missing:
        sys.exit(f"STOP: missing {missing} in {a.pubtator_dir}. Present: {sorted(os.listdir(a.pubtator_dir))}")
    os.makedirs(a.outdir, exist_ok=True)
    genes = set()
    for r in csv.DictReader(open(a.gene_ids), delimiter="\t"):
        if r["mouse_entrez"]: genes.add(r["mouse_entrez"])
        genes |= {x for x in r["human_entrez"].split("|") if x}
    line_p = {r["pmid"] for r in csv.DictReader(open(a.line_pmids), delimiter="\t")}
    print(f"gene IDs {len(genes):,}, line PMIDs {len(line_p):,}", flush=True)
    manifest = {}

    print("pass 1 of 3: genes", flush=True)
    gene_p = set(); n = 0
    with gzip.open(os.path.join(a.outdir, "gene_rows.tsv.gz"), "wt", encoding="utf-8") as w:
        w.write("pmid\tgene_entrez\n")
        for f in rows(os.path.join(a.pubtator_dir, "gene2pubtator3.gz"), manifest):
            hit = [g for g in ids(f[2]) if g in genes]
            if hit:
                gene_p.add(f[0]); n += 1
                for g in hit: w.write(f"{f[0]}\t{g}\n")
    print(f"  gene rows kept {n:,}, PMIDs {len(gene_p):,}", flush=True)
    keep = gene_p | line_p

    print("pass 2 of 3: species", flush=True)
    mouse = set()
    for f in rows(os.path.join(a.pubtator_dir, "species2pubtator3.gz"), manifest):
        if f[0] in keep and MOUSE in ids(f[2]): mouse.add(f[0])
    with gzip.open(os.path.join(a.outdir, "mouse_pmids.txt.gz"), "wt") as w:
        w.write("\n".join(sorted(mouse, key=int)) + "\n")
    print(f"  kept PMIDs with Mus musculus {len(mouse):,}", flush=True)

    print("pass 3 of 3: diseases", flush=True)
    cand = {c for v in CANDIDATES.values() for c in v}
    cand_mentions = collections.defaultdict(collections.Counter); cand_rows = collections.Counter()
    text_ids = collections.defaultdict(collections.Counter); text_rows = collections.Counter()
    n = 0
    with gzip.open(os.path.join(a.outdir, "disease_rows.tsv.gz"), "wt", encoding="utf-8") as w:
        w.write("pmid\tconcept\tmentions\n")
        for f in rows(os.path.join(a.pubtator_dir, "disease2pubtator3.gz"), manifest):
            cs = ids(f[2]); ments = [m.strip().lower() for m in f[3].split("|") if m.strip()]
            textual = any(DISORDER_TEXT.search(m) for m in ments)
            for c in cs:
                if c in cand:
                    cand_rows[c] += 1
                    for m in ments: cand_mentions[c][m] += 1
                if textual:
                    text_rows[c] += 1
                    for m in ments:
                        if DISORDER_TEXT.search(m): text_ids[c][m] += 1
            if (textual or cand & set(cs)) and f[0] in keep:
                n += 1; w.write(f"{f[0]}\t{';'.join(cs)}\t{'|'.join(ments)}\n")
    print(f"  disease rows kept {n:,}", flush=True)

    with open(os.path.join(a.outdir, "concept_check_candidates.tsv"), "w", encoding="utf-8") as w:
        w.write("disorder\tconcept\trows_in_corpus\ttop10_mentions\n")
        for d, cl in CANDIDATES.items():
            for c in cl:
                top = "; ".join(f"{m} ({k:,})" for m, k in cand_mentions[c].most_common(10))
                w.write(f"{d}\t{c}\t{cand_rows[c]}\t{top}\n")
    with open(os.path.join(a.outdir, "concept_check_by_text.tsv"), "w", encoding="utf-8") as w:
        w.write("concept\trows_with_disorder_text\ttop10_disorder_mentions\n")
        for c, k in text_rows.most_common(150):
            w.write(f"{c}\t{k}\t{'; '.join(f'{m} ({x:,})' for m, x in text_ids[c].most_common(10))}\n")
    manifest["counts"] = dict(gene_ids=len(genes), line_pmids=len(line_p), gene_pmids=len(gene_p),
                              mouse_pmids=len(mouse), disease_rows_kept=n)
    json.dump(manifest, open(os.path.join(a.outdir, "manifest.json"), "w"), indent=1)
    print("DONE. Send me a note when this prints. Outputs:", sorted(os.listdir(a.outdir)), flush=True)


if __name__ == "__main__":
    main()
