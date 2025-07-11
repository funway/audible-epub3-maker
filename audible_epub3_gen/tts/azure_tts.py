import azure.cognitiveservices.speech as speechsdk
from audible_epub3_gen.config import AZURE_TTS_KEY, AZURE_TTS_REGION, DEFAULT_LANGUAGE, DEFAULT_VOICE

def synthesize_speech_with_timestamps(text, output_file, language=None, voice=None):
    language = language or DEFAULT_LANGUAGE
    voice = voice or DEFAULT_VOICE

    speech_config = speechsdk.SpeechConfig(
        subscription=AZURE_TTS_KEY,
        region=AZURE_TTS_REGION
    )
    speech_config.speech_synthesis_voice_name = voice

    audio_config = speechsdk.audio.AudioOutputConfig(filename=output_file)

    synthesizer = speechsdk.SpeechSynthesizer(
        speech_config=speech_config,
        audio_config=audio_config
    )

    # 用 SSML 启用 word boundary
    ssml = f"""
    <speak version='1.0' xml:lang='{language}'>
        <voice name='{voice}'>{text}</voice>
    </speak>
    """

    def word_boundary_callback(evt):
        print(f"Word boundary: {evt.text} at {evt.audio_offset / 10000}ms")

    synthesizer.synthesis_word_boundary.connect(word_boundary_callback)

    result = synthesizer.speak_ssml_async(ssml).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        print(f"Speech synthesized to [{output_file}]")
    else:
        print(f"Speech synthesis failed: {result.reason}")

    return []  # TODO: 解析真实 boundary
