import io
import wave
from pathlib import Path

import pytest

from app.services import audio


def _wav(duration: float, rate: int = 24000) -> bytes:
    import math
    import struct
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(rate * duration)
        w.writeframes(b"".join(
            struct.pack("<h", int(500 * math.sin(2 * math.pi * 440 * i / rate)))
            for i in range(n)))
    return buf.getvalue()


def test_wav_duration():
    assert abs(audio.wav_duration(_wav(2.0)) - 2.0) < 0.01


def test_concat_wavs_duration_and_format(tmp_path):
    parts = [_wav(1.0), _wav(0.5), _wav(0.25)]
    out = audio.concat_wavs(parts, tmp_path)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert abs(w.getnframes() / 24000 - 1.75) < 0.02


def test_speed_wav_doubles(tmp_path):
    out = audio.speed_wav(_wav(2.0), 2.0, tmp_path)
    assert abs(audio.wav_duration(out) - 1.0) < 0.05


def test_build_subtitles():
    segments = [
        {"index": 1, "text": "第一句。", "start": 0.0, "end": 2.5},
        {"index": 2, "text": "第二句。", "start": 2.5, "end": 5.0},
    ]
    srt, vtt = audio.build_subtitles(segments)
    assert "00:00:00,000 --> 00:00:02,500" in srt
    assert "第一句。" in srt
    assert "00:00:02.500 --> 00:00:05.000" in vtt
    assert "WEBVTT" in vtt


def test_split_speech_text_groups_paragraphs_and_caps():
    text = "第一段句子。\n\n第二段" + "很长的内容。" * 200
    parts = audio.split_speech_text(text, max_chars=200)
    assert len(parts) >= 2
    assert all(len(p) <= 250 for p in parts)
    assert "第一段句子。" in parts[0]


def test_text_hash_stable():
    assert audio.text_hash("abc") == audio.text_hash("abc")
    assert audio.text_hash("abc") != audio.text_hash("abd")
