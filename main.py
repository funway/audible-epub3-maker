import argparse
import logging
import sys
import multiprocessing as mp
from pathlib import Path


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
        default=None,
        help=(
            "Language code for TTS. The default depends on the chosen engine:\n"
            "  * azure => en-US\n"
            "  * kokoro => en-US if available otherwise the first supported code\n"
            "You only need to specify this when you want to override the engine default."
        )
    )

    # 6. TTS 声音
    parser.add_argument(
        "--tts_voice",
        default=None,
        help=(
            "Voice name for TTS. Default is engine-specific:\n"
            "  * azure => en-US-AvaMultilingualNeural\n"
            "  * kokoro => first voice matching the language default\n"
            "(leave blank to pick the engine default)")
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


def apply_tts_defaults(args: dict) -> dict:
    """Return a new args dict with tts defaults filled in.

    The values are chosen based on ``tts_engine``.  This mirrors the
    very similar logic in :func:`web_gui.on_engine_change` so that CLI users
    don't have to remember Azure-specific defaults when switching to Kokoro.
    """
    from audible_epub3_maker.utils import helpers

    engine = args.get("tts_engine", "azure").lower()
    out = dict(args)  # copy so caller can still mutate the original

    if engine == "kokoro":
        langs_voices = helpers.get_langs_voices_kokoro()
        lang_choices = list(langs_voices.keys())
        default_lang = "en-US" if "en-US" in lang_choices else next(iter(lang_choices), None)
        if not out.get("tts_lang"):
            out["tts_lang"] = default_lang
        voices = langs_voices.get(out.get("tts_lang"), [])
        if not out.get("tts_voice") and voices:
            out["tts_voice"] = voices[0]
    else:
        if not out.get("tts_lang"):
            out["tts_lang"] = "en-US"
        if not out.get("tts_voice"):
            out["tts_voice"] = "en-US-AvaMultilingualNeural"

    return out


def main():
    # 1. Set multiprocessing mode
    mp.set_start_method("spawn")

    # 2. Read user settings from command line args
    from audible_epub3_maker.config import settings
    args = vars(parse_args())

    # fill in any missing language/voice parameters based on selected engine
    args = apply_tts_defaults(args)

    settings.update(args)
    
    # 3. Setup logging system
    from audible_epub3_maker.utils import logging_setup
    logging.getLogger().setLevel(getattr(logging, settings.log_level.upper()))
    logger = logging.getLogger(__name__)

    # 4. Validate user settings
    from audible_epub3_maker.utils import helpers
    logger.info(f"⚙️ Settings: {settings.to_dict()}")
    try:
        helpers.validate_settings()
    except Exception as e:
        logger.error(f"🛑 [Abort] Settings validation failed: {e}")
        sys.exit(1)

    # 5. Running application
    from audible_epub3_maker.app import App
    app = App()
    try:
        app.run()
    except Exception as e:
        logger.exception(f"🛑 [Exit] Unexpected Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()