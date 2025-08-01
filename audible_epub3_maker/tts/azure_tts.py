import logging, re, html
from pathlib import Path
from bs4 import BeautifulSoup
from pydub import AudioSegment
from rapidfuzz import fuzz
import azure.cognitiveservices.speech as speechsdk

from audible_epub3_maker.utils import logging_setup
from audible_epub3_maker.utils import helpers
from audible_epub3_maker.utils.types import WordBoundary, TTSEmptyAudioError, TTSEmptyContentError
from audible_epub3_maker.utils.constants import BEAUTIFULSOUP_PARSER, SEG_MARK_ATTR, SEG_TAG
from audible_epub3_maker.config import AZURE_TTS_KEY, AZURE_TTS_REGION, settings, in_dev
from audible_epub3_maker.tts.base_tts import BaseTTS
from audible_epub3_maker.segmenter import html_segmenter, text_segmenter

logger = logging.getLogger(__name__)
# logging.getLogger('pydub.converter').setLevel(max(logging.INFO, logger.getEffectiveLevel()))

class AzureTTS(BaseTTS):
    """docstring for AzureTTS."""

    def __init__(self):
        super(AzureTTS, self).__init__()
        
        pass
    
    @staticmethod
    def get_break_ssml(break_time_ms: int = 500) -> str:
        """
        Returns an SSML <break> tag with the given pause time in milliseconds.

        A leading newline is added to improve TTS word boundary detection between words surrounding a break.
        """
        return f'\n<break time="{break_time_ms}ms" />'

    @staticmethod
    def max_chars_per_chunk() -> int:
        default = 3000
        lang = settings.tts_lang.lower()
        if lang.startswith(("zh", "ja", "ko")):
            default = 2000
        
        if settings.tts_chunk_len <= 0:
            return default
        else:
            return settings.tts_chunk_len

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
        """将 HTML 正文内容切分成多个文本块 (会引入 SSML break 标签)，每个块的大小不超过 max_chars_per_chunk。

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
        # 1.1 给 HTML 中指定的标签尾部添加 #BRK 标记 (因为 h1 的文字经常没有句号)
        html_with_break_mark = html_segmenter.append_suffix_to_tags(html_text, suffix_map=break_map)
        # logger.debug(f"HTML with BREAK mark: \n{html_with_break_mark}")
        
        soup = BeautifulSoup(html_with_break_mark, BEAUTIFULSOUP_PARSER)
        body_text = soup.body.get_text() if soup.body else soup.get_text()
        
        # 1.2 处理换行符，对于 TTS 而言，换行符会认为是发音的一个停顿，空格则不会引起停顿。
        # 而对于 HTML 而言，一个标签文本中的换行符通常是无效的。
        if settings.newline_mode == "single":
            cleaned_text = body_text
        elif settings.newline_mode == "multi":
            tmp_text = re.sub(r"\n(?:\s*\n)+", "_#NLINE#_", body_text)  # 多个换行 => 标记
            tmp_text = re.sub(r"\n", " ", tmp_text)                     # 单个换行 => 空格
            cleaned_text = tmp_text.replace("_#NLINE#_", "\n")          # 多个换行 => 单个换行
        elif settings.newline_mode == "none":
            cleaned_text = re.sub(r"\n+", " ", body_text)
        else:
            raise ValueError(f"Unsupported newline_mode: {settings.newline_mode}")

        # 1.3 带着 #BRK 标记做分句
        sentences_with_inline_break_mark = text_segmenter.segment_text_by_re(cleaned_text)
        # logger.debug(f"Sentences with inline break mark: \n{sentences_with_inline_break_mark}")
        
        # 1.4 替换 #BRK 标记为 SSML 支持的 <break 标签>
        sentences_and_ssml_breaks = []
        break_pattern = re.compile(r"(_#BRK\d#)")
        for sentence_with_break in sentences_with_inline_break_mark:
            segs = break_pattern.split(sentence_with_break)
            for idx, seg in enumerate(segs):
                if idx % 2 == 1:  # odd index is break
                    n = int(seg[5]) if seg.startswith("_#BRK") else 1
                    sentences_and_ssml_breaks.append(AzureTTS.get_break_ssml(n * 500))
                else:  # even index is text
                    sentences_and_ssml_breaks.append(html.escape(seg))  # escape HTML entities
        # logger.debug(f"Sentences (and ssml breaks): {sentences_and_ssml_breaks}")

        # 2. 将 sentences_and_ssml_breaks 按 max_bytes_per_request 组合成 text_chunks 给 Azure TTS 使用。
        text_chunks = []
        current_chunk = ""
        for segment in sentences_and_ssml_breaks:
            # if len(current_chunk.encode('utf-8')) + len(segment.encode('utf-8')) > self.max_bytes_per_request:
            if len(current_chunk) + len(segment) > AzureTTS.max_chars_per_chunk():
                text_chunks.append(current_chunk)
                current_chunk = segment
            else:
                current_chunk += segment
        if current_chunk.strip():  # skip empty chunk
            text_chunks.append(current_chunk)
        
        # logger.debug(f"Text chunks [{len(text_chunks)}]: {text_chunks}")
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
            f'xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="{settings.tts_lang}">\n'
            f'  <voice name="{settings.tts_voice}">\n'
            f'    {text}\n'
            f'  </voice>\n'
            f'</speak>'
        )
        
        result = synthesizer.speak_ssml_async(ssml).get()
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            logger.debug(f"Speech synthesized to {output_file}")
            logger.debug(f"  data size: {len(result.audio_data)/1024:.2f} KB")
        else:
            logger.error(f"Speech synthesis failed: {result.reason}")
            logger.error(f"  Error details: {result.cancellation_details.error_details if result.cancellation_details else 'No error details'}")
            logger.debug(f"  Error SSML: {ssml}")

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
        Converts an HTML string into a speech audio file and returns word-level alignment information.

        This method performs the following steps:
        1. Parses and segments the input HTML into readable text chunks.
        2. Synthesizes each chunk using TTS and collects word boundary metadata.
        3. Merges all audio chunks and boundary data into a single output.
        4. Saves the merged audio to the specified output path with optional metadata.

        Args:
            html_text (str): HTML content to be synthesized into speech.
            output_file (Path): Path to save the final merged audio file (e.g., output.wav).
            metadata (dict | None): Optional metadata for the audio file (e.g., title, language, voice).

        Returns:
            list[WordBoundary]: A list of word boundary objects representing the alignment information.
        """
        output_file = Path(output_file)
        metadata = metadata or {}
        metadata.update({"artist": f"Azure TTS - {settings.tts_voice}", 
                         "language": f"{settings.tts_lang}",})
        
        # 1. split
        text_chunks = self._break_html_into_text_chunks(html_text)
        if not text_chunks:
            raise TTSEmptyContentError("Input HTML contains no valid text content.")
        if in_dev():
            html_file = output_file.with_suffix(".original_html.txt")
            helpers.save_text(html_text, html_file)
            
            merged_texts = "\n\n##### chunk ######\n\n".join(text_chunks)
            text_file = output_file.with_suffix(".chunks.txt")
            helpers.save_text(merged_texts, text_file)
        
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
        if merged_audio is None or len(merged_audio) == 0:
            raise TTSEmptyAudioError("TTS returned empty or invalid audio data.")
        
        # 4. save merged audio
        self._save_audio(merged_audio, output_file, metadata)
        
        # 5. save wbs file
        if in_dev():
            wbs_file = output_file.with_suffix(".wbs.txt")
            helpers.save_wbs_as_json(merged_wbs, wbs_file)
        
        # 5. clear temp audio_chunk
        for chunk in chunks:
            chunk["audio_file"].unlink(missing_ok=True)

        return merged_wbs
  

