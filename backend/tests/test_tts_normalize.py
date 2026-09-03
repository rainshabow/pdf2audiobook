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
    assert normalize_for_tts("NVIDIA GPU 与 AMD") == "NVIDIA G P U 与 A M D"  # NVIDIA 整词读，GPU/AMD 逐字母
    for w in ["CUDA", "AdamW", "ZeRO", "LoRA", "DoRA", "RoPE", "ReAct", "NVLink", "BERT"]:
        assert normalize_for_tts(w) == w, w
    # QLoRA 未入选白名单，仍按逐字母展开
    assert normalize_for_tts("LoRA 与 QLoRA") == "LoRA 与 Q L O R A"


def test_plain_words_and_single_letters_unchanged():
    assert normalize_for_tts("Agent 与 Token 是常用词") == "Agent 与 Token 是常用词"
    assert normalize_for_tts("A 与 B") == "A 与 B"
    assert normalize_for_tts("这是普通文本 123。") == "这是普通文本 123。"


def test_longer_than_six_letters_pass_through():
    # >6 字母直接放行（即使含混排大写/全大写也不再展开）
    assert normalize_for_tts("AutoGPT 与 AgentGPT") == "AutoGPT 与 AgentGPT"
    assert normalize_for_tts("TensorFlow、PyTorch") == "TensorFlow、PyTorch"
    assert normalize_for_tts("ABCDEFGH") == "ABCDEFGH"
    # 6 字母及以下仍按缩写规则展开
    assert normalize_for_tts("ABCDEF") == "A B C D E F"


def test_idempotent():
    once = normalize_for_tts("LLM、MoE、vLLM 与 OpenAI")
    assert normalize_for_tts(once) == once


def test_empty():
    assert normalize_for_tts("") == ""
