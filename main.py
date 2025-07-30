import argparse
import logging
from pathlib import Path

from audible_epub3_gen.config import settings
from audible_epub3_gen.app import App

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Audible-style EPUB with TTS narration.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # 1. input_file 作为位置参数
    parser.add_argument("input_file", 
                        type=Path, 
                        help="Input EPUB file"
                        )

    # 2. 输出目录参数，支持 -d 和 --output_dir
    parser.add_argument(
        "-d", "--output_dir",
        type=Path,
        help="Output directory (default: <input_file>_audible)"
    )

    # 3. 日志等级
    parser.add_argument(
        "--log_level",
        type=str.upper,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="Logging level (default: INFO)"
    )

    # 4. TTS 引擎
    parser.add_argument(
        "--tts_engine",
        type=str.lower,
        choices=["azure", "kokoro"],
        default="azure",
        help=(
            "TTS engine to use (default: azure). \n"
            "Voice & language references: \n"
            "  Azure: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts \n"
            "  Kokoro: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md"
        )
    )

    # 5. TTS 语言
    parser.add_argument(
        "--tts_lang",
        default="en-US",
        help="Language code for TTS (default: en-US for Azure)"
    )

    # 6. TTS 声音
    parser.add_argument(
        "--tts_voice",
        default="en-US-AvaMultilingualNeural",
        help="Voice name for TTS (default: en-US-AvaMultilingualNeural for Azure)"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        default=False,
        help="Force all prompts to be accepted (non-interactive mode)"
    )

    parser.add_argument(
        "-m", "--max_workers",
        type=int,
        default=3,
        help="Max count of multi-processing workers for audio and alignment generating (default: 3)"
    )

    return parser.parse_args()

def main():
    args = vars(parse_args())
    settings.update(args)
    
    logging.getLogger().setLevel(getattr(logging, settings.log_level))

    app = App()
    app.run()
    pass


if __name__ == "__main__":
    main()