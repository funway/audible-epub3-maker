import azure.cognitiveservices.speech as speechsdk
from audible_epub3_gen.utils import logging_setup

from audible_epub3_gen.config import AZURE_TTS_KEY, AZURE_TTS_REGION


# === 输入文本 (SSML with style & break) ===
ssml = """
<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
       xmlns:mstts="http://www.w3.org/2001/mstts"
       xml:lang="en-US">
  <voice name="en-US-AriaNeural">
    <mstts:express-as style="narration">
      <prosody rate="0%">
        Hello,Wrod! It's 2025! Let’s see what happens.
        All animals are equal,
        <break time="300ms"/>
        but some animals are more equal than others.
        <break time="500ms"/>
        The creatures outside looked from pig to man,
        and from man to pig,
        <break time="300ms"/>
        and from pig to man again;
        but already it was impossible to say which was which.
      </prosody>
    </mstts:express-as>
  </voice>
</speak>
"""

# === 创建 Speech Synthesizer with Word Boundary ===
speech_config = speechsdk.SpeechConfig(subscription=AZURE_TTS_KEY, region=AZURE_TTS_REGION)
audio_config = speechsdk.audio.AudioOutputConfig(filename="output.wav")

synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

# === 绑定 Word Boundary 事件 ===
word_boundaries = []

def word_boundary_cb(evt):
    word_boundaries.append({
        "text": evt.text,
        "offset": evt.audio_offset / 10000  # 100-nanoseconds to milliseconds
    })
    # print(f"Word: '{evt.text}' at {evt.audio_offset / 10000:.2f} ms")
    print('WordBoundary event:')
    print('\tBoundaryType: {}'.format(evt.boundary_type))
    print('\tAudioOffset: {}ms'.format((evt.audio_offset + 5000) / 10000))
    print('\tDuration: {}'.format(evt.duration))
    print('\tText: {}'.format(evt.text))
    print('\tTextOffset: {}'.format(evt.text_offset))
    print('\tWordLength: {}'.format(evt.word_length))


synthesizer.synthesis_word_boundary.connect(word_boundary_cb)

# === 开始合成 ===
result = synthesizer.speak_ssml_async(ssml).get()

# === 检查状态 ===
if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
    print("Speech synthesized to output.wav")
else:
    print(f"Speech synthesis failed: {result.reason}")
    print(f"Error details: {result.cancellation_details.error_details if result.cancellation_details else 'No error details'}")

# === 保存 Word Boundaries 为简单 SMIL ===
smil_content = """<smil xmlns="http://www.w3.org/ns/SMIL" version="3.0">
  <body>
    <seq>
"""

for i, word in enumerate(word_boundaries):
    smil_content += f'      <par>\n'
    smil_content += f'        <text src="animal_farm.xhtml#word{i}" />\n'
    smil_content += f'        <audio src="output.wav" clipBegin="{word["offset"]/1000:.3f}s" />\n'
    smil_content += f'      </par>\n'

smil_content += """    </seq>
  </body>
</smil>
"""

with open("output.smil", "w") as f:
    f.write(smil_content)

print("SMIL file written: output.smil")