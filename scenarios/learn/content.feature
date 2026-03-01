Feature: Content model
  Unified content model for guide chapters and educational labs.
  Bridges guide_chapters.py + guide_strings.py into structured
  ContentSection/ContentPage/ContentBlock dataclasses.

  # ── Guide sections ──────────────────────────────────────

  Scenario: Content model loads all guide chapters
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); assert len(s[0].pages) == 8'"
    Then exit code is 0

  Scenario: Guide pages have sequential IDs
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); ids = [p.id for p in s[0].pages]; assert ids == [f"guide-{i}" for i in range(1,9)]'"
    Then exit code is 0

  Scenario: Guide has bilingual titles
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); assert all("en" in p.title and "fr" in p.title for p in s[0].pages)'"
    Then exit code is 0

  Scenario: Content section has metadata
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); m = s[0].metadata; assert m["type"] == "guide" and m["total_chapters"] == 8'"
    Then exit code is 0

  Scenario: Guide section has bilingual titles
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); assert "en" in s[0].title and "fr" in s[0].title'"
    Then exit code is 0

  Scenario: Guide chapter 1 has clickable commands
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); p = s[0].pages[0]; cmds = [b for b in p.blocks if b.type == "command"]; assert len(cmds) > 0 and all(b.clickable for b in cmds)'"
    Then exit code is 0

  Scenario: Guide chapters 3 and 4 have no commands (not safe for web)
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); p3 = s[0].pages[2]; p4 = s[0].pages[3]; assert not any(b.type == "command" for b in p3.blocks) and not any(b.type == "command" for b in p4.blocks)'"
    Then exit code is 0

  Scenario: Guide chapter has text blocks
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); p = s[0].pages[0]; texts = [b for b in p.blocks if b.type == "text"]; assert len(texts) > 0'"
    Then exit code is 0

  # ── Dataclass defaults ──────────────────────────────────

  Scenario: Content dataclasses have correct defaults
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import ContentBlock, ContentPage; b = ContentBlock(type="text", text="x"); p = ContentPage(id="p", title={"en":"T"}); assert not b.clickable and p.blocks == [] and p.validation is None'"
    Then exit code is 0

  Scenario: ContentBlock mutable defaults are independent
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import ContentPage; a = ContentPage(id="a", title={}); b = ContentPage(id="b", title={}); a.blocks.append("x"); assert b.blocks == []'"
    Then exit code is 0

  # ── Lab loading ─────────────────────────────────────────

  Scenario: Load lab from real directory
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; s = load_lab(Path("labs/01-first-deploy")); assert s.title["en"] == "First Deployment" and len(s.pages) == 3'"
    Then exit code is 0

  Scenario: All five labs are loadable
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; [load_lab(d) for d in sorted(Path("labs").iterdir()) if d.is_dir() and (d / "lab.yml").exists()]'"
    Then exit code is 0

  Scenario: Lab metadata includes difficulty and duration
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; s = load_lab(Path("labs/01-first-deploy")); assert s.metadata["type"] == "lab" and "difficulty" in s.metadata and "duration" in s.metadata'"
    Then exit code is 0

  Scenario: Lab step with validation creates validation block
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; s = load_lab(Path("labs/01-first-deploy")); found = any(p.validation for p in s.pages); assert found'"
    Then exit code is 0

  Scenario: Load lab from nonexistent directory raises error
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; exec("try:\n load_lab(Path(\"no-such-lab\"))\n ok = False\nexcept FileNotFoundError:\n ok = True"); assert ok'"
    Then exit code is 0
