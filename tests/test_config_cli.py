from dataclasses import replace
import json

import pytest

from kg_generator.cli import main
from kg_generator.config import Config, ConfigError, GeneratorConfig, OutputConfig, from_dict, load_config


@pytest.mark.parametrize("data", [
    {"generator": {"num_organizations": -1}}, {"generator": {"max_depth": 1.5}},
    {"generator": {"employees_per_post": True}}, {"generator": {"branching_factor_range": [3, 1]}},
    {"generator": {"posts_per_unit_range": [1]}}, {"generator": {"namespace": "relative"}},
    {"generator": {"namespace": "https://test.example/bad uri/"}},
    {"generator": {"max_depth": 101}}, {"generator": {"unknown": 1}},
    {"unknown": {}}, {"output": {"format": "csv"}}, {"output": {"directory": ""}},
    {"evaluation": {"generate_ground_truth": "true"}}, {"evaluation": {"shortage_policy": "ignore"}},
    {"evaluation": {"questions_per_category": -1}}, {"generator": None},
])
def test_invalid_configuration(data):
    with pytest.raises(ConfigError):
        from_dict(data)


def test_yaml_roundtrip(tmp_path):
    import yaml
    path = tmp_path / "config.yaml"
    config = Config(generator=GeneratorConfig(branching_factor_range=(1, 2)))
    path.write_text(yaml.safe_dump(config.to_dict()))
    assert load_config(path) == config


def test_cli_overrides_and_verify(tmp_path, capsys):
    assert main(["generate", "--config", "examples/small.yaml", "--seed", "99",
                 "--output-directory", str(tmp_path), "--output-format", "nt"]) == 0
    assert main(["verify", str(tmp_path / "experiment_001")]) == 0
    assert '"verified": true' in capsys.readouterr().out
    assert main(["estimate", "--config", "examples/small.yaml"]) == 0
    assert '"estimate_kind"' in capsys.readouterr().out


def test_cli_error(capsys):
    assert main(["generate", "--num-organizations", "-1"]) == 2
    assert "num_organizations" in capsys.readouterr().err


def test_limit_fails_before_serializing(tmp_path):
    assert main(["generate", "--max-entities", "10", "--output-directory", str(tmp_path)]) == 2
    assert not (tmp_path / "experiment_001").exists()


def test_shortage_does_not_leave_partial_output(tmp_path):
    assert main(["generate", "--max-depth", "0", "--output-directory", str(tmp_path)]) == 2
    assert not (tmp_path / "experiment_001").exists()


def test_saved_truth_corruption_detected(tmp_path):
    assert main(["generate", "--config", "examples/small.yaml", "--output-directory", str(tmp_path)]) == 0
    path = tmp_path / "experiment_001" / "ground_truth.json"
    truth = json.loads(path.read_text())
    next(iter(truth.values()))["answer"] = ["incorrect"]
    path.write_text(json.dumps(truth))
    assert main(["verify", str(path.parent)]) == 2


def test_missing_saved_questions_detected(tmp_path):
    assert main(["generate", "--config", "examples/small.yaml", "--output-directory", str(tmp_path)]) == 0
    folder = tmp_path / "experiment_001"
    (folder / "competency_questions.json").unlink()
    assert main(["verify", str(folder)]) == 2
