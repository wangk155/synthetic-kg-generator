import pytest

from kg_generator.config import EvaluationConfig, GeneratorConfig
from kg_generator.generator import generate_graph


@pytest.fixture
def settings():
    return GeneratorConfig(num_organizations=2, max_depth=3, branching_factor=2,
                           posts_per_unit=3, employees_per_post=2, seed=42)


@pytest.fixture
def graph(settings):
    return generate_graph(settings)


@pytest.fixture
def evaluation():
    return EvaluationConfig(questions_per_category=5)
