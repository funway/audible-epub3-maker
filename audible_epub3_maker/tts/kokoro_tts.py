import logging, io
import soundfile as sf
from pathlib import Path
from kokoro import KPipeline
from bs4 import BeautifulSoup

from audible_epub3_maker.utils.logging_setup import setup_logging
from audible_epub3_maker.tts.base_tts import BaseTTS
from audible_epub3_maker.config import settings, in_dev
from audible_epub3_maker.utils import helpers
from audible_epub3_maker.utils.constants import BEAUTIFULSOUP_PARSER
from audible_epub3_maker.utils.types import WordBoundary, TTSEmptyAudioError, TTSEmptyContentError
from audible_epub3_maker.segmenter import html_segmenter, text_segmenter

logger = logging.getLogger(__name__)

class KokoroTTS(BaseTTS):
    
    def __init__(self):
        super(KokoroTTS, self).__init__()
        
        pass
    
    def html_to_speech(self, html_text: str, output_file: Path, metadata: dict|None = None) -> list[WordBoundary]:
        output_file = Path(output_file)
        metadata = metadata or {}
        metadata.update({"artist": f"Kokoro TTS - {settings.tts_voice}", 
                         "language": f"{settings.tts_lang}",})
        
        soup = BeautifulSoup(html_text, BEAUTIFULSOUP_PARSER)
        # 1. 替换在 HTML 中 h 标签后追加 BRK 标记
        break_map = {
            "h1": "_#BRK#",
            "h2": "_#BRK#",
            "h3": "_#BRK#",
            "h4": "_#BRK#",
            "h5": "_#BRK#",
            "h6": "_#BRK#",
            "li": "_#BRK#",
            "p" : "_#BRK#",
        }
        html_segmenter.bs_append_suffix_to_tags(soup, break_map)
        
        # 2. 获取正文
        body_text = soup.body.get_text() if soup.body else soup.get_text()
        # 清洗换行符
        text = text_segmenter.normalize_newlines(body_text, settings.newline_mode)
        # 根据 BRK 标记添加换行符 (Kokoro 不识别 SSML 的 <break> 标签，只能根据换行符做朗读的停顿)
        text = text.replace("_#BRK#", "\n")
        
        # TODO: chunking

        if in_dev():
            html_file = output_file.with_suffix(".original_html.txt")
            helpers.save_text(html_text, html_file)
            
            text_file = output_file.with_suffix(".chunks.txt")
            helpers.save_text(text, text_file)

        # 剩下的就交给 Kokoro 好了，它自己会做 分句 与 chunking (不行，还是得自己做个 chunking)
        pipeline = KPipeline(lang_code=settings.tts_lang, repo_id="hexgrad/Kokoro-82M")
        generator = pipeline(text, voice=settings.tts_voice, speed=settings.tts_speed)
        chunk_results = []
        for idx, result in enumerate(generator):
            # KPipeline.Result → https://github.com/hexgrad/kokoro/blob/f1d129d8356dde124a5550ab88d61ba25620c0fd/kokoro/pipeline.py#L333
            tokens = result.tokens or []
            logger.debug(f"chunk [{idx}] result: {type(result)}") 
            logger.debug(f"  graphemes: {result.graphemes[:50]} ...")
            logger.debug(f"  phonemes: {result.phonemes[:50]} ...")
            logger.debug(f"  audio length: {len(result.audio)}")
            logger.debug(f"  tokens length: {len(tokens)}")

            # audio_chunk_file = output_file.parent / f"{output_file.stem}.part{idx}.wav"
            if result.audio is not None:
                audio_data = io.BytesIO()
                sf.write(audio_data, result.audio, 24000, format="WAV")
                audio_data.seek(0)

            wbs = []            
            for token in tokens:
                if not token.text.strip():
                    continue  # skip empty token
                if token.start_ts is None or token.end_ts is None:
                    logger.warning(f"token times error: {token}")
                    continue
                wb = WordBoundary(start_ms = token.start_ts * 1000,
                                  end_ms = token.end_ts * 1000,
                                  text = token.text)
                wbs.append(wb)

            chunk_results.append({
                "idx": idx,
                "text": result.graphemes,
                # "audio_file": audio_chunk_file,
                "audio_data": audio_data,
                "wbs": wbs,
            })
        
        # 3. merge audio and word boundaries
        merged_audio, merged_wbs = self.merge_audios_and_word_boundaries(chunk_results, key="audio_data")
        if merged_audio is None or len(merged_audio) == 0:
            raise TTSEmptyAudioError("TTS returned empty or invalid audio data.")

        # 4. save merged audio
        self.save_audio(merged_audio, output_file, metadata)

        # 5. save wbs file
        if in_dev():
            wbs_file = output_file.with_suffix(".wbs.txt")
            helpers.save_wbs_as_json(merged_wbs, wbs_file)
        
        return merged_wbs



