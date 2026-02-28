#!/usr/bin/env python3
"""help-i18n.py — Render bilingual help for student mode.

Reads the Makefile's categorized help sections and appends French
translations from i18n/fr.yml when ANKLUME_MODE=student.

Usage: python3 scripts/help-i18n.py <mode> [lang]
  mode: student | user | dev
  lang: fr (default in student mode)
"""

import re
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
I18N_DIR = PROJECT_ROOT / "i18n"
MAKEFILE = PROJECT_ROOT / "Makefile"


def load_translations(lang):
    """Load translation file for the given language."""
    path = I18N_DIR / f"{lang}.yml"
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    # Strip comments (YAML handles this) — return flat dict
    return {k: v for k, v in data.items() if isinstance(v, str)}


def extract_documented_targets(content):
    """Extract targets with ## comments from Makefile content."""
    pattern = re.compile(r"^([a-zA-Z_-]+):\s*(?:[^#]*?)##\s*(.+)$", re.MULTILINE)
    return {m.group(1): m.group(2).strip() for m in pattern.finditer(content)}


def print_help_student(translations):
    """Print student-friendly help with prominent quick start."""
    content = MAKEFILE.read_text()
    documented = extract_documented_targets(content)

    # Quick start: the 4 commands every student needs
    quick_start = [
        ("sync", "Generate infrastructure files / Generer les fichiers"),
        ("apply", "Deploy infrastructure / Deployer l'infrastructure"),
        ("console", "Open domain console / Console par domaine"),
        ("lab-start", "Start a guided lab / Lancer un exercice guide"),
    ]

    # Additional useful commands, grouped
    more_commands = [
        ("USEFUL COMMANDS", "COMMANDES UTILES", [
            "guide", "lab-list", "lab-check", "doctor",
            "snapshot", "restore", "disp", "flush",
        ]),
    ]

    print()
    print("  \033[1manklume\033[0m — Infrastructure Compartmentalization")
    print()
    print("  \033[1;32mQUICK START / DEMARRAGE RAPIDE\033[0m")
    for target, desc in quick_start:
        fr_desc = translations.get(target, "")
        display = fr_desc if fr_desc else desc
        print(f"    \033[1;36mmake {target:<18}\033[0m {display}")
    print()

    for en_name, fr_name, targets in more_commands:
        print(f"  \033[1;33m{en_name} / {fr_name}\033[0m")
        for target in targets:
            en_desc = documented.get(target, "")
            fr_desc = translations.get(target, "")
            display_target = f"make {target}"
            if fr_desc:
                print(f"    \033[36m{display_target:<22}\033[0m {fr_desc}")
            elif en_desc:
                print(f"    \033[36m{display_target:<22}\033[0m {en_desc}")
        print()

    print("  \033[2mAll commands: make mode-user && make help\033[0m")
    print("  Mode: \033[33mstudent\033[0m"
          " | Change: \033[36mmake mode-user\033[0m")
    print()


def print_help_dev(translations):
    """Print all targets (dev mode shows everything)."""
    content = MAKEFILE.read_text()
    documented = extract_documented_targets(content)

    print()
    print("  \033[1manklume\033[0m — All targets (dev mode)")
    print()
    for target in sorted(documented):
        desc = documented[target]
        fr = translations.get(target, "")
        if fr:
            print(f"    \033[36m{target:<22}\033[0m {desc}")
            print(f"    {'':22}  \033[2m{fr}\033[0m")
        else:
            print(f"    \033[36m{target:<22}\033[0m {desc}")
    print()
    print("  Mode: \033[33mdev\033[0m"
          " | Change: \033[36mmake mode-user\033[0m")
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: help-i18n.py <student|user|dev> [lang]", file=sys.stderr)
        raise SystemExit(1)

    mode = sys.argv[1]
    lang = sys.argv[2] if len(sys.argv) > 2 else "fr"

    translations = load_translations(lang)

    if mode == "student":
        print_help_student(translations)
    elif mode == "dev":
        print_help_dev(translations)
    else:
        # user mode: should not reach here (Makefile uses native help)
        print("User mode uses the default Makefile help target.", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
