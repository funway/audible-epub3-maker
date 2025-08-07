import os
import sys
import subprocess
import argparse
from pathlib import Path
from urllib.parse import unquote

import gradio as gr

from audible_epub3_maker.epub.epub_book import EpubBook
from audible_epub3_maker.config import AZURE_TTS_KEY, AZURE_TTS_REGION
from audible_epub3_maker.utils.constants import APP_NAME, APP_FULLNAME, OUTPUT_DIR, BEAUTIFULSOUP_PARSER, LOG_FILE
from audible_epub3_maker.utils import helpers


# NOTE:
# Global variables defined at the module level are shared across all users and sessions.
# This means that refreshing the page, opening a new browser tab, or accessing from different clients
# will all interact with the same variable.
#
# If you need per-session or per-user isolation (e.g., each user maintains their own counter or state),
# use `gr.State()` within your Gradio app to store and manage session-specific data.

CSS = """
#adv_sets > button > span:first-of-type {
    font-size: var(--text-lg);
    font-weight: var(--prose-header-text-weight);
    color: var(--body-text-color);
}
"""
BTN_RUN_IDLE = "🚀  Run"
BTN_RUN_RUNNING = "🔁 Running"
BTN_CANCEL = "🛑 Cancel"
LOG_MAX_LINES = 1000  # 最多保留的日志行数

aem_process: subprocess.Popen | None = None  # 当前运行的 audible epub3 maker 主进程
langs_voices = {}  # 存储 TTS 的语言与声音选项
log_file = LOG_FILE
log_inode = -1
log_offset = -1
log_buffer = []


def tail_log_file():
    global log_inode, log_offset, log_buffer
    try:
        if not os.path.exists(log_file):
            return gr.update(value="‼️[Log Error] Log file not found!")
        
        stat = os.stat(log_file)
        current_inode = stat.st_ino
        file_size = stat.st_size

        if log_offset == -1:
            # initialize
            log_inode = current_inode
            log_offset = file_size
            log_buffer.clear()

        if log_inode != current_inode:
            # file rotated
            log_inode = current_inode
            log_offset = 0
        
        elif log_offset > file_size:
            # file cleared
            log_offset = 0
            log_buffer.clear()
        
        with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(log_offset)          # jump to offset
            new_lines = f.readlines()   # read all lines from offset
            log_offset = f.tell()       # remember new offset

        log_buffer.extend(line.rstrip() for line in new_lines)
        if len(log_buffer) > LOG_MAX_LINES:
            log_buffer = log_buffer[-LOG_MAX_LINES:]
        
        return gr.update(value="\n".join(log_buffer))

    except Exception as e:
        return gr.update(value=f"‼️[Log Error] {e}")


def run_preview(input_file):
    if not input_file:
        return
    epub_path = Path(input_file)
    book = EpubBook(epub_path)
    preview = []
    preview.append(f"Title: {book.title}")
    preview.append(f"Identifier: {book.identifier}")
    preview.append(f"Language: {book.language}")
    
    preview.append("="*20)
    total_chars = 0
    for idx, ch in enumerate(book.get_chapters()):
        chars_count = ch.count_visible_chars()
        total_chars += chars_count
        preview.append(f"ch[{idx}]: {unquote(ch.href)}  ({chars_count:,} characters)")
    
    preview.append("="*20)
    preview.append(f"Total characters: {total_chars:,}")
    
    return "\n".join(preview)


def run_generation(input_file, output_dir, log_level, cleanup,
                   tts_engine, tts_lang, tts_voice, tts_speed,
                   tts_chunk_len, newline_mode, align_threshold, max_workers):
    global aem_process

    if aem_process and aem_process.poll() is None:
        raise RuntimeError(f"AEM process [PID={aem_process.pid}] is already running. Please do not start it again.")
    
    args = [
        sys.executable, "main.py",
        str(input_file),
        "-d", str(output_dir) if output_dir else "",
        "--log_level", log_level,
        "--tts_engine", tts_engine.lower(),
        "--tts_lang", tts_lang,
        "--tts_voice", tts_voice or "",
        "--tts_speed", str(tts_speed),
        "--tts_chunk_len", str(tts_chunk_len),
        "--newline_mode", newline_mode,
        "--align_threshold", str(align_threshold),
        "--max_workers", str(max_workers),
        "--force"
    ]
    if cleanup:
        args.append("--cleanup")
    
    print(args)
    
    aem_process = subprocess.Popen(args)
    pass


