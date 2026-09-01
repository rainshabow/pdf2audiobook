import hashlib
import io
import re
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg

_RATE = 24000


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def concat_wavs(parts: list[bytes], tmp_dir: Path) -> bytes:
    """把多个 WAV 统一为 24kHz/mono/16bit 后拼接（用 ffmpeg）。"""
    if not parts:
        raise ValueError("parts 为空")
    if len(parts) == 1:
        return _normalize(parts[0], tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    norm_paths = []
    for i, p in enumerate(parts):
        path = tmp_dir / f"part_{i:04d}.wav"
        path.write_bytes(_normalize(p, tmp_dir))
        norm_paths.append(path)
    list_path = tmp_dir / "concat.txt"
    list_path.write_text("".join(f"file '{p.name}'\n" for p in norm_paths), encoding="utf-8")
    out_path = tmp_dir / "concat_out.wav"
    _ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
             "-c", "copy", str(out_path)])
    data = out_path.read_bytes()
    return data


def speed_wav(data: bytes, factor: float, tmp_dir: Path) -> bytes:
    """用 ffmpeg atempo 变速（factor > 1 变快）。"""
    if factor <= 0:
        raise ValueError("factor 必须为正数")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_dir / "speed_src.wav"
    dst = tmp_dir / "speed_dst.wav"
    src.write_bytes(_normalize(data, tmp_dir))
    # atempo 支持 0.5–2.0，超范围时链式调用
    filters = []
    remaining = factor
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining /= 0.5
    filters.append(f"atempo={remaining:.6f}")
    _ffmpeg(["-y", "-i", str(src), "-filter:a", ",".join(filters),
             "-ar", str(_RATE), "-ac", "1", str(dst)])
    return dst.read_bytes()


def build_subtitles(segments: list[dict]) -> tuple[str, str]:
    srt_lines = []
    vtt_lines = ["WEBVTT", ""]
    for seg in segments:
        idx = seg["index"]
        text = seg["text"]
        srt_lines.append(f"{idx}\n{_fmt_srt(seg['start'])} --> {_fmt_srt(seg['end'])}\n{text}\n")
        vtt_lines.append(f"{idx}\n{_fmt_vtt(seg['start'])} --> {_fmt_vtt(seg['end'])}\n{text}\n")
    return "\n\n".join(srt_lines).strip(), "\n\n".join(vtt_lines).strip()


def split_speech_text(text: str, max_chars: int = 500) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out: list[str] = []
    for block in blocks:
        if len(block) <= max_chars:
            out.append(block)
            continue
        # 超长块按句切
        sentences = re.split(r"(?<=[。！？；])", block)
        cur = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(cur) + len(s) <= max_chars:
                cur += s
            else:
                if cur:
                    out.append(cur)
                cur = s
        if cur:
            out.append(cur)
    return out


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize(data: bytes, tmp_dir: Path) -> bytes:
    src = tmp_dir / "norm_src.wav"
    dst = tmp_dir / "norm_dst.wav"
    src.write_bytes(data)
    _ffmpeg(["-y", "-i", str(src), "-ar", str(_RATE), "-ac", "1",
             "-c:a", "pcm_s16le", str(dst)])
    return dst.read_bytes()


def _ffmpeg(args: list[str]) -> None:
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([exe, *args], check=True, capture_output=True)


def _fmt_srt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
