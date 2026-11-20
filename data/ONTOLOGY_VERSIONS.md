# ONTOLOGY_VERSIONS.md

Release versions of every external ontology, annotation dump and source document the
FACET pipeline consumes, each recorded with the file and the exact line or field it
was read from. Compiled 2026-08-01. Replaces the bracketed placeholder on the final
slide.

Everything below was read off the files on disk. Where a version genuinely cannot be
established from the artifact, it is listed as such in section 3 rather than guessed.

---

## 1. Slide table

| Resource | Version / release | Evidence: file and field |
|---|---|---|
| Mammalian Phenotype Ontology (MP) | `releases/2026-05-19/mp.obo`, OBO format-version 1.2 | `MPheno_OBO.ontology`, line 2 `data-version: releases/2026-05-19/mp.obo`; line 1 `format-version: 1.2` |
| Human Phenotype Ontology (HPO) | release **2026-02-16** (confirmed, not assumed) | `hp.json`, `graphs[0].meta` field `"version" : "http://purl.obolibrary.org/obo/hp/releases/2026-02-16/hp.json"` |
| HPO disease annotations (HPOA) | release 2026-02-16, built against HPO 2026-02-16 | `phenotype.hpoa`, header lines 2 and 4: `#version: 2026-02-16`, `#hpo-version: http://purl.obolibrary.org/obo/hp/releases/2026-02-16/hp.json` |
| MGI `MGI_PhenoGenoMP.rpt` | no release stamp in file; snapshot date 2026-03-23 (file mtime, UTC) | `MGI_PhenoGenoMP.rpt`, first line is data, no header or comment block; 53,498,021 bytes, 391,665 lines |
| MGI `MGI_DO.rpt` | no release stamp in file; snapshot date 2026-04-06 (file mtime, UTC) | `MGI_DO.rpt`, line 1 is a column header only (`DO Disease ID ... Mouse MGI ID`); 1,574,869 bytes |
| MGI `MGI_Geno_DiseaseDO.rpt` | no release stamp in file; snapshot date 2026-04-06 (file mtime, UTC) | `MGI_Geno_DiseaseDO.rpt`, first line is data, no header; 8,473,426 bytes |
| MGI `MGI_PhenotypicAllele` | no release stamp in file; snapshot date 2026-07-31 (file mtime, UTC) | on disk as `MGI_PhenotypicAllele.rpt.txt` (note the `.txt`); 6 leading `#` comment lines are nomenclature notes and carry no date; 32,189,848 bytes |
| MGI `ALL_Phenotype.rpt` | no release stamp in file; snapshot date 2026-03-23 (file mtime, UTC) | `ALL_Phenotype.rpt`, line 1 is a column header only (`Allele ID / Allele Symbol / Phenotypes`); 14,870,123 bytes |
| MGI `VOC_MammalianPhenotype.rpt` (MP term labels and definitions) | no release stamp in file; snapshot date 2026-03-23 (file mtime, UTC) | `VOC_MammalianPhenotype.rpt`, first line is data; 2,908,361 bytes |
| Monarch semsimian HP to MP table | **0.4** (from the filename), Monarch flavour | `phenio-monarch-hp-mp.0.4.semsimian.tsv`, 250,525,100 bytes, file mtime 2024-11-19 (UTC); 16-column header ending `phenodigm_score` |
| Monarch semsimian IC companion table | 0.4, same family | `phenio-monarch-hp-mp.0.4.semsimian.ic.tsv`, 250,500,570 bytes, file mtime 2024-09-16 (UTC) |
| Monarch semsimian "equivalent" variant | 0.4, same family | `phenio-equivalent-hp-mp.0.4.semsimian.tsv` and `.ic.tsv` |
| `phenio-monarch.db` (Monarch phenio SQLite) | not established | 19,988,598,784 bytes, file mtime 2026-04-06 (UTC); no version read (see section 3) |
| DSM-5-TR | American Psychiatric Association, *Diagnostic and Statistical Manual of Mental Disorders*, Fifth Edition, Text Revision (DSM-5-TR), 2022 | criteria read as paraphrased items written for the project (S1 Table) |

Timestamps are UTC, read from the file system through the project mount.

## 2. Prose paragraph for a methods section

