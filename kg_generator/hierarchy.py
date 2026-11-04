"""Deterministic layout streams: organization-local randomness enables nesting."""
import hashlib
import random
from collections import deque
from dataclasses import dataclass

from .config import GeneratorConfig, ConfigError

ROLE_NAMES = ("Director", "Manager", "Supervisor", "Analyst", "Engineer")


def rng_for(seed: int, key: str) -> random.Random:
    digest = hashlib.sha256(f"synthetic-org-v1|{seed}|{key}".encode()).digest()
    return random.Random(int.from_bytes(digest, "big"))


@dataclass(frozen=True)
class UnitSpec:
    key: str
    parent_key: str
    depth: int
    posts: int


def unit_layout(config: GeneratorConfig, org_key: str):
    rng = rng_for(config.seed, org_key + "/layout")
    queue = deque([(org_key, 0)])
    emitted = 0
    while queue:
        parent, depth = queue.popleft()
        if depth >= config.max_depth:
            continue
        children = (rng.randint(*config.branching_factor_range)
                    if config.branching_factor_range else config.branching_factor)
        for index in range(1, children + 1):
            emitted += 1
            if emitted > config.max_entities:
                raise ConfigError("Layout exceeds max_entities; reduce depth/branching or raise the limit")
            key = f"{parent}/u{index:04d}"
            posts = (rng.randint(*config.posts_per_unit_range)
                     if config.posts_per_unit_range else config.posts_per_unit)
            yield UnitSpec(key, parent, depth + 1, posts)
            queue.append((key, depth + 1))


def chain(node, parent):
    """Strict ancestors, closest first. Reject cycles even on external RDF."""
    seen = {node}
    result = []
    while node in parent:
        node = parent[node]
        if node in seen:
            raise ValueError("Cycle in hierarchy")
        seen.add(node)
        result.append(node)
    return result


def depths(parent, nodes):
    """Memoized forest depths in O(V+E), without recursion."""
    result = {}
    for start in nodes:
        path, seen = [], set()
        current = start
        while current not in result:
            if current in seen:
                raise ValueError("Cycle in hierarchy")
            seen.add(current)
            path.append(current)
            if current not in parent:
                result[current] = 0
                break
            current = parent[current]
        for node in reversed(path):
            if node not in result:
                result[node] = result[parent[node]] + 1
    return result
