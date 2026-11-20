#!/usr/bin/env python3

RULES = {

"grooming_routing": """
GROOMING AND STEREOTYPY, A ROUTING RULE LOCKED 2026-07-27
Rodent grooming is a repetitive, syntactically organised motor sequence, and the field treats it as
stereotypy. Route grooming terms to B1, "movements that are stereotyped or repeated", which is what
grooming IS. Do NOT route grooming to B2. B2 is for insistence-on-sameness and inflexibility constructs
such as cognitive inflexibility, perseveration, and impaired reversal, where the item's language about
routines and rigid patterns applies directly. Nest building and other patterned home-cage sequences follow
the same rule: B1 if the term names the repetitive motor act, B2 only if it names inflexibility.
""",

"involuntary_motor_sign": """
VOLUNTARY BEHAVIOUR VERSUS INVOLUNTARY MOTOR SIGN, A REFUSAL RULE LOCKED 2026-07-27
Every example DSM B1 gives (simple repeated motor acts, arranging toys in rows, turning objects over and over,
repeating the words of others, phrases with a private meaning) is an ORGANISED ACT THE INDIVIDUAL PERFORMS. B1 does not describe movement that
merely repeats. REPETITION ALONE IS NOT SUFFICIENT FOR B1.

An involuntary neurological motor sign is repetitive and is still not a stereotypy. It is produced by
pathology of the motor system rather than emitted as behaviour. REFUSE the following for B1 and for every
other item, and set modality=physiological:
  tremor, myoclonus, muscle spasm, muscle twitch, fasciculation, dystonia, chorea, athetosis, clonus,
  catalepsy and waxy flexibility, ataxia and other incoordination, paralysis, palsy and paresis,
  reflex-elicited postures such as limb grasping and hindlimb clasping, and seizures of every kind,
  including convulsive, nonconvulsive, absence, clonic, tonic, tonic-clonic, focal, febrile, audiogenic,
  psychomotor and induced seizures and every seizure threshold or susceptibility measure.

THIS IS A CONSTRUCT REFUSAL, NOT A VOCABULARY ONE, so the vocabulary realism rule above does NOT override
it. Do not admit any of these because the definition contains the words "repetitive", "cyclical",
"stereotyped" or "movement". MP defines tremors as "repetitive, cyclical movements of the body or a body
part; usually involuntary": the kinematics repeat, and the sign is still not a stereotypy. Read the WHOLE
definition, including any clause naming the phenotype as involuntary, uncontrolled, reflexive, elicited,
induced or a loss of coordination or power.

THE BOUNDARY, STATED POSITIVELY. ADMIT to B1 a term naming an act the animal performs: grooming,
barbering, scratching, nest building, digging, burrowing, marble burying, object manipulation, bar biting,
rearing, jumping, and stereotypic behaviour as such.

WHERE THE BOUNDARY IS GENUINELY AMBIGUOUS, FLAG IT RATHER THAN GUESSING. Some locomotor and head movement
terms have both a stereotypy reading and a vestibular or reflexive one, and MP's own definition often
names the second (for example, circling is defined as "repeated movement in a circle; often associated
with inner ear defects"). For circling, spinning, head bobbing, head shaking, abnormal head movements and
any similar term whose definition names an inner ear, vestibular, reflex or neurological association,
assign your best item AND SET needs_manual_review=true, saying in reason which reading you took and what
the competing reading is. These terms go to a human audit worksheet. Do not silently resolve them.
""",

"asd_construct_refusals": """
ADDITIONAL CONSTRUCT REFUSALS SPECIFIC TO THIS DISORDER
  - The term measures a COGNITIVE FACULTY no item names. Object RECOGNITION MEMORY is a memory assay; it
    is not "smelling or touching objects to excess". Refuse it even though the word "object" appears. The same
    goes for spatial learning and working memory: autism's criteria name none of them.
  - The term is a loss of sensory CAPACITY where the item describes a RESPONSE and MP does offer a
    response-framed alternative. Deafness, blindness and anosmia are capacity losses with behavioral
    alternatives available; refuse them.
  - The term is maternal, agonistic, dominance or sexual behavior and the item describes peer social
    interaction. Note that the same term may legitimately serve a DIFFERENT item; judge against the item
    you assign, not against autism in general.
""",

"human_schooling_constructs": """
HUMAN SCHOOLING AND PSYCHOMETRIC CONSTRUCTS, A REFUSAL RULE FOR THIS DISORDER
Criterion A names learning in school and is confirmed by intelligence tests that are standardized and
given individually. Criterion B names everyday activities in more than one setting, at home, at school,
at work and in the community. Reading, writing, arithmetic, IQ, school and workplace performance are HUMAN
INSTITUTIONAL constructs. No mouse vocabulary instantiates them, and none ever will.

When an item's construct is of this kind, do NOT reach for a loose surrogate. Set item_id to that item,
admissible=false, and construct_inadmissible=true, so the pipeline can report the construct as
UNASSESSABLE rather than as a measured zero. A measured zero says the models were tested and failed; an
unassessable says the question cannot be put to a mouse. Those are different claims and the difference is
the point of this project.

TWO SPECIFIC TRAPS, both observed in this project's own prior ID spine and both to be avoided here:
  - Dyscalculia and dysgraphia are not mouse constructs. They are the schooling surrogate, not the
    criterion, and admitting them manufactures coverage.
  - LANGUAGE IS NOT HEARING. A prior ID target for language impairment pulled a pool made entirely of
    auditory threshold and hearing loss terms. Auditory CAPACITY is not communicative function. Refuse
    hearing terms for any communication construct, and say so in reason.

Where a component IS instantiable, admit normally. Learning and problem solving have direct mouse assays;
reasoning, planning and abstract thinking are the contested middle and should be admitted only when the
term names the operation rather than a task that merely requires it, with needs_manual_review=true.
""",

"decline_versus_deficit": """
DECLINE VERSUS DEFICIT, THE VOCABULARY REALISM CASE FOR THIS DISORDER
Criterion A asks for a DROP FROM THE PERSON'S EARLIER LEVEL OF PERFORMANCE. That is a within-individual longitudinal
comparison. MGI genotype-phenotype annotation is a BETWEEN-GENOTYPE comparison against wild type, and MP
has no longitudinal frame at all: it cannot say "worse than this animal used to be".

DO NOT REFUSE A TERM FOR LACKING THE LONGITUDINAL FRAME. If the term names a deficit in the right
cognitive domain, admit it and set qualifier_absent=true. Refusing every term because none is longitudinal
would zero the disorder for a reason that is about the vocabulary rather than about the models.

This substitution is a known and disclosed concession of the project, not a discovery, and it is recorded
so the reader can discount it. Criterion A's numbered sub-items 1 and 2 are EVIDENCE REQUIREMENTS
(informant or clinician concern; standardized neuropsychological testing). They are not symptom domains
and nothing may be admitted to them.
""",

"language_floor": """
LANGUAGE, WHICH IS FLAGGED RATHER THAN FORCED
A project decision holds that the language domain is a floor for this disorder, meaning no mouse analog.
That decision is NOT encoded here as a refusal, because a rule that assumes its own answer cannot be
tested. Judge language terms on their merits. If you find yourself admitting a vocalization or
communication term to the language domain, do so AND set needs_manual_review=true, naming in reason what
you think the term instantiates. The human audit worksheet then adjudicates the floor against real
candidates rather than against an assumption.

Note the distinction the previous rule also draws: auditory capacity (hearing thresholds, deafness) is
not language. Refuse those for language regardless.
""",

"scz_motor_boundary_from_dsm": """
WHAT COUNTS AS A4, DECIDED FROM THE DEFINITION OF A4 GIVEN IN THIS UNIT AND NOTHING ELSE
The governing text is the paraphrase of DSM-5-TR's definition given in this unit's definition addendum:
motor behavior that is grossly disorganized or abnormal can take many forms, from childlike silliness to
agitation that cannot be predicted; any kind of goal-directed behavior can be affected; and catatonic
behavior is a marked fall in how much the person responds to the surroundings, running from resisting
instructions (negativism), through holding a rigid, inappropriate or odd posture, to no verbal or motor
response at all (mutism and stupor).

Read that text literally. It names BEHAVIOR, and specifically GOAL-DIRECTED behavior, at one pole, and a
MARKED FALL IN RESPONSIVENESS TO THE SURROUNDINGS at the other. Three consequences follow from that
definition, and no other disorder's rules bear on this one.

ADMIT, because the definition names them. Holding a rigid, inappropriate or odd posture: catalepsy, waxy
flexibility, abnormal or bizarre posturing, and immobility or stupor-like unresponsiveness. Resistance to
instructions and negativism. Agitation and disorganization of goal-directed behavior where the term names
the disorganization rather than the activity level.

REFUSE, because the definition excludes them, and set modality=physiological.
  - SEIZURES of every kind, including absence, convulsive, clonic, tonic, tonic-clonic, focal, febrile,
    audiogenic and psychomotor seizures, and every seizure threshold or susceptibility measure. A seizure
    is a paroxysmal ictal event. It is neither behavior nor a fall in responsiveness to the surroundings,
    and the A4 definition describes no such phenomenon.
  - EXAGGERATED REFLEX RESPONSES to environmental stimulation, including hyperekplexia and every startle
    measure. Catatonia is defined here as a marked FALL in responsiveness to the surroundings. An
    exaggerated startle is an INCREASE in reactivity, which is the opposite pole of the construct DSM
    names, not an instance of it.
  - ELEMENTARY MOTOR SIGNS produced by motor system pathology rather than emitted as behavior: tremor,
    myoclonus, muscle twitch, muscle spasm, fasciculation, dystonia, chorea, athetosis, clonus, paralysis,
    palsy and paresis. None is a form of goal-directed behavior and none is a fall in responsiveness to
    the surroundings.
  - BARE ACTIVITY LEVEL. The definition names agitation that cannot be predicted and disorganized goal-directed behavior.
    Plain hyperactivity, increased or decreased locomotor activity, and stimulus-induced hyperactivity name
    an activity LEVEL and not a disorganization. Refuse them unless the term itself names agitation,
    unpredictability, disorganization, or a loss of goal direction.

DO NOT ADMIT A TERM TO A4 SIMPLY BECAUSE THE ITEM IS BIDIRECTIONAL. Bidirectional means DSM names both a
decreased and an increased pole. It does not mean any motor abnormality qualifies.

A5 AVOLITION, THE SAME DISCIPLINE
The definition describes avolition as a drop in purposeful activity that the person starts and sustains
from their own motivation, and reduced emotional expression as less emotion in face, eye contact, speech
melody and gesture. Terms
naming MATERNAL, REPRODUCTIVE or NURTURING behavior, for example pup retrieval, nursing and nest building
for pups, are self-started purposeful activities on a plain reading, but they are also species-specific
reproductive behaviors whose deficit is routinely produced by circuitry unrelated to motivation. DSM does
not settle this. Assign your best item AND SET needs_manual_review=true, saying in reason that the
competing reading is a reproductive rather than a motivational deficit. Do not silently resolve it.
""",

"mechanism_is_not_face_validity": """
THE ENDOPHENOTYPE IS NOT FACE VALIDITY, A HARD SEPARATION FOR THIS DISORDER
Prepulse inhibition, sensorimotor gating, latent inhibition, and psychotomimetic hyper-response to
amphetamine, MK-801 or PCP are the aberrant-salience ENDOPHENOTYPE. They are the substrate a symptom is
theorised to arise from, not the symptom. They must NEVER be admissible for any Criterion A item, however
strongly the literature associates them with this disorder.

This separation is load-bearing rather than fastidious. A term-attribution probe on this project's own
data found that prepulse inhibition plus sensorimotor gating alone carry 57 percent of the competing
method's best matches for this disorder, and endophenotype plus circuit carriers about 80 percent. Keeping
them off the face-validity axis is what makes the comparison between the two methods interpretable.
""",
}


def render(names):
    out = []
    for n in names or []:
        if n not in RULES:
            raise KeyError(f"unknown rule {n!r}. Known: {sorted(RULES)}")
        out.append(RULES[n].strip())
    return "\n\n".join(out)
