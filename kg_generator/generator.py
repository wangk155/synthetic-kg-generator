"""Generate instance assertions only; schema axioms live in schema.ttl."""
from collections.abc import Callable, Iterable

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import FOAF, RDF, RDFS

from .config import ConfigError, GeneratorConfig
from .hierarchy import ROLE_NAMES, rng_for, unit_layout
from .namespaces import ORG, bind_namespaces

Extension = Callable[[Graph, GeneratorConfig], None]


def generate_graph(config: GeneratorConfig, extensions: Iterable[Extension] = ()) -> Graph:
    graph = Graph()
    bind_namespaces(graph)
    base = f"{config.namespace}graph-{config.seed}/"
    roles = [URIRef(base + "role/" + name.lower()) for name in ROLE_NAMES]
    for role, name in zip(roles, ROLE_NAMES):
        graph.add((role, RDF.type, ORG.Role))
        graph.add((role, RDFS.label, Literal(name)))
    entities = len(roles)

    def entity(uri, kind, label):
        nonlocal entities
        entities += 1
        if entities > config.max_entities:
            raise ConfigError("Graph exceeds max_entities; reduce counts or explicitly raise the limit")
        graph.add((uri, RDF.type, kind))
        graph.add((uri, RDFS.label, Literal(label)))

    for org_index in range(1, config.num_organizations + 1):
        org_key = f"org-{org_index:06d}"
        organization = URIRef(base + org_key)
        entity(organization, ORG.FormalOrganization, f"Organization {org_index:06d}")
        parents, leaders = {}, {}
        assignment_rng = rng_for(config.seed, org_key + "/assignments")
        report_rng = rng_for(config.seed, org_key + "/reports")
        for spec in unit_layout(config, org_key):
            unit = URIRef(base + spec.key)
            parent = URIRef(base + spec.parent_key)
            entity(unit, ORG.OrganizationalUnit, f"Unit {spec.key}")
            parents[unit] = parent
            for subject, predicate, obj in ((unit, ORG.unitOf, parent), (parent, ORG.hasUnit, unit),
                                          (unit, ORG.subOrganizationOf, parent)):
                graph.add((subject, predicate, obj))
            # ORG has no requirement to materialize the transitive closure.
            candidates = []
            ancestor = parent
            for _ in range(config.reporting_ancestor_window):
                if ancestor in leaders:
                    candidates.append(leaders[ancestor])
                if ancestor not in parents:
                    break
                ancestor = parents[ancestor]
            for post_index in range(1, spec.posts + 1):
                post = URIRef(f"{unit}/post-{post_index:04d}")
                role_index = (min(spec.depth - 1, 2) if post_index == 1
                              else assignment_rng.randrange(len(roles)))
                name = ROLE_NAMES[role_index]
                entity(post, ORG.Post, f"{name} {spec.key} P{post_index:04d}")
                graph.add((post, ORG.postIn, unit))
                graph.add((unit, ORG.hasPost, post))
                graph.add((post, ORG.role, roles[role_index]))
                if post_index == 1:
                    leaders[unit] = post
                    if candidates:
                        graph.add((post, ORG.reportsTo, report_rng.choice(candidates)))
                else:
                    graph.add((post, ORG.reportsTo, leaders[unit]))
                for employee_index in range(1, config.employees_per_post + 1):
                    person = URIRef(f"{post}/person-{employee_index:04d}")
                    first = assignment_rng.choice(("Alex", "Sam", "Taylor", "Jordan", "Casey", "Robin"))
                    last = assignment_rng.choice(("Chen", "Patel", "Morgan", "Singh", "Ali", "Lee"))
                    label = f"{first} {last} ({spec.key} P{post_index:04d} E{employee_index:04d})"
                    entity(person, FOAF.Person, label)
                    graph.add((person, FOAF.name, Literal(label)))
                    graph.add((person, ORG.holds, post))
                    graph.add((post, ORG.heldBy, person))
                    graph.add((person, ORG.memberOf, unit))
    for extension in extensions:
        extension(graph, config)
    return graph
