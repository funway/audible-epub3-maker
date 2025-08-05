import argparse
import logging
from pathlib import Path

from audible_epub3_maker.config import settings
from audible_epub3_maker.app import App

def clean_path(p: str) -> Path:
    return Path(p.strip())

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate Audible-style EPUB with TTS narration.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    # 1. input_file 作为位置参数
    parser.add_argument("input_file", 
                        type=clean_path, 
                        help="Input EPUB file"
                        )

    # 2. 输出目录参数，支持 -d 和 --output_dir
    parser.add_argument(
        "-d", "--output_dir",
        type=clean_path,
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
        "--tts_speed",
        type=float,
        default=1.0,
        help="Playback speed for TTS synthesis (e.g., 1.0 = normal speed, 0.8 = slower, 1.2 = faster). Default is 1.0."
    )

    parser.add_argument(
        "--tts_chunk_len",
        type=int,
        default=0,
        help="Maximum number of characters per TTS chunk (default: auto by language)"
    )

    parser.add_argument(
        "--newline_mode",
        choices=["none", "single", "multi"],
        default="multi",
        help=(
            "How to handle newlines in HTML text:\n"
            "none      - remove all newlines and replace them with space\n"
            "single    - preserve all newlines as-is\n"
            "multi     - collapse 2 or more consecutive newlines (with optional spaces/tabs) into one newline"
        ),
    )

    parser.add_argument(
        "--align_threshold",
        type=float,
        default=95.0,
        help=(
            "Threshold for force alignment fuzzy matching (0–100).\n"
            "Higher value means stricter alignment. Default: 95.0"
        )
    )

    parser.add_argument(
        "-m", "--max_workers",
        type=int,
        default=3,
        help="Max count of multi-processing workers for audio and alignment generating (default: 3)"
    )

    parser.add_argument(
        "-f", "--force",
        action="store_true",
        default=False,
        help="Force all prompts to be accepted (non-interactive mode)"
    )

    parser.add_argument(
        "--cleanup",
        action="store_true",
        default=False,
        help="Remove temporary files after generation."
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