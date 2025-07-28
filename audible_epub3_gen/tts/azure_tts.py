import logging, re, html, io
from pathlib import Path
from bs4 import BeautifulSoup
from pydub import AudioSegment
from rapidfuzz import fuzz
import azure.cognitiveservices.speech as speechsdk

from audible_epub3_gen.utils import logging_setup
from audible_epub3_gen.utils import helpers
from audible_epub3_gen.utils.types import WordBoundary, TagAlignment
from audible_epub3_gen.config import AZURE_TTS_KEY, AZURE_TTS_REGION, BEAUTIFULSOUP_PARSER, SEG_MARK_ATTR, settings
from audible_epub3_gen.tts.base_tts import BaseTTS
from audible_epub3_gen.segmenter import html_segmenter, text_segmenter

logger = logging.getLogger(__name__)
# logging.getLogger('pydub.converter').setLevel(max(logging.INFO, logger.getEffectiveLevel()))

class AzureTTS(BaseTTS):
    """docstring for AzureTTS."""
  
    # max_bytes_per_request = 10_000  # Azure TTS has a limit of 10_000 bytes per request
    max_bytes_per_request = 200  # Azure TTS has a limit of 10_000 bytes per request

    def __init__(self):
        super(AzureTTS, self).__init__()
        
        pass
    
    @staticmethod
    def get_break_ssml(break_time_ms: int = 500) -> str:
        """Returns a SSML break tag with the specified time in milliseconds."""
        # Adding `\n` before the <break> tag helps improve the stability of word boundary detection, 
        # by preventing the lack of effective delimiters between words surrounding a <break> tag.
        return f'\n<break time="{break_time_ms}ms" />'

    def word_boundary_cb(self, evt, word_boundaries: list):
        """
        Callback function for Azure TTS word boundary events.
        
        Attention: This function is called in a multithreaded environment, so be careful with shared state.
        """
        # logger.debug(f"WordBoundary event: {evt.boundary_type}, audio_offset: {evt.audio_offset}, duration: {evt.duration}, \
        #              text_offset: {evt.text_offset}, word_length: {evt.word_length}, text: {evt.text}")
        start_ms = evt.audio_offset / 10000
        dur_ms = evt.duration.total_seconds() * 1000 if evt.duration else 0  # evt.duration is a timedelta object
        text = evt.text
        if evt.text_offset < 0 and evt.word_length > 0:
            # logger.warning(f"Negative text offset: 【{evt.text_offset}】. Text: 【{evt.text}】")
            text = evt.text.split()[0]
            
        wb = WordBoundary(
            start_ms = start_ms,
            end_ms = start_ms + dur_ms,
            text = text,
        )
        word_boundaries.append(wb)
        # logger.debug(f"wb_list @{id(word_boundaries)}, wb: {wb}")
        pass

    def _break_html_into_text_chunks(self, html_text: str) -> list[str]:
        """将 HTML 正文内容切分成多个文本块，每个块的大小不超过 max_bytes_per_request 字节。

        Args:
            html_text (str): _description_

        Returns:
            list[str]: _description_
        """
        # 1. 先将 HTML 分句，以及添加 SSML break 标签, 得到 sentences_and_ssml_breaks 列表。
        break_map = {
            "h1": "_#BRK3#",
            "h2": "_#BRK2#",
            "h3": "_#BRK1#",
            "h4": "_#BRK1#",
            "h5": "_#BRK1#",
            "h6": "_#BRK1#",
            "li": "_#BRK1#",
            "p" : "_#BRK1#",
        }
        html_with_break_mark = html_segmenter.append_suffix_to_tags(html_text, suffix_map=break_map)
        logger.debug(f"Breaked HTML: \n{html_with_break_mark}")
        
        soup = BeautifulSoup(html_with_break_mark, BEAUTIFULSOUP_PARSER)
        body_text = soup.body.get_text() if soup.body else soup.get_text()
        sentences_with_inline_break = text_segmenter.segment_text_by_re(body_text)
        logger.debug(f"Sentences with inline break mark: \n{sentences_with_inline_break}")
        
        sentences_and_ssml_breaks = []
        break_pattern = re.compile(r"(_#BRK\d#)")
        for sentence_with_break in sentences_with_inline_break:
            segs = break_pattern.split(sentence_with_break)
            logger.debug(f"Segmented sentence splited by break marker: {segs}")
            for idx, seg in enumerate(segs):
                if idx % 2 == 1:  # odd index is break
                    n = int(seg[5]) if seg.startswith("_#BRK") else 1
                    sentences_and_ssml_breaks.append(self.get_break_ssml(n * 500))
                else:  # even index is text
                    sentences_and_ssml_breaks.append(html.escape(seg))  # escape HTML entities
        logger.debug(f"Sentences (and ssml breaks): {sentences_and_ssml_breaks}")

        # 2. 将 sentences_and_ssml_breaks 按 max_bytes_per_request 组合成 text_chunks 给 Azure TTS 使用。
        text_chunks = []
        current_chunk = ""
        for segment in sentences_and_ssml_breaks:
            if len(current_chunk.encode('utf-8')) + len(segment.encode('utf-8')) > self.max_bytes_per_request:
                text_chunks.append(current_chunk)
                current_chunk = segment
            else:
                current_chunk += segment
        if current_chunk:
            text_chunks.append(current_chunk)
        logger.debug(f"Text chunks [{len(text_chunks)}]: {text_chunks}")
        return text_chunks

    def _text_to_speech(self, text: str, output_file: Path) -> tuple[bytes, list[WordBoundary]]:
        word_boundaries = []
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_TTS_KEY, region=AZURE_TTS_REGION)
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff16Khz16BitMonoPcm)

        audio_config = speechsdk.audio.AudioOutputConfig(filename=str(output_file))
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        synthesizer.synthesis_word_boundary.connect(lambda evt, wb_list=word_boundaries: self.word_boundary_cb(evt, wb_list))

        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="{settings.tts_lang}">'
            f'<voice name="{settings.tts_voice}"> {text} </voice>'
            f'</speak>'
        )
        logger.debug(f"SSML chunk: {ssml}")
        
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.debug("Speech synthesized to output.wav")
            logger.debug(f"data size: {len(result.audio_data)/1024:.2f} KB")
        else:
            logger.error(f"Speech synthesis failed: {result.reason}")
            logger.error(f"  Error details: {result.cancellation_details.error_details if result.cancellation_details else 'No error details'}")
            logger.error(f"  Error SSML: {ssml}")
            raise RuntimeError(f"Speech synthesis failed for reason: {result.reason}. {result.cancellation_details.error_details}")
        
        return result.audio_data, word_boundaries

    def _merge_audio_chunks_and_word_boundaries(self, chunks: list[dict]) -> tuple[AudioSegment, list[WordBoundary]]:
        merged_audio = AudioSegment.empty()
        merged_wbs = []
        current_offset = 0.0

        for chunk in chunks:
            audio_file = chunk["audio_file"]
            audio_data = chunk["audio_data"]
            wbs = chunk["wbs"]

            # 1. merge audio
            audio = AudioSegment.from_file(audio_file, format="wav")
            merged_audio += audio
            
            # 2. merge word boundaries
            for wb in wbs:
                adjusted_wb = WordBoundary(
                    start_ms = wb.start_ms + current_offset,
                    end_ms = wb.end_ms + current_offset,
                    text = wb.text,
                )
                merged_wbs.append(adjusted_wb)
            
            # 3. add current audio offset
            current_offset += len(audio)
            logger.debug(f"audio [{audio_file}] duration: {len(audio)}ms")
            pass
        
        logger.debug(f"Merged audio duration (calculated): {current_offset}ms")
        return merged_audio, merged_wbs
    
    def _save_audio(self, audio: AudioSegment, output_file: Path, metadata: dict|None = None):
        """"""
        metadata = metadata or {}

        export_format = output_file.suffix.lower().lstrip('.') or "mp3"
        if export_format not in ["wav", "mp3"]:
            logger.warning(f"Unsupported output format '{export_format}', falling back to 'mp3'")
            export_format = "mp3"
        
        audio.export(str(output_file), format=export_format, tags=metadata)
        logger.debug(f"Audio saved to {output_file}")

        # check audio time length
        final_audio = AudioSegment.from_file(output_file, format=export_format)
        logger.debug(f"Final audio duration (actual): {len(final_audio)}ms")
        pass

    def html_to_speech(self, html_text: str, output_file: Path, metadata: dict|None = None) -> list[WordBoundary]:
        """
        """
        output_file = Path(output_file)
        metadata = metadata or {}
        metadata.update({"artist": f"Azure TTS - {settings.tts_voice}", 
                         "language": f"{settings.tts_lang}",})
        
        # 1. split
        text_chunks = self._break_html_into_text_chunks(html_text)

        # 2. tts
        chunks = []
        for i, text_chunk in enumerate(text_chunks):
            audio_chunk_file = output_file.parent / f"{output_file.stem}.part{i}.wav"
            audio_chunk, word_boundaries = self._text_to_speech(text_chunk, audio_chunk_file)
            chunks.append({
                "idx": i,
                "text": text_chunk,
                "audio_file": audio_chunk_file,
                "audio_data": audio_chunk,
                "wbs": word_boundaries,
            })

        # 3. merge audio and word boundaries
        merged_audio, merged_wbs = self._merge_audio_chunks_and_word_boundaries(chunks)
        for wb in merged_wbs:
            logger.debug(f"wb: {wb}")

        # 4. save merged audio
        self._save_audio(merged_audio, output_file, metadata)
        
        return merged_wbs
  
