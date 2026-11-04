"""Graph-derived, versioned deterministic question solvers; no OWL engine claims."""
from rdflib import URIRef

from .hierarchy import chain
from .namespaces import ORG
from .validation import GraphIndex, ValidationError

ALGORITHMS = {
    "R1": "direct_holders", "R2": "indirect_containment", "R3": "reporting_path",
    "R4": "closest_common_unit", "R5": "post_owner", "R6": "root_membership", "R7": "enumerate_posts",
}


def edge(subject, predicate, obj):
    return [str(subject), str(predicate), str(obj)]


def containment_path(start, end, index):
    path = []
    for ancestor in chain(start, index.parent):
        path.append(edge(start, ORG.subOrganizationOf, ancestor))
        start = ancestor
        if start == end:
            return path
    raise ValidationError("Requested ancestor is not reachable")


def solve(index: GraphIndex, category: str, entities: list[str]) -> dict:
    """Paths contain asserted triples. hop_count is maximum supporting path length.

    R4 uses the sum of both arms. R7 uses one hop even when the answer is empty.
    Answers are URI sets in sorted lists, except R2 (boolean) and R3 (ordered path).
    """
    nodes = [URIRef(e) for e in entities]
    paths = []
    try:
        if category == "R1":
            post, = nodes
            if post not in index.posts:
                raise ValidationError("R1 requires a post")
            answer = list(map(str, index.holders[post]))
            paths = [[edge(post, ORG.heldBy, p)] for p in index.holders[post]]
            hops = 1
        elif category == "R2":
            unit, ancestor = nodes
            path = containment_path(unit, ancestor, index)
            if len(path) < 2:
                raise ValidationError("R2 requires indirect containment (at least two edges)")
            answer, paths, hops = True, [path], len(path)
        elif category == "R3":
            person, = nodes
            post = index.holds[person]
            post_path = [post] + chain(post, index.reports)
            if len(post_path) < 3:
                raise ValidationError("R3 requires at least two reportsTo edges")
            path = [edge(person, ORG.holds, post)]
            path += [edge(a, ORG.reportsTo, b) for a, b in zip(post_path, post_path[1:])]
            answer, paths, hops = list(map(str, post_path)), [path], len(path)
        elif category == "R4":
            a, b = nodes
            if a == b or a not in index.units or b not in index.units:
                raise ValidationError("R4 needs distinct organizational units")
            a_chain, b_chain = chain(a, index.parent), chain(b, index.parent)
            if a in b_chain or b in a_chain:
                raise ValidationError("R4 operands must not contain each other")
            b_ancestors = set(b_chain)
            common = next((n for n in a_chain if n in b_ancestors and n in index.units), None)
            if common is None:
                raise ValidationError("R4 has no common parent organizational unit")
            paths = [containment_path(a, common, index), containment_path(b, common, index)]
            answer, hops = [str(common)], sum(map(len, paths))
        elif category in ("R5", "R6"):
            person, = nodes
            post = index.holds[person]
            owner = index.owner[post]
            path = [edge(person, ORG.holds, post), edge(post, ORG.postIn, owner)]
            if category == "R6":
                ancestors = chain(owner, index.parent)
                root = ancestors[-1] if ancestors else owner
                if root not in index.organizations:
                    raise ValidationError("R6 requires a top-level organization")
                if root != owner:
                    path += containment_path(owner, root, index)
                owner = root
            answer, paths, hops = [str(owner)], [path], len(path)
        elif category == "R7":
            unit, = nodes
            if unit not in index.units:
                raise ValidationError("R7 requires an organizational unit")
            answer = list(map(str, index.posts_in[unit]))
            paths = [[edge(unit, ORG.hasPost, p)] for p in index.posts_in[unit]]
            hops = 1
        else:
            raise ValidationError(f"Unknown category {category}")
    except (KeyError, ValueError) as exc:
        raise ValidationError(f"Invalid operands for {category}: {entities}: {exc}") from exc
    return {"answer": answer, "relationship_paths": paths, "hop_count": hops,
            "algorithm": ALGORITHMS[category], "algorithm_version": 1}


def verify_questions(graph, questions: list[dict], truth: dict[str, dict]) -> None:
    """Recompute every answer, depth and witness against the supplied RDF graph."""
    index = GraphIndex(graph)
    ids = [q["question_id"] for q in questions]
    if len(set(ids)) != len(ids) or set(ids) != set(truth):
        raise ValidationError("Question IDs and ground truth IDs must match uniquely")
    for question in questions:
        category = question["category"]
        result = solve(index, category, question["relevant_entities"])
        if result != truth[question["question_id"]]:
            raise ValidationError(f"Ground truth mismatch: {question['question_id']}")
        if question["reasoning_depth"] != result["hop_count"]:
            raise ValidationError("Question reasoning_depth mismatch")
        if question["method"] != {"algorithm": ALGORITHMS[category], "version": 1}:
            raise ValidationError("Question algorithm mismatch")
        for path in result["relationship_paths"]:
            for s, p, o in path:
                if (URIRef(s), URIRef(p), URIRef(o)) not in graph:
                    raise ValidationError(f"Unsupported witness triple: {(s, p, o)}")
