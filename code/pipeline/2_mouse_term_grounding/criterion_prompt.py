#!/usr/bin/env python3
import criterion_rules
from criterion_spec import component_enum

MODES = ("joint", "joint_reversed", "binary_isolated", "binary_context")


def _unit_block(spec, it, criteria, stems, mark_target=False):
    iid, letter = it["item_id"], it["letter"]
    head = f"UNIT {iid}" + ("   <<< THIS IS THE UNIT YOU ARE JUDGING" if mark_target else "")
    b = [head]
    if stems.get(letter) and stems[letter] != criteria[iid]:
        b.append(f"  Criterion {letter} stem: {stems[letter]}")
    b.append(f"  Text (PARAPHRASED FROM DSM-5-TR): {criteria[iid]}")
    comps = it.get("components", [])
    if comps:
        b.append(f"  NAMED COMPONENTS OF THIS CRITERION, {len(comps)}, named in the same text: "
                 + "; ".join(comps))
        b.append("  These are EXAMPLES, not a list to be satisfied. The criterion is met by any ONE "
                 "of them. Record which one in `component`.")
        desc = it.get("component_descriptions") or {}
        if desc:
            b.append("  WHAT DSM MEANS BY EACH OF THOSE NAMES. These paraphrase DSM's definitions and they "
                     "OVERRIDE the plain reading of the name. A name like `perceptual-motor` sounds "
                     "broader than DSM's definition of it; use the definition, not the name.")
            for c in comps:
                if c in desc:
                    b.append(f"    {desc[c]}")
    if it.get("floor"):
        b.append(f"  NOTE: {it.get('floor_reason','')}")
    elif it.get("note"):
        b.append(f"  NOTE: {it['note']}")
    dd = it.get("dsm_definition")
    if dd:
        b.append("  WHAT DSM ITSELF MEANS BY THE TERMS IN THIS UNIT. This paraphrases DSM-5-TR's definitional "
                 "text from elsewhere in the same chapter, and it OVERRIDES the plain reading of a name. "
                 "A term of art like `perceptual-motor` sounds broader than DSM's definition of it. Use "
                 "the definition, not the name.")
        for chunk in dd.split("\n"):
            if chunk.strip():
                b.append("    " + chunk.strip())
    return "\n".join(b)


def _shared_tail(spec, comp_txt, binary=False):
    extra = criterion_rules.render(spec.get("extra_rules"))
    extra_txt = ("\n\n" + extra) if extra else ""
    unit_word = "unit" if not binary else "unit you are judging"
    return f"""
BLINDING, WHICH STILL APPLIES
Classify ONLY from the MP term label, definition, parent and ancestor text. Do NOT use or infer genotype,
gene identity, disease-gene status, disease association, literature prominence, or any ranking result.
This is a blinded ontology-term task. The blinding covers evidence about MODELS. It does NOT cover the
diagnostic criteria above, which you are required to use.

VOCABULARY REALISM, AND THIS IS THE MOST IMPORTANT INSTRUCTION
MP labels are terse and are written for mouse phenotyping, not for psychiatry. They almost never carry the
qualifiers the DSM text uses. MP has no way to say "rigid", "fixated", "excessive", "unusual in strength
or focus", "a behavioral response rather than a measured threshold", or "worse than this animal used to
be".

DO NOT REFUSE A TERM FOR LACKING A QUALIFIER THE VOCABULARY CANNOT EXPRESS. If the term names the right
construct in the right modality for the {unit_word}, admit it and set qualifier_absent=true. Recording the
uncertainty is correct; refusing every real term because none carries an impossible qualifier is not.{{WORKED}}

WHERE TO STILL SAY NO. The rule above widens admission for VOCABULARY reasons only. It does not widen it
for CONSTRUCT reasons. Refuse when:
  - The term is anatomical, morphological, histological or molecular (set modality accordingly).
  - The term is a mechanistic or circuit-level measure (synaptic transmission, EEG, receptor currents,
    neuronal morphology). These support mechanism, not face validity.
  - The term is an ontology umbrella node so broad it names no specific phenotype ("abnormal behavior").{{NOFIT}}{extra_txt}

COMPONENT
{comp_txt}

DIRECTION
Report in term_direction the direction the MP LABEL ITSELF states for the underlying function:
  increase        the label states more of it ("increased grooming behavior", "excessive vocalization",
                  "enhanced social recognition", "hyperresponsive to tactile stimuli")
  decrease        the label states less of it ("decreased vocalization", "impaired social recognition",
                  "hyporesponsive to tactile stimuli", "reduced ...")
  unspecified     the label says only "abnormal ..." and does not state which way
  not_directional the term names no quantity that could go either way
Report what the LABEL SAYS. Do NOT judge whether the direction resembles the disorder; that comparison is
made downstream from the DSM text and is not your call. A term whose direction is opposite to the {unit_word} is
still correctly classified here, and will be handled later.

CONSTRUCT INADMISSIBILITY
Set construct_inadmissible=true only when the DSM unit names something NO mouse can instantiate under any
vocabulary, for example spoken idiosyncratic phrases, delusional belief content, or standardized
intelligence testing. This is a statement about the UNIT, not about this term, and it lets the pipeline
report the unit as unassessable rather than as a measured zero. Those are different claims: a measured
zero says the models were tested and failed, an unassessable says the question cannot be put to a mouse.
""".rstrip()


