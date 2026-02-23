#!/usr/bin/env python3
"""STT streaming temps réel — audio cumulatif + diff par mots.

Enregistre via pw-record, envoie l'audio CUMULATIF à l'API toutes les ~3s,
compare par mots avec la transcription précédente, tape uniquement les nouveaux mots.

Arrêt via fichier stop (STT_STOP_FILE) créé par Meta+S.

Sécurité anti-boucle :
  - threading.Event global vérifié AVANT chaque appel ydotool
  - Compteur max d'opérations de frappe (MAX_TYPE_OPS)
  - Hard timeout avec os._exit() en dernier recours
  - Signal handlers SIGINT/SIGTERM pour arrêt propre
  - Nouveau process group pour kill groupé
"""

import io
import json
import math
import os
import signal
import struct
import subprocess
import sys
import threading
import time
import wave

# ── Configuration ─────────────────────────────────────────────
API_URL = os.environ.get("STT_API_URL", "http://localhost:8000")
MODEL = os.environ.get("STT_MODEL", "mobiuslabsgmbh/faster-whisper-large-v3-turbo")
LANGUAGE = os.environ.get("STT_LANGUAGE", "fr")
CHUNK_INTERVAL = float(os.environ.get("STT_CHUNK_INTERVAL", "3.0"))
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH

# ── Chemin du typer AZERTY ────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AZERTY_TYPER = os.path.join(SCRIPT_DIR, "stt-azerty-type.py")

# ── Fichier d'arrêt ──────────────────────────────────────────
STOP_FILE = os.environ.get("STT_STOP_FILE", "")
TIMEOUT = 120

# ── Sécurité anti-boucle ─────────────────────────────────────
MAX_TYPE_OPS = 200          # Max d'appels type_text() avant arrêt forcé
HARD_TIMEOUT = TIMEOUT + 30  # os._exit() en dernier recours

# Event global : si set → plus AUCUNE frappe autorisée
_kill_switch = threading.Event()
_type_count = 0
_type_lock = threading.Lock()

# ── Hallucinations Whisper courantes pendant le silence ───────
HALLUCINATIONS = [
    "sous-titres", "sous titres", "sous-titre",
    "merci d'avoir regardé", "merci de votre attention",
    "abonnez-vous", "like and subscribe",
]


def should_stop():
    return _kill_switch.is_set() or (STOP_FILE and os.path.exists(STOP_FILE))


def pcm_to_wav(pcm_data):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_data)
    return buf.getvalue()


def is_hallucination(text):
    lower = text.lower().strip()
    if len(lower) < 2:
        return True
    return any(h in lower for h in HALLUCINATIONS)


def rms_energy(pcm_data):
    """Calcule l'énergie RMS d'un buffer PCM 16-bit signé."""
    if len(pcm_data) < 2:
        return 0.0
    n_samples = len(pcm_data) // SAMPLE_WIDTH
    if n_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{n_samples}h", pcm_data[:n_samples * SAMPLE_WIDTH])
    sum_sq = sum(s * s for s in samples)
    return math.sqrt(sum_sq / n_samples)


# Seuil de silence : ~300 sur 32768 (16-bit) ≈ -40dB
SILENCE_THRESHOLD = 300


