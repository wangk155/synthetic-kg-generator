"""Strict, serializable configuration; no implicit type coercion."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

FORMATS = {"turtle": ("turtle", "ttl"), "rdfxml": ("xml", "rdf"),
           "nt": ("nt", "nt"), "json-ld": ("json-ld", "jsonld")}
FORMAT_ALIASES = {"ttl": "turtle", "xml": "rdfxml", "rdf/xml": "rdfxml",
                  "rdf-xml": "rdfxml", "n-triples": "nt", "jsonld": "json-ld"}


class ConfigError(ValueError):
    pass


def integer(name, value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ConfigError(f"{name} must be an integer >= {minimum}; got {value!r}")


@dataclass(frozen=True)
class GeneratorConfig:
    num_organizations: int = 2
    max_depth: int = 3
    branching_factor: int = 2
    posts_per_unit: int = 3
    employees_per_post: int = 1
    seed: int = 42
    num_graphs: int = 1
    branching_factor_range: tuple[int, int] | None = None
    posts_per_unit_range: tuple[int, int] | None = None
    reporting_ancestor_window: int = 1
    namespace: str = "https://example.org/synthetic-org/"
    max_entities: int = 2_000_000

    def __post_init__(self):
        for name in ("num_organizations", "num_graphs", "reporting_ancestor_window", "max_entities"):
            integer(name, getattr(self, name), 1)
        for name in ("max_depth", "branching_factor", "posts_per_unit", "employees_per_post", "seed"):
            integer(name, getattr(self, name))
        # Bounded depth protects recursive RDF serializers and accidental explosions.
        if self.max_depth > 100:
            raise ConfigError("max_depth must be <= 100")
        for name in ("branching_factor_range", "posts_per_unit_range"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, (tuple, list)) or len(value) != 2:
                    raise ConfigError(f"{name} must be [minimum, maximum]")
                for item in value:
                    integer(name, item)
                if value[0] > value[1]:
                    raise ConfigError(f"{name}: minimum exceeds maximum")
                object.__setattr__(self, name, tuple(value))
        if not isinstance(self.namespace, str):
            raise ConfigError("namespace must be an absolute HTTP(S) URI ending in / or #")
        parsed = urlparse(self.namespace)
        if (parsed.scheme not in ("http", "https") or not parsed.netloc
                or not self.namespace.endswith(("/", "#"))
                or any(c.isspace() or c in '<>\"{}|\\^`' for c in self.namespace)):
            raise ConfigError("namespace must be an absolute HTTP(S) URI ending in / or #")


@dataclass(frozen=True)
class OutputConfig:
    format: str = "turtle"
    directory: str = "output"

    def __post_init__(self):
        if not isinstance(self.format, str):
            raise ConfigError("output.format must be a string")
        fmt = FORMAT_ALIASES.get(self.format.lower(), self.format.lower())
        if fmt not in FORMATS:
            raise ConfigError(f"output.format must be one of {list(FORMATS)}")
        object.__setattr__(self, "format", fmt)
        if not isinstance(self.directory, str) or not self.directory.strip():
            raise ConfigError("output.directory must be a nonempty path string")


@dataclass(frozen=True)
class EvaluationConfig:
    generate_competency_questions: bool = True
    questions_per_category: int = 20
    generate_ground_truth: bool = True
    shortage_policy: str = "error"

    def __post_init__(self):
        integer("questions_per_category", self.questions_per_category)
        for name in ("generate_competency_questions", "generate_ground_truth"):
            if type(getattr(self, name)) is not bool:
                raise ConfigError(f"{name} must be true or false")
        if self.shortage_policy not in ("error", "available"):
            raise ConfigError("shortage_policy must be error or available")


@dataclass(frozen=True)
class Config:
    generator: GeneratorConfig = field(default_factory=GeneratorConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    evaluation: EvaluationConfig = field(default_factory=EvaluationConfig)

    def to_dict(self):
        result = asdict(self)
        for key in ("branching_factor_range", "posts_per_unit_range"):
            value = result["generator"][key]
            if value is not None:
                result["generator"][key] = list(value)
        return result


def from_dict(data: dict) -> Config:
    if not isinstance(data, dict):
        raise ConfigError("Configuration must be a YAML mapping")
    if set(data) - {"generator", "output", "evaluation"}:
        raise ConfigError(f"Unknown sections: {sorted(set(data) - {'generator', 'output', 'evaluation'})}")
    try:
        return Config(**{name: cls(**data.get(name, {})) for name, cls in
                         (("generator", GeneratorConfig), ("output", OutputConfig),
                          ("evaluation", EvaluationConfig))})
    except TypeError as exc:
        raise ConfigError(f"Invalid configuration key or section: {exc}") from exc


def load_config(path: str | Path) -> Config:
    try:
        with open(path, encoding="utf-8") as handle:
            return from_dict(yaml.safe_load(handle))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML: {exc}") from exc
