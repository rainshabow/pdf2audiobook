from app.services.tts_normalize import normalize_for_tts


def test_pure_uppercase_acronyms_spaced():
    assert normalize_for_tts("LLM 与 ID 和 API") == "L L M 与 I D 和 A P I"
    assert normalize_for_tts("填写你的ID。") == "填写你的I D。"
    assert normalize_for_tts("检查 URL 是否正确") == "检查 U R L 是否正确"


def test_words_and_mixed_case_unchanged():
    # 单词/品牌名/带数字型号不应被拆字母
    assert normalize_for_tts("OpenAI、DeepSeek-R1、GPT-4o") == "OpenAI、DeepSeek-R1、GPT-4o"
    assert normalize_for_tts("MoE、QwQ、o1") == "MoE、QwQ、o1"
    # 单字母不变
    assert normalize_for_tts("A 与 B") == "A 与 B"


def test_vllm_curated_spelling():
    assert normalize_for_tts("用 vLLM 部署") == "用 V L L M 部署"
    assert normalize_for_tts("vLLM2 不处理") == "vLLM2 不处理"  # 避免命中子串


def test_no_acronym_returns_same():
    text = "这是一段没有缩写的普通文本，包含 123 与中文标点。"
    assert normalize_for_tts(text) == text
    assert normalize_for_tts("") == ""
