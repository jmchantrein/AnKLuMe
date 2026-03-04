@requires.web_html
Feature: HTML helpers
  String builders for HTML pages, cards, command blocks, navigation,
  and minimal markdown rendering. No template engine.

  # ── page_wrap ───────────────────────────────────────────

  Scenario: HTML page_wrap produces valid HTML document
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("T", "<p>ok</p>"); assert "DOCTYPE" in h and "</html>" in h and "<meta charset" in h'"
    Then exit code is 0

  Scenario: page_wrap includes htmx CDN
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("T", "B"); assert "htmx.org" in h'"
    Then exit code is 0

  Scenario: page_wrap escapes title
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("<script>xss</script>", "B"); assert "<script>xss" not in h and "&lt;script&gt;" in h'"
    Then exit code is 0

  Scenario: page_wrap with xterm includes xterm.js CDN
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("T", "B", xterm=True); assert "xterm.js" in h and "addon-attach" in h and "addon-fit" in h'"
    Then exit code is 0

  Scenario: page_wrap without xterm has no xterm scripts
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("T", "B"); assert "xterm.js" not in h'"
    Then exit code is 0

  Scenario: page_wrap includes extra_css and extra_js
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import page_wrap; h = page_wrap("T", "B", extra_css=".custom{}", extra_js="<script>custom</script>"); assert ".custom{}" in h and "custom</script>" in h'"
    Then exit code is 0

  # ── command_block ───────────────────────────────────────

  Scenario: Command blocks support clickable mode
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import command_block; h = command_block("ls", clickable=True); assert "runCmd" in h and "run-btn" in h and "cmd-block" in h'"
    Then exit code is 0

  Scenario: Non-clickable command shows pre tag
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import command_block; h = command_block("ls"); assert "<pre" in h and "runCmd" not in h and "$ ls" in h'"
    Then exit code is 0

  Scenario: Command block escapes HTML in commands
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import command_block; h = command_block("echo <b>x</b>", clickable=True); assert "<b>" not in h and "&lt;b&gt;" in h'"
    Then exit code is 0

  # ── card ────────────────────────────────────────────────

  Scenario: Card escapes HTML content
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import card; h = card("T", "<script>xss</script>"); assert "<script>" not in h and "&lt;script&gt;" in h'"
    Then exit code is 0

  Scenario: Card escapes title
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import card; h = card("<b>T</b>", "C"); assert "<b>T" not in h and "&lt;b&gt;" in h'"
    Then exit code is 0

  Scenario: Card with border_color renders inline style
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import card; h = card("T", "C", border_color="#ff0000"); assert "border-left" in h and "#ff0000" in h'"
    Then exit code is 0

  Scenario: Card escapes border_color to prevent injection
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import card; h = card("T", "C", border_color="x" + chr(34) + "onclick=alert(1)"); assert "&quot;" in h or "&#x27;" in h or "onclick" not in h'"
    Then exit code is 0

  # ── nav_bar ─────────────────────────────────────────────

  Scenario: Nav bar renders links
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import nav_bar; h = nav_bar([("Home","/"),("Guide","/guide")]); assert "href" in h and "Home" in h and "Guide" in h and "class=\"nav\"" in h'"
    Then exit code is 0

  Scenario: Nav bar escapes labels
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import nav_bar; h = nav_bar([("<b>X</b>", "/")]); assert "<b>X" not in h and "&lt;b&gt;" in h'"
    Then exit code is 0

  Scenario: Nav bar handles empty list
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import nav_bar; h = nav_bar([]); assert "nav" in h'"
    Then exit code is 0

  # ── render_markdown ─────────────────────────────────────

  Scenario: Markdown renderer handles headings
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("# Hello"); assert "<h1>Hello</h1>" in h'"
    Then exit code is 0

  Scenario: Markdown renderer handles h2 and h3
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; assert "<h2>" in render_markdown("## H2") and "<h3>" in render_markdown("### H3")'"
    Then exit code is 0

  Scenario: Markdown renderer handles code blocks
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("```\ncode\n```"); assert "<pre" in h and "code" in h'"
    Then exit code is 0

  Scenario: Markdown renderer handles unordered lists
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("- item1\n- item2"); assert "<li>" in h and "item1" in h and "item2" in h'"
    Then exit code is 0

  Scenario: Markdown renderer handles bold and italic
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("**bold** and *italic*"); assert "<strong>bold</strong>" in h and "<em>italic</em>" in h'"
    Then exit code is 0

  Scenario: Markdown renderer handles inline code
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("use `cmd` here"); assert "<code>cmd</code>" in h'"
    Then exit code is 0

  Scenario: Markdown renderer escapes HTML in text
    Given "python3" is available
    When I run "python3 -c 'from scripts.web.html import render_markdown; h = render_markdown("<script>xss</script>"); assert "<script>" not in h'"
    Then exit code is 0
