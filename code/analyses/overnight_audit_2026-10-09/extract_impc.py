import csv, gzip, collections, sys, time
csv.field_size_limit(10**9)
IN = "_overnight/impc/statistical-results-ALL.csv.gz"; OUT = "_overnight/parsed"
agg = collections.defaultdict(lambda: [0, 0, set(), set()]); procs = collections.Counter(); status = collections.Counter()
t0 = time.time(); n = 0
with gzip.open(IN, "rt", encoding="utf-8", newline="") as f:
    for r in csv.DictReader(f):
        n += 1
        status[r["status"]] += 1
        if r["status"] != "Successful": continue
        procs[(r["procedure_stable_id"][:8], r["procedure_name"])] += 1
        k = (r["allele_symbol"], r["zygosity"], r["procedure_name"], r["marker_symbol"])
        a = agg[k]; a[0] += 1
        if r["significant"].lower() == "true":
            a[1] += 1
            if r["mp_term_id"]: a[2].add(r["mp_term_id"])
        a[3].add(r["phenotyping_center"])
        if n % 2000000 == 0: print(n, "rows", round(time.time() - t0), "s", flush=True)
with open(f"{OUT}/impc_compact.tsv", "w", encoding="utf-8") as o:
    o.write("allele_symbol\tzygosity\tprocedure_name\tmarker_symbol\tn_parameters\tn_significant\tsignificant_mp\tcenters\n")
    for (al, z, p, m), (np_, ns, mp, c) in sorted(agg.items()):
        o.write(f"{al}\t{z}\t{p}\t{m}\t{np_}\t{ns}\t{'|'.join(sorted(mp))}\t{'|'.join(sorted(c))}\n")
with open(f"{OUT}/impc_procedures.tsv", "w", encoding="utf-8") as o:
    o.write("procedure_prefix\tprocedure_name\trows\n")
    for (pid, p), c in procs.most_common(): o.write(f"{pid}\t{p}\t{c}\n")
print("DONE rows", n, "status", dict(status), "keys", len(agg), "seconds", round(time.time() - t0))
