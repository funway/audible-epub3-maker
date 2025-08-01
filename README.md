# Audible EPUB3 Maker

Generate audiobooks in **EPUB3 Media Overlays** format using high-quality TTS (Text-to-Speech) engines like Azure and Kokoro (🚧 Todo).

This tool converts standard EPUB files into narrated versions compatible with screen readers and audiobook readers like Thorium Reader.

---

## 🚀 Features

- ✅ Supports [EPUB 3 Media Overlays](https://www.w3.org/TR/epub/#sec-media-overlays)
- 🎙️ Supports Azure TTS (Kokoro TTS support is coming soon)
- 🔊 Generates mp3 audio and integrates it into EPUB3 format
- 🧠 Sentence-level text-to-audio alignment with SMIL sync
- 🔁 Parallel multi-process generation for both TTS and force alignment

---

## 🛠 Installation

```bash
git clone https://github.com/<your-name>/audible-epub3-maker.git
cd audible-epub3-maker
pip install -r requirements.txt
```

You must also configure Azure or Kokoro voice environment depending on your engine choice.

---

## ⚙️ Usage

```bash
python main.py <input_file.epub> [options]
```

### Required:
- `input_file`: The path to the source EPUB file.

### Optional arguments:

| Option                | Description                                                                                  |
| --------------------- | -------------------------------------------------------------------------------------------- |
| `-d`, `--output_dir`  | Output directory. Default: `<input_file_stem>_audible`                                       |
| `--log_level`         | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default: INFO                          |
| `--tts_engine`        | TTS engine: `azure` or `kokoro`. Default: azure                                              |
| `--tts_lang`          | Language code. Default: `en-US` for Azure                                                    |
| `--tts_voice`         | Voice name. Default: `en-US-AvaMultilingualNeural` (Azure)                                   |
| `--tts_chunk_len`     | Max characters per TTS chunk. Default: auto (2000 for zh/ja/ko, 3000 for others)             |
| `-m`, `--max_workers` | Number of worker processes for multiprocessing. Default: 3                                   |
| `-f`, `--force`       | Force all prompts to be accepted (non-interactive mode)                                      |
| `--newline_mode`      | How to detect paragraph breaks from newlines: `none`, `single`, or `multi`. Default: `multi` |
| `--align_threshold`   | Fuzzy match threshold for force alignment (0–100). Default: 95.0                             |

---

## 📦 Example

```bash
python main.py mybook.epub \
    --tts_engine azure \
    --tts_lang zh-CN \
    --tts_voice zh-CN-XiaoxiaoNeural \
    -d ./output_dir \
    -m 4 \
    --log_level DEBUG
```

---

## 📚 Output

- `*.mp3`: Generated audio for each chapter
- `*.epub`: A new EPUB file with embedded mp3 audio and synchronized smil overlays

---

## 📝 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [EPUB 3](https://www.w3.org/TR/epub/)
- [Azure Speech Service](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/get-started-text-to-speech)
- [Kokoro TTS](https://huggingface.co/hexgrad/Kokoro-82M)
