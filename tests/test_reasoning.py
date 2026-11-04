import copy
import itertools

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import FOAF, RDF, RDFS

from kg_generator.competency_questions import common_ancestor_pair_space, generate_questions
from kg_generator.config import ConfigError, EvaluationConfig, GeneratorConfig
from kg_generator.generator import generate_graph
from kg_generator.ground_truth import solve, verify_questions
from kg_generator.namespaces import ORG
from kg_generator.validation import GraphIndex, ValidationError


def test_every_question_verified(graph, settings, evaluation):
    questions, truth, coverage = generate_questions(graph, evaluation, settings.seed)
    assert len(questions) == 35
    assert set(q["category"] for q in questions) == {f"R{i}" for i in range(1, 8)}
    verify_questions(graph, questions, truth)
    assert all(v["shortfall"] == 0 for v in coverage["categories"].values())
    for q in questions:
        t = truth[q["question_id"]]
        assert t["answer"] is not None
        if q["category"] == "R2":
            assert q["reasoning_depth"] >= 2
        if q["category"] == "R3":
            assert len(t["answer"]) >= 3
            path = t["relationship_paths"][0]
            assert [step[2] for step in path] == t["answer"]
            assert all(a[2] == b[0] for a, b in zip(path, path[1:]))


def test_r1_r7_match_independent_sparql(graph, settings, evaluation):
    questions, truth, _ = generate_questions(graph, evaluation, settings.seed)
    for question in questions:
        if question["category"] not in ("R1", "R7"):
            continue
        predicate = ORG.heldBy if question["category"] == "R1" else ORG.hasPost
        uri = URIRef(question["relevant_entities"][0])
        actual = sorted(str(row[0]) for row in graph.query(f"SELECT ?x WHERE {{ <{uri}> <{predicate}> ?x }}"))
        assert actual == truth[question["question_id"]]["answer"]


def test_hand_authored_reasoning_oracle():
    # Independently constructed tree: root <- A <- B <- D; A <- C <- E.
    g = Graph()
    u = {name: URIRef("https://test.example/" + name) for name in ("root", "A", "B", "C", "D", "E", "P", "Q", "R", "person")}
    g.add((u["root"], RDF.type, ORG.FormalOrganization))
    for name in "ABCDE":
        g.add((u[name], RDF.type, ORG.OrganizationalUnit))
    for child, parent in (("A", "root"), ("B", "A"), ("C", "A"), ("D", "B"), ("E", "C")):
        g.add((u[child], ORG.subOrganizationOf, u[parent]))
    for post, owner in (("P", "D"), ("Q", "B"), ("R", "A")):
        g.add((u[post], RDF.type, ORG.Post))
        g.add((u[post], ORG.postIn, u[owner]))
    for child, parent in (("P", "Q"), ("Q", "R")):
        g.add((u[child], ORG.reportsTo, u[parent]))
    g.add((u["person"], RDF.type, FOAF.Person))
    g.add((u["person"], ORG.holds, u["P"]))
    index = GraphIndex(g)
    assert solve(index, "R2", [str(u["D"]), str(u["root"])])["hop_count"] == 3
    assert solve(index, "R3", [str(u["person"])])["answer"] == [str(u[n]) for n in "PQR"]
    lca = solve(index, "R4", [str(u["D"]), str(u["E"])])
    assert lca["answer"] == [str(u["A"])]
    assert lca["hop_count"] == 4
    assert solve(index, "R5", [str(u["person"])])["answer"] == [str(u["D"])]
    assert solve(index, "R6", [str(u["person"])])["answer"] == [str(u["root"])]


def test_ranked_pair_space_matches_bruteforce(graph):
    index = GraphIndex(graph)
    count, unrank = common_ancestor_pair_space(index)
    actual = {frozenset(unrank(rank)) for rank in range(count)}
    # Independent brute-force oracle used only on the small test graph.
    expected = set()
    for a, b in itertools.combinations(index.units, 2):
        def ancestors(node):
            result = set()
            while node in index.parent:
                node = index.parent[node]
                result.add(node)
            return result
        aa, bb = ancestors(a), ancestors(b)
        if a not in bb and b not in aa and aa & bb & index.units:
            expected.add(frozenset((a, b)))
    assert actual == expected
    assert count == len(actual)


def test_corrupted_truth_rejected(graph, settings, evaluation):
    questions, truth, _ = generate_questions(graph, evaluation, settings.seed)
    broken = copy.deepcopy(truth)
    broken[questions[0]["question_id"]]["answer"] = ["invented"]
    with pytest.raises(ValidationError, match="mismatch"):
        verify_questions(graph, questions, broken)
    broken = copy.deepcopy(truth)
    reporting = next(q for q in questions if q["category"] == "R3")
    broken[reporting["question_id"]]["relationship_paths"][0][1][2] = "invented-intermediate-node"
    with pytest.raises(ValidationError):
        verify_questions(graph, questions, broken)


def test_shortages_are_explicit():
    graph = generate_graph(GeneratorConfig(max_depth=1, posts_per_unit=0))
    with pytest.raises(ConfigError, match="supports"):
        generate_questions(graph, EvaluationConfig(), 42)
    questions, truth, coverage = generate_questions(graph, EvaluationConfig(shortage_policy="available"), 42)
    assert coverage["categories"]["R4"]["shortfall"] == 20
    assert all(q["category"] == "R7" for q in questions)
    assert all(t["answer"] == [] for t in truth.values())
    verify_questions(graph, questions, truth)
