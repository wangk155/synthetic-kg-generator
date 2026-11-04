# Validation record

Generator version: **0.1.0**. Tested with CPython **3.12.14**, RDFLib **7.6.0**,
PyYAML **6.0.3**, and pytest **9.2.0**. Exact dependencies are in `requirements.lock`.

## Automated checks

`python -m pytest -q`: **65 passed** in 11.27 seconds on the implementation environment.
Two upstream RDFLib JSON-LD parser deprecation warnings were emitted; all format
round trips and saved-file checks passed.

Coverage includes:

- RDFLib parsing and equivalent round trips for Turtle, RDF/XML, N-Triples, JSON-LD.
- Exact counts, zero counts, bounded random counts, valid post/person/role assignments.
- Containment/reporting cycle rejection, inverse checks, and membership consistency.
- All seven question categories and graph-supported intermediate witness triples.
- Independent SPARQL retrieval, hand-authored reasoning answers, and brute-force LCA pairs.
- Reproducible graph hashes/questions, differing seeded assignments, independent batches.
- Exact estimates, nested graph preservation, frozen questions, explicit shortages.
- Invalid configuration, entity safety limits, saved-data corruption, and overwrite refusal.
- Generation, validation, question selection and verification for >100,000 triples
  under a 400 MiB Python allocation bound (tracemalloc; not process RSS).

`python -m compileall -q kg_generator examples/query_example.py` and `git diff --check`
also passed. Editable installation and the `kg-generator --version` entry point worked.

## Included small example

Generated using `examples/small.yaml`, overriding the directory to `examples/generated`.
The saved graph was reparsed and checked using the `verify` command. The included
SPARQL query script successfully queried this graph.

| Measure | Count |
|---|---:|
| Top-level organizations | 1 |
| Organizational units | 14 |
| Posts | 28 |
| People | 28 |
| Shared abstract roles | 5 |
| RDF triples | 416 |
| Competency questions | 21 (3 per R1–R7 category) |
| Maximum unit depth | 3 |
| Maximum post reporting path length | 3 edges |

Graph content SHA-256:
`ccf181625165c01de7da775111b55e2cdaa39c1e520914e61c090892fc0b3236`.

## End-to-end scaling check

Executed:

```bash
python -m kg_generator scale --config examples/small.yaml \
  --targets 1000 5000 10000 50000 100000 \
  --output-directory work/scaling-validation
python -m kg_generator verify work/scaling-validation/scale_005
```

All exact estimates matched the serialized actual counts. Baseline questions were
frozen and verified against each graph before saving. The largest output was also
reparsed and verified from disk. Large validation files are omitted from the download
to keep it compact; the command reproduces them.

| Target triples | Actual triples | Organizations | Overshoot |
|---|---:|---:|---:|
| 1,000 | 1,228 | 3 | 228 |
| 5,000 | 5,288 | 13 | 288 |
| 10,000 | 10,160 | 25 | 160 |
| 50,000 | 50,354 | 124 | 354 |
| 100,000 | 100,292 | 247 | 292 |

The largest graph has 3,458 units, 6,916 posts, and 6,916 people. Additional
organizations preserve every earlier triple under identical structural parameters.
The task's supplied `config.yaml` estimates to exactly **78,000 triples**.

## Interpretation limits

The generator implements the documented synthetic forest profile, not arbitrary ORG
validation or a general OWL reasoner. R2 currently samples positive reachability only.
R6 uses an explicitly stated benchmark membership rule. Graph storage is in memory;
the current implementation does not claim arbitrary-size streaming. Refer to the
README for detailed parameter meanings and experiment assumptions.