def check_process():
    if aem_process and aem_process.poll() is None:
        # is running
        return gr.update(value=BTN_RUN_RUNNING, interactive=False)
    else:
        return gr.update(value=BTN_RUN_IDLE, interactive=True)

 
def on_run_click(input_file, output_dir, log_level, cleanup,
                 tts_engine, tts_lang, tts_voice, tts_speed,
                 tts_chunk_len, newline_mode, align_threshold, max_workers):
    # 检查 input_file, output_dir, tts_engine 必须不为空
    if not input_file:
        raise gr.Error(f"Select a EPUB file to process")
        # return ("", gr.update(), gr.update())
    if not tts_engine:
        raise gr.Error(f"Select a TTS engine to continue")
        # return ("", gr.update(), gr.update())
    
    try:
        run_generation(
            input_file=input_file.name,
            output_dir=output_dir.strip(),
            log_level=log_level,
            cleanup=cleanup,
            tts_engine=tts_engine,
            tts_lang=tts_lang,
            tts_voice=tts_voice,
            tts_speed=tts_speed,
            tts_chunk_len=tts_chunk_len,
            newline_mode=newline_mode,
            align_threshold=align_threshold,
            max_workers=max_workers
        )
    except Exception as e:
        raise gr.Error(f"{e}")


def on_cancel_click():
    global aem_process
    
    if aem_process and aem_process.poll() is None:
        aem_process.terminate()
        aem_process = None
        gr.Info(f"AEM process terminated")
    else:
        gr.Warning(f"No AEM process running")
    

def on_engine_change(tts_engine):
    global langs_voices
    tts_name = tts_engine.lower()
    
    if tts_name == "azure":
        if not AZURE_TTS_KEY or not AZURE_TTS_REGION:
            gr.Warning(message="Please set AZURE_TTS_KEY and AZURE_TTS_REGION in your environment",
                       title="Azure Key Unconfigured")
            return (
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None)
            )
        try:
            langs_voices = helpers.get_langs_voices_azure(AZURE_TTS_KEY, AZURE_TTS_REGION)
        except Exception as e:
            gr.Warning(message=str(e),
                       title="Failed to load Azure voices")
            return (
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None)
            )
        
    elif tts_name == "kokoro":
        langs_voices = helpers.get_langs_voices_kokoro()
    
    lang_choices = list(langs_voices.keys())
    default_lang = "en-US" if "en-US" in lang_choices else next(iter(lang_choices), None)
    voice_choices = langs_voices[default_lang] if default_lang else []

    return (
        gr.update(choices=lang_choices, value=default_lang),
        gr.update(choices=voice_choices, value=voice_choices[0] if voice_choices else None)
    )


def on_lang_change(tts_lang):
    voices = langs_voices.get(tts_lang, [])
    return gr.update(choices=voices, value=voices[0] if voices else None)


