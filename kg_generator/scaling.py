"""Exact core triple estimates and nested scaling by adding whole organizations."""
from dataclasses import replace
from pathlib import Path

from .competency_questions import generate_questions
from .config import Config, ConfigError, GeneratorConfig, integer
from .generator import generate_graph
from .hierarchy import unit_layout
from .serialization import save_experiment, write_json


def organization_size(config, org_index):
    key = f"org-{org_index:06d}"
    # root: type + label; roles are shared and counted separately.
    triples, entities, units, posts, people, reporting = 2, 1, 0, 0, 0, 0
    parents, occupied = {}, set()
    for spec in unit_layout(config, key):
        units += 1
        parents[spec.key] = spec.parent_key
        ancestor = spec.parent_key
        has_supervisor = False
        for _ in range(config.reporting_ancestor_window):
            has_supervisor |= ancestor in occupied
            if ancestor not in parents:
                break
            ancestor = parents[ancestor]
        count = spec.posts
        if count:
            reporting += count - 1 + int(has_supervisor)
            occupied.add(spec.key)
        posts += count
        people += count * config.employees_per_post
    triples += units * 5 + posts * 5 + people * 6 + reporting
    entities += units + posts + people
    return {"num_triples": triples, "num_entities": entities,
            "num_organizational_units": units, "num_posts": posts, "num_individuals": people}


def estimate(config: GeneratorConfig):
    totals = {"num_triples": 10, "num_entities": 5, "num_organizational_units": 0,
              "num_posts": 0, "num_individuals": 0}
    for index in range(1, config.num_organizations + 1):
        counts = organization_size(config, index)
        for key, value in counts.items():
            totals[key] += value
        if totals["num_entities"] > config.max_entities:
            raise ConfigError("Estimate exceeds max_entities")
    return {**totals, "num_organizations": config.num_organizations,
            "estimate_kind": "exact for the core generator; excludes extension modules"}


def scaling_plan(config: GeneratorConfig, targets):
    if not targets:
        raise ConfigError("Provide at least one target triple count")
    for target in targets:
        integer("target triple count", target, 1)
    targets = sorted(set(targets))
    triples, entities, organizations = 10, 5, 0
    plan = []
    for target in targets:
        while organizations < config.num_organizations or triples < target:
            organizations += 1
            counts = organization_size(config, organizations)
            triples += counts["num_triples"]
            entities += counts["num_entities"]
            if entities > config.max_entities:
                raise ConfigError(f"Target {target} exceeds max_entities; raise the limit explicitly")
        plan.append({"target_triples": target, "num_organizations": organizations,
                     "estimated_triples": triples, "overshoot_triples": triples - target})
    return plan


def run_scaling(config: Config, targets, *, freeze_questions: bool = True):
    if config.generator.num_graphs != 1:
        raise ConfigError("scale requires num_graphs: 1; use generate for independent graph batches")
    plan = scaling_plan(config.generator, targets)
    root = Path(config.output.directory)
    destinations = [root / f"scale_{i + 1:03d}" for i in range(len(plan))]
    for destination in [root / "scaling_manifest.json", *destinations]:
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite existing output: {destination}")
    frozen, baseline_coverage = None, None
    if freeze_questions and config.evaluation.generate_competency_questions:
        baseline_config = replace(config.generator, num_organizations=plan[0]["num_organizations"])
        baseline = generate_graph(baseline_config)
        questions, truth, baseline_coverage = generate_questions(baseline, config.evaluation, baseline_config.seed)
        frozen = (questions, truth)
        del baseline
    results = []
    for entry, destination in zip(plan, destinations):
        effective = replace(config, generator=replace(config.generator, num_organizations=entry["num_organizations"]))
        extra = {"scaling": {**entry, "nested": True, "frozen_questions": frozen is not None,
                             "growth_variable": "num_organizations"}}
        if baseline_coverage is not None:
            extra["question_coverage"] = {**baseline_coverage, "frozen_baseline_questions": True}
        metadata = save_experiment(effective, destination, frozen_questions=frozen,
                                   extra_metadata=extra)
        shortfalls = {category: coverage["shortfall"] for category, coverage in
                      metadata["question_coverage"].get("categories", {}).items() if coverage["shortfall"]}
        results.append({**entry, "actual_triples": metadata["num_triples"], "directory": destination.name,
                        "question_shortfalls": shortfalls})
    write_json(root / "scaling_manifest.json", {
        "generator_seed": config.generator.seed, "nested": True,
        "frozen_baseline_questions": frozen is not None,
        "preserved": ["seed", "namespace", "max_depth", "branching_factor", "branching_factor_range",
                      "posts_per_unit", "posts_per_unit_range", "employees_per_post", "reporting_ancestor_window"],
        "growth": "Whole independent organizations are added; all earlier triples remain unchanged",
        "datasets": results,
    })
    return results
