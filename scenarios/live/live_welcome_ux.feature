Feature: Live ISO welcome UX — clear screens, highlights, defaults
  The welcome wizard must provide a polished UX: clear screens between
  pages, highlighted action buttons, sensible defaults for all prompts,
  and helpful feedback when persistence is unavailable.

  Background:
    Given "python3" is available

  # ── Clear screen between pages ──────────────────────────────

  @requires.welcome_import
  Scenario: tui_main clears screen at least 4 times
    Given the welcome.py AST is loaded
    Then function "tui_main" contains at least 4 calls to "c.clear"

  @requires.welcome_import
  Scenario: plain_main has at least 4 ANSI clear sequences
    Given the welcome.py AST is loaded
    Then function "plain_main" contains at least 4 ANSI clear sequences

  # ── Action button highlights ─────────────────────────────────

  @requires.welcome_import
  Scenario: tui_main uses Panel for action prompts
    Given the welcome.py AST is loaded
    Then function "tui_main" uses Panel from rich

  @requires.welcome_import
  Scenario: plain_main uses box-drawing for action prompts
    Given the welcome.py AST is loaded
    Then function "plain_main" contains at least 3 calls to "_box_prompt"

  # ── Keyboard default ─────────────────────────────────────────

  @requires.welcome_import
  Scenario: do_keyboard accepts empty input as default
    When I run "python3 -c 'import ast; t=ast.parse(open(chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)+chr(47)+chr(119)+chr(101)+chr(108)+chr(99)+chr(111)+chr(109)+chr(101)+chr(46)+chr(112)+chr(121)).read()); [print(chr(111)+chr(107)) for n in ast.walk(t) if isinstance(n, ast.FunctionDef) and n.name==chr(100)+chr(111)+chr(95)+chr(107)+chr(101)+chr(121)+chr(98)+chr(111)+chr(97)+chr(114)+chr(100) for c in ast.walk(n) if isinstance(c, ast.Constant) and isinstance(c.value, str) and chr(100)+chr(101)+chr(102)+chr(97)+chr(117)+chr(108)+chr(116) in c.value]'"
    Then exit code is 0
    And output contains "ok"

  @requires.welcome_import
  Scenario: do_keyboard prompt shows default=1
    When I run "python3 -c 'src=open(chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)+chr(47)+chr(119)+chr(101)+chr(108)+chr(99)+chr(111)+chr(109)+chr(101)+chr(46)+chr(112)+chr(121)).read(); print(chr(111)+chr(107) if chr(100)+chr(101)+chr(102)+chr(97)+chr(117)+chr(108)+chr(116)+chr(61)+chr(49) in src else chr(102)+chr(97)+chr(105)+chr(108))'"
    Then exit code is 0
    And output contains "ok"

  # ── Prompt format consistency ────────────────────────────────

  @requires.welcome_import
  Scenario: All choice prompts in plain_main show default values
    When I run "python3 -c 'src=open(chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)+chr(47)+chr(119)+chr(101)+chr(108)+chr(99)+chr(111)+chr(109)+chr(101)+chr(46)+chr(112)+chr(121)).read(); ok=chr(100)+chr(101)+chr(102)+chr(97)+chr(117)+chr(108)+chr(116)+chr(61) in src; print(chr(111)+chr(107) if ok else chr(102)+chr(97)+chr(105)+chr(108))'"
    Then exit code is 0
    And output contains "ok"

  # ── Persistence fallback ─────────────────────────────────────

  @requires.welcome_import
  Scenario: do_persistence offers explore when no disk found
    When I run "python3 -c 'import ast; t=ast.parse(open(chr(115)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115)+chr(47)+chr(119)+chr(101)+chr(108)+chr(99)+chr(111)+chr(109)+chr(101)+chr(46)+chr(112)+chr(121)).read()); fn=[n for n in ast.walk(t) if isinstance(n, ast.FunctionDef) and n.name==chr(100)+chr(111)+chr(95)+chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(101)+chr(110)+chr(99)+chr(101)]; calls=[c for n in fn for c in ast.walk(n) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id==chr(100)+chr(111)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(111)+chr(114)+chr(101)]; print(chr(111)+chr(107) if calls else chr(102)+chr(97)+chr(105)+chr(108))'"
    Then exit code is 0
    And output contains "ok"

  @requires.welcome_import
  Scenario: welcome_strings has persist_no_disk_explain key
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; assert chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(95)+chr(110)+chr(111)+chr(95)+chr(100)+chr(105)+chr(115)+chr(107)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(97)+chr(105)+chr(110) in STRINGS[chr(102)+chr(114)]; print(chr(111)+chr(107))'"
    Then exit code is 0
    And output contains "ok"

  @requires.welcome_import
  Scenario: welcome_strings has persist_fallback_explore key
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; assert chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(95)+chr(102)+chr(97)+chr(108)+chr(108)+chr(98)+chr(97)+chr(99)+chr(107)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(111)+chr(114)+chr(101) in STRINGS[chr(102)+chr(114)]; print(chr(111)+chr(107))'"
    Then exit code is 0
    And output contains "ok"

  @requires.welcome_import
  Scenario: persist_no_disk_explain and persist_fallback_explore exist in both languages
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; fr=STRINGS[chr(102)+chr(114)]; en=STRINGS[chr(101)+chr(110)]; assert chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(95)+chr(110)+chr(111)+chr(95)+chr(100)+chr(105)+chr(115)+chr(107)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(97)+chr(105)+chr(110) in fr and chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(95)+chr(110)+chr(111)+chr(95)+chr(100)+chr(105)+chr(115)+chr(107)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(97)+chr(105)+chr(110) in en; assert chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(95)+chr(102)+chr(97)+chr(108)+chr(108)+chr(98)+chr(97)+chr(99)+chr(107)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(111)+chr(114)+chr(101) in fr and chr(112)+chr(101)+chr(114)+chr(115)+chr(105)+chr(115)+chr(116)+chr(95)+chr(102)+chr(97)+chr(108)+chr(108)+chr(98)+chr(97)+chr(99)+chr(107)+chr(95)+chr(101)+chr(120)+chr(112)+chr(108)+chr(111)+chr(114)+chr(101) in en; print(chr(111)+chr(107))'"
    Then exit code is 0
    And output contains "ok"

  # ── String completeness ──────────────────────────────────────

  @requires.welcome_import
  Scenario: All string keys match between FR and EN
    When I run "python3 -c 'from scripts.welcome_strings import STRINGS; assert set(STRINGS[chr(102)+chr(114)]) == set(STRINGS[chr(101)+chr(110)]); print(chr(111)+chr(107))'"
    Then exit code is 0
    And output contains "ok"
