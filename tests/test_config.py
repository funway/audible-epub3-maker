from audible_epub3_gen import config

def test_azure_tts_config():
    assert config.AZURE_TTS_KEY, "AZURE_TTS_KEY is not set"
    assert config.AZURE_TTS_REGION, "AZURE_TTS_REGION is not set"
    print(f"AZURE_TTS_REGION: {config.AZURE_TTS_REGION}")
