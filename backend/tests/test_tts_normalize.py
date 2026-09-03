from app.services.tts_normalize import normalize_for_tts


def test_pure_uppercase_acronyms_spaced():
    assert normalize_for_tts("LLM 与 ID 和 API") == "L L M 与 I D 和 A P I"
    assert normalize_for_tts("填写你的ID。") == "填写你的I D。"
    assert normalize_for_tts("检查 URL 是否正确") == "检查 U R L 是否正确"


def test_mixed_case_abbreviations_spelled():
    assert normalize_for_tts("MoE 架构") == "M O E 架构"
    assert normalize_for_tts("用 vLLM 部署") == "用 V L L M 部署"
    assert normalize_for_tts("QwQ 模型") == "Q W Q 模型"
    assert normalize_for_tts("LLM-as-Judge") == "L L M-as-Judge"
    assert normalize_for_tts("GPT-4o") == "G P T-4o"


def test_whitelist_proper_nouns_unchanged():
    assert normalize_for_tts("OpenAI 与 DeepSeek-R1 和 ChatGPT") == "OpenAI 与 DeepSeek-R1 和 ChatGPT"
    assert normalize_for_tts("GitHub、HuggingFace、LangChain") == "GitHub、HuggingFace、LangChain"
    assert normalize_for_tts("iPhone 与 macOS、Qwen、MiMo") == "iPhone 与 macOS、Qwen、MiMo"


def test_plain_words_and_single_letters_unchanged():
    assert normalize_for_tts("Agent 与 Token 是常用词") == "Agent 与 Token 是常用词"
    assert normalize_for_tts("A 与 B") == "A 与 B"
    assert normalize_for_tts("这是普通文本 123。") == "这是普通文本 123。"


def test_idempotent():
    once = normalize_for_tts("LLM、MoE、vLLM 与 OpenAI")
    assert normalize_for_tts(once) == once


def test_empty():
    assert normalize_for_tts("") == ""
