"""Run from the repository after installation: python examples/query_example.py."""
import argparse
from pathlib import Path

from rdflib import Graph

parser = argparse.ArgumentParser()
parser.add_argument("graph", nargs="?", type=Path,
                    default=Path(__file__).parent / "generated/experiment_001/knowledge_graph.ttl")
args = parser.parse_args()
graph = Graph().parse(args.graph)
query = """
PREFIX org: <http://www.w3.org/ns/org#>
SELECT ?person ?post ?unit ?organization WHERE {
    ?person org:holds ?post .
    ?post org:postIn ?unit .
    ?unit org:subOrganizationOf+ ?organization .
    ?organization a org:FormalOrganization .
}
ORDER BY ?person
LIMIT 5
"""
for row in graph.query(query):
    print(" | ".join(str(value) for value in row))
