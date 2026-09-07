import json
import glob
import os

EXTRACTED_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "masterthesis", "data", "excel", "phase2", "extracted",
)
OUTPUT_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "masterthesis", "data", "excel", "phase2", "word_count",
)


def count_words(text: str) -> int:
    if not text:
        return 0
    return len(text.split())


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pattern = os.path.join(EXTRACTED_DIR, "*_extracted.json")
    files = sorted(glob.glob(pattern))

    if not files:
        return

    for filepath in files:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        items = data.get("items", [])
        results = []
        participant = ""

        for item in items:
            content_id = item.get("content_id", "")
            participant = item.get("participant_username", "")
            cms_text = item.get("cms_article", {}).get("text", "")
            word_count = count_words(cms_text)

            results.append({
                "content_id": content_id,
                "participant_username": participant,
                "cms_text_word_count": word_count,
            })

        if not participant:
            participant = os.path.basename(filepath).replace("_extracted.json", "")

        out_file = os.path.join(OUTPUT_DIR, f"{participant.lower()}_word_count.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
