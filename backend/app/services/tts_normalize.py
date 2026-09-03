"""送 TTS 前的文本归一化（默认预处理）。

只影响“实际送入语音引擎朗读”的文本，不修改 speech.md，也不影响字幕文本。
当前规则：把独立的全大写缩写（如 LLM、ID、API）改写为逐字母空格拼读，
避免 TTS 把它们误当英文单词导致发音异常。混合大小写/带数字的专名
（OpenAI、DeepSeek-R1、GPT-4o）与单字母保持不变；vLLM 因含 LLM 走词表。
"""

import re

# 独立的全大写缩写：前后都不是字母/数字/连字符（避免拆散 GPT-4o、LLM-as-Judge 等复合名）
_ACRONYM_RE = re.compile(r"(?<![A-Za-z0-9-])[A-Z]{2,}(?![A-Za-z0-9-])")

# 混合大小写但包含易误读大写串的专名（词边界匹配，避免命中子串）
_CURATED = [
    (re.compile(r"(?<![A-Za-z0-9])vLLM(?![A-Za-z0-9])"), "V L L M"),
]


def _spell_acronym(match: re.Match) -> str:
    return " ".join(match.group(0))


def normalize_for_tts(text: str) -> str:
    """把纯大写缩写拆成逐字母拼读；无缩写时原样返回。"""
    if not text:
        return text
    out = _ACRONYM_RE.sub(_spell_acronym, text)
    for pattern, repl in _CURATED:
        out = pattern.sub(repl, out)
    return out
