#!/usr/bin/env python3
"""streaming.py — Transcription STT en temps réel via Speaches.

Enregistre l'audio en continu, envoie des chunks ~3s au serveur STT,
et tape le texte transcrit en temps réel avec diff mot-à-mot.
"""

from __future__ import annotations

import io
import math
import os
import struct
import subprocess
import sys
import time
import wave

import requests

# ── Configuration ────────────────────────────────────────────────────

STT_API_URL = os.environ.get("STT_API_URL", "http://10.100.3.1:8000")
STT_LANGUAGE = os.environ.get("STT_LANGUAGE", "fr")
STT_MODEL = os.environ.get("STT_MODEL", "base")

CHUNK_DURATION = 3.0  # secondes par chunk
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit

SILENCE_THRESHOLD = 500  # RMS en dessous duquel on considère le silence
SILENCE_TIMEOUT = 5.0  # secondes de silence avant arrêt automatique

# Hallucinations fréquentes de Whisper
HALLUCINATION_PATTERNS = {
    "sous-titres",
    "sous-titrage",
    "merci d'avoir regardé",
    "merci de votre attention",
    "merci.",
    "...",
    "",
}


# ── Utilitaires audio ───────────────────────────────────────────────


def compute_rms(audio_data: bytes) -> float:
    """Calcule le RMS (Root Mean Square) d'un buffer audio 16-bit."""
    if len(audio_data) < 2:
        return 0.0
    n_samples = len(audio_data) // 2
    samples = struct.unpack(f"<{n_samples}h", audio_data[: n_samples * 2])
    if not samples:
        return 0.0
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / n_samples)


def is_silence(audio_data: bytes, threshold: float = SILENCE_THRESHOLD) -> bool:
    """Détecte si un buffer audio est du silence."""
    rms = compute_rms(audio_data)
    return rms < threshold


def is_hallucination(text: str) -> bool:
    """Filtre les hallucinations connues de Whisper."""
    cleaned = text.strip().lower()
    return cleaned in HALLUCINATION_PATTERNS or len(cleaned) <= 1


# ── Transcription ────────────────────────────────────────────────────


def transcribe_chunk(audio_data: bytes) -> str:
    """Envoie un chunk audio au serveur STT et retourne le texte."""
    # Créer un fichier WAV en mémoire
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio_data)

    wav_buffer.seek(0)

    response = requests.post(
        f"{STT_API_URL}/v1/audio/transcriptions",
        files={"file": ("chunk.wav", wav_buffer, "audio/wav")},
        data={
            "model": STT_MODEL,
            "language": STT_LANGUAGE,
            "response_format": "json",
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("text", "")


# ── Diff mot-à-mot ──────────────────────────────────────────────────


def word_diff(previous: str, current: str) -> str:
    """Retourne les mots nouveaux par rapport à la transcription précédente."""
    prev_words = previous.split()
    curr_words = current.split()

    # Chercher le point de divergence
    common = 0
    for pw, cw in zip(prev_words, curr_words, strict=False):
        if pw == cw:
            common += 1
        else:
            break

    new_words = curr_words[common:]
    return " ".join(new_words)


# ── Boucle principale ───────────────────────────────────────────────


def stream_loop() -> None:
    """Boucle d'enregistrement et transcription en temps réel."""
    chunk_size = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH * CHUNK_DURATION)
    previous_text = ""
    silence_start: float | None = None

    # Démarrer pw-record en mode raw PCM
    proc = subprocess.Popen(
        [
            "pw-record",
            "--target=0",
            "--format=s16",
            f"--rate={SAMPLE_RATE}",
            f"--channels={CHANNELS}",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    try:
        while True:
            if proc.stdout is None:  # pragma: no cover
                break
            audio_data = proc.stdout.read(chunk_size)
            if not audio_data:
                break

            # Détection de silence
            if is_silence(audio_data):
                if silence_start is None:
                    silence_start = time.monotonic()
                elif time.monotonic() - silence_start > SILENCE_TIMEOUT:
                    break
                continue
            else:
                silence_start = None

            # Transcrire le chunk
            try:
                text = transcribe_chunk(audio_data)
            except (requests.RequestException, OSError):
                continue

            if not text or is_hallucination(text):
                continue

            # Diff : ne taper que les nouveaux mots
            new_text = word_diff(previous_text, text)
            if new_text:
                sys.stdout.write(new_text + " ")
                sys.stdout.flush()
                previous_text = text

    finally:
        proc.terminate()
        proc.wait()


def main() -> None:
    """Point d'entrée du mode streaming."""
    try:
        stream_loop()
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
