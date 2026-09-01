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


@pytest.mark.parametrize("parts", [[], ()])
def test_concat_wavs_empty_parts_raises(tmp_path, parts):
    with pytest.raises(ValueError):
        audio.concat_wavs(parts, tmp_path)


def test_concat_wavs_single_part_normalized(tmp_path):
    out = audio.concat_wavs([_wav(1.0, rate=16000)], tmp_path)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert abs(audio.wav_duration(out) - 1.0) < 0.01


def test_concat_wavs_mixed_sample_rates(tmp_path):
    out = audio.concat_wavs([_wav(0.5, rate=8000), _wav(0.5, rate=48000)], tmp_path)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getframerate() == 24000
        assert abs(w.getnframes() / 24000 - 1.0) < 0.02


def test_speed_wav_doubles(tmp_path):
    out = audio.speed_wav(_wav(2.0), 2.0, tmp_path)
    assert abs(audio.wav_duration(out) - 1.0) < 0.05


@pytest.mark.parametrize("factor", [0, -1.0])
def test_speed_wav_nonpositive_factor_raises(tmp_path, factor):
    with pytest.raises(ValueError):
        audio.speed_wav(_wav(1.0), factor, tmp_path)


@pytest.mark.parametrize("duration,factor,expected", [(2.0, 4.0, 0.5), (1.0, 0.5, 2.0)])
def test_speed_wav_chained_atempo(tmp_path, duration, factor, expected):
    out = audio.speed_wav(_wav(duration), factor, tmp_path)
    assert abs(audio.wav_duration(out) - expected) < 0.05


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


def test_build_subtitles_cue_spacing():
    segments = [
        {"index": 1, "text": "a", "start": 0.0, "end": 1.0},
        {"index": 2, "text": "b", "start": 1.0, "end": 2.0},
    ]
    srt, vtt = audio.build_subtitles(segments)
    assert srt.count("\n\n") == len(segments) - 1
    assert vtt.startswith("WEBVTT\n\n")
    assert vtt.count("\n\n") == len(segments)


def test_split_speech_text_groups_paragraphs_and_caps():
    text = "第一段句子。\n\n第二段" + "很长的内容。" * 200
    max_chars = 200
    parts = audio.split_speech_text(text, max_chars=max_chars)
    assert len(parts) >= 2
    assert all(len(p) <= max_chars for p in parts)
    assert "第一段句子。" in parts[0]


def test_split_speech_text_hard_caps_without_punctuation():
    text = "x" * 1000
    parts = audio.split_speech_text(text, max_chars=500)
    assert all(len(p) <= 500 for p in parts)
    assert "".join(parts) == text


@pytest.mark.parametrize("n,max_chars", [(500, 500), (499, 500)])
def test_split_speech_text_max_chars_boundary(n, max_chars):
    text = "字" * n
    assert audio.split_speech_text(text, max_chars=max_chars) == [text]


def test_split_speech_text_preserves_internal_whitespace():
    text = "第一句。 第二句。 第三句。 第四句。" * 10
    parts = audio.split_speech_text(text, max_chars=50)
    assert "".join(parts) == text


def test_text_hash_stable():
    assert audio.text_hash("abc") == audio.text_hash("abc")
    assert audio.text_hash("abc") != audio.text_hash("abd")

