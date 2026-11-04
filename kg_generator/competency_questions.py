"""Sample well-defined questions without enumerating quadratic pair spaces."""
import bisect
import hashlib

from .config import ConfigError, EvaluationConfig
from .ground_truth import ALGORITHMS, solve
from .hierarchy import rng_for
from .validation import GraphIndex

CATEGORY_NAMES = {
    "R1": "Direct factual retrieval", "R2": "Transitive hierarchical reasoning",
    "R3": "Multi-hop reporting", "R4": "Common ancestor reasoning",
    "R5": "Cross-relationship reasoning", "R6": "Membership inference", "R7": "Enumeration",
}


def common_ancestor_pair_space(index):
    """Rank all incomparable unit pairs sharing a unit ancestor in O(V) space.

    In DFS order every eligible second unit lies after the first unit's subtree
    and before the end of its first-level unit subtree. No pair list is built.
    """
    order, groups, cumulative = [], [], []
    ends = {}
    for organization in sorted(index.organizations, key=str):
        for top_unit in index.children[organization]:
            begin = len(order)
            stack = [(top_unit, False)]
            while stack:
                unit, exiting = stack.pop()
                if exiting:
                    ends[unit] = len(order)
                else:
                    order.append(unit)
                    stack.append((unit, True))
                    stack.extend((child, False) for child in reversed(index.children[unit]))
            stop = len(order)
            for position in range(begin, stop):
                start = ends[order[position]]
                count = stop - start
                if count:
                    groups.append((position, start))
                    cumulative.append((cumulative[-1] if cumulative else 0) + count)

    def unrank(rank):
        group = bisect.bisect_right(cumulative, rank)
        offset = rank - (cumulative[group - 1] if group else 0)
        first, start = groups[group]
        return [order[first], order[start + offset]]

    return (cumulative[-1] if cumulative else 0), unrank


def question_text(category, entities, index):
    labels = [index.label(n) for n in entities]
    if category == "R1":
        return f"Which people explicitly hold the post '{labels[0]}'? Return all person URIs."
    if category == "R2":
        return (f"Is '{labels[0]}' indirectly contained in '{labels[1]}' via at least two "
                "org:subOrganizationOf edges?")
    if category == "R3":
        return (f"Starting with the post held by '{labels[0]}', give the complete ordered post URI "
                "path following org:reportsTo to its terminal supervisor post. Include the starting post.")
    if category == "R4":
        return (f"What is the closest common parent organizational unit of '{labels[0]}' and "
                f"'{labels[1]}'? Return its URI.")
    if category == "R5":
        return (f"Which organizational unit directly contains the post held by '{labels[0]}'? "
                "Use org:holds followed by org:postIn. Return its URI.")
    if category == "R6":
        return (f"Under the benchmark membership rule (holds, postIn, then zero or more "
                f"subOrganizationOf edges), which top-level organization is '{labels[0]}' "
                "a member of? Return its URI.")
    return f"List all post URIs directly belonging to '{labels[0]}' via org:hasPost."


def generate_questions(graph, config: EvaluationConfig, seed: int):
    if not config.generate_competency_questions:
        return [], {}, {"enabled": False}
    index = GraphIndex(graph)
    units = sorted(index.units, key=str)
    people = sorted(index.people, key=str)
    pools = {
        "R1": sorted(index.posts, key=str),
        "R2": [n for n in units if index.depth[n] >= 2],
        "R3": [n for n in people if index.report_depth[index.holds[n]] >= 2],
        "R5": people, "R6": people, "R7": units,
    }
    pair_count, pair_at = common_ancestor_pair_space(index)
    questions, truth, coverage = [], {}, {}
    for category in CATEGORY_NAMES:
        available = pair_count if category == "R4" else len(pools[category])
        requested = config.questions_per_category
        if available < requested and config.shortage_policy == "error":
            raise ConfigError(f"{category} supports {available} unique questions, but {requested} requested. "
                              "Increase graph depth/branching/posts/employees, reduce questions_per_category, "
                              "or explicitly set evaluation.shortage_policy: available")
        count = min(available, requested)
        coverage[category] = {"requested": requested, "available": available, "generated": count,
                              "shortfall": requested - count}
        ranks = rng_for(seed, "questions/" + category).sample(range(available), count)
        for rank in sorted(ranks):
            if category == "R4":
                entities = pair_at(rank)
            else:
                node = pools[category][rank]
                entities = [node, _root(node, index)] if category == "R2" else [node]
            uris = list(map(str, entities))
            identity = hashlib.sha256((category + "|" + "|".join(uris)).encode()).hexdigest()[:20]
            question_id = f"{category}-{identity}"
            result = solve(index, category, uris)
            questions.append({
                "question_id": question_id, "question": question_text(category, entities, index),
                "category": category, "category_name": CATEGORY_NAMES[category],
                "reasoning_depth": result["hop_count"], "relevant_entities": uris,
                "method": {"algorithm": ALGORITHMS[category], "version": 1},
            })
            truth[question_id] = result
    return questions, truth, {"enabled": True, "categories": coverage,
                              "shortage_policy": config.shortage_policy}


def _root(unit, index):
    while unit in index.parent:
        unit = index.parent[unit]
    return unit
