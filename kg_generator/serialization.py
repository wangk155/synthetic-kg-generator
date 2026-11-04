"""Atomic experiment directories, validated round trips and content hashes."""
import hashlib
import json
import os
import platform
import shutil
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import yaml
import rdflib
from rdflib import Graph

from . import __version__
from .competency_questions import generate_questions
from .config import Config, FORMATS
from .generator import generate_graph
from .ground_truth import verify_questions
from .validation import validate_graph


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def graph_digest(graph):
    """Graphs contain named nodes only; sorted N-Triples is a canonical content digest."""
    digest = hashlib.sha256()
    for line in sorted(f"{s.n3()} {p.n3()} {o.n3()} .\n" for s, p, o in graph):
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def save_experiment(config: Config, destination: Path, *, frozen_questions=None, extra_metadata=None):
    """Never overwrite existing data. A failed experiment leaves no partial directory."""
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing experiment: {destination}")
    graph = generate_graph(config.generator)
    metadata = validate_graph(graph, config.generator)
    if frozen_questions is None:
        questions, truth, coverage = generate_questions(graph, config.evaluation, config.generator.seed)
    else:
        questions, truth = frozen_questions
        coverage = {"enabled": True, "frozen_baseline_questions": True, "count": len(questions)}
    verify_questions(graph, questions, truth)
    metadata.update({"seed": config.generator.seed, "generator_version": __version__,
                     "runtime_versions": {"python": platform.python_version(), "rdflib": rdflib.__version__,
                                          "pyyaml": yaml.__version__},
                     "generated_at": datetime.now(timezone.utc).isoformat(),
                     "graph_sha256": graph_digest(graph), "question_coverage": coverage,
                     "ground_truth_verified": True, "ground_truth_saved": config.evaluation.generate_ground_truth,
                     "ontology_profile": "W3C ORG asserted instance forest; schema kept separate",
                     "membership_inference": "benchmark rule; no general OWL entailment claim"})
    if extra_metadata:
        metadata.update(extra_metadata)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".kg-staging-", dir=destination.parent))
    try:
        rdf_format, extension = FORMATS[config.output.format]
        graph_path = staging / f"knowledge_graph.{extension}"
        # RDFLib writes directly to a file; no second full serialized string.
        graph.serialize(destination=graph_path, format=rdf_format, encoding="utf-8")
        # Round-trip checking is available via the verify command; do not retain a
        # second RDF graph in memory during normal large-dataset generation.
        if config.evaluation.generate_competency_questions or frozen_questions is not None:
            write_json(staging / "competency_questions.json", questions)
            if config.evaluation.generate_ground_truth:
                write_json(staging / "ground_truth.json", truth)
        metadata["questions_sha256"] = hashlib.sha256(
            json.dumps(questions, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        write_json(staging / "metadata.json", metadata)
        (staging / "config.yaml").write_text(yaml.safe_dump(config.to_dict(), sort_keys=False), encoding="utf-8")
        os.rename(staging, destination)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return metadata


def run_generation(config: Config):
    destinations = [Path(config.output.directory) / f"experiment_{i + 1:03d}"
                    for i in range(config.generator.num_graphs)]
    for destination in destinations:
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite existing experiment: {destination}")
    results = []
    for index, destination in enumerate(destinations):
        effective = replace(config, generator=replace(config.generator, seed=config.generator.seed + index, num_graphs=1))
        results.append((destination, save_experiment(effective, destination,
                        extra_metadata={"batch_graph_index": index + 1,
                                        "batch_base_seed": config.generator.seed})))
    return results


def verify_experiment(directory):
    from .config import load_config
    directory = Path(directory)
    config = load_config(directory / "config.yaml")
    rdf_format, extension = FORMATS[config.output.format]
    graph = Graph().parse(directory / f"knowledge_graph.{extension}", format=rdf_format)
    result = validate_graph(graph, config.generator)
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    for key, value in result.items():
        if metadata.get(key) != value:
            raise ValueError(f"Saved metadata mismatch: {key}")
    if graph_digest(graph) != metadata["graph_sha256"]:
        raise ValueError("Saved graph content hash mismatch")
    questions_expected = config.evaluation.generate_competency_questions
    question_path = directory / "competency_questions.json"
    if questions_expected and not question_path.exists():
        raise ValueError("Saved competency questions file is missing")
    if question_path.exists():
        questions = json.loads((directory / "competency_questions.json").read_text(encoding="utf-8"))
        expected_hash = hashlib.sha256(json.dumps(questions, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        if metadata["questions_sha256"] != expected_hash:
            raise ValueError("Saved question content hash mismatch")
        if not (directory / "ground_truth.json").exists():
            raise ValueError("Ground truth was not saved; full saved-dataset verification requires generate_ground_truth: true")
        truth = json.loads((directory / "ground_truth.json").read_text(encoding="utf-8"))
        verify_questions(graph, questions, truth)
    return result