def build_developer_prompt(spec, criteria, stems, mode="joint", target=None, item_order=None):
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}, expected one of {MODES}")
    disorder = spec["disorder"]
    long = spec.get("disorder_long", disorder)
    grain = spec["scored_grain"]
    unit_word = ("diagnostic item" if grain == "item"
                 else "diagnostic unit" if grain == "mixed" else "diagnostic criterion")

    items = list(spec["items"])
    if item_order:
        by_id = {i["item_id"]: i for i in items}
        items = [by_id[k] for k in item_order]
    elif mode == "joint_reversed":
        items = list(reversed(items))

    binary = mode in ("binary_isolated", "binary_context")
    if binary and target is None:
        raise ValueError(f"mode {mode} requires target")

    if mode == "binary_isolated":
        shown = [i for i in items if i["item_id"] == target]
    else:
        shown = items
    items_txt = "\n\n".join(
        _unit_block(spec, it, criteria, stems, mark_target=(binary and it["item_id"] == target))
        for it in shown)

    if grain == "item":
        grain_txt = (f"THIS DISORDER'S ENUMERATION IS COUNTED. {spec['counting_rule']} So each numbered "
                     f"item is a separate unit, and a term serves the item it instantiates, not the "
                     f"criterion in general. There are {len(spec['items'])} units.")
        comp_txt = ("This disorder's units enumerate no named components, so set component to "
                    "not_applicable.")
    elif grain == "mixed":
        counted = [i for i in spec["items"] if i.get("extract") == "lettered_item"]
        crit = [i for i in spec["items"] if i.get("extract") == "lettered_criterion"]
        grain_txt = (f"THIS DISORDER'S UNITS ARE OF TWO KINDS, because DSM enumerates it two ways in the "
                     f"same criteria set. {spec['counting_rule']} There are {len(spec['items'])} units in "
                     f"total. {len(counted)} are COUNTED items "
                     f"({', '.join(i['item_id'] for i in counted)}): DSM counts them, so each is a "
                     f"separate unit and a term serves the item it instantiates rather than the criterion "
                     f"in general. {len(crit)} is a CRITERION-level unit "
                     f"({', '.join(i['item_id'] for i in crit)}): its own enumeration is ILLUSTRATIVE and "
                     f"is satisfied by any ONE named area, so do not hold a term to the whole criterion "
                     f"when it cleanly instantiates one named area of it.")
        comp_txt = ("Only some units name components. Where a unit lists NAMED COMPONENTS above, set "
                    "component to the one the term instantiates, choosing the most accurate rather than "
                    "the most favourable, or none if the term serves that criterion but no named "
                    "component. For every unit that lists no components, set component to "
                    "not_applicable.")
    else:
        grain_txt = (f"THIS DISORDER'S ENUMERATION IS ILLUSTRATIVE, NOT COUNTED. {spec['counting_rule']} "
                     f"So the CRITERION is the unit, and the named components are examples of it. There "
                     f"are {len(spec['items'])} units. SATISFYING ONE COMPONENT SATISFIES THE CRITERION: "
                     f"do not hold a term to the whole criterion when it cleanly instantiates one named "
                     f"component of it.")
        comp_txt = ("Set component to the named component the term instantiates. This is recorded for "
                    "audit and is NEVER scored, so choose the most accurate one rather than the most "
                    "favourable. Use none if the term serves the criterion but no named component.")

    worked = spec.get("worked_examples") or []
    worked_txt = ""
    if worked:
        worked_txt = "\n\nWorked application of the vocabulary realism rule:\n" + "\n".join(
            "  - " + w for w in worked)

    tail = _shared_tail(spec, comp_txt, binary=binary).replace("{WORKED}", worked_txt).lstrip("\n")

    if not binary:
        tail = tail.replace("{NOFIT}", """
  - No unit fits. Then item_id is "none" and admissible is false. This is a normal and expected outcome
    for the large majority of MP terms.""")
        head = f"""
You are classifying a single Mammalian Phenotype (MP) ontology term for a {disorder} mouse-model
face-validity pipeline. {disorder} is {long}.

YOUR TASK
Decide which DSM-5-TR {unit_word}, if any, this mouse phenotype term could serve as a STRICT analog of,
meaning a defensible mouse instantiation of what that unit describes.

{grain_txt}

THE UNITS, PARAPHRASED FROM DSM-5-TR. These are the ONLY definitions. Do not substitute your own summary of what
this disorder is, and do not apply criteria the text does not state. The parenthetical examples are part
of the text and are AUTHORITATIVE: a mouse term matching a named example matches the unit.

{items_txt}
""".strip()
        out = """
OUTPUT
Assign the single best unit to item_id. If a term genuinely serves two, put the second in second_item_id,
otherwise "none". Set needs_manual_review=true whenever the decision is close, and write one or two
sentences in reason naming which part of the unit text you relied on.""".rstrip()
        return (head + "\n\n" + tail + "\n" + out).strip()

    tail = tail.replace("{NOFIT}", """
  - The term does not instantiate the unit you are judging. Then admissible is false. This is a normal and
    expected outcome for the large majority of MP terms.""")

    if mode == "binary_isolated":
        scope_note = (f"ONLY ONE UNIT IS SHOWN. Judge the term against it on its own terms. You are not "
                      f"choosing among alternatives and no alternative is available to you.")
    else:
        scope_note = (
            "ALL UNITS ARE SHOWN, BUT YOU ARE JUDGING EXACTLY ONE OF THEM, marked above.\n"
            "The others are shown so that you can tell the units APART, because neighbouring DSM units are\n"
            "defined partly by contrast with each other and judging one in a vacuum invites an\n"
            "over-inclusive reading. They are NOT shown so that you can choose among them.\n\n"
            "THIS IS THE CRITICAL INSTRUCTION FOR THIS TASK. A BETTER FIT ELSEWHERE IS NOT A REASON TO\n"
            "REFUSE THE TARGET. If the term instantiates the target unit, admit it, EVEN IF it also\n"
            "instantiates another unit, and EVEN IF the other fit is stronger. Terms that serve two units\n"
            "are expected and are handled downstream. Answer only the question: does this term instantiate\n"
            "the marked unit.\n\n"
            "Record separately, in better_fit_unit, which unit you think fits best overall. That field is\n"
            "DIAGNOSTIC AND NON-BINDING: it is recorded to measure how often a competing unit would have\n"
            "suppressed this admission, and it must not influence your admissible verdict.")

    head = f"""
You are judging a single Mammalian Phenotype (MP) ontology term against a SINGLE DSM-5-TR {unit_word} for
a {disorder} mouse-model face-validity pipeline. {disorder} is {long}.

YOUR TASK
Decide whether this mouse phenotype term could serve as a STRICT analog of UNIT {target}, meaning a
defensible mouse instantiation of what that unit describes. Answer yes or no about {target} only.

{scope_note}

{grain_txt}

THE UNIT TEXT, PARAPHRASED FROM DSM-5-TR. This is the ONLY definition. Do not substitute your own summary of what
this disorder is, and do not apply criteria the text does not state. The parenthetical examples are part
of the text and are AUTHORITATIVE: a mouse term matching a named example matches the unit.

{items_txt}
""".strip()
    out = f"""
OUTPUT
Set admissible true or false for UNIT {target} alone. Set needs_manual_review=true whenever the decision is
close, and write one or two sentences in reason naming which part of the unit text you relied on.""".rstrip()
    return (head + "\n\n" + tail + "\n" + out).strip()


