from rdflib import Graph, Namespace
from rdflib.namespace import FOAF, OWL, RDF, RDFS

ORG = Namespace("http://www.w3.org/ns/org#")
EX = Namespace("https://example.org/synthetic-org/")


def bind_namespaces(graph: Graph) -> None:
    for prefix, namespace in (("org", ORG), ("ex", EX), ("rdf", RDF),
                              ("rdfs", RDFS), ("owl", OWL), ("foaf", FOAF)):
        graph.bind(prefix, namespace)
