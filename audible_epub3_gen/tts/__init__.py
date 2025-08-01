def create_tts_engine(tts_name: str):
    tts_name = tts_name.lower()
    
    if "azure" == tts_name:
        from audible_epub3_gen.tts.azure_tts import AzureTTS
        return AzureTTS()
    
    elif "kokoro" == tts_name:
        from audible_epub3_gen.tts.kokoro_tts import KokoroTTS
        return KokoroTTS()