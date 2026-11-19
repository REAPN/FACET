# Pre-registration: audit of the overnight MGI page and IMPC data, 2026-10-09

Written 2026-10-09T21:32Z. Before writing it, only formats were inspected: the IMPC statistical-results header and README, and the HTML around one annotation block of one MGI page (Shank3<tm1Yhj>, MGI:5056404, already quoted in FINDINGS_LOG F36). No parsed count or outcome was seen. Definitions follow `METHODS_DEFINITIONS_2026-10-08.md`: K4 pool, corrected labels of 2026-10-08, "behaviorally annotated" means at least one abnormal annotation equal to or below MP:0004924. No dash-family characters. No LLM call.

## Data

- MGI genotype pages: `_overnight/mgi_genoview/`, 16,021 of 16,027 fetched (6 errors, all priority 4), in four priority groups (319 curated positives, a random 2,000 K4 lines without behavioral annotation drawn with seed 20261008, 7,977 uncurated disorder-gene lines, 5,725 other behaviorally annotated lines).
- IMPC: `_overnight/impc/statistical-results-ALL.csv.gz`, latest release, every analyzed parameter, significant or not.

## Parsing

- MGI. Each term block (`div.termDiv`) gives the system section, the MP term, and one or more rows. A row is normal when its qualifier cell (`td.sexTd`) reads N. The row's notes are its `div.mpNote` texts. A term is abnormal on the page when it has at least one row that is not normal.
- Parse gate. For each fetched genotype, the set of abnormal page terms is compared with its MP set in the K4 summary (from `MGI_PhenoGenoMP.rpt`). The parse passes if at least 99 percent of genotypes match exactly. Mismatches are listed and characterized before any outcome is read.
- A genotype has a recorded normal behavioral result when it has a normal row on MP:0005386, MP:0004924 or any MP:0004924 descendant. It is "behaviorally assessed" when it is behaviorally annotated or has a recorded normal behavioral result.
- Assay lexicon, fixed now and applied to every note (case-insensitive), with each match assigned to one domain:
  - social: three-chamber, three chamber, social interaction, social preference, social novelty, social recognition, social approach, resident-intruder, resident intruder, dyadic, reciprocal social, social transmission, partition test, tube test, huddling
  - communication: ultrasonic vocali, USV
  - repetitive and restricted: grooming, marble burying, marble-burying, hole-board, hole board, stereotyp, reversal
  - anxiety and exploration: open field, open-field, elevated plus, elevated zero, light-dark, light/dark, dark-light, novelty-suppressed, emergence
  - learning and memory: water maze, Barnes maze, Y-maze, Y maze, T-maze, T maze, radial arm, object recognition, novel object, fear conditioning, contextual fear, cued fear, passive avoidance, active avoidance, conditioned place, operant, spontaneous alternation
  - sensorimotor gating and startle: prepulse, pre-pulse, startle
  - motor: rotarod, grip strength, wire hang, pole test, beam walk, balance beam, gait, footprint, locomotor activity
  - affect: forced swim, tail suspension, sucrose preference, learned helplessness
  - other: nest building, nesting, burrowing, sleep
- IMPC. Rows are kept when `status` is Successful. A behavioral IMPC procedure is one whose name contains any of Open Field, Startle, Pre-pulse, Grip Strength, SHIRPA, Rotarod, Light-Dark, Fear Conditioning, Hot Plate, Y-maze or Sleep. Indirect Calorimetry is excluded even though it records activity. (Wording of this sentence corrected at 21:34Z, before any data was parsed.) The final procedure list is printed and logged before any outcome. IMPC lines are matched to K4 genotypes by allele symbol and zygosity (homozygote as allele/allele, heterozygote as allele/+, hemizygote as allele/Y). Per matched genotype: behavioral procedures with results, parameters analyzed, and parameters significant.

## Outcomes

O1. Warning 1 quantified. In the random 2,000 lines without behavioral annotation, the share with a recorded normal behavioral result (MGI) and the share with a successful behavioral IMPC procedure. These are lower bounds on how often "not behaviorally annotated" hides an assay with a normal outcome. Binomial (Wilson) 95 percent intervals. The same shares among curated positives and uncurated disorder-gene lines.

O2. What was assayed. Assay-domain counts from notes (normal and abnormal rows together) for curated positives per disorder, for uncurated disorder-gene lines (H lines as in 6c) and for other behaviorally annotated lines. The F24 question at assay grain: is the social domain more often assayed in ASD gene lines than in other lines, and so on per disorder (social for ASD, learning and memory for IDD and NCD, sensorimotor gating for SCZ, affect for MDD). Reported as rates with Wilson intervals, not tests.

O3. The tested restriction. Discrimination AUROC on the support score (full pool) and convergent AUROC on diagnostic coverage, with both classes restricted to behaviorally assessed lines, beside the behaviorally annotated values of F25 and F27. Gene-clustered percentile intervals, 1,000 replicates, seed 20261008. Lines outside the fetched set have unknown assessment status. The restriction therefore covers fetched lines only and is reported with its coverage.

O4. IMPC normal-result rate. Among K4 genotypes matched to IMPC with at least one successful behavioral procedure, the share with no abnormal behavioral MGI annotation. This is the direct "tested, no behavioral annotation" rate for a uniform battery.

## Rules

- Every number states pool, label version, restriction and classes, score, AUROC family, interval type.
- If the parse gate fails, no outcome is reported until the parser is fixed and the gate is rerun.
- Results go to FINDINGS_LOG as new F numbers. No value of record changes.
