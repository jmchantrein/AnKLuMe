"""Unified content model for guide and labs.

Bridges guide_chapters.py + guide_strings.py into a structured model
that the learning platform uses for rendering.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

# Ensure scripts/ is in sys.path for sibling imports
_scripts_dir = str(Path(__file__).resolve().parent.parent)
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


@dataclass
class ContentBlock:
    """A single block of content within a page."""

    type: str  # "text", "command", "hint", "validation"
    text: str
    clickable: bool = False


@dataclass
class ContentPage:
    """A page within a section (guide chapter or lab step)."""

    id: str  # "guide-1" or "lab-01-step-01"
    title: dict[str, str]  # {"en": "...", "fr": "..."}
    blocks: list[ContentBlock] = field(default_factory=list)
    validation: str | None = None
    hint: str | None = None


@dataclass
class ContentSection:
    """A section grouping multiple pages (guide or lab)."""

    id: str  # "guide" or "lab-01"
    title: dict[str, str]
    pages: list[ContentPage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


def load_guide_sections() -> list[ContentSection]:
    """Load the capability tour as a ContentSection.

    Bridges guide_chapters.py and guide_strings.py into the
    unified content model.
    """
    from guide_chapters import CHAPTERS
    from guide_strings import STRINGS

    pages = []
    for ch in CHAPTERS:
        cid = ch["id"]
        # Store blocks per language for rendering
        blocks_by_lang: dict[str, list[ContentBlock]] = {}
        for lang_key in ("en", "fr"):
            lang_blocks: list[ContentBlock] = []
            explain = STRINGS[lang_key].get(f"ch{cid}_explain", "")
            if explain:
                lang_blocks.append(ContentBlock(type="text", text=explain))
            if ch["safe_for_web"]:
                for cmd in ch["demo_commands"]:
                    lang_blocks.append(ContentBlock(
                        type="command", text=cmd, clickable=True,
                    ))
            recap = STRINGS[lang_key].get(f"ch{cid}_recap", "")
            if recap:
                lang_blocks.append(ContentBlock(type="text", text=recap))
            blocks_by_lang[lang_key] = lang_blocks

        page = ContentPage(
            id=f"guide-{cid}",
            title=ch["title"],
            blocks=blocks_by_lang["en"],  # default
        )
        page._blocks_by_lang = blocks_by_lang  # type: ignore[attr-defined]
        pages.append(page)

    return [ContentSection(
        id="guide",
        title={"en": "Getting Started with anklume", "fr": "Prise en main d'anklume"},
        pages=pages,
        metadata={"type": "guide", "total_chapters": len(pages)},
    )]


def load_lab(lab_dir: Path) -> ContentSection:
    """Load a lab directory into a ContentSection.

    Reads lab.yml + steps/*.md and converts to the unified model.
    """
    import yaml

    lab_yml = lab_dir / "lab.yml"
    if not lab_yml.exists():
        msg = f"lab.yml not found in {lab_dir}"
        raise FileNotFoundError(msg)

    with open(lab_yml) as f:
        meta = yaml.safe_load(f)

    pages = []
    for step in meta.get("steps", []):
        step_file = lab_dir / step.get("instruction_file", "")
        text = step_file.read_text() if step_file.exists() else ""
        blocks = [ContentBlock(type="text", text=text)]

        if step.get("validation"):
            blocks.append(ContentBlock(
                type="validation", text=step["validation"],
            ))

        pages.append(ContentPage(
            id=f"{lab_dir.name}-step-{step['id']}",
            title={"en": step["title"], "fr": step["title"]},
            blocks=blocks,
            validation=step.get("validation"),
            hint=step.get("hint"),
        ))

    return ContentSection(
        id=lab_dir.name,
        title={"en": meta["title"], "fr": meta["title"]},
        pages=pages,
        metadata={
            "type": "lab",
            "difficulty": meta.get("difficulty", "beginner"),
            "duration": meta.get("duration", ""),
            "description": meta.get("description", ""),
        },
    )