text = '''
    [Kokoro](/kˈOkəɹO/) is an open-weight TTS model with 82 million parameters. Despite its lightweight architecture, it delivers comparable quality to larger models while being significantly faster and more cost-efficient. With Apache-licensed weights, [Kokoro](/kˈOkəɹO/) can be deployed anywhere from production environments to personal projects. [Kokoro](/kˈOkəɹO/) is an open-weight TTS model with 82 million parameters. Despite its lightweight architecture, it delivers comparable quality to larger models while being significantly faster and more cost-efficient. With Apache-licensed weights, [Kokoro](/kˈOkəɹO/) can be deployed anywhere from production environments to personal projects.
    '''

# text = '''
# 《二○○六年十一月廿七日版》 《好读书柜》经典版
#  　　明海出家已经四年了。  　　他是十三岁来的。
#  　　这个地方的地名有点怪，叫庵赵庄。赵，是因为庄上大都姓赵。叫做庄，可是人家住得很分散，这里两三家，那里两三家。一出门，远远可以看到，走起来得走一会，因为没有大路，都是弯弯曲曲的田埂。庵，是因为有一个庵。庵叫苦提庵，可是大家叫讹了，叫成荸荠庵。连庵里的和尚也这样叫。「宝刹何处？」－－「荸荠庵。」庵本来是住尼姑的。「和尚庙」、「尼姑庵」嘛。可是荸荠庵住的是和尚。也许因为荸荠庵不大，大者为庙，小者为庵。明海在家叫小明子。他是从小就确定要出家的。他的家乡不叫「出家」，叫「当和尚」。他的家乡出和尚。就像有的地方出劁猪的，有的地方出织席子的，有的地方出箍桶的，有的地方出弹棉花的，有的地方出画匠，有的地方出婊子，他的家乡出和尚。人家弟兄多，就派一个出去当和尚。当和尚也要通过关系，也有帮。这地方的和尚有的走得很远。有到杭州灵隐寺的、上海静安寺的、镇江金山寺的、扬州天宁寺的。一般的就在本县的寺庙。明海家田少，老大、老二、老三，就足够种的了。他是老四。他七岁那年，他当和尚的舅舅回家，他爹、他娘就和舅舅商议，决定叫他当和尚。他当时在旁边，觉得这实在是在情在理，没有理由反对。当和尚有很多好处。一是可以吃现成饭。哪个庙里都是管饭的。二是可以攒钱。只要学会了放瑜伽焰口，拜梁皇忏，可以按例分到辛苦钱。积攒起来，将来还俗娶亲也可以；不想还俗，买几亩田也可以。当和尚也不容易，一要面如朗月，二要声如钟磬，三要聪明记性好。他舅舅给他相了相面，叫他前走几步，后走几步，又叫他喊了一声赶牛打场的号子：「格当了－－」，说是「明子准能当个好和尚，我包了！」要当和尚，得下点本，－－念几年书。哪有不认字的和尚呢！于是明子就开蒙入学，读了《三字经》、《百家姓》、《四言杂字》、《幼学琼林》、《上论、下论》、《上孟、下孟》，每天还写一张仿。村里都夸他字写得好，很黑。
# '''


