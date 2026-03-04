from audible_epub3_maker import config

def test_azure_tts_config():
    assert config.AZURE_TTS_KEY, "AZURE_TTS_KEY is not set"
    assert config.AZURE_TTS_REGION, "AZURE_TTS_REGION is not set"
    print(f"AZURE_TTS_REGION: {config.AZURE_TTS_REGION}")


def test_apply_tts_defaults():
    from main import apply_tts_defaults

    # default Azure case (no language/voice supplied)
    args = {"tts_engine": "azure"}
    out = apply_tts_defaults(args)
    assert out["tts_lang"] == "en-US"
    assert out["tts_voice"] == "en-US-AvaMultilingualNeural"

    # kokoro with empty args should pick first language/voice
    out = apply_tts_defaults({"tts_engine": "kokoro"})
    # known voices map: languages 'a','b', default picks 'a' and first voice af_heart
    assert out["tts_lang"] == "a"
    assert out["tts_voice"] == "af_heart"

    # explicit overrides should be preserved
    custom = {"tts_engine": "kokoro", "tts_lang": "b", "tts_voice": "bf_lily"}
    out = apply_tts_defaults(custom)
    assert out["tts_lang"] == "b"
    assert out["tts_voice"] == "bf_lily"
