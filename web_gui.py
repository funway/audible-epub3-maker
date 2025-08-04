from pathlib import Path
import gradio as gr

from audible_epub3_maker.epub.epub_book import EpubBook
from audible_epub3_maker.config import AZURE_TTS_KEY, AZURE_TTS_REGION
from audible_epub3_maker.utils.constants import APP_NAME, APP_FULLNAME, OUTPUT
from audible_epub3_maker.utils import helpers


css = """
#adv_sets > button > span:first-of-type {
    font-size: var(--text-lg);
    font-weight: var(--prose-header-text-weight);
    color: var(--body-text-color);
}
"""


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
        
        preview.append(f"ch[{idx}]: {ch.href}")
    
    return "\n".join(preview)


def run_generation(arg):
    pass

langs_voices = {}
def on_engine_change(tts_engine):
    global langs_voices
    tts_name = tts_engine.lower()
    
    if tts_name == "azure":
        if not AZURE_TTS_KEY or not AZURE_TTS_REGION:
            gr.Warning(message="Please set AZURE_TTS_KEY and AZURE_TTS_REGION in your environment",
                       title="Azure Key Unconfigured")
            return (
                gr.update(),
                gr.update()
            )
        try:
            langs_voices = helpers.get_langs_voices_azure(AZURE_TTS_KEY, AZURE_TTS_REGION)
        except Exception as e:
            gr.Warning(message=str(e),
                       title="Failed to load Azure voices")
            return (
                gr.update(), 
                gr.update()
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
    voices = langs_voices[tts_lang]
    return gr.update(choices=voices, value=voices[0] if voices else None)


def launch_gui():
    with gr.Blocks(title=APP_NAME, css=css) as demo:
        gr.Markdown(f"# 🎧 {APP_FULLNAME} - Web GUI")
        gr.Markdown("---")

        gr.Markdown("### ⚙️ General Settings")
        with gr.Row(equal_height=True):
            input_file = gr.File(label="Select the EPUB file to process", 
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
            run_btn = gr.Button("🚀 Run", variant="primary")
            cancel_btn = gr.Button("🛑 Cancel")
        
        log_output = gr.Textbox(label="📝 Log Output", lines=20)

        input_file.change(fn=run_preview, inputs=input_file, outputs=preview_output)
        tts_engine.change(fn=on_engine_change, inputs=tts_engine, outputs=[tts_lang, tts_voice])
        tts_lang.change(fn=on_lang_change, inputs=tts_lang, outputs=tts_voice)
    
    demo.launch()


if __name__ == "__main__":
    launch_gui()