def launch_gui(host: str = "127.0.0.1", port: int = 7860):
    with gr.Blocks(theme=gr.themes.Ocean(), title=APP_NAME, css=CSS) as demo:
        gr.Markdown(f"# 🎧 {APP_FULLNAME} - Web GUI")
        gr.Markdown("---")

        gr.Markdown("### ⚙️ General Settings")
        with gr.Row(equal_height=True):
            input_file = gr.File(label="Select a EPUB file to process", 
                                    file_types=[".epub"], 
                                    file_count="single", 
                                    interactive=True
                                    )

            preview_output = gr.Textbox(label="EPUB Preview", 
                                        lines=10,
                                        max_lines=10,
                                        )
            
            with gr.Column():
                output_dir = gr.Textbox(label="Output Directory",
                                        value=OUTPUT_DIR,
                                        interactive=True
                                        )
                gr.Markdown("---")
                
                log_level = gr.Dropdown(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], 
                                        value="INFO", 
                                        label="Log Level",
                                        interactive=True
                                        )
                gr.Markdown("---")
                cleanup = gr.Checkbox(label="Cleanup Temporary Files")

        gr.Markdown("### 🎙 TTS Settings")
        with gr.Row(equal_height=True):
            tts_engine = gr.Dropdown(choices=["Azure", "Kokoro"],
                                     label="TTS Engine",
                                     value=None,
                                     interactive=True
                                     )
            
            tts_lang = gr.Dropdown(choices=[], 
                                   label="Language",
                                   interactive=True
                                   )
            
            tts_voice = gr.Dropdown(choices=[],
                                    label="Voice",
                                    interactive=True
                                    )
            
            tts_speed = gr.Slider(0.5, 2.0, 
                                  step=0.1, 
                                  value=1.0, 
                                  label="Speed",
                                  interactive=True
                                  )
            
        with gr.Accordion("🛠 Advanced Settings", open=False, elem_id="adv_sets"):
            with gr.Row():
                with gr.Column():
                    newline_mode = gr.Dropdown(["none", "single", "multi"], 
                                       value="multi", 
                                       label="Newline Mode",
                                       info="Choose the mode of detecting new paragraphs for TTS",
                                       interactive=True
                                       )
                with gr.Column():
                    tts_chunk_len = gr.Number(value=0, 
                                        label="Chunk Length (0 = auto)",
                                        info="Set the max characters per TTS request (0 = auto by language)",
                                        interactive=True
                                        )
                    
                with gr.Column():
                    align_threshold = gr.Slider(80.0, 100.0, 
                                            step=0.5, 
                                            value=95.0, 
                                            label="Force Alignment Threshold",
                                            info="Set the threshold for force alignment fuzzy matching",
                                            interactive=True)
                with gr.Column():
                    max_workers = gr.Slider(1, 16, 
                                        step=1, 
                                        value=3, 
                                        label="Max Workers",
                                        info="Set the max number of parallel worker processes",
                                        interactive=True
                                        )

        with gr.Row():
            run_btn = gr.Button(BTN_RUN_IDLE, variant="primary")
            cancel_btn = gr.Button(BTN_CANCEL)
        
        log_output = gr.Textbox(label="Log Output", 
                                lines=20,
                                max_lines=20,
                                interactive=False)

        # Events
        input_file.change(fn=run_preview, inputs=input_file, outputs=preview_output)
        tts_engine.change(fn=on_engine_change, inputs=tts_engine, outputs=[tts_lang, tts_voice])
        tts_lang.change(fn=on_lang_change, inputs=tts_lang, outputs=tts_voice)
        run_btn.click(
            fn=on_run_click,
            inputs=[
                input_file, output_dir, log_level, cleanup,
                tts_engine, tts_lang, tts_voice, tts_speed,
                tts_chunk_len, newline_mode, align_threshold, max_workers
            ],
            outputs=None
        )
        cancel_btn.click(
            fn=on_cancel_click,
            inputs=None,
            outputs=None
        )
        gr.Timer(0.5).tick(
            fn=check_process,
            inputs=None,
            outputs=[run_btn]
        )
        gr.Timer(0.5).tick(
            fn=tail_log_file,
            inputs=None,
            outputs=[log_output]
        )
    
    demo.launch(server_name=host, server_port=port)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audible EPUB3 Maker Web GUI (powered by Gradio)",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind the Gradio web server")
    parser.add_argument("--port", type=int, default=7860, help="Port to bind the Gradio web server")
    args = parser.parse_args()

    launch_gui(host=args.host, port=args.port)