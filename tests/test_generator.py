from dataclasses import replace

import pytest
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import FOAF, OWL, RDF

from kg_generator.config import Config, EvaluationConfig, FORMATS, GeneratorConfig, OutputConfig
from kg_generator.generator import generate_graph
from kg_generator.namespaces import ORG
from kg_generator.serialization import run_generation, verify_experiment
from kg_generator.validation import GraphIndex, ValidationError, validate_graph


def test_exact_counts(graph, settings):
    stats = validate_graph(graph, settings)
    units = settings.num_organizations * sum(settings.branching_factor ** depth
                                           for depth in range(1, settings.max_depth + 1))
    assert stats["num_organizations"] == 2
    assert stats["num_organizational_units"] == units
    assert stats["num_posts"] == units * 3
    assert stats["num_individuals"] == units * 3 * 2
    assert stats["maximum_hierarchy_depth"] == 3
    assert stats["average_branching_factor"] == 2
    index = GraphIndex(graph)
    assert not index.people & index.posts
    assert len(index.roles) == 5
    assert not list(graph.subjects(RDF.type, OWL.TransitiveProperty))


@pytest.mark.parametrize("fmt", list(FORMATS))
def test_serialization_roundtrip(tmp_path, fmt):
    config = Config(generator=GeneratorConfig(num_organizations=1, max_depth=3, posts_per_unit=2),
                    evaluation=EvaluationConfig(questions_per_category=2),
                    output=OutputConfig(format=fmt, directory=str(tmp_path)))
    results = run_generation(config)
    folder, metadata = results[0]
    rdf_format, ext = FORMATS[fmt]
    saved = Graph().parse(folder / f"knowledge_graph.{ext}", format=rdf_format)
    assert isomorphic(saved, generate_graph(config.generator))
    assert verify_experiment(folder)["num_triples"] == metadata["num_triples"]
    assert (folder / "ground_truth.json").exists()


@pytest.mark.parametrize("changes", [
    {"max_depth": 0}, {"branching_factor": 0}, {"posts_per_unit": 0}, {"employees_per_post": 0},
    {"branching_factor_range": (0, 2), "posts_per_unit_range": (0, 3)},
])
def test_zero_and_variable_counts(settings, changes):
    config = replace(settings, **changes)
    validate_graph(generate_graph(config), config)


def test_assignments_and_roles(graph):
    index = GraphIndex(graph)
    for post, unit in index.owner.items():
        assert unit in index.units
        assert (unit, ORG.hasPost, post) in graph
        assert graph.value(post, ORG.role) in index.roles
    for person, post in index.holds.items():
        assert (person, RDF.type, FOAF.Person) in graph
        assert (post, ORG.heldBy, person) in graph
        assert (person, ORG.memberOf, index.owner[post]) in graph


@pytest.mark.parametrize("predicate", [ORG.hasUnit, ORG.hasPost, ORG.heldBy, ORG.memberOf, ORG.role])
def test_missing_assignment_rejected(graph, settings, predicate):
    graph.remove(next(graph.triples((None, predicate, None))))
    with pytest.raises(ValidationError):
        validate_graph(graph, settings)


def test_invalid_owner_rejected(graph, settings):
    post = next(graph.subjects(RDF.type, ORG.Post))
    graph.set((post, ORG.postIn, URIRef("https://invalid.example/owner")))
    with pytest.raises(ValidationError):
        validate_graph(graph, settings)


def test_extension_hook(settings):
    predicate = URIRef("https://example.org/custom/skill")
    def add_skills(graph, config):
        for person in list(graph.subjects(RDF.type, FOAF.Person)):
            graph.add((person, predicate, URIRef("https://example.org/custom/python")))
    graph = generate_graph(settings, extensions=[add_skills])
    validate_graph(graph, settings)
    assert len(list(graph.triples((None, predicate, None)))) > 0


def test_no_overwrite(tmp_path):
    folder = tmp_path / "experiment_001"
    folder.mkdir()
    (folder / "keep.txt").write_text("existing research data")
    with pytest.raises(FileExistsError):
        run_generation(Config(output=OutputConfig(directory=str(tmp_path))))
    assert (folder / "keep.txt").read_text() == "existing research data"
