Feature: Learning platform
  The unified learning platform serves guide content with a split-pane
  terminal interface. Tests cover theme, content model, HTML helpers,
  PTY management, and platform server.

  # ── Theme module ──────────────────────────────────────────

  Scenario: Web theme module is importable
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS; assert chr(58) + chr(114) + chr(111) + chr(111) + chr(116) in BASE_CSS'"
    Then exit code is 0

  Scenario: Theme has all CSS constants
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import BASE_CSS, DASHBOARD_CSS, GUIDE_CSS, TERMINAL_CSS; assert all(len(c) > 50 for c in [BASE_CSS, DASHBOARD_CSS, GUIDE_CSS, TERMINAL_CSS])'"
    Then exit code is 0

  Scenario: Trust CSS returns colors for all trust levels
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; results = [trust_css(l) for l in ["admin","trusted","semi-trusted","untrusted","disposable"]]; assert all("border" in r and "bg" in r for r in results)'"
    Then exit code is 0

  Scenario: Trust CSS returns fallback for unknown level
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.theme import trust_css; c = trust_css("unknown"); assert c["border"] == "#30363d"'"
    Then exit code is 0

  # ── Content model ─────────────────────────────────────────

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

  Scenario: Content dataclasses have correct defaults
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.content import ContentBlock, ContentPage; b = ContentBlock(type="text", text="x"); p = ContentPage(id="p", title={"en":"T"}); assert not b.clickable and p.blocks == [] and p.validation is None'"
    Then exit code is 0

  Scenario: Load lab from real directory
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; s = load_lab(Path("labs/01-first-deploy")); assert s.title["en"] == "First Deployment" and len(s.pages) == 3'"
    Then exit code is 0

  Scenario: All five labs are loadable
    Given "python3" is available
    When I run "python3 -c 'from pathlib import Path; from scripts.web.content import load_lab; [load_lab(d) for d in sorted(Path("labs").iterdir()) if d.is_dir() and (d / "lab.yml").exists()]'"
    Then exit code is 0

  # ── HTML helpers ──────────────────────────────────────────

  Scenario: HTML helpers produce valid markup
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("T", "<p>ok</p>"); assert "DOCTYPE" in h and "</html>" in h'"
    Then exit code is 0

  Scenario: Command blocks support clickable mode
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import command_block; h = command_block("ls", clickable=True); assert "runCmd" in h and "run-btn" in h'"
    Then exit code is 0

  Scenario: Non-clickable command shows pre tag
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import command_block; h = command_block("ls"); assert "<pre" in h and "runCmd" not in h'"
    Then exit code is 0

  Scenario: Card escapes HTML content
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import card; h = card("T", "<script>xss</script>"); assert "<script>" not in h and "&lt;script&gt;" in h'"
    Then exit code is 0

  Scenario: Markdown renderer handles headings
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("# Hello"); assert "<h1>Hello</h1>" in h'"
    Then exit code is 0

  Scenario: Markdown renderer handles code blocks
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("```\ncode\n```"); assert "<pre" in h and "code" in h'"
    Then exit code is 0

  Scenario: Nav bar renders links
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import nav_bar; h = nav_bar([("Home","/"),("Guide","/guide")]); assert "href" in h and "Home" in h'"
    Then exit code is 0

  # ── PTY manager ───────────────────────────────────────────

  Scenario: PTY session creates valid process
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtySession; s = PtySession(cmd=["/bin/echo","hi"]); assert s.fd >= 0 and s.pid > 0; s.close()'"
    Then exit code is 0

  Scenario: PTY manager enforces max sessions
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.pty_manager import PtyManager; m = PtyManager(max_sessions=1); m.create("a"); failed = False; exec("try:\n m.create(chr(98))\nexcept RuntimeError:\n failed = True"); m.close_all(); assert failed'"
    Then exit code is 0

  # ── Platform server ──────────────────────────────────────

  Scenario: Platform server module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/platform_server.py"
    Then exit code is 0

  Scenario: WebSocket terminal module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/web/ws_terminal.py"
    Then exit code is 0

  Scenario: PTY manager module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/web/pty_manager.py"
    Then exit code is 0

  # ── CLI learn module ──────────────────────────────────────

  Scenario: Learn CLI module has valid syntax
    Given "python3" is available
    When I run "python3 -m py_compile scripts/cli/learn.py"
    Then exit code is 0

  # ── Shell script ──────────────────────────────────────────

  Scenario: learn-setup.sh has valid bash syntax
    Given "bash" is available
    When I run "bash -n scripts/learn-setup.sh"
    Then exit code is 0

  Scenario: learn-setup.sh passes shellcheck
    Given "shellcheck" is available
    When I run "shellcheck -S warning scripts/learn-setup.sh"
    Then exit code is 0
