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
    tmp_dir.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        return _normalize(parts[0], tmp_dir)
    norm_paths: list[Path] = []
    list_path = tmp_dir / "concat.txt"
    out_path = tmp_dir / "concat_out.wav"
    try:
        for i, p in enumerate(parts):
            path = tmp_dir / f"part_{i:04d}.wav"
            path.write_bytes(_normalize(p, tmp_dir))
            norm_paths.append(path)
        list_path.write_text("".join(f"file '{p.name}'\n" for p in norm_paths), encoding="utf-8")
        _ffmpeg(["-y", "-f", "concat", "-safe", "0", "-i", str(list_path),
                 "-c", "copy", str(out_path)])
        return out_path.read_bytes()
    finally:
        _cleanup(*norm_paths, list_path, out_path)


def speed_wav(data: bytes, factor: float, tmp_dir: Path) -> bytes:
    """用 ffmpeg atempo 变速（factor > 1 变快）。"""
    if factor <= 0:
        raise ValueError("factor 必须为正数")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    src = tmp_dir / "speed_src.wav"
    dst = tmp_dir / "speed_dst.wav"
    try:
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
    finally:
        _cleanup(src, dst)


def build_subtitles(segments: list[dict]) -> tuple[str, str]:
    srt_cues = []
    vtt_cues = []
    for seg in segments:
        idx = seg["index"]
        text = seg["text"]
        srt_cues.append(f"{idx}\n{_fmt_srt(seg['start'])} --> {_fmt_srt(seg['end'])}\n{text}")
        vtt_cues.append(f"{idx}\n{_fmt_vtt(seg['start'])} --> {_fmt_vtt(seg['end'])}\n{text}")
    srt = "\n\n".join(srt_cues)
    vtt = "WEBVTT\n\n" + "\n\n".join(vtt_cues)
    return srt, vtt


def split_utterances(text: str) -> list[str]:
    """把朗读文本切成“句子级”语音单元（每句一个字幕条）。

    - 按空行分段落，避免跨段粘连；
    - 段落内按中文句读（。！？；）与英文句点（后随空白/结尾）切句；
    - 无句读的独立行（如标题行、列表项）按换行保留为一个单元。
    返回去除首尾空白、非空的单元列表。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for para in re.split(r"\n[ \t]*\n", text):
        para = para.strip()
        if not para:
            continue
        pieces = re.split(
            r"(?<=[。！？；])\s*|(?<=[.!?])(?=\s|$)|\n+",
            para,
        )
        for piece in pieces:
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def split_speech_text(text: str, max_chars: int = 500) -> list[str]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out: list[str] = []
    # 合并相邻短段，减少 TTS 请求数（一次提交较多句子）
    buf = ""
    for block in blocks:
        if not buf:
            buf = block
        elif len(buf) + len(block) + 2 <= max_chars:
            buf += "\n\n" + block
        else:
            out.append(buf)
            buf = block
    if buf:
        out.append(buf)
    result: list[str] = []
    for block in out:
        if len(block) <= max_chars:
            result.append(block)
            continue
        # 超长块按句切
        sentences = re.split(r"(?<=[。！？；])", block)
        cur = ""
        for s in sentences:
            if not s.strip():
                continue
            if len(cur) + len(s) <= max_chars:
                cur += s
            else:
                _append_capped(result, cur, max_chars)
                cur = s
        _append_capped(result, cur, max_chars)
    return result


def _append_capped(out: list[str], text: str, max_chars: int) -> None:
    """追加分句结果；整段仍超长（句边界不足）时按 max_chars 硬切，字符完整保留。"""
    if not text:
        return
    if len(text) <= max_chars:
        out.append(text)
    else:
        out.extend(text[i:i + max_chars] for i in range(0, len(text), max_chars))


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _normalize(data: bytes, tmp_dir: Path) -> bytes:
    src = tmp_dir / "norm_src.wav"
    dst = tmp_dir / "norm_dst.wav"
    try:
        src.write_bytes(data)
        _ffmpeg(["-y", "-i", str(src), "-ar", str(_RATE), "-ac", "1",
                 "-c:a", "pcm_s16le", str(dst)])
        return dst.read_bytes()
    finally:
        _cleanup(src, dst)


def _cleanup(*paths: Path) -> None:
    """best-effort 删除临时文件：失败不影响结果。"""
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


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
