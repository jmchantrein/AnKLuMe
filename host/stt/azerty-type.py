#!/usr/bin/env python3
"""azerty-type.py — Frappe de texte via wtype avec support AZERTY.

Lit le texte sur stdin et le tape via wtype.
Batch les caractères directs, gère les dead keys individuellement.
"""

from __future__ import annotations

import subprocess
import sys

# Caractères nécessitant des dead keys
CIRCUMFLEX_MAP = {"â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u"}
DIAERESIS_MAP = {"ä": "a", "ë": "e", "ï": "i", "ö": "o", "ü": "u", "ÿ": "y"}
DEAD_KEY_CHARS = set(CIRCUMFLEX_MAP) | set(DIAERESIS_MAP)


def _flush_buffer(buf: list[str]) -> None:
    """Tape un buffer de caractères directs en un seul appel wtype."""
    if not buf:
        return
    subprocess.run(["wtype", "--", "".join(buf)], check=True)
    buf.clear()


def _type_dead_key(char: str) -> None:
    """Tape un caractère via dead key (circumflex ou diaeresis)."""
    if char in CIRCUMFLEX_MAP:
        subprocess.run(
            ["wtype", "-k", "dead_circumflex", "-s", "50", CIRCUMFLEX_MAP[char]],
            check=True,
        )
    elif char in DIAERESIS_MAP:
        subprocess.run(
            ["wtype", "-k", "dead_diaeresis", "-s", "50", DIAERESIS_MAP[char]],
            check=True,
        )


def type_text(text: str) -> None:
    """Tape le texte — batch les caractères directs, dead keys individuels."""
    buf: list[str] = []
    for char in text:
        if char in DEAD_KEY_CHARS:
            _flush_buffer(buf)
            _type_dead_key(char)
        else:
            buf.append(char)
    _flush_buffer(buf)


def main() -> None:
    """Point d'entrée : lit stdin et tape le texte."""
    text = sys.stdin.read()
    if text:
        type_text(text)


if __name__ == "__main__":
    main()