def main():
    from audible_epub3_maker.utils.constants import DEV_OUTPUT

    pipeline = KPipeline(lang_code='a')
    generator = pipeline(text, voice='af_heart', speed=0.6)
    # pipeline = KPipeline(lang_code='z')
    # generator = pipeline(text, voice='zf_xiaoxiao')
    
    chunks = []
    for idx, result in enumerate(generator):
        # KPipeline.Result → https://github.com/hexgrad/kokoro/blob/f1d129d8356dde124a5550ab88d61ba25620c0fd/kokoro/pipeline.py#L333
        # kokoro 默认根据输入 text 的换行符进行分块
        logger.debug(f"[{idx}] result: {type(result)}") 

        logger.debug(f"graphemes: {result.graphemes[:50]} ...{len(result.graphemes)}")
        logger.debug(f"phonemes: {result.phonemes[:50]} ...{len(result.phonemes)}")
        logger.debug(f"audio length: {len(result.audio)}")

        tokens = result.tokens or []
        logger.debug(f"tokens length: {len(tokens)}")
        for token in tokens[:5]:
            logger.debug(f"token: {token}")

        audio_chunk_file = DEV_OUTPUT / f'output{idx}.wav'
        if result.audio is not None:
            sf.write(DEV_OUTPUT / f'output{idx}.wav', result.audio, 24000)
        
        wbs = []            
        for token in tokens:
            wb = WordBoundary(start_ms = token.start_ts * 1000,
                                end_ms = token.end_ts * 1000,
                                text = token.text)
            wbs.append(wb)
        chunks.append({
            "idx": idx,
            "text": result.graphemes,
            "audio_file": audio_chunk_file,
            "audio_data": result.audio,
            "wbs": wbs,
        })

        pass
    
    merged_audio, merged_wbs = BaseTTS.merge_audios_and_word_boundaries(chunks)
    BaseTTS.save_audio(merged_audio, DEV_OUTPUT / "output.mp3")

    # from misaki import en
    # g2p = en.G2P()
    # ps, tokens = g2p(text)
    # logger.debug(f"\n  g2p -> ps [{len(ps)}]: {ps}")
    # logger.debug(f"\n  g2p -> tokens [{len(tokens)}]: {tokens}\n")

def test():
    graphemes = text

    chunk_size = 400
    chunks = [graphemes[i:i+chunk_size] for i in range(0, len(graphemes), chunk_size)]
    for idx, chunk in enumerate(chunks):
        logger.debug(f"{idx} - {chunk}")

def test2():
    chunk_size = 400
    chunks = []
    
    # Try to split on sentence boundaries first
    import re
    graphemes = text
    sentences = re.split(r'([.!?]+)', graphemes)
    current_chunk = ""
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        # Add the punctuation back if it exists
        if i + 1 < len(sentences):
            sentence += sentences[i + 1]
            
        if len(current_chunk) + len(sentence) <= chunk_size:
            current_chunk += sentence
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    # If no chunks were created (no sentence boundaries), fall back to character-based chunking
    logger.info(f"chunks: {chunks}")
    if not chunks:
        logger.info("fall back chunking")
        chunks = [graphemes[i:i+chunk_size] for i in range(0, len(graphemes), chunk_size)]

    logger.info(f"chunks count = {len(chunks)}")    
    # Process each chunk
    for idx, chunk in enumerate(chunks):
        logger.info(f"chunk [{idx}]: {len(chunk)}| {chunk}")
        if not chunk.strip():
            continue
        
        from misaki import zh
        g2p = zh.ZHG2P()
        ps, _ = g2p(chunk)
        logger.info(f"  ps: {ps}")
        if not ps:
            continue
        elif len(ps) > 510:
            logger.warning(f'Truncating len(ps) == {len(ps)} > 510')
            ps = ps[:510]
            logger.info(f"  ps (truncated): {len(ps)}| {ps}")

if __name__ == "__main__":
    main()
    # test2()
    
