import sys
import subprocess
import shlex
from pathlib import Path
from urllib.parse import unquote

import gradio as gr
from gradio_log import Log

from audible_epub3_maker.epub.epub_book import EpubBook
from audible_epub3_maker.config import AZURE_TTS_KEY, AZURE_TTS_REGION
from audible_epub3_maker.utils.constants import APP_NAME, APP_FULLNAME, OUTPUT, BEAUTIFULSOUP_PARSER, LOG_FILE
from audible_epub3_maker.utils import helpers


css = """
#adv_sets > button > span:first-of-type {
    font-size: var(--text-lg);
    font-weight: var(--prose-header-text-weight);
    color: var(--body-text-color);
}
"""
langs_voices = {}  # 存储 TTS 的语言与声音选项
aem_process: subprocess.Popen | None = None  # 当前运行的 audible epub3 maker 主进程
log_file = LOG_FILE


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
        raise RuntimeError(f"AEM process [{Path(input_file).name}] is still running, please do not run again.")
    
    args = [
        sys.executable, "main.py",
        shlex.quote(str(input_file)),
        "-d", shlex.quote(str(output_dir)) if output_dir else "",
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
    
    aem_process = subprocess.Popen(args)
    pass

 
def on_run_click(input_file, output_dir, log_level, cleanup,
                 tts_engine, tts_lang, tts_voice, tts_speed,
                 tts_chunk_len, newline_mode, align_threshold, max_workers):
    # 检查 input_file, output_dir, tts_engine 必须不为空
    # 然后调用 run_generation
    if not input_file:
        raise gr.Error(f"Select a EPUB file to process")
        # return ("", gr.update(), gr.update())
    if not tts_engine:
        raise gr.Error(f"Select a TTS engine to continue")
        # return ("", gr.update(), gr.update())
    
    print(f"input_file: {type(input_file)}, {input_file.name}, out: {type(output_dir)},{output_dir}, tts_engine: {type(tts_engine)},{tts_engine}")

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


def launch_gui():
    with gr.Blocks(title=APP_NAME, css=css) as demo:
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
                                        value=OUTPUT,
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
            run_btn = gr.Button("🚀  Run", variant="primary")
            cancel_btn = gr.Button("🛑  Cancel")
        
        log_output = Log(log_file, tail=1, dark=True)

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
    
    demo.launch()


if __name__ == "__main__":
    launch_gui()