Mouse phenotype terms were taken from the Mammalian Phenotype Ontology, release
2026-05-19 (`data-version: releases/2026-05-19/mp.obo`, OBO format-version 1.2), and
human phenotype terms from the Human Phenotype Ontology, release 2026-02-16, verified
from the ontology's own metadata (`"version" : "http://purl.obolibrary.org/obo/hp/releases/2026-02-16/hp.json"`)
rather than from the download record; the accompanying HPO disease annotation file
(`phenotype.hpoa`) declares the same release, 2026-02-16, and is built against that
HPO version. Mouse genotype to phenotype associations, allele records and disease
mappings were taken from Mouse Genome Informatics report files
(`MGI_PhenoGenoMP.rpt`, `ALL_Phenotype.rpt`, `VOC_MammalianPhenotype.rpt`,
`MGI_DO.rpt`, `MGI_Geno_DiseaseDO.rpt`, `MGI_PhenotypicAllele`). MGI report files
carry no release identifier in their contents, so the file modification time is the
best available provenance: `MGI_PhenoGenoMP.rpt`, `ALL_Phenotype.rpt` and
`VOC_MammalianPhenotype.rpt` date to 2026-03-23, `MGI_DO.rpt` and
`MGI_Geno_DiseaseDO.rpt` to 2026-04-06, and `MGI_PhenotypicAllele` to 2026-07-31;
these are therefore three separate downloads and not a single coherent MGI release
snapshot. Precomputed cross-species phenotype similarity was taken from the Monarch
Initiative semsimian HP to MP tables, version 0.4
(`phenio-monarch-hp-mp.0.4.semsimian.tsv`), whose file timestamps of 2024-09-16 and
2024-11-19 predate this project and so appear to be the upstream build dates carried
through the download. Diagnostic criteria follow the DSM-5-TR (American
Psychiatric Association, 2022) and are read as paraphrased items written for the project.

## 3. Versions we could NOT establish

This list is part of the record, not an omission from it. Each entry is a version we
looked for in the artifact and did not find.

1. **MGI release identifier for any `.rpt` file.** MGI publishes numbered, dated
   releases, but none of `MGI_PhenoGenoMP.rpt`, `MGI_DO.rpt`, `MGI_Geno_DiseaseDO.rpt`,
   `MGI_PhenotypicAllele.rpt.txt`, `ALL_Phenotype.rpt` or `VOC_MammalianPhenotype.rpt`
   embeds a release number, build date or generation timestamp anywhere in its header,
   comment block or trailing lines. We checked the first and last lines of each. Only
   the file modification time is available, and a modification time records the last
   write on this machine, which could be a copy or a move rather than the download.
   Treat every MGI date in section 1 as a lower-bound proxy.
2. **Whether the MGI files form one coherent snapshot.** They do not. The three
   distinct mtimes (2026-03-23, 2026-04-06, 2026-07-31) mean at least three separate
   pulls, so any statement of the form "MGI as of <date>" is wrong for at least one
   file. If a single-snapshot claim is needed, the files must be re-downloaded
   together and re-stamped.
3. **The phenio knowledge graph release behind the semsimian tables.** The filename
   gives `0.4`, which identifies the semsimian table family, not the phenio KG release
   or the semsimian tool version. There is no manifest, checksum file or header row
   naming a phenio release. The two directories that might have held one,
   `phenio-equivalent container/` and `phenio.db container/`, are empty of any metadata
   file.
4. **The `phenio-monarch.db` release version.** The database is 19.99 GB; we did not
   open it, so any internal metadata table it may carry is unread. Its mtime,
   2026-04-06, is the only datum.
5. **The DSM-5-TR printing, impression or ISBN.** The edition and year (Fifth Edition,
   Text Revision, 2022) are established; the specific printing is not. Cite the DSM-5-TR
   bibliographically, from the published work.
6. **Download dates as opposed to file mtimes, for every resource above.** No download
   log, no HTTP date header and no checksum manifest was retained for any external
   file. `MPheno_OBO.ontology` illustrates the gap: its content declares release
   2026-05-19, while its mtime is 2026-06-01, so the mtime is a download-or-copy date
   and is not the version. For HPO the analogous mtime is 2026-03-23 against a
   declared release of 2026-02-16.
7. **SFARI Gene animal-model export release.** Recorded here only for completeness:
   `SFARI-Gene_animal-genes_03-22-2026.csv` carries a date in its filename (2026-03-22)
   but no version field inside the file, so the filename is the only provenance.

## 4. Recommendation

Going forward, capture a provenance stub next to every external download recording the
URL, the HTTP `Last-Modified` and `Date` headers, an SHA-256, and the retrieval
timestamp. Items 1, 2, 3, 6 and 7 above would all be answerable if that had existed;
none of them can be recovered from the files as they now stand.
