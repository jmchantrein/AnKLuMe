"""Tests for example infra.yml files."""
from pathlib import Path

import pytest
from generate import load_infra, validate

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def discover_examples():
    """Find all example infra.yml files."""
    return sorted(EXAMPLES_DIR.glob("*/infra.yml"))


@pytest.mark.parametrize(
    "example_path",
    discover_examples(),
    ids=lambda p: p.parent.name,
)
class TestExampleValid:
    def test_validates(self, example_path):
        """Each example infra.yml must pass PSOT validation."""
        infra = load_infra(str(example_path))
        errors = validate(infra)
        assert not errors, f"Validation errors in {example_path}:\n" + "\n".join(errors)

    def test_has_required_keys(self, example_path):
        """Each example must have project_name, global, and domains."""
        infra = load_infra(str(example_path))
        for key in ("project_name", "global", "domains"):
            assert key in infra, f"Missing key '{key}' in {example_path}"

    def test_has_readme(self, example_path):
        """Each example directory must contain a README.md."""
        readme = example_path.parent / "README.md"
        assert readme.exists(), f"Missing README.md in {example_path.parent}"


def test_at_least_six_examples():
    """The examples directory must contain at least 6 examples."""
    examples = discover_examples()
    assert len(examples) >= 6, f"Expected >= 6 examples, found {len(examples)}"
