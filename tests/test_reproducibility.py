from dataclasses import replace
import json

from rdflib.compare import isomorphic

from kg_generator.competency_questions import generate_questions
from kg_generator.config import Config, OutputConfig
from kg_generator.generator import generate_graph
from kg_generator.serialization import graph_digest, run_generation


def test_repeatable(graph, settings, evaluation):
    again = generate_graph(settings)
    assert isomorphic(graph, again)
    assert graph_digest(graph) == graph_digest(again)
    assert generate_questions(graph, evaluation, settings.seed) == generate_questions(again, evaluation, settings.seed)


def test_seed_changes_assignments(settings):
    from rdflib.namespace import FOAF
    from kg_generator.validation import GraphIndex
    # URI seeds also differ, so check randomized names and structures independently.
    a = generate_graph(replace(settings, branching_factor_range=(1, 3), posts_per_unit_range=(1, 4)))
    b = generate_graph(replace(settings, seed=999, branching_factor_range=(1, 3), posts_per_unit_range=(1, 4)))
    assert sorted(map(str, a.objects(None, FOAF.name))) != sorted(map(str, b.objects(None, FOAF.name)))
    assert len(GraphIndex(a).units) != len(GraphIndex(b).units)


def test_multiple_independent_graphs(tmp_path, settings, evaluation):
    config = Config(generator=replace(settings, num_graphs=3), evaluation=evaluation,
                    output=OutputConfig(directory=str(tmp_path)))
    results = run_generation(config)
    assert [m["seed"] for _, m in results] == [42, 43, 44]
    assert len({m["graph_sha256"] for _, m in results}) == 3
    for path, _ in results:
        questions = json.loads((path / "competency_questions.json").read_text())
        assert len(questions) == 35
