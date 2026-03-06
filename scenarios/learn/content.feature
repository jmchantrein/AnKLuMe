@requires.guide_imports
Feature: Content model
  Unified content model for guide chapters and educational labs.
  Guide content is served via the web learn platform.

  # ── Guide sections ─────────────────────────────────────

  Scenario: Guide sections returns 8 chapters
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); assert len(s) == 1 and len(s[0].pages) == 8'"
    Then exit code is 0

  Scenario: Guide pages have English titles
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import load_guide_sections; s = load_guide_sections(); assert all(chr(101)+chr(110) in p.title for p in s[0].pages)'"
    Then exit code is 0

  # ── Lab loading ─────────────────────────────────────────

  Scenario: Load lab from real directory
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; s = load_lab(Path("labs/01-first-deploy")); assert s.title["en"] == "First Deployment" and len(s.pages) == 3'"
    Then exit code is 0

  Scenario: Load lab from nonexistent directory raises error
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; exec("try:\n load_lab(Path(\"no-such-lab\"))\n ok = False\nexcept FileNotFoundError:\n ok = True"); assert ok'"
    Then exit code is 0
