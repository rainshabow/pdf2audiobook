"""送 TTS 前的文本归一化（默认预处理）。

只影响“实际送入语音引擎朗读”的文本，不修改 speech.md，也不影响字幕文本。

判定为缩写/疑似缩写的拉丁字母串会被逐字母空格拼读（如 LLM→L L M、
MoE→M O E、vLLM→V L L M、QwQ→Q W Q），避免 TTS 把缩写当成普通英文词
读成与原文无关的音。常见专名/品牌（OpenAI、DeepSeek、ChatGPT 等）放入
白名单原样保留；若后续发现某个词被误判，只需加入 _WHITELIST。
"""

import re

_LETTER_RUN_RE = re.compile(r"[A-Za-z]+")
# “数字+K”（如 128K、32k）在技术语境常被 TTS 误读为“开尔文”；
# 转成中文数字 + 空格 K（“一百二十八 K”），引导引擎按字母读 K。
_NUM_K_RE = re.compile(r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*[Kk](?![A-Za-z0-9])")
_DIGITS = "零一二三四五六七八九"

# 白名单：TTS 可正确朗读的专名/品牌/产品名，不参与逐字母展开
_WHITELIST = {
    "OpenAI", "DeepSeek", "ChatGPT", "GitHub", "HuggingFace", "LangChain",
    "LlamaIndex", "DeepMind", "Anthropic", "YouTube", "PowerPoint", "Excel",
    "iOS", "macOS", "iPhone", "iPad", "Qwen", "MiMo", "NVIDIA",
    "CUDA", "AdamW", "ZeRO", "LoRA", "DoRA", "RoPE", "ReAct", "NVLink", "BERT",
}


def _int_cn(n: int) -> str:
    """整数转中文（支持 0 ~ 99999999，足够容量类数字）。"""
    if n == 0:
        return "零"
    if n >= 100000000:
        return str(n)  # 超范围直接保留阿拉伯数字
    units = ["", "十", "百", "千"]

    def under_wan(x: int) -> str:
        res = ""
        zero = False
        for i in range(3, -1, -1):
            d = x // (10 ** i) % 10
            if d == 0:
                if res:
                    zero = True
            else:
                if zero:
                    res += "零"
                    zero = False
                res += _DIGITS[d] + units[i]
        return res

    wan = n // 10000 % 10000
    rest = n % 10000
    out = ""
    if wan:
        out += under_wan(wan) + "万"
        if rest and rest < 1000:
            out += "零"
    if rest:
        out += under_wan(rest)
    if not out:
        out = _DIGITS[n]
    return out


def _number_cn(text_num: str) -> str:
    if "." in text_num:
        whole, _, frac = text_num.partition(".")
        w = _int_cn(int(whole or "0"))
        f = "".join(_DIGITS[int(d)] for d in frac)
        return f"{w}点{f}"
    return _int_cn(int(text_num))


def _spell_k_number(match: re.Match) -> str:
    return f"{_number_cn(match.group(1))} K"


def _is_abbreviation(run: str) -> bool:
    """启发式判断缩写：全大写串，或大小写混排且含“非词首大写”（如 MoE/vLLM）。

    长度 > 6 的字母串直接放行：此类多半是品牌/长专名，即使偶尔读错，
    逐字母朗读的听感也很差，不值得展开。
    """
    if len(run) > 6:
        return False
    if run in _WHITELIST:
        return False
    if len(run) >= 2 and run.isupper():
        return True
    upper_count = sum(1 for ch in run if ch.isupper())
    has_mid_upper = any(ch.isupper() for ch in run[1:])
    return upper_count >= 2 and has_mid_upper


def _spell_letters(run: str) -> str:
    return " ".join(run.upper())


def normalize_for_tts(text: str) -> str:
    """对疑似缩写逐字母拼读；白名单/普通单词原样返回。"""
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        run = match.group(0)
        return _spell_letters(run) if _is_abbreviation(run) else run

    # 先处理“数字+K”（避免 128KB 被拆成 128K B 后误匹配），再处理字母串
    out = _NUM_K_RE.sub(_spell_k_number, text)
    return _LETTER_RUN_RE.sub(_replace, out)
