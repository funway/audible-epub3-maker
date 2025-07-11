import argparse
import os
from audible_epub3_gen.config import DEFAULT_LANGUAGE, DEFAULT_VOICE
from audible_epub3_gen.epub.parser import extract_text_from_epub
from audible_epub3_gen.tts.azure_tts import synthesize_speech_with_timestamps
from audible_epub3_gen.epub.generator import generate_smil

INPUT_EPUB = 'input/your_book.epub'
OUTPUT_DIR = 'output/'

def main(language, voice):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    chapters = extract_text_from_epub(INPUT_EPUB)

    for ch in chapters:
        text = ' '.join([p['text'] for p in ch['paragraphs']])
        audio_file = os.path.join(OUTPUT_DIR, f"{os.path.basename(ch['file_name'])}.mp3")
        timestamps = synthesize_speech_with_timestamps(text, audio_file, language, voice)

        par_list = []
        offset = 0.0
        for p in ch['paragraphs']:
            duration = 2.5
            par_list.append({
                'id': p['id'],
                'clipBegin': offset,
                'clipEnd': offset + duration
            })
            offset += duration

        smil_file = os.path.join(OUTPUT_DIR, f"{os.path.basename(ch['file_name'])}.smil")
        generate_smil(ch['file_name'], os.path.basename(audio_file), par_list, smil_file)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--language", type=str, default=DEFAULT_LANGUAGE)
    parser.add_argument("--voice", type=str, default=DEFAULT_VOICE)
    args = parser.parse_args()
    main(args.language, args.voice)
