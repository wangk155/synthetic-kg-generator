from dataclasses import replace

import pytest

from kg_generator.generator import generate_graph
from kg_generator.namespaces import ORG
from kg_generator.validation import GraphIndex, ValidationError, validate_graph


def test_forests_have_no_cycles(graph):
    index = GraphIndex(graph)
    for mapping in (index.parent, index.reports):
        for start in mapping:
            seen, node = set(), start
            while node in mapping:
                assert node not in seen
                seen.add(node)
                node = mapping[node]


@pytest.mark.parametrize("predicate", [ORG.subOrganizationOf, ORG.reportsTo])
def test_cycles_rejected(graph, settings, predicate):
    subject, _, _ = next(graph.triples((None, predicate, None)))
    graph.set((subject, predicate, subject))
    with pytest.raises(ValidationError, match="Cycle"):
        validate_graph(graph, settings)


def test_cross_level_skip(settings):
    config = replace(settings, max_depth=5, branching_factor=2, reporting_ancestor_window=3)
    graph = generate_graph(config)
    validate_graph(graph, config)
    index = GraphIndex(graph)
    deltas = [index.depth[index.owner[a]] - index.depth[index.owner[b]] for a, b in index.reports.items()]
    assert max(deltas) > 1
    assert max(deltas) <= 3


def test_multiple_parent_rejected(graph, settings):
    index = GraphIndex(graph)
    unit = next(iter(index.units))
    other = next(n for n in index.organizations if n != index.parent[unit])
    graph.add((unit, ORG.subOrganizationOf, other))
    with pytest.raises(ValidationError, match="multiple values"):
        validate_graph(graph, settings)


def test_missing_reporting_edge_rejected(graph, settings):
    graph.remove(next(graph.triples((None, ORG.reportsTo, None))))
    with pytest.raises(ValidationError, match="report"):
        validate_graph(graph, settings)
