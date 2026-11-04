# Synthetic Organizational Knowledge Graph Generator

A Python 3.11+ research tool that builds parameterized RDF instance graphs using the
[W3C Organization Ontology (ORG)](https://www.w3.org/TR/vocab-org/), generates seven
categories of competency questions, and verifies answers against the graph.
It supports one large graph, independent seeded graphs, and nested scaling datasets
that preserve baseline questions as unrelated organizations are added.
No LLM APIs, databases, external services, or runtime ontology downloads are used.

## Install and run

From this repository:

```bash
python -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install -e '.[test]'
python -m pytest -q

# Small working example: 1 organization, 14 units, 28 posts, 28 people
python -m kg_generator generate --config examples/small.yaml
python -m kg_generator verify output/small/experiment_001

# Thesis-sized example configuration
python -m kg_generator estimate --config config.yaml
python -m kg_generator generate --config config.yaml
```

For the tested dependency versions, run `python -m pip install -r requirements.lock`
before installing the project with `python -m pip install --no-deps -e .`.
Runtime versions are also written to every experiment's metadata.
The `kg-generator` console command is equivalent to `python -m kg_generator`.

CLI overrides take precedence over YAML:

```bash
python -m kg_generator generate --config examples/small.yaml \
  --num-organizations 20 --seed 123 --num-graphs 3 \
  --output-format json-ld --output-directory output/independent

python -m kg_generator generate --config examples/variable.yaml \
  --branching-factor-range 1 4 --posts-per-unit-range 1 6
```

Run `python -m kg_generator generate --help` for all overrides, including
`--no-generate-competency-questions` and `--no-generate-ground-truth`.
Invalid configuration produces an explanatory error and exit status 2.
Existing experiment directories are never overwritten; choose a new output directory.
One experiment is staged atomically. In a batch, completed earlier experiments remain
if a later experiment fails.

## Configuration semantics

All keys are optional; unknown keys and incorrectly typed values are rejected.
The supplied `config.yaml` uses the values in the task's example.

| Section/key | Meaning |
|---|---|
| `generator.num_organizations` | **Exact**, positive number of independent top-level formal organizations per graph. |
| `generator.max_depth` | **Maximum unit levels**, 0–100. Root organizations have depth 0; their units have depth 1. At 0, there are no units, posts or people. |
| `generator.branching_factor` | **Exact** child-unit count for each owner below the depth limit, unless a range is set. Nonnegative integer. |
| `generator.branching_factor_range` | Optional inclusive `[minimum, maximum]`, uniform integer per potential parent. Replaces the exact branching factor. Zero terminates a branch. |
| `generator.posts_per_unit` | **Exact** post count per unit, unless a range is set. Nonnegative integer. Roots receive no posts in this profile. |
| `generator.posts_per_unit_range` | Optional inclusive uniform integer range replacing the exact post count. Zero permits empty units. |
| `generator.employees_per_post` | **Exact**, nonnegative person count per post; 0 means vacant posts. Each person holds exactly one post in this profile. |
| `generator.seed` | Nonnegative integer controlling random choices and the graph namespace. |
| `generator.num_graphs` | **Exact**, positive independent dataset count. Graph *i* uses `seed + i - 1`. |
| `generator.reporting_ancestor_window` | Positive **maximum** containment edges upward to find an ancestor unit leader; default 1. Choose uniformly among occupied ancestor units in this window. |
| `generator.namespace` | Absolute HTTP(S) base ending in `/` or `#`; default `https://example.org/synthetic-org/`. |
| `generator.max_entities` | Safety limit on named entities, including five roles; default 2,000,000. Exceeding it fails rather than truncating output. |
| `output.format` | `turtle`, `rdfxml`, `nt`, or `json-ld`; aliases include `ttl`, `xml`, `rdf/xml`, and `n-triples`. |
| `output.directory` | Output path relative to the **current working directory**, not the YAML file. |
| `evaluation.generate_competency_questions` | Boolean, default true. |
| `evaluation.questions_per_category` | **Exact requested count** of unique questions in each R1–R7 category; default 20. |
| `evaluation.generate_ground_truth` | Boolean, default true. Answers are always computed/verified; false suppresses saving them. Full saved-output verification requires the answer file. |
| `evaluation.shortage_policy` | `error` (default) fails on insufficient questions. Explicit `available` produces the available count, with CLI warnings and metadata shortfalls. |

For a uniform integer range `[a,b]`, the draw's expectation is `(a+b)/2`.
Realized total counts and maximum depth are not fixed when branching varies; they
are always reported. A CLI exact count override clears its YAML range; an explicit
CLI range wins if both are supplied.

For fixed branching `b`, depth `d`, and organization count `n`:

```text
units  = n × sum(b**level for level in 1..d)
posts  = units × posts_per_unit
people = posts × employees_per_post
```

Zero counts are valid but may make question categories impossible. R2 needs depth ≥2;
R3 needs occupied posts with ≥2 reporting edges; R4 needs incomparable units with a
common **unit** ancestor (e.g., depth ≥2 and branching ≥2). The requested unique
question count must also be available.

## RDF model and logical scope

Namespaces `org`, `rdf`, `rdfs`, `owl`, `foaf`, and `ex` are bound.
URIs use `<namespace>graph-<seed>/org-000001/...`. Five shared abstract roles are
Director, Manager, Supervisor, Analyst, and Engineer. Entity labels include unique
identifiers, even when synthetic personal names repeat.

| Entity/assertions | Policy |
|---|---|
| `org:FormalOrganization` | One labeled root per organization. ORG defines it as a subclass of `org:Organization`; RDF-only queries should query its asserted type. |
| `org:OrganizationalUnit` | One parent via `org:unitOf` and `org:subOrganizationOf`, inverse `org:hasUnit`. Parent may be a root or unit. |
| `org:Post` | One unit via `org:postIn`, inverse `org:hasPost`. |
| `foaf:Person` | `org:holds` a post, inverse `org:heldBy`, and `org:memberOf` the post's immediate unit. Person and post are distinct resources. |
| `org:Role` | Abstract role referenced by the post's `org:role`, distinct from that specific post and its occupants. |
| `org:reportsTo` | Post-to-post edges; people report through their posts. |

The first post in a unit is its leader. Other local posts report to it. The leader
reports to an eligible ancestor unit leader, if one exists in the configured window.
First-level leaders are terminal posts. Empty intermediate units can create additional
terminal posts when no eligible supervisor is in the window. This is a forest; a
single global CEO is not required. Reporting stays within one root organization.
Cross-level skips are supported; cross-organization reporting is outside this profile.

`org:transitiveSubOrganizationOf` is the transitive containment vocabulary term.
Only immediate containment edges are stored; ancestor closure is computed by traversal.
Do not treat `org:reportsTo`, `org:unitOf`, or `org:subOrganizationOf` as individually
declared transitive properties. SPARQL `org:subOrganizationOf+` explicitly computes
reachability without asserting each resulting pair.

Instance graphs contain **no schema axioms**. `schema.ttl` is a separate ontology
descriptor, references ORG, and adds no inference axioms. It does not import or bundle
the complete W3C schema. RDFLib performs no automatic RDFS/OWL reasoning here.
R6's top-level membership rule is an operational benchmark rule, **not a general
OWL/ORG entailment claim**. Direct unit membership is asserted consistently with
post occupancy.

## Competency questions and ground truth

Questions are sampled from real graph entities, with deterministic category-specific
seeds. There are no invented answers, duplicate questions within a category, or
undefined common ancestors. Answers use full URIs to avoid name ambiguity.

| Category | Task | Algorithm and hop convention |
|---|---|---|
| R1 | Who explicitly holds this post? | Full `org:heldBy` set; 1 hop. |
| R2 | Is this unit indirectly contained in its root organization? | ≥2 containment edges; depth is path length. |
| R3 | Full reporting path from a person's post to its terminal supervisor post. | `holds` then ≥2 `reportsTo` edges; includes starting/terminal posts; depth includes `holds`. |
| R4 | Closest common parent **unit** of two incomparable units. | Nearest shared strict unit ancestor; depth sums both path lengths. |
| R5 | Which unit directly contains the person's post? | `holds` → `postIn`; 2 hops. |
| R6 | Which root organization contains the person's affiliation? | Project rule: `holds` → `postIn` → zero or more `subOrganizationOf` edges to a root. |
| R7 | Every post directly in a unit. | Complete `org:hasPost` set; 1 hop, including valid empty sets. |

These are operational categories, not proofs of the minimum reasoning an LLM must
use; asserted direct membership can shorten a route. The initial R2 pool contains
**positive reachability examples only**; it does not benchmark negative answers or
open-world non-entailment. R4 excludes ancestor/descendant operands and cross-root
pairs. These restrictions avoid undefined or misleading answers.

`competency_questions.json` contains IDs, text, categories, depths, operand URIs, and
versioned algorithm names. `ground_truth.json`, keyed by the same IDs, contains answers
and paths. Each path is a list of `[subject_uri, predicate_uri, object_uri]` triples,
all of which must exist in RDF. Set answers are sorted; R3 is ordered; R2 is boolean.
Empty R1/R7 sets refer to the complete generated dataset scope, not an OWL closed-world
assertion. Intermediate relevant entities appear in the supporting paths.

Algorithms live in `ground_truth.py`; their arguments are `relevant_entities`:

```python
from kg_generator.ground_truth import solve
from kg_generator.validation import GraphIndex
answer = solve(GraphIndex(graph), question["category"], question["relevant_entities"])
```

All questions are verified before output. `verify` reparses RDF, checks structure,
counts, metadata and hashes, recomputes saved answers/depths, and checks witness triples.
Tests include independent SPARQL checks, a hand-authored reasoning oracle, and a
brute-force common-ancestor sampling oracle. Pair sampling ranks eligible pairs in
O(V) space rather than constructing O(V²) pairs.

## Output and reproducibility

```text
output/experiment_001/
    knowledge_graph.ttl          # .rdf, .nt, or .jsonld for other formats
    competency_questions.json
    ground_truth.json
    metadata.json
    config.yaml                  # effective configuration of this graph
```

Metadata records entity/triple counts, realized hierarchy depth, average child count
among non-leaf owners, reporting path length histogram/mean/maximum, seed, generator
and runtime versions, UTC timestamp, question coverage, and content hashes.
Reporting statistics count post-to-terminal-post edges, omitting R3's person-to-post edge.

Fixed effective configuration and seed reproduce equivalent RDF and identical questions
and answers in the same runtime. Timestamps can change; serialization byte order across
RDFLib versions is not promised. Graph hashes use sorted N-Triples for named-node
graphs; question hashes use sorted-key JSON. Record Python/dependency and generator
versions for published experiments. Cross-version sampling/serialization behavior is
not a compatibility promise. A graph's saved config has its effective seed and
`num_graphs: 1`, enabling standalone reproduction of any batch member.

## Controlled scaling experiments

`estimate` computes the **exact core triple count without building RDF**, replaying
the deterministic layout. Counts include five shared roles (10 triples), root types
and labels, units, posts, people and reporting edges. It excludes extensions; no
arbitrary padding triples are introduced.

```bash
python -m kg_generator estimate --config examples/variable.yaml
python -m kg_generator scale --config examples/small.yaml \
  --targets 1000 5000 10000 50000 100000 \
  --output-directory output/scaling
```

The helper varies **only `num_organizations`**, adding whole independent organizations
while preserving seed, namespace, depth, branching/post distributions, occupancy,
and reporting policy. The supplied organization count is a minimum. Targets are sorted
and deduplicated. Each target is met or exceeded; actual counts and overshoot are saved.
Nearby targets can map to the same size because organizations are indivisible.
Depth/path distributions are held by the generation policy; realized histograms can
vary when random ranges are used.

Outputs are `scale_001/`, `scale_002/`, etc., plus `scaling_manifest.json`.
Every earlier triple remains in larger graphs. Organization-local random streams keep
earlier people, labels and edges unchanged. By default, the smallest graph's questions
and answers are reused and reverified at every size. Added organizations are disconnected
from baseline entities, supplying controlled irrelevant knowledge for those questions.
Use `--no-freeze-questions` to sample separately per size. Scaling requires `num_graphs: 1`;
independent seeds use `generate`.

For other experimental factors, run one CLI override per separate output directory.
Changing depth or branching does **not** carry a nesting guarantee; only appending
organizations with otherwise identical parameters does. URI identity alone does not
guarantee unchanged relationships.

RDFLib's in-memory store requires O(T) memory. Batch/scaling graphs are built and
written sequentially. Validation and pair indexing use O(V+E) storage; canonical hashing
sorts O(T) strings. Serialization writes directly to disk. Tests exercise >100,000
triples, including questions and verification, under a broad 400 MiB Python allocation
bound. This is not arbitrary-size streaming or a fixed OS RSS promise. Estimate first;
N-Triples is useful for large simple interchange.

## Example graph and querying

`examples/generated/experiment_001/` contains a complete small dataset. This abbreviated
pattern shows the model; full files also contain labels, inverses, roles, and more units:

```turtle
@prefix org: <http://www.w3.org/ns/org#> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
@prefix ex: <https://example.org/synthetic-org/graph-42/> .
ex:org-000001 a org:FormalOrganization .
<https://example.org/synthetic-org/graph-42/org-000001/u0001>
    a org:OrganizationalUnit ; org:unitOf ex:org-000001 ;
    org:subOrganizationOf ex:org-000001 .
<https://example.org/synthetic-org/graph-42/org-000001/u0001/post-0001>
    a org:Post ;
    org:postIn <https://example.org/synthetic-org/graph-42/org-000001/u0001> .
<https://example.org/synthetic-org/graph-42/org-000001/u0001/post-0001/person-0001>
    a foaf:Person ;
    org:holds <https://example.org/synthetic-org/graph-42/org-000001/u0001/post-0001> .
```

Run `python examples/query_example.py` after installation. It executes:

```sparql
PREFIX org: <http://www.w3.org/ns/org#>
SELECT ?person ?post ?unit ?organization WHERE {
    ?person org:holds ?post .
    ?post org:postIn ?unit .
    ?unit org:subOrganizationOf+ ?organization .
    ?organization a org:FormalOrganization .
}
ORDER BY ?person
LIMIT 5
```

## Extending the generator

Modules separate configuration, hierarchy construction, RDF generation, validation,
serialization, question selection, solvers, scaling, and CLI. Validation describes this
deliberately strict synthetic forest profile, not every real-world structure ORG allows.

`generate_graph(config, extensions=[callable, ...])` invokes domain hooks after the
core graph is built, passing `(graph, GeneratorConfig)`. Hooks can add skills,
responsibilities, activities, resources, amenities, transportation or housing. Use
established vocabularies where appropriate, or declare custom predicates in a
**separate project schema**; do not invent ORG properties.

```python
from rdflib import Namespace, Literal
from rdflib.namespace import RDF, RDFS, FOAF
from kg_generator.config import GeneratorConfig
from kg_generator.generator import generate_graph
from kg_generator.hierarchy import rng_for
from kg_generator.validation import validate_graph

domain = Namespace("https://example.org/synthetic-org/domain/")
def add_skills(graph, config):
    # Declare domain:Skill and domain:hasSkill in a separate schema file.
    skill = domain.python
    graph.add((skill, RDF.type, domain.Skill))
    graph.add((skill, RDFS.label, Literal("Python")))
    for person in sorted(graph.subjects(RDF.type, FOAF.Person), key=str):
        if rng_for(config.seed, str(person) + "/skills").random() < 0.5:
            graph.add((person, domain.hasSkill, skill))

config = GeneratorConfig()
graph = generate_graph(config, extensions=[add_skills])
validate_graph(graph, config)
graph.serialize("extended.ttl", format="turtle")
```

Use named nodes and entity-local RNG for reproducible/nested extensions. Extensions
need their own schema, validation, counts and questions. The core entity limit and
exact estimator exclude additions. The initial CLI generates the core domain only;
a future registry can expose hooks through configuration without rewriting generation.
