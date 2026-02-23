#!/usr/bin/env python3
"""Tape du texte via ydotool key en utilisant le mapping AZERTY français.

Usage: echo "Bonjour le monde" | stt-azerty-type.py
       stt-azerty-type.py "Bonjour le monde"

Envoie des keycodes physiques correspondant au layout AZERTY FR,
interprétés correctement par le compositeur Wayland (KWin, etc.).
"""

import subprocess
import sys

# Keycodes Linux (identiques quelle que soit la disposition)
# 42 = Left Shift, 100 = Right Alt (AltGr)
SHIFT = 42
ALTGR = 100

# Mapping AZERTY FR : caractère → (keycode, modifiers[])
# Modifiers: [] = aucun, [SHIFT] = shift, [ALTGR] = altgr
CHAR_MAP = {
    # Lettres minuscules (rangée AZERTY)
    'a': (16, []),  'z': (17, []),  'e': (18, []),  'r': (19, []),
    't': (20, []),  'y': (21, []),  'u': (22, []),  'i': (23, []),
    'o': (24, []),  'p': (25, []),
    'q': (30, []),  's': (31, []),  'd': (32, []),  'f': (33, []),
    'g': (34, []),  'h': (35, []),  'j': (36, []),  'k': (37, []),
    'l': (38, []),  'm': (39, []),
    'w': (44, []),  'x': (45, []),  'c': (46, []),  'v': (47, []),
    'b': (48, []),  'n': (49, []),

    # Lettres majuscules
    'A': (16, [SHIFT]),  'Z': (17, [SHIFT]),  'E': (18, [SHIFT]),  'R': (19, [SHIFT]),
    'T': (20, [SHIFT]),  'Y': (21, [SHIFT]),  'U': (22, [SHIFT]),  'I': (23, [SHIFT]),
    'O': (24, [SHIFT]),  'P': (25, [SHIFT]),
    'Q': (30, [SHIFT]),  'S': (31, [SHIFT]),  'D': (32, [SHIFT]),  'F': (33, [SHIFT]),
    'G': (34, [SHIFT]),  'H': (35, [SHIFT]),  'J': (36, [SHIFT]),  'K': (37, [SHIFT]),
    'L': (38, [SHIFT]),  'M': (39, [SHIFT]),
    'W': (44, [SHIFT]),  'X': (45, [SHIFT]),  'C': (46, [SHIFT]),  'V': (47, [SHIFT]),
    'B': (48, [SHIFT]),  'N': (49, [SHIFT]),

    # Chiffres (Shift + rangée du haut sur AZERTY)
    '1': (2, [SHIFT]),   '2': (3, [SHIFT]),   '3': (4, [SHIFT]),
    '4': (5, [SHIFT]),   '5': (6, [SHIFT]),   '6': (7, [SHIFT]),
    '7': (8, [SHIFT]),   '8': (9, [SHIFT]),   '9': (10, [SHIFT]),
    '0': (11, [SHIFT]),

    # Caractères directs sur la rangée du haut (sans Shift)
    '&': (2, []),    'é': (3, []),    '"': (4, []),    "'": (5, []),
    '(': (6, []),    '-': (7, []),    'è': (8, []),    '_': (9, []),
    'ç': (10, []),   'à': (11, []),   ')': (12, []),   '=': (13, []),

    # Shift + rangée du haut (symboles)
    '°': (12, [SHIFT]),  '+': (13, [SHIFT]),

    # Ponctuation (rangée du bas AZERTY)
    ',': (50, []),       # m position on QWERTY
    ';': (51, []),       # , position on QWERTY
    ':': (52, []),       # . position on QWERTY
    '!': (53, []),       # / position on QWERTY
    '?': (50, [SHIFT]),  # Shift+,
    '.': (51, [SHIFT]),  # Shift+;
    '/': (52, [SHIFT]),  # Shift+:
    '§': (53, [SHIFT]),  # Shift+!

    # Autres touches directes
    'ù': (40, []),       # ' position on QWERTY
    '*': (43, []),       # \ position on QWERTY
    '%': (40, [SHIFT]),
    'µ': (43, [SHIFT]),
    '$': (27, []),       # ] position on QWERTY
    '£': (27, [SHIFT]),
    '<': (86, []),       # ISO extra key
    '>': (86, [SHIFT]),

    # Espace, entrée, tab
    ' ': (57, []),
    '\n': (28, []),
    '\t': (15, []),

    # AltGr combinations courantes
    '@': (11, [ALTGR]),   # AltGr + à
    '#': (4, [ALTGR]),    # AltGr + "
    '{': (5, [ALTGR]),    # AltGr + '
    '[': (6, [ALTGR]),    # AltGr + (
    '|': (7, [ALTGR]),    # AltGr + -
    '`': (8, [ALTGR]),    # AltGr + è
    '\\': (9, [ALTGR]),   # AltGr + _
    ']': (12, [ALTGR]),   # AltGr + )
    '}': (13, [ALTGR]),   # AltGr + =
    '€': (18, [ALTGR]),   # AltGr + e
    '~': (3, [ALTGR]),    # AltGr + é
}

