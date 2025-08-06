# Audible EPUB3 Maker

Generate audiobooks in **EPUB3 Media Overlays** format using high-quality TTS (Text-to-Speech) engines like **Azure** and **Kokoro**, now with an intuitive **Web GUI**.

This tool converts standard EPUB files into narrated versions compatible with screen readers and audiobook readers like Thorium Reader.

---

## ✨ Features

- Convert plain-text EPUB books into human-like audiobooks.
- Output conforms to **[EPUB 3 Media Overlays](https://www.w3.org/TR/epub/#sec-media-overlays)** specification.
- Supports TTS engines:
  - Azure TTS (high-quality cloud service)
  - Kokoro-82M (offline open-source model)
- Automatic sentence segmentation and force alignment
- Parallel multi-process generation
- Gradio-based Web GUI for easy interaction without command line
- Docker-ready architecture for easy deployment (coming soon)
---

## 🛠 Installation

### From Source
#### 1. pip install
```bash
git clone https://github.com/<your-name>/audible-epub3-maker.git
cd audible-epub3-maker
pip install -r requirements.txt
```

#### 2. TTS Engine Configuration

Depending on the engine you plan to use, follow the steps below:

- **Azure**:
  - You must configure the following two environment variables:
    ```bash
    AZURE_TTS_KEY=your_azure_speech_key
    AZURE_TTS_REGION=your_speech_region
    ```
  - You can define them:
    - In a `.env` file in the project root (recommended)
    - Or `export` them manually in your shell or `.bashrc` / `.zshrc` file:
      ```bash
      export AZURE_TTS_KEY=your_key
      export AZURE_TTS_REGION=your_region
      ```

- **Kokoro**:
  - No environment configuration is required.
  - The model file will automatically download on first use.


### From Docker (Comming Soon)

---

## ⚙️ Usage

### CLI

```bash
python main.py <input_file.epub> -d <output_dir> \
    --tts_engine azure \
    --tts_lang en-US \
    --tts_voice en-US-JennyMultilingualNeural
```

#### Required:
- `input_file`: The path to the source EPUB file.

#### Optional arguments:

| Option                | Description                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------- |
| `-d`, `--output_dir`  | Output directory. Default: `<input_file_stem>_audible`                                       |
| `--log_level`         | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default: INFO                          |
| `--tts_engine`        | TTS engine: `azure` or `kokoro`. Default: azure                                              |
| `--tts_lang`          | Language code. Default: `en-US` for Azure                                                    |
| `--tts_voice`         | Voice name. Default: `en-US-AvaMultilingualNeural` (Azure)                                   |
| `--tts_speed`         | Playback speed for TTS synthesis (e.g., 1.0 = normal speed). Default: 1.0                    |
| `--tts_chunk_len`     | Max characters per TTS chunk. Default: auto (2000 for zh/ja/ko, 3000 for others)             |
| `--newline_mode`      | How to detect paragraph breaks from newlines: `none`, `single`, or `multi`. Default: `multi` |
| `-m`, `--max_workers` | Number of worker processes for multiprocessing. Default: 3                                   |
| `--align_threshold`   | Fuzzy match threshold for force alignment (0–100). Default: 95.0                             |
| `-f`, `--force`       | Force all prompts to be accepted (non-interactive mode)                                      |
| `--cleanup`           | Remove temporary files (**.mp3**) after generation. Default: False                           |

#### 📦 Example

```bash
python main.py mybook.epub \
    --tts_engine azure \
    --tts_lang zh-CN \
    --tts_voice zh-CN-XiaoxiaoNeural \
    -d ./output_dir \
    -m 4 \
    --log_level DEBUG
```

### Web GUI

```bash
python web_gui.py
```

Then open your browser and interact with the friendly interface!

---

## 📚 Output

- `*.mp3`: Generated audio for each chapter
- `*.epub`: A new EPUB file with embedded mp3 audio and synchronized smil overlays

---

## 📝 License

This project is licensed under the MIT License.

---


