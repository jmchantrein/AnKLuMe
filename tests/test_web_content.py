"""Tests for scripts/web/content.py — unified content model."""

import textwrap
from pathlib import Path

import pytest

from scripts.web.content import (
    ContentBlock,
    ContentPage,
    ContentSection,
    load_guide_sections,
    load_lab,
)


class TestContentBlock:
    def test_defaults(self):
        block = ContentBlock(type="text", text="hello")
        assert block.clickable is False

    def test_command_clickable(self):
        block = ContentBlock(type="command", text="ls", clickable=True)
        assert block.clickable is True
        assert block.type == "command"

    def test_hint_type(self):
        block = ContentBlock(type="hint", text="try this")
        assert block.type == "hint"

    def test_validation_type(self):
        block = ContentBlock(type="validation", text="test -f x")
        assert block.type == "validation"


class TestContentPage:
    def test_defaults(self):
        page = ContentPage(id="p1", title={"en": "Test"})
        assert page.blocks == []
        assert page.validation is None
        assert page.hint is None

    def test_with_blocks(self):
        blocks = [ContentBlock(type="text", text="hello")]
        page = ContentPage(id="p1", title={"en": "T"}, blocks=blocks)
        assert len(page.blocks) == 1

    def test_with_validation_and_hint(self):
        page = ContentPage(
            id="p1", title={"en": "T"},
            validation="test -f x", hint="check the file",
        )
        assert page.validation == "test -f x"
        assert page.hint == "check the file"

    def test_mutable_default_blocks(self):
        """Each page gets its own block list."""
        p1 = ContentPage(id="p1", title={"en": "A"})
        p2 = ContentPage(id="p2", title={"en": "B"})
        p1.blocks.append(ContentBlock(type="text", text="x"))
        assert len(p2.blocks) == 0


class TestContentSection:
    def test_defaults(self):
        section = ContentSection(id="s1", title={"en": "S"})
        assert section.pages == []
        assert section.metadata == {}

    def test_with_metadata(self):
        section = ContentSection(
            id="s1", title={"en": "S"},
            metadata={"type": "lab", "difficulty": "beginner"},
        )
        assert section.metadata["type"] == "lab"

    def test_mutable_default_pages(self):
        s1 = ContentSection(id="s1", title={"en": "A"})
        s2 = ContentSection(id="s2", title={"en": "B"})
        s1.pages.append(ContentPage(id="p1", title={"en": "P"}))
        assert len(s2.pages) == 0


class TestLoadGuideSections:
    """Guide content is served via the web learn platform."""

    def test_returns_one_section(self):
        sections = load_guide_sections()
        assert len(sections) == 1

    def test_section_is_guide_type(self):
        sections = load_guide_sections()
        assert sections[0].id == "guide"
        assert sections[0].metadata["type"] == "guide"

    def test_guide_has_8_chapters(self):
        sections = load_guide_sections()
        assert len(sections[0].pages) == 8

    def test_guide_pages_have_ids(self):
        sections = load_guide_sections()
        for i, page in enumerate(sections[0].pages, 1):
            assert page.id == f"guide-{i}"

    def test_guide_pages_have_titles(self):
        sections = load_guide_sections()
        for page in sections[0].pages:
            assert "en" in page.title
            assert len(page.title["en"]) > 0

    def test_guide_pages_have_blocks(self):
        sections = load_guide_sections()
        for page in sections[0].pages:
            assert len(page.blocks) >= 1


class TestLoadLab:
    def test_load_real_lab(self):
        """Load lab 01 from the actual labs/ directory."""
        lab_dir = Path("labs/01-first-deploy")
        section = load_lab(lab_dir)
        assert section.id == "01-first-deploy"
        assert "en" in section.title
        assert section.title["en"] == "First Deployment"

    def test_real_lab_has_steps(self):
        section = load_lab(Path("labs/01-first-deploy"))
        assert len(section.pages) == 3

    def test_real_lab_step_ids(self):
        section = load_lab(Path("labs/01-first-deploy"))
        assert section.pages[0].id == "01-first-deploy-step-01"
        assert section.pages[1].id == "01-first-deploy-step-02"

    def test_real_lab_metadata(self):
        section = load_lab(Path("labs/01-first-deploy"))
        assert section.metadata["type"] == "lab"
        assert section.metadata["difficulty"] == "beginner"
        assert section.metadata["duration"] == "30m"

    def test_real_lab_has_validation(self):
        section = load_lab(Path("labs/01-first-deploy"))
        # Step 01 has validation
        assert section.pages[0].validation is not None

    def test_real_lab_has_hints(self):
        section = load_lab(Path("labs/01-first-deploy"))
        assert section.pages[0].hint is not None

    def test_real_lab_step_content_not_empty(self):
        section = load_lab(Path("labs/01-first-deploy"))
        for page in section.pages:
            text_blocks = [b for b in page.blocks if b.type == "text"]
            assert len(text_blocks) >= 1

    def test_missing_lab_dir(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="lab.yml not found"):
            load_lab(tmp_path / "nonexistent")

    def test_empty_lab_yml(self, tmp_path):
        (tmp_path / "lab.yml").write_text("---\ntitle: Empty\n")
        section = load_lab(tmp_path)
        assert section.pages == []
        assert section.title["en"] == "Empty"

    def test_lab_with_missing_step_file(self, tmp_path):
        lab_yml = textwrap.dedent("""\
            title: "Test Lab"
            description: "desc"
            difficulty: beginner
            duration: "10m"
            steps:
              - id: "01"
                title: "Step one"
                instruction_file: "steps/missing.md"
        """)
        (tmp_path / "lab.yml").write_text(lab_yml)
        section = load_lab(tmp_path)
        # Missing file -> empty text block
        assert section.pages[0].blocks[0].text == ""

    def test_lab_with_step_file(self, tmp_path):
        lab_yml = textwrap.dedent("""\
            title: "Test Lab"
            description: "Test"
            difficulty: intermediate
            duration: "20m"
            steps:
              - id: "01"
                title: "Do something"
                instruction_file: "steps/01.md"
                hint: "Try harder"
                validation: "test -f /tmp/done"
        """)
        (tmp_path / "lab.yml").write_text(lab_yml)
        steps_dir = tmp_path / "steps"
        steps_dir.mkdir()
        (steps_dir / "01.md").write_text("# Step 1\nDo this thing.")
        section = load_lab(tmp_path)
        assert len(section.pages) == 1
        page = section.pages[0]
        assert page.hint == "Try harder"
        assert page.validation == "test -f /tmp/done"
        assert "Step 1" in page.blocks[0].text
        # Validation block added
        assert any(b.type == "validation" for b in page.blocks)

    def test_all_five_labs_loadable(self):
        """All 5 labs in labs/ directory load without error."""
        labs_dir = Path("labs")
        for lab_dir in sorted(labs_dir.iterdir()):
            if lab_dir.is_dir() and (lab_dir / "lab.yml").exists():
                section = load_lab(lab_dir)
                assert len(section.pages) >= 1, f"{lab_dir.name} has no pages"
                assert section.metadata["type"] == "lab"
