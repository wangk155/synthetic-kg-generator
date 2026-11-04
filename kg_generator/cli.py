"""Command line interface with explicit overrides and useful validation errors."""
import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from . import __version__
from .config import Config, ConfigError, load_config
from .scaling import estimate, run_scaling
from .serialization import run_generation, verify_experiment


def parser():
    root = argparse.ArgumentParser(description="Reproducible synthetic W3C ORG reasoning datasets")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("generate", "estimate", "scale"):
        command = commands.add_parser(name)
        command.add_argument("--config", type=Path)
        for field in ("num_organizations", "max_depth", "branching_factor", "posts_per_unit",
                      "employees_per_post", "seed", "num_graphs", "reporting_ancestor_window", "max_entities"):
            command.add_argument("--" + field.replace("_", "-"), type=int)
        command.add_argument("--branching-factor-range", type=int, nargs=2, metavar=("MIN", "MAX"))
        command.add_argument("--posts-per-unit-range", type=int, nargs=2, metavar=("MIN", "MAX"))
        command.add_argument("--namespace")
        command.add_argument("--output-format")
        command.add_argument("--output-directory")
        command.add_argument("--questions-per-category", type=int)
        command.add_argument("--shortage-policy", choices=("error", "available"))
        command.add_argument("--generate-competency-questions", action=argparse.BooleanOptionalAction, default=None)
        command.add_argument("--generate-ground-truth", action=argparse.BooleanOptionalAction, default=None)
        if name == "scale":
            command.add_argument("--targets", type=int, nargs="+", required=True)
            command.add_argument("--freeze-questions", action=argparse.BooleanOptionalAction, default=True)
    verify = commands.add_parser("verify")
    verify.add_argument("directory", type=Path)
    return root


def effective_config(args):
    config = load_config(args.config) if args.config else Config()
    generator_overrides = {name: getattr(args, name) for name in config.generator.__dataclass_fields__
                           if getattr(args, name, None) is not None}
    # An exact count override clears its corresponding YAML range; an explicit
    # CLI range has precedence if both flags are supplied.
    for exact in ("branching_factor", "posts_per_unit"):
        if exact in generator_overrides and getattr(args, exact + "_range") is None:
            generator_overrides[exact + "_range"] = None
    output_overrides = {name: getattr(args, "output_" + name) for name in ("format", "directory")
                        if getattr(args, "output_" + name) is not None}
    evaluation_overrides = {name: getattr(args, name) for name in config.evaluation.__dataclass_fields__
                           if getattr(args, name, None) is not None}
    return replace(config, generator=replace(config.generator, **generator_overrides),
                   output=replace(config.output, **output_overrides),
                   evaluation=replace(config.evaluation, **evaluation_overrides))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_experiment(args.directory)
            print(json.dumps({"verified": True, **result}, indent=2))
            return 0
        config = effective_config(args)
        if args.command == "estimate":
            print(json.dumps(estimate(config.generator), indent=2))
        elif args.command == "scale":
            results = run_scaling(config, args.targets, freeze_questions=args.freeze_questions)
            print(json.dumps(results, indent=2))
            for result in results:
                for category, shortfall in result["question_shortfalls"].items():
                    print(f"Warning: {result['directory']} {category}: {shortfall} requested questions "
                          "unavailable (shortage_policy=available)", file=sys.stderr)
        else:
            for destination, metadata in run_generation(config):
                print(f"{destination}: {metadata['num_triples']} triples, "
                      f"{metadata['num_organizational_units']} units, {metadata['num_posts']} posts, "
                      f"{metadata['num_individuals']} people")
                for category, coverage in metadata["question_coverage"].get("categories", {}).items():
                    if coverage["shortfall"]:
                        print(f"Warning: {category}: requested {coverage['requested']}, "
                              f"generated {coverage['generated']} (shortage_policy=available)", file=sys.stderr)
        return 0
    except (ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