def build_schema(spec, mode="joint", target=None):
    comps = component_enum(spec)
    binary = mode in ("binary_isolated", "binary_context")
    common = {
        "component": {"type": "string", "enum": comps,
                      "description": "Which NAMED component of that criterion the term instantiates. "
                                     "Reported, never scored. not_applicable when none are enumerated."},
        "admissible": {"type": "boolean"},
        "modality": {"type": "string",
                     "enum": ["behavioral", "anatomical", "physiological", "developmental", "other"]},
        "term_direction": {"type": "string",
                           "enum": ["increase", "decrease", "unspecified", "not_directional"]},
        "qualifier_absent": {"type": "boolean"},
        "construct_inadmissible": {"type": "boolean"},
        "confidence": {"type": "number"},
        "needs_manual_review": {"type": "boolean"},
        "reason": {"type": "string"},
    }
    if not binary:
        ids = [it["item_id"] for it in spec["items"]] + ["none"]
        props = {"item_id": {"type": "string", "enum": ids},
                 "second_item_id": {"type": "string", "enum": ids},
                 **common}
        req = ["item_id", "admissible", "second_item_id", "component", "modality", "term_direction",
               "qualifier_absent", "construct_inadmissible", "confidence", "needs_manual_review",
               "reason"]
    else:
        props = dict(common)
        req = ["admissible", "component", "modality", "term_direction", "qualifier_absent",
               "construct_inadmissible", "confidence", "needs_manual_review", "reason"]
        if mode == "binary_context":
            ids = [it["item_id"] for it in spec["items"]] + ["none"]
            props["better_fit_unit"] = {
                "type": "string", "enum": ids,
                "description": "DIAGNOSTIC AND NON-BINDING. Which unit fits best overall. Recorded to "
                               "measure competitive suppression. Must not influence admissible."}
            req.append("better_fit_unit")
    return {"name": "mp_criterion_classification", "strict": True,
            "schema": {"type": "object", "additionalProperties": False,
                       "required": req, "properties": props}}