# Caractères via touches mortes (dead keys)
# ^ = keycode 26 (dead circumflex), ¨ = Shift+26 (dead diaeresis)
DEAD_KEY_MAP = {
    'ê': (26, [], 18, []),          # ^ puis e
    'ë': (26, [SHIFT], 18, []),     # ¨ puis e
    'â': (26, [], 16, []),          # ^ puis a
    'ä': (26, [SHIFT], 16, []),     # ¨ puis a
    'î': (26, [], 23, []),          # ^ puis i
    'ï': (26, [SHIFT], 23, []),     # ¨ puis i
    'ô': (26, [], 24, []),          # ^ puis o
    'ö': (26, [SHIFT], 24, []),     # ¨ puis o
    'û': (26, [], 22, []),          # ^ puis u
    'ü': (26, [SHIFT], 22, []),     # ¨ puis u
    'Ê': (26, [], 18, [SHIFT]),     # ^ puis Shift+e
    'Ë': (26, [SHIFT], 18, [SHIFT]),
    'Â': (26, [], 16, [SHIFT]),
    'Ä': (26, [SHIFT], 16, [SHIFT]),
    'Î': (26, [], 23, [SHIFT]),
    'Ï': (26, [SHIFT], 23, [SHIFT]),
    'Ô': (26, [], 24, [SHIFT]),
    'Ö': (26, [SHIFT], 24, [SHIFT]),
    'Û': (26, [], 22, [SHIFT]),
    'Ü': (26, [SHIFT], 22, [SHIFT]),
    '^': (26, [], 57, []),          # ^ puis espace (pour ^ littéral)
    '¨': (26, [SHIFT], 57, []),     # ¨ puis espace (pour ¨ littéral)
}


def char_to_keys(char: str) -> list[str]:
    """Convertit un caractère en séquence de keycodes ydotool."""
    # Caractère direct
    if char in CHAR_MAP:
        keycode, mods = CHAR_MAP[char]
        seq = []
        for m in mods:
            seq.append(f"{m}:1")
        seq.append(f"{keycode}:1")
        seq.append(f"{keycode}:0")
        for m in reversed(mods):
            seq.append(f"{m}:0")
        return seq

    # Touche morte
    if char in DEAD_KEY_MAP:
        dk_code, dk_mods, char_code, char_mods = DEAD_KEY_MAP[char]
        seq = []
        # Appui touche morte
        for m in dk_mods:
            seq.append(f"{m}:1")
        seq.append(f"{dk_code}:1")
        seq.append(f"{dk_code}:0")
        for m in reversed(dk_mods):
            seq.append(f"{m}:0")
        # Appui caractère
        for m in char_mods:
            seq.append(f"{m}:1")
        seq.append(f"{char_code}:1")
        seq.append(f"{char_code}:0")
        for m in reversed(char_mods):
            seq.append(f"{m}:0")
        return seq

    # Caractère inconnu — ignorer
    return []


def type_text(text: str) -> None:
    """Tape le texte via ydotool key."""
    all_keys = []
    for char in text:
        keys = char_to_keys(char)
        all_keys.extend(keys)

    if not all_keys:
        return

    # Envoyer par lots de 50 caractères (~200 keycodes) pour éviter
    # des lignes de commande trop longues
    batch_size = 200
    for i in range(0, len(all_keys), batch_size):
        batch = all_keys[i:i + batch_size]
        subprocess.run(
            ["ydotool", "key", "--key-delay", "2"] + batch,
            capture_output=True,
        )


if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else sys.stdin.read()

    type_text(text)