def transcribe(wav_data, prompt=""):
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_data)
        tmp_name = tmp.name
    try:
        cmd = [
            "curl", "-s", "--max-time", "30",
            "-X", "POST", f"{API_URL}/v1/audio/transcriptions",
            "-F", f"file=@{tmp_name}",
            "-F", f"model={MODEL}",
            "-F", f"language={LANGUAGE}",
            "-F", "response_format=json",
        ]
        if prompt:
            cmd.extend(["-F", f"prompt={prompt}"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return ""
        try:
            data = json.loads(result.stdout)
            return data.get("text", "").strip()
        except (json.JSONDecodeError, ValueError):
            return ""
    finally:
        os.unlink(tmp_name)


def type_text(text):
    """Tape du texte via stt-azerty-type.py.

    Protections :
      1. Vérifie _kill_switch AVANT de taper
      2. Incrémente un compteur, arrêt si > MAX_TYPE_OPS
      3. Timeout de 10s sur le sous-processus
    """
    global _type_count

    if not text or _kill_switch.is_set():
        return

    with _type_lock:
        _type_count += 1
        if _type_count > MAX_TYPE_OPS:
            _kill_switch.set()
            print(f"SÉCURITÉ: {MAX_TYPE_OPS} opérations atteintes, frappe désactivée",
                  file=sys.stderr)
            return

    # Double vérification juste avant l'appel
    if _kill_switch.is_set():
        return

    try:
        subprocess.run(
            [sys.executable, AZERTY_TYPER, text],
            capture_output=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        print("SÉCURITÉ: type_text timeout, frappe désactivée", file=sys.stderr)
        _kill_switch.set()


def normalize_word(w):
    """Normalise un mot pour la comparaison (minuscule, sans ponctuation finale)."""
    return w.lower().rstrip('.,!?;:…\'"»)')


def find_new_words(old_text, new_text):
    """Compare par mots et retourne le texte nouveau à taper.

    Protections anti-duplication :
      1. Préfixe commun normalisé (ignore ponctuation)
      2. Vérifie que le résultat n'est pas déjà en fin du texte tapé
    """
    if not old_text:
        return new_text
    if not new_text:
        return ""

    old_words = old_text.strip().split()
    new_words = new_text.strip().split()

    if not old_words:
        return new_text.strip()

    # Trouver le plus long préfixe commun (mots normalisés)
    match_len = 0
    for i in range(min(len(old_words), len(new_words))):
        if normalize_word(old_words[i]) == normalize_word(new_words[i]):
            match_len = i + 1
        else:
            break

    if match_len >= len(new_words):
        return ""

    candidate = " ".join(new_words[match_len:])

    # Anti-duplication : vérifier que le candidat n'est pas déjà
    # une sous-séquence en fin du texte déjà tapé
    candidate_normalized = [normalize_word(w) for w in candidate.split()]
    old_normalized = [normalize_word(w) for w in old_words]

    if len(candidate_normalized) <= len(old_normalized):
        tail = old_normalized[-len(candidate_normalized):]
        if tail == candidate_normalized:
            return ""

    return candidate


def _hard_timeout_watchdog():
    """Dernier recours : os._exit() après HARD_TIMEOUT secondes."""
    time.sleep(HARD_TIMEOUT)
    print(f"SÉCURITÉ: hard timeout {HARD_TIMEOUT}s, exit forcé", file=sys.stderr)
    os._exit(1)


def main():
    # ── Nouveau process group pour kill groupé ───────────────
    os.setpgrp()

    # ── Watchdog hard timeout ────────────────────────────────
    watchdog = threading.Thread(target=_hard_timeout_watchdog, daemon=True)
    watchdog.start()

    # ── Signal handlers ──────────────────────────────────────
    def _signal_handler(signum, frame):
        _kill_switch.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ── Lancer pw-record en mode raw PCM ──────────────────────
    rec_proc = subprocess.Popen(
        ["pw-record", "--raw", "--rate", str(SAMPLE_RATE), "--channels", str(CHANNELS),
         "--format", "s16", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    time.sleep(0.1)
    if rec_proc.poll() is not None:
        print("ERREUR: pw-record n'a pas démarré", file=sys.stderr)
        sys.exit(1)

    # ── Thread de lecture audio ───────────────────────────────
    audio_buffer = bytearray()
    audio_lock = threading.Lock()
    recording = True

    def read_audio():
        nonlocal recording
        while recording and not _kill_switch.is_set():
            try:
                chunk = rec_proc.stdout.read(BYTES_PER_SECOND // 10)  # ~100ms
                if not chunk:
                    break
                with audio_lock:
                    audio_buffer.extend(chunk)
            except Exception:
                break

    reader_thread = threading.Thread(target=read_audio, daemon=True)
    reader_thread.start()

    # ── Boucle principale ─────────────────────────────────────
    typed_text = ""
    last_full_text = ""
    start_time = time.time()
    last_transcribe_time = start_time
    last_transcribed_len = 0         # Taille audio à la dernière transcription
    min_audio_bytes = BYTES_PER_SECOND  # Au moins 1s d'audio
    min_new_audio = BYTES_PER_SECOND // 2  # Au moins 0.5s de NOUVEL audio
    transcribing = False
    check_interval = 0.1

    try:
        while time.time() - start_time < TIMEOUT:
            time.sleep(check_interval)

            if should_stop():
                break

            now = time.time()
            if transcribing or (now - last_transcribe_time) < CHUNK_INTERVAL:
                continue

            with audio_lock:
                current_audio = bytes(audio_buffer)

            if len(current_audio) < min_audio_bytes:
                continue

            # Pas assez de nouvel audio depuis la dernière transcription
            new_audio_len = len(current_audio) - last_transcribed_len
            if new_audio_len < min_new_audio:
                continue

            # Vérifier si le nouvel audio est du silence
            new_audio_chunk = current_audio[last_transcribed_len:]
            if rms_energy(new_audio_chunk) < SILENCE_THRESHOLD:
                # Silence détecté — pas de re-transcription
                last_transcribe_time = now
                continue

            transcribing = True
            last_transcribe_time = now
            snapshot_len = len(current_audio)

            def do_transcribe(audio_data, prev_typed, audio_len):
                nonlocal typed_text, last_full_text, transcribing, last_transcribed_len
                try:
                    if should_stop():
                        return

                    wav_data = pcm_to_wav(audio_data)
                    full_text = transcribe(wav_data)

                    if should_stop():
                        return

                    if not full_text or is_hallucination(full_text):
                        return

                    # Ne pas re-transcrire le même audio si le résultat est identique
                    if full_text == last_full_text:
                        return

                    new_words = find_new_words(prev_typed, full_text)

                    if new_words:
                        if should_stop():
                            return

                        to_type = " " + new_words if prev_typed else new_words
                        type_text(to_type)
                        typed_text = prev_typed + to_type

                    last_full_text = full_text
                    last_transcribed_len = audio_len
                finally:
                    transcribing = False

            t = threading.Thread(
                target=do_transcribe,
                args=(current_audio, typed_text, snapshot_len),
                daemon=True,
            )
            t.start()

    finally:
        # ── Activer le kill switch — plus aucune frappe ──────
        _kill_switch.set()

        # ── Arrêter l'enregistrement ─────────────────────────
        recording = False
        try:
            rec_proc.send_signal(2)  # SIGINT
            rec_proc.wait(timeout=3)
        except Exception:
            rec_proc.kill()
            rec_proc.wait()

        reader_thread.join(timeout=2)

        # Attendre la fin d'une éventuelle transcription en cours
        deadline = time.time() + 5
        while transcribing and time.time() < deadline:
            time.sleep(0.05)

        # ── Transcription finale (sans frappe — kill switch actif) ──
        # On transcrit pour le résultat texte, mais on ne tape plus rien
        with audio_lock:
            final_audio = bytes(audio_buffer)

        if len(final_audio) >= min_audio_bytes:
            wav_data = pcm_to_wav(final_audio)
            final_text = transcribe(wav_data)

            if final_text and not is_hallucination(final_text):
                remaining = find_new_words(typed_text, final_text)
                if remaining:
                    if typed_text:
                        typed_text += " " + remaining
                    else:
                        typed_text = remaining

        # Résultat pour la notification
        final = typed_text.strip()
        if final:
            print(final)


if __name__ == "__main__":
    main()