# 这个不应该放在某个 TTS 类里面了，应该是一个 utils 的函数，或者放到 EpubBook 类里？你觉得呢？
def force_alignment_bak(html_text: str, tag_name: str, word_boundaries: list[WordBoundary]) -> list[TagAlignment]:
    """
    根据 html_text 中之前 segment and wrap 的标签 <span id="prefix+ddd">. 将其与 word_boundaries 中的字符时间进行对齐。
    返回 [id: xxxx, time_stard: xxx, time_end: xxx] 列表。
    你觉得应该给 [id: xxxx, time_stard: xxx, time_end: xxx] 这个三元组对象起个什么名字？ 叫做 Alignment?? 感觉不够清晰。

    修改一下逻辑，首先要对两边都做 nomalize, 去掉所有空格，连续拼接在一起。
    然后对于每个 sentence, 计算长度 N, 从 wb_text 中取前 N+10 个字符做相似度匹配，没匹配到就不管。继续下一个 sentence
    """
    if not len(word_boundaries):
        logger.warning(f"Word boundaries is empty!")
        return []
    
    soup = BeautifulSoup(html_text, BEAUTIFULSOUP_PARSER)
    segment_elems = soup.select(f"{tag_name}[{SEG_MARK_ATTR}]")
    segments = [ (tag["id"], tag.get_text()) for tag in segment_elems]
    logger.debug(f"segments: {segments}")
    
    result_alignments = []
    cur_left  = 0  # 当前从 wbs 中取词的起点
    cur_right = 0  # 当前从 wbs 中取词的终点+1 (= 下一次起点)
    
    for seg_id, seg_text in segments:
        logger.debug(f"force alignment: {seg_id}, {seg_text}")
        seg_text = seg_text.strip().lower()
        max_similarity = 0
        if not seg_text:
            continue
        
        cur_left = cur_right  # 初始化此次取 wb 的起点
        if cur_left >= len(word_boundaries):
            logger.warning(f"All word boundaries have been consumed, but some segment texts remain unaligned!")
            break
        
        # wb_sentence 扩展右边界，达到最大相似度
        while cur_right < len(word_boundaries):
            cur_right += 1
            wb_consumed = word_boundaries[cur_left: cur_right]
            wb_sentence = helpers.join_words(wb_consumed, "zh")
            cur_similarity = fuzz.token_sort_ratio("".join(seg_text.split()), wb_sentence.lower())
            logger.debug(f"similarity: {cur_similarity:.2f}, origin: {seg_text} 🆚 wb_sentence: {wb_sentence}")
            if cur_similarity >= max_similarity:
                max_similarity = cur_similarity
                continue
            else:
                cur_right -= 1
                break
        # wb_sentence 收缩左边界，达到最大相似度
        while cur_left < cur_right:
            cur_left += 1
            wb_consumed = word_boundaries[cur_left: cur_right]
            wb_sentence = helpers.join_words(wb_consumed, "zh")
            cur_similarity = fuzz.token_sort_ratio("".join(seg_text.split()), wb_sentence.lower())
            logger.debug(f"similarity: {cur_similarity:.2f}, origin: {seg_text} 🆚 wb_sentence: {wb_sentence}")
            if cur_similarity > max_similarity:
                max_similarity = cur_similarity
                continue
            else:
                cur_left -= 1  # restore left pointer
                break
        
        # Now, word_boundaries[cur_left: cur_right] is the most similar to the seg_text
        wb_consumed = word_boundaries[cur_left: cur_right]
        wb_sentence = helpers.join_words(wb_consumed, settings.tts_lang)
        logger.debug(f"Max similarity: {max_similarity:.2f}, origin: {seg_text} 🆚 wb_sentence: {wb_sentence}")
        alignment = TagAlignment(tag_id = seg_id, 
                                 start_ms = word_boundaries[cur_left].start_ms,
                                 end_ms = word_boundaries[cur_right-1].end_ms,
                                 )
        logger.debug(f"New alignment: {alignment}")
        result_alignments.append(alignment)
            
    return result_alignments

