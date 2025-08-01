# Audible EPUB3 Maker

Generate audiobooks in **EPUB3 Media Overlays** format using high-quality TTS (Text-to-Speech) engines like Azure and Kokoro.

This tool converts standard EPUB files into narrated versions compatible with screen readers and audiobook readers like Thorium Reader.

---

## 🚀 Features

- ✅ Supports [EPUB 3 Media Overlays](https://www.w3.org/TR/epub-mediaoverlays/)
- 🎙️ Supports Azure TTS and Kokoro-82M TTS engine
- 🔊 Generates mp3 audio files and syncs word-level alignment
- 🔁 Parallel multi-process audio generation
- 💾 Embeds `<smil>` files and updates manifest/spine for media overlays

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

| Option               | Description                                                                                 |
|----------------------|---------------------------------------------------------------------------------------------|
| `-d`, `--output_dir` | Output directory. Default: `<input_file_stem>_audible`                                      |
| `--log_level`        | Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL. Default: INFO                         |
| `--tts_engine`       | TTS engine: `azure` or `kokoro`. Default: azure                                            |
| `--tts_lang`         | Language code. Default: `en-US` for Azure                                                  |
| `--tts_voice`        | Voice name. Default: `en-US-AvaMultilingualNeural` (Azure)                                 |
| `--tts_chunk_len`    | Max characters per TTS chunk. Default: auto (2000 for zh/ja/ko, 3000 for others)            |
| `-m`, `--max_workers`| Number of worker processes for multiprocessing. Default: 3                                  |
| `-f`, `--force`      | Force all prompts to be accepted (non-interactive mode)                                     |

---

## 📦 Example

```bash
python -m audible_epub3_maker mybook.epub   --tts_engine azure   --tts_lang en-US   --tts_voice en-US-AvaMultilingualNeural   -d ./output_dir   -m 4   --log_level DEBUG
```

---

## 📚 Output

- `*.mp3`: Generated audio for each chapter
- `*.smil`: SMIL overlay files for syncing audio with text
- Updated `.opf` manifest and spine
- EPUB rebuilt with Media Overlays support

---

## 📝 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [EPUB Media Overlays 3.1](https://www.w3.org/TR/epub-mediaoverlays/)
- [Azure Speech Service](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/)
- [Kokoro TTS](https://huggingface.co/hexgrad/Kokoro-82M)