def main():
    # === 输入文本 (SSML with style & break) ===
    ssml = """
    <speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
        xmlns:mstts="http://www.w3.org/2001/mstts"
        xml:lang="en-US">
    <voice name="en-us-avaMultilingualNeural">
受戒》汪曾祺
<break time="500ms" />《二○○六年十一月廿七日版》 《好讀書櫃》經典版
 　　明海出家已經四年了。  　　他是十三歲來的。  　　這個地方的地名有點怪，叫庵趙莊。趙，是因為莊上大都姓趙。叫做莊，可是人家住得很分散，這裡兩三家，那裡兩三家。一出門，遠遠可以看到，走起來得走一會，因為沒有大路，都是彎彎曲曲的田埂。庵，是因為有一個庵。庵叫苦提庵，可是大家叫訛了，叫成荸薺庵。連庵裡的和尚也這樣叫。「寶剎何處？」－－「荸薺庵。」庵本來是住尼姑的。「和尚廟」、「尼姑庵」嘛。可是荸薺庵住的是和尚。也許因為荸薺庵不大，大者為廟，小者為庵。  　　明海在家叫小明子。他是從小就確定要出家的。他的家鄉不叫「出家」，叫「當和尚」。他的家鄉出和尚。就像有的地方出劁豬的，有的地方出織蓆子的，有的地方出箍桶的，有的地方出彈棉花的，有的地方出畫匠，有的地方出婊子，他的家鄉出和尚。人家弟兄多，就派一個出去當和尚。當和尚也要通過關係，也有幫。這地方的和尚有的走得很遠。有到杭州靈隱寺的、上海靜安寺的、鎮江金山寺的、揚州天寧寺的。一般的就在本縣的寺廟。明海家田少，老大、老二、老三，就足夠種的了。他是老四。他七歲那年，他當和尚的舅舅回家，他爹、他娘就和舅舅商議，決定叫他當和尚。他當時在旁邊，覺得這實在是在情在理，沒有理由反對。當和尚有很多好處。一是可以吃現成飯。哪個廟裡都是管飯的。二是可以攢錢。只要學會了放瑜伽焰口，拜梁皇懺，可以按例分到辛苦錢。積攢起來，將來還俗娶親也可以；不想還俗，買幾畝田也可以。當和尚也不容易，一要面如朗月，二要聲如鐘磬，三要聰明記性好。他舅舅給他相了相面，叫他前走幾步，後走幾步，又叫他喊了一聲趕牛打場的號子：「格當了－－」，說是「明子準能當個好和尚，我包了！」要當和尚，得下點本，－－念幾年書。哪有不認字的和尚呢！於是明子就開蒙入學，讀了《三字經》、《百家姓》、《四言雜字》、《幼學瓊林》、《上論、下論》、《上孟、下孟》，每天還寫一張仿。村裡都誇他字寫得好，很黑。  　　舅舅按照約定的日期又回了家，帶了一件他自己穿的和尚領的短衫，叫明子娘改小一點，給明子穿上。明子穿了這件和尚短衫，下身還是在家穿的紫花褲子，赤腳穿了一雙新布鞋，跟他爹、他娘磕了一個頭，就隨舅舅走了。  　　他上學時起了個學名，叫明海。舅舅說，不用改了。於是「明海」就從學名變成了法名。  　　過了一個湖。好大一個湖！穿過一個縣城。縣城真熱鬧：官鹽店，稅務局，肉鋪裡掛著成邊的豬，一個驢子在磨芝麻，滿街都是小磨香油的香味，布店，賣茉莉粉、梳頭油的什麼齋，賣絨花的，賣絲線的，打把式賣膏藥的，吹糖人的，耍蛇的，－－他什麼都想看看。舅舅一勁地推他：「快走！快走！」  　　到了一個河邊，有一隻船在等著他們。船上有一個五十來歲的瘦長瘦長的大伯，船頭蹲著一個跟明子差不多大的女孩子，在剝一個蓮蓬吃。明子和舅舅坐到艙裡，船就開了。明子聽見有人跟他說話，是那個女孩子。  　　「是你要到荸薺庵當和尚嗎？」  　　明子點點頭。  　　「當和尚要燒戒疤嘔！你不怕？」  　　明子不知道怎麼回答，就含含糊糊地搖了搖頭。  　　「你叫什麼？」  　　「明海。」  　　「在家的時候？」  　　「叫明子。」  　　「明子！我叫小英子！我們是鄰居。我家挨著荸薺庵。－－給你！」  　　小英子把吃剩的半個蓮蓬扔給明海，小明子就剝開蓮蓬殼，一顆一顆吃起來。  　　大伯一槳一槳地划著，只聽見船槳撥水的聲音：「嘩－－許！嘩－－許！」  　　－－  　　荸薺庵的地勢很好，在一片高地上。這一帶就數這片地勢高，當初建庵的人很會選地方。門前是一條河。門外是一片很大的打穀場。三面都是高大的柳樹。山門裡是一個穿堂。迎門供著彌勒佛。不知是哪一位名士撰寫了一副對聯：  　　大肚能容　容天下難容之事 　　開顏一笑　笑世間可笑之人  　　彌勒佛背後，是韋馱。過穿堂，是一個不小的天井，種著兩棵白果樹。天井兩邊各有三間廂房。走過天井，便是大殿，供著三世佛。佛像連龕才四尺來高。大殿東邊是方丈，西邊是庫房。大殿東側，有一個小小的六角門，白門綠字，刻著一副對聯：  　　一花一世界  　　三藐三菩提  　　進門有一個狹長的天井，幾塊假山石，幾盆花，有三間小房。  　　小和尚的日子清閒得很。一早起來，開山門，掃地。庵裡的地鋪的都是籮底方磚，好掃得很，給彌勒佛、韋馱燒一炷香，正殿的三世佛面前也燒一炷香、磕三個頭、念三聲「南無阿彌陀佛」，敲三聲磬。這庵裡的和尚不興做什麼早課、晚課，明子這三聲磬就全都代替了。然後，挑水，餵豬。然後，等當家和尚，即明子的舅舅起來，教他唸經。  　　教唸經也跟教書一樣，師父面前一本經，徒弟面前一本經，師父唱一句，徒弟跟著唱一句。是唱哎。舅舅一邊唱，一邊還用手在桌上拍板。一板一眼，拍得很響，就跟教唱戲一樣。是跟教唱戲一樣，完全一樣哎。連用的名詞都一樣。舅舅說，唸經：一要板眼準，二要合工尺。說：當一個好和尚，得有條好嗓子。說：民國二十年鬧大水，運河倒了堤，最後在清水潭合龍，因為大水淹死的人很多，放了一台大焰口，十三大師－－十三個正座和尚，各大廟的方丈都來了，下面的和尚上百。誰當這個首座？推來推去，還是石橋－－善因寺的方丈！他往上一坐，就跟地藏王菩薩一樣，這就不用說了；那一聲「開香贊」，圍看的上千人立時鴉雀無聲。說：嗓子要練，夏練三伏，冬練三九，要練丹田氣！說：要吃得苦中苦，方為人上人！說：和尚裡也有狀元、榜眼、探花！要用心，不要貪玩！舅舅這一番大法要說得明海和尚實在是五體投地，於是就一板一眼地跟著舅舅唱起來：  　　「爐香乍爇－－」  　　「爐香乍爇－－」  　　「法界蒙薰－－」  　　「法界蒙薰－－」  　　「諸佛現金身－－」  　　「諸佛現金身－－」  　　－－  　　等明海學完了早經，－－他晚上臨睡前還要學一段，叫做晚經，－－荸薺庵的師父們就都陸續起床了。  　　這庵裡人口簡單，一共六個人。連明海在內，五個和尚。有一個老和尚，六十幾了，是舅舅的師叔，法名普照，但是知道的人很少，因為很少人叫他法名，都稱之為老和尚或老師父，明海叫他師爺爺。這是個很枯寂的人，一天關在房裡，就是那「一花一世界」裡。也看不見他念佛，只是那麼一聲不響地坐著。他是吃齋的，過年時除外。  　　下面就是師兄弟三個，仁字排行：仁山、仁海、仁渡。庵裡庵外，有的稱他們為大師父、二師父；有的稱之為山師父、海師父。只有仁渡，沒有叫他「渡師父」的，因為聽起來不像話，大都直呼之為仁渡。他也只配如此，因為他還年輕，才二十多歲。仁山，即明子的舅舅，是當家的。不叫「方丈」，也不叫「住持」，卻叫「當家的」，是很有道理的，因為他確確實實幹的是當家的職務。他屋裡擺的是一張帳桌，桌子上放的是帳簿和算盤。帳簿共有三本。一本是經帳，一本是租帳，一本是債帳。和尚要做法事，做法事要收錢，－－要不，當和尚幹什麼？常做的法事是放焰口。正規的焰口是十個人。一個正座，一個敲鼓的，兩邊一邊四個。人少了，八個，一邊三個，也湊合了。荸薺庵只有四個和尚，要放整焰口就得和別的廟裡合夥。這樣的時候也有過，通常只是放半台焰口。一個正座，一個敲鼓，另外一邊一個。一來找別的廟裡合夥費事；二來這一帶放得起整焰口的人家也不多。有的時候，誰家死了人，就只請兩個，
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
<body><header/><section class="chapter" title="The Old Man and the Sea" epub:type="chapter" id="id70295538646860"><div class="titlepage"><div><div><h1 class="title"><span class="strong" id="xx013" data-ae-x="1">The Old Man and the Sea</span></h1></div></div></div><p><span class="strong" id="xx003" data-ae-x="1">He was an old man who fished alone in a skiff in the Gulf Stream and he had gone <strong>eighty–four</strong> days now without taking a fish.</span> <span class="strong" id="xx005" data-ae-x="1">"</span><i><span id="xx006" data-ae-x="1">he</span></i><span id="xx007" data-ae-x="1">'s so good." said Mrs Wei.</span></p>
<span class="strong" id="xx001" data-ae-x="1">The sky he is <strong>blue</strong>. The grass</span> is green. 咱们试试中英文吧？</section></body>
</html>'''

    html = '''
<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<title>受戒</title>
<meta content="text/html; charset=utf-8" http-equiv="Content-Type"/>
<link href="stylesheet.css" rel="stylesheet" type="text/css"/>
<link href="page_styles.css" rel="stylesheet" type="text/css"/>
</head>
<body class="calibre"><div class="calibre1" id="filepos109"><p class="calibre2"><span class="calibre3"><span class="bold"><span data-ae-x="1" id="ae00001">《受戒》汪曾祺</span></span></span></p><p class="calibre4"><span data-ae-x="1" id="ae00002">《二○○六年十一月廿七日版》</span><br class="calibre1"/><span data-ae-x="1" id="ae00003"> 《好讀書櫃》經典版</span><br class="calibre1"/>
<br class="calibre1"/>
<br class="calibre1"/><span data-ae-x="1" id="ae00004"> 　　明海出家已經四年了。</span><br class="calibre1"/>
<br class="calibre1"/><span data-ae-x="1" id="ae00005"> 　　他是十三歲來的。</span><br class="calibre1"/>
<br class="calibre1"/><span data-ae-x="1" id="ae00006"> 　　這個地方的地名有點怪，</span><span data-ae-x="1" id="ae00007">叫庵趙莊。</span><span data-ae-x="1" id="ae00008">趙，</span><span data-ae-x="1" id="ae00009">是因為莊上大都姓趙。</span><span data-ae-x="1" id="ae00010">叫做莊，</span><span data-ae-x="1" id="ae00011">可是人家住得很分散，</span><span data-ae-x="1" id="ae00012">這裡兩三家，</span><span data-ae-x="1" id="ae00013">那裡兩三家。</span><span data-ae-x="1" id="ae00014">一出門，</span><span data-ae-x="1" id="ae00015">遠遠可以看到，</span><span data-ae-x="1" id="ae00016">走起來得走一會，</span><span data-ae-x="1" id="ae00017">因為沒有大路，</span><span data-ae-x="1" id="ae00018">都是彎彎曲曲的田埂。</span><span data-ae-x="1" id="ae00019">庵，</span><span data-ae-x="1" id="ae00020">是因為有一個庵。</span><span data-ae-x="1" id="ae00021">庵叫苦提庵，</span><span data-ae-x="1" id="ae00022">可是大家叫訛了，</span><span data-ae-x="1" id="ae00023">叫成荸薺庵。</span><span data-ae-x="1" id="ae00024">連庵裡的和尚也這樣叫。</span><span data-ae-x="1" id="ae00025">「寶剎何處？」</span><span data-ae-x="1" id="ae00026">－－「荸薺庵。」</span><span data-ae-x="1" id="ae00027">庵本來是住尼姑的。</span><span data-ae-x="1" id="ae00028">「和尚廟」、「尼姑庵」嘛。</span><span data-ae-x="1" id="ae00029">可是荸薺庵住的是和尚。</span><span data-ae-x="1" id="ae00030">也許因為荸薺庵不大，</span><span data-ae-x="1" id="ae00031">大者為廟，</span><span data-ae-x="1" id="ae00032">小者為庵。</span><br class="calibre1"/>
<br class="calibre1"/><span data-ae-x="1" id="ae00033"> 　　明海在家叫小明子。</span><span data-ae-x="1" id="ae00034">他是從小就確定要出家的。</span><span data-ae-x="1" id="ae00035">他的家鄉不叫「出家」，</span><span data-ae-x="1" id="ae00036">叫「當和尚」。</span><span data-ae-x="1" id="ae00037">他的家鄉出和尚。</span><span data-ae-x="1" id="ae00038">就像有的地方出劁豬的，</span><span data-ae-x="1" id="ae00039">有的地方出織蓆子的，</span><span data-ae-x="1" id="ae00040">有的地方出箍桶的，</span><span data-ae-x="1" id="ae00041">有的地方出彈棉花的，</span><span data-ae-x="1" id="ae00042">有的地方出畫匠，</span><span data-ae-x="1" id="ae00043">有的地方出婊子，</span><span data-ae-x="1" id="ae00044">他的家鄉出和尚。</span><span data-ae-x="1" id="ae00045">人家弟兄多，</span><span data-ae-x="1" id="ae00046">就派一個出去當和尚。</span><span data-ae-x="1" id="ae00047">當和尚也要通過關係，</span><span data-ae-x="1" id="ae00048">也有幫。</span><span data-ae-x="1" id="ae00049">這地方的和尚有的走得很遠。</span><span data-ae-x="1" id="ae00050">有到杭州靈隱寺的、上海靜安寺的、鎮江金山寺的、揚州天寧寺的。</span><span data-ae-x="1" id="ae00051">一般的就在本縣的寺廟。</span><span data-ae-x="1" id="ae00052">明海家田少，</span><span data-ae-x="1" id="ae00053">老大、老二、老三，</span><span data-ae-x="1" id="ae00054">就足夠種的了。</span><span data-ae-x="1" id="ae00055">他是老四。</span><span data-ae-x="1" id="ae00056">他七歲那年，</span><span data-ae-x="1" id="ae00057">他當和尚的舅舅回家，</span><span data-ae-x="1" id="ae00058">他爹、他娘就和舅舅商議，</span><span data-ae-x="1" id="ae00059">決定叫他當和尚。</span><span data-ae-x="1" id="ae00060">他當時在旁邊，</span><span data-ae-x="1" id="ae00061">覺得這實在是在情在理，</span><span data-ae-x="1" id="ae00062">沒有理由反對。</span><span data-ae-x="1" id="ae00063">當和尚有很多好處。</span><span data-ae-x="1" id="ae00064">一是可以吃現成飯。</span><span data-ae-x="1" id="ae00065">哪個廟裡都是管飯的。</span><span data-ae-x="1" id="ae00066">二是可以攢錢。</span><span data-ae-x="1" id="ae00067">只要學會了放瑜伽焰口，</span><span data-ae-x="1" id="ae00068">拜梁皇懺，</span><span data-ae-x="1" id="ae00069">可以按例分到辛苦錢。</span><span data-ae-x="1" id="ae00070">積攢起來，</span><span data-ae-x="1" id="ae00071">將來還俗娶親也可以；</span><span data-ae-x="1" id="ae00072">不想還俗，</span><span data-ae-x="1" id="ae00073">買幾畝田也可以。</span><span data-ae-x="1" id="ae00074">當和尚也不容易，</span><span data-ae-x="1" id="ae00075">一要面如朗月，</span><span data-ae-x="1" id="ae00076">二要聲如鐘磬，</span><span data-ae-x="1" id="ae00077">三要聰明記性好。</span><span data-ae-x="1" id="ae00078">他舅舅給他相了相面，</span><span data-ae-x="1" id="ae00079">叫他前走幾步，</span><span data-ae-x="1" id="ae00080">後走幾步，</span><span data-ae-x="1" id="ae00081">又叫他喊了一聲趕牛打場的號子：「格當了－－」，</span><span data-ae-x="1" id="ae00082">說是「明子準能當個好和尚，</span><span data-ae-x="1" id="ae00083">我包了！」</span><span data-ae-x="1" id="ae00084">要當和尚，</span><span data-ae-x="1" id="ae00085">得下點本，</span><span data-ae-x="1" id="ae00086">－－念幾年書。</span><span data-ae-x="1" id="ae00087">哪有不認字的和尚呢！</span><span data-ae-x="1" id="ae00088">於是明子就開蒙入學，</span><span data-ae-x="1" id="ae00089">讀了《三字經》、《百家姓》、《四言雜字》、《幼學瓊林》、《上論、下論》、《上孟、下孟》，</span><span data-ae-x="1" id="ae00090">每天還寫一張仿。</span><span data-ae-x="1" id="ae00091">村裡都誇他字寫得好，</span><span data-ae-x="1" id="ae00092">很黑。</span><br class="calibre1"/>
</body>
</html>
    '''

#     html = '''
# <html xmlns="http://www.w3.org/1999/xhtml">
# <head><meta content="application/xhtml+xml; charset=utf-8" http-equiv="Content-Type"/>
# <link href="page-template.xpgt" rel="stylesheet" type="application/vnd.adobe-page-template+xml"/>
# <title>Harry Potter and the Prisoner of Azkaban - Chapter 3</title>
# <link href="flow0001.css" rel="stylesheet" type="text/css"/>
# </head>
# <body style="font-family:serif;"><div/>
# <p class="pagebreak EPubfirstparagraph Epubpagerstart" id="hp3_ch3"> </p>
# <p> </p>
# <h4><span data-ae-x="1" id="ae00001">– CHAPTER THREE –</span></h4>
# <p> </p>
# <h1 class="chaptitle"><span data-ae-x="1" id="ae00002">The Knight Bus</span></h1>
# <p class="first"><span data-ae-x="1" id="ae00003">Harry was several streets away before he collapsed onto a low wall in Magnolia Crescent,</span><span data-ae-x="1" id="ae00004"> panting from the effort of dragging his trunk.</span><span data-ae-x="1" id="ae00005"> He sat quite still,</span><span data-ae-x="1" id="ae00006"> anger still surging through him,</span><span data-ae-x="1" id="ae00007"> listening to the frantic thumping of his heart.</span></p>
# <p><span data-ae-x="1" id="ae00008">But after ten minutes alone in the dark street,</span><span data-ae-x="1" id="ae00009"> a new emotion overtook him: panic.</span><span data-ae-x="1" id="ae00010"> Whichever way he looked at it,</span><span data-ae-x="1" id="ae00011"> he had never been in a worse fix.</span><span data-ae-x="1" id="ae00012"> He was stranded,</span><span data-ae-x="1" id="ae00013"> quite alone,</span><span data-ae-x="1" id="ae00014"> in the dark Muggle world,</span><span data-ae-x="1" id="ae00015"> with absolutely nowhere to go.</span><span data-ae-x="1" id="ae00016"> And the worst of it was,</span><span data-ae-x="1" id="ae00017"> he had just done serious magic,</span><span data-ae-x="1" id="ae00018"> which meant that he was almost certainly expelled from Hogwarts.</span><span data-ae-x="1" id="ae00019"> He had broken the Decree for the Restriction of Underage Wizardry so badly,</span><span data-ae-x="1" id="ae00020"> he was surprised Ministry of Magic representatives weren’t swooping down on him where he sat.</span></p>
# <p><span data-ae-x="1" id="ae00021">Harry shivered and looked up and down Magnolia Crescent.</span><span data-ae-x="1" id="ae00022"> What was going to happen to him?</span><span data-ae-x="1" id="ae00023"> Would he be arrested,</span><span data-ae-x="1" id="ae00024"> or would he simply be outlawed from the wizarding world?</span><span data-ae-x="1" id="ae00025"> He thought of Ron and Hermione,</span><span data-ae-x="1" id="ae00026"> and his heart sank even lower.</span><span data-ae-x="1" id="ae00027"> Harry was sure that,</span><span data-ae-x="1" id="ae00028"> criminal or not,</span><span data-ae-x="1" id="ae00029"> Ron and Hermione would want to help him now,</span><span data-ae-x="1" id="ae00030"> but they were both abroad,</span><span data-ae-x="1" id="ae00031"> and with Hedwig gone,</span><span data-ae-x="1" id="ae00032"> he had no means of contacting them.</span></p>
# <p><span data-ae-x="1" id="ae00033">He didn’t have any Muggle money,</span><span data-ae-x="1" id="ae00034"> either.</span><span data-ae-x="1" id="ae00035"> There was a little wizard gold in the moneybag at the bottom of his trunk,</span><span data-ae-x="1" id="ae00036"> but the rest of the fortune his parents had left him was stored in a vault at Gringotts Wizarding Bank in London.</span><span data-ae-x="1" id="ae00037"> He’d never be able to drag his trunk all the way to London.</span><span data-ae-x="1" id="ae00038"> Unless …</span></p>
# <p><span data-ae-x="1" id="ae00039">He looked down at his wand,</span><span data-ae-x="1" id="ae00040"> which he was still clutching in his hand.</span><span data-ae-x="1" id="ae00041"> If he was already expelled (his heart was now thumping painfully fast),</span><span data-ae-x="1" id="ae00042"> a bit more magic couldn’t hurt.</span><span data-ae-x="1" id="ae00043"> He had the Invisibility Cloak he had inherited from his father – what if he bewitched the trunk to make it feather-light,</span><span data-ae-x="1" id="ae00044"> tied it to his broomstick,</span><span data-ae-x="1" id="ae00045"> covered himself in the Cloak and flew to London?</span><span data-ae-x="1" id="ae00046"> Then he could get the rest of his money out of his vault and … begin his life as an outcast.</span><span data-ae-x="1" id="ae00047"> It was a horrible prospect,</span><span data-ae-x="1" id="ae00048"> but he couldn’t sit on this wall for ever or he’d find himself trying to explain to Muggle police why he was out in the dead of night with a trunkful of spellbooks and a broomstick.</span></p>
# <p><span data-ae-x="1" id="ae00049">Harry opened his trunk again and pushed the contents aside,</span><span data-ae-x="1" id="ae00050"> looking for the Invisibility Cloak – but before he had found it,</span><span data-ae-x="1" id="ae00051"> he straightened up suddenly,</span><span data-ae-x="1" id="ae00052"> looking around him once more.</span></p>
# <p><span data-ae-x="1" id="ae00053">A funny prickling on the back of his neck had made Harry feel he was being watched,</span><span data-ae-x="1" id="ae00054"> but the street appeared to be deserted,</span><span data-ae-x="1" id="ae00055"> and no lights shone from any of the large square houses.</span></p>
# </body></html>
# '''
    html = '''
<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=UTF-8"/>
        <meta name="calibre:cover" content="true"/>
        <title>Cover</title>
        <style type="text/css" title="override_css">
            @page {padding: 0pt; margin:0pt}
            body { text-align: center; padding:0pt; margin: 0pt; }
        </style>
    </head>
    <body>
        <div>
            <svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1" width="100%" height="100%" viewBox="0 0 250 402" preserveAspectRatio="none">
                <p><image width="250" height="402" xlink:href="cover.jpeg"/></p>
            </svg>
        </div>
    </body>
</html>

'''

    tts = AzureTTS()

    wb_list = tts.html_to_speech(html, "output.mp3", metadata={})
    #   logger.debug(f"wb_list: {wb_list}")
    #   aligns = force_alignment(html, "span", wb_list)
    
    wbs_file = "outpu.wbs"
    helpers.save_wbs_as_json(wb_list, wbs_file)

    soup = BeautifulSoup(html, BEAUTIFULSOUP_PARSER)
    segment_elems = soup.select(f"{SEG_TAG}[{SEG_MARK_ATTR}]")
    # segments = [ tag.get_text() for tag in segment_elems]
    idx_segments = [(tag.get("id"), tag.get_text()) for tag in segment_elems]
    logger.debug(f"segments: {idx_segments}")
    alignments = helpers.force_alignment(idx_segments, wb_list)
    # logger.debug(alignments)
    print(helpers.generate_smil("text/01.smil", "text/ch01.xhtml", "audio/aud_01.mp3", alignments))
    pass


if __name__ == "__main__":
    main()
    # test()