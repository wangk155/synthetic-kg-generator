"""Validate the asserted graph under the generator's explicit forest profile."""
from collections import Counter, defaultdict
from dataclasses import dataclass

from rdflib import Graph
from rdflib.namespace import FOAF, RDF, RDFS

from .config import GeneratorConfig
from .hierarchy import chain, depths
from .namespaces import ORG


class ValidationError(ValueError):
    pass


def functional(graph, predicate):
    result = {}
    for subject, obj in graph.subject_objects(predicate):
        if subject in result and result[subject] != obj:
            raise ValidationError(f"{predicate}: multiple values for {subject}")
        result[subject] = obj
    return result


@dataclass
class GraphIndex:
    graph: Graph

    def __post_init__(self):
        g = self.graph
        self.organizations = set(g.subjects(RDF.type, ORG.FormalOrganization)) | set(g.subjects(RDF.type, ORG.Organization))
        self.units = set(g.subjects(RDF.type, ORG.OrganizationalUnit))
        self.organizations -= self.units
        self.posts = set(g.subjects(RDF.type, ORG.Post))
        self.people = set(g.subjects(RDF.type, FOAF.Person))
        self.roles = set(g.subjects(RDF.type, ORG.Role))
        self.parent = functional(g, ORG.subOrganizationOf)
        self.owner = functional(g, ORG.postIn)
        self.holds = functional(g, ORG.holds)
        self.reports = functional(g, ORG.reportsTo)
        self.children = defaultdict(list)
        self.posts_in = defaultdict(list)
        self.holders = defaultdict(list)
        for child, parent in self.parent.items():
            self.children[parent].append(child)
        for post, owner in self.owner.items():
            self.posts_in[owner].append(post)
        for person, post in self.holds.items():
            self.holders[post].append(person)
        for mapping in (self.children, self.posts_in, self.holders):
            for values in mapping.values():
                values.sort(key=str)
        try:
            self.depth = depths(self.parent, self.units | self.organizations)
            self.report_depth = depths(self.reports, self.posts)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc

    def label(self, node):
        return str(self.graph.value(node, RDFS.label) or node)


def validate_graph(graph: Graph, config: GeneratorConfig | None = None) -> dict:
    index = GraphIndex(graph)

    def require(condition, message):
        if not condition:
            raise ValidationError(message)

    groups = [index.organizations, index.units, index.posts, index.people, index.roles]
    for i, group in enumerate(groups):
        for other in groups[i + 1:]:
            require(not group & other, "Entity classes must be distinct in the synthetic profile")
    owners = index.organizations | index.units
    require(set(index.parent) == index.units, "Every unit must have exactly one parent; roots cannot have parents")
    require(set(index.parent.values()) <= owners, "Unit parent must be an organization or unit")
    require(set(graph.subject_objects(ORG.unitOf)) == set(index.parent.items()), "unitOf must agree with containment")
    require(set(graph.subject_objects(ORG.hasUnit)) == {(p, u) for u, p in index.parent.items()}, "hasUnit inverse mismatch")
    for unit in index.units:
        require(chain(unit, index.parent)[-1] in index.organizations, "Unit hierarchy must terminate at a top-level organization")
    for child, ancestor in graph.subject_objects(ORG.transitiveSubOrganizationOf):
        require(ancestor in chain(child, index.parent), "Unsupported transitive containment assertion")
    require(set(index.owner) == index.posts, "Every post must have exactly one valid owner")
    require(set(index.owner.values()) <= owners, "postIn references an invalid owner")
    require(set(graph.subject_objects(ORG.hasPost)) == {(u, p) for p, u in index.owner.items()}, "hasPost inverse mismatch")
    require(set(index.holds) == index.people, "Every person must hold exactly one post in this profile")
    require(set(index.holds.values()) <= index.posts, "Person holds an invalid post")
    require(set(graph.subject_objects(ORG.heldBy)) == {(p, e) for e, p in index.holds.items()}, "heldBy inverse mismatch")
    require(set(graph.subject_objects(ORG.memberOf)) == {(e, index.owner[p]) for e, p in index.holds.items()},
            "Direct membership must agree with holds/postIn")
    post_roles = functional(graph, ORG.role)
    require(set(post_roles) == index.posts and set(post_roles.values()) <= index.roles, "Every post must have a valid abstract role")
    require(set(index.reports) <= index.posts and set(index.reports.values()) <= index.posts,
            "Reporting endpoints must be posts")
    for post, supervisor in index.reports.items():
        source_owner, target_owner = index.owner[post], index.owner[supervisor]
        require(source_owner == target_owner or target_owner in chain(source_owner, index.parent),
                "Reporting must remain within a unit or go to an ancestor unit")
        if config and source_owner != target_owner:
            require(index.depth[source_owner] - index.depth[target_owner] <= config.reporting_ancestor_window,
                    "Reporting edge exceeds reporting_ancestor_window")
    for group in groups:
        for entity in group:
            require(len(list(graph.objects(entity, RDFS.label))) == 1, "Every entity needs one readable label")
    if config:
        require(len(index.organizations) == config.num_organizations, "Top-level organization count mismatch")
        require(max(index.depth.values(), default=0) <= config.max_depth, "Hierarchy exceeds max_depth")
        branch_min, branch_max = config.branching_factor_range or (config.branching_factor,) * 2
        post_min, post_max = config.posts_per_unit_range or (config.posts_per_unit,) * 2
        for owner in owners:
            count = len(index.children[owner])
            lower, upper = ((branch_min, branch_max) if index.depth[owner] < config.max_depth else (0, 0))
            require(lower <= count <= upper, f"Child count outside configuration at {owner}")
        for unit in index.units:
            require(post_min <= len(index.posts_in[unit]) <= post_max, f"Post count outside configuration at {unit}")
        require(not any(index.posts_in[root] for root in index.organizations), "This profile generates posts in units only")
        for post in index.posts:
            require(len(index.holders[post]) == config.employees_per_post, "employees_per_post count mismatch")
        # A same-unit reporting tree connects every local nonleader to a leader.
        # Leaders report upward whenever an occupied ancestor is in the allowed window.
        for unit in index.units:
            local = index.posts_in[unit]
            if not local:
                continue
            leader = local[0]  # Deterministic URI ordering in this profile.
            ancestors = chain(unit, index.parent)[:config.reporting_ancestor_window]
            eligible = {index.posts_in[a][0] for a in ancestors if index.posts_in[a]}
            require((index.reports.get(leader) in eligible) if eligible else leader not in index.reports,
                    "Unit leader reporting assignment is missing or inconsistent")
            require(all(index.reports.get(p) == leader for p in local[1:]), "Local post must report to its unit leader")
    branching = [len(index.children[n]) for n in owners if index.children[n]]
    paths = list(index.report_depth.values())
    histogram = Counter(paths)
    return {
        "num_organizations": len(index.organizations), "num_organizational_units": len(index.units),
        "num_posts": len(index.posts), "num_individuals": len(index.people), "num_roles": len(index.roles),
        "num_triples": len(graph), "maximum_hierarchy_depth": max(index.depth.values(), default=0),
        "average_branching_factor": sum(branching) / len(branching) if branching else 0,
        "average_branching_factor_definition": "mean child count among non-leaf organizations and units",
        "reporting_path_statistics": {"max_edges": max(paths, default=0),
            "mean_edges": sum(paths) / len(paths) if paths else 0,
            "histogram": {str(k): histogram[k] for k in sorted(histogram)},
            "definition": "post-to-terminal-post paths, includes posts with zero reporting edges"},
    }