def main():
    # === 输入文本 (SSML with style & break) ===
    ssml = """
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
        xmlns:mstts="http://www.w3.org/2001/mstts"
        xml:lang="en-US">
    <voice name="en-US-AvaMultilingualNeural">
        <mstts:express-as style="narration">
        <prosody rate="0%">
            <mark name="ae001"/> Hello,World! It's 2025! 哈哈！Let<mark name="ae998"/>'s see what happens<mark name="ae001_end"/>.
            <mark name="ae002"/> All animals are equal, 
            <break time="500ms"/><break time="300ms"/>
            <mark name="ae003"/> but some animals are more equal than others\n<break time="10ms"/>Oh,这里还可以出现中文吗？
        </prosody>
        </mstts:express-as>
    </voice>
    </speak>
    """
    plain_text = "hello, world. My name is funway wang."

    # === 创建 Speech Synthesizer with Word Boundary ===
    speech_config = speechsdk.SpeechConfig(subscription=AZURE_TTS_KEY, region=AZURE_TTS_REGION)
    # logger.info(f"output format: {speech_config.speech_synthesis_output_format_string}, {speech_config.output_format}")
    # speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio16Khz32KBitRateMonoMp3)
    # logger.info(f"output format: {speech_config.speech_synthesis_output_format_string}, {speech_config.output_format}")
    audio_config = speechsdk.audio.AudioOutputConfig(filename=str(Path("output.wav")))
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)

    # === 创建事件回调函数 ===
    word_boundaries = []
    def word_boundary_cb(evt):
        word_boundaries.append({
            "text": evt.text,
            "offset": evt.audio_offset / 10000  # 100-nanoseconds to milliseconds
        })
        # print(f"Word: '{evt.text}' at {evt.audio_offset / 10000:.2f} ms")
        logger.debug(f"WordBoundary event: {evt.boundary_type}")
        logger.debug(f"  Text: 【{evt.text}】,   TextOffset: {evt.text_offset},   WordLength: {evt.word_length}")
        logger.debug(f"  AudioOffset: {evt.audio_offset},   Duration: {evt.duration}")

    # 监听 mark 事件
    def on_bookmark(evt):
        logger.debug(f"Mark event: {evt}.")

    # 绑定事件
    synthesizer.synthesis_word_boundary.connect(word_boundary_cb)
    synthesizer.bookmark_reached.connect(on_bookmark)


    # === 开始合成 ===
    result = synthesizer.speak_ssml_async(ssml).get()
    # result = synthesizer.speak_text_async(plain_text).get()

    # === 检查状态 ===
    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        logger.debug("Speech synthesized to output.wav")
        logger.debug(f"data size: {len(result.audio_data)/1024:.2f} KB")
    else:
        logger.error(f"Speech synthesis failed: {result.reason}")
        logger.error(f"Error details: {result.cancellation_details.error_details if result.cancellation_details else 'No error details'}")

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

    logger.debug("SMIL file written: output.smil")
    pass

def test():
    html =   '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
        <!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xmlns:m="http://www.w3.org/1998/Math/MathML" xmlns:pls="http://www.w3.org/2005/01/pronunciation-lexicon" xmlns:ssml="http://www.w3.org/2001/10/synthesis" xmlns:svg="http://www.w3.org/2000/svg">
<head><title>The Old Man and the Sea</title>
<link rel="stylesheet" type="text/css" href="docbook-epub.css"/><meta name="generator" content="DocBook XSL Stylesheets Vsnapshot_9885"/>
<style type="text/css"> img { max-width: 100%; }</style>
</head>
<body><header/><section class="chapter" title="The Old Man and the Sea" epub:type="chapter" id="id70295538646860"><div class="titlepage"><div><div><h1 class="title">The Old Man and the Sea</h1></div></div></div><p><span class="strong" id="xx003" data-ae-x="1">He was an old man who fished alone in a skiff in the Gulf Stream and he had gone <strong>eighty–four</strong> days now without taking a fish.</span> <span class="strong" id="xx005" data-ae-x="1">"<i>he</i>'s so good." said Mrs Wei.</span></p>
<span class="strong" id="xx001" data-ae-x="1">The sky is <strong>blue</strong>. The grass</span> is green. 咱们试试中英文吧？</section></body>
</html>'''

    tts = AzureTTS()
    wb_list = tts.html_to_speech(html, "output.mp3", metadata={})
    #   logger.debug(f"wb_list: {wb_list}")
    #   aligns = force_alignment(html, "span", wb_list)
    soup = BeautifulSoup(html, BEAUTIFULSOUP_PARSER)
    segment_elems = soup.select(f"span[{SEG_MARK_ATTR}]")
    segments = [ tag.get_text() for tag in segment_elems]
    logger.debug(f"segments: {segments}")
    alignments = helpers.force_alignment(segments, wb_list)
    pass


if __name__ == "__main__":
    # main()
    test()