from dataclasses import replace
import json
import tracemalloc

import pytest
from rdflib import Graph

from kg_generator.config import Config, ConfigError, GeneratorConfig, OutputConfig
from kg_generator.generator import generate_graph
from kg_generator.ground_truth import verify_questions
from kg_generator.scaling import estimate, run_scaling, scaling_plan
from kg_generator.validation import validate_graph


@pytest.mark.parametrize("variation", [False, True])
def test_exact_estimate(settings, variation):
    if variation:
        settings = replace(settings, posts_per_unit_range=(0, 4), branching_factor_range=(0, 3),
                           reporting_ancestor_window=3)
    graph = generate_graph(settings)
    counts = estimate(settings)
    actual = validate_graph(graph, settings)
    for key in ("num_triples", "num_posts", "num_individuals", "num_organizational_units", "num_organizations"):
        assert counts[key] == actual[key]


def test_nested_graphs(settings, evaluation):
    small = generate_graph(settings)
    large = generate_graph(replace(settings, num_organizations=4))
    assert all(triple in large for triple in small)
    from kg_generator.competency_questions import generate_questions
    questions, truth, _ = generate_questions(small, evaluation, settings.seed)
    verify_questions(large, questions, truth)


def test_scaling_run(tmp_path, settings, evaluation):
    config = Config(generator=settings, evaluation=evaluation, output=OutputConfig(directory=str(tmp_path)))
    results = run_scaling(config, [1000, 5000])
    assert len(results) == 2
    small, large = [tmp_path / r["directory"] for r in results]
    assert (small / "competency_questions.json").read_bytes() == (large / "competency_questions.json").read_bytes()
    assert (small / "ground_truth.json").read_bytes() == (large / "ground_truth.json").read_bytes()
    previous = Graph().parse(small / "knowledge_graph.ttl")
    current = Graph().parse(large / "knowledge_graph.ttl")
    assert all(t in current for t in previous)
    for entry in results:
        assert entry["actual_triples"] == entry["estimated_triples"]
        assert entry["actual_triples"] >= entry["target_triples"]
    assert json.loads((tmp_path / "scaling_manifest.json").read_text())["nested"]


def test_scaling_memory_and_large_dataset():
    # Real ~100k-triple generation plus validation under a broad memory bound.
    # Pair sampling is separately checked against a brute-force oracle on small RDF.
    base = GeneratorConfig(num_organizations=1, max_depth=3, branching_factor=3, posts_per_unit=4)
    entry = scaling_plan(base, [100_000])[0]
    config = replace(base, num_organizations=entry["num_organizations"])
    tracemalloc.start()
    try:
        graph = generate_graph(config)
        stats = validate_graph(graph, config)
        from kg_generator.competency_questions import generate_questions
        from kg_generator.config import EvaluationConfig
        questions, truth, _ = generate_questions(graph, EvaluationConfig(), config.seed)
        verify_questions(graph, questions, truth)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert stats["num_triples"] >= 100_000
    assert peak < 400 * 1024 * 1024


def test_scaling_invalid(settings):
    with pytest.raises(ConfigError):
        scaling_plan(settings, [0])


def test_frozen_scaling_retains_shortfall_metadata(tmp_path):
    from kg_generator.config import EvaluationConfig
    config = Config(generator=GeneratorConfig(num_organizations=1, max_depth=1, posts_per_unit=1),
                    evaluation=EvaluationConfig(shortage_policy="available"),
                    output=OutputConfig(directory=str(tmp_path)))
    results = run_scaling(config, [40, 100])
    assert all(r["question_shortfalls"]["R4"] == 20 for r in results)
    for entry in results:
        metadata = json.loads((tmp_path / entry["directory"] / "metadata.json").read_text())
        assert metadata["question_coverage"]["categories"]["R4"]["shortfall"] == 20


def test_scaling_rejects_batch():
    config = Config(generator=GeneratorConfig(num_graphs=2))
    with pytest.raises(ConfigError, match="num_graphs"):
        run_scaling(config, [100])
