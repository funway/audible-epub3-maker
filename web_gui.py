import gradio as gr

from audible_epub3_maker.utils.constants import APP_FULLNAME, OUTPUT


def launch_gui():
    with gr.Blocks(title=APP_FULLNAME) as demo:
        with gr.Row(equal_height=True):
            with gr.Column():
                input_file = gr.File(label="Select the EPUB file to process", 
                                     file_types=[".epub"], 
                                     file_count="single", 
                                     interactive=True,
                                     )

            with gr.Column():
                output_dir = gr.Textbox(label="Set Output Directory", 
                                        value=OUTPUT, 
                                        interactive=True,
                                        )
    
    demo.launch()


if __name__ == "__main__":
    launch_gui()