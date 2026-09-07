import json
import glob
import os
import html

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "masterthesis", "extracted")
os.makedirs(OUTPUT_DIR, exist_ok=True)

TEXT_ATTRS = {
    "line_head", "line_roof", "line_sub", "origin_id",
    "seo_description", "seo_title", "h1",
    "paywall_teaser", "text", "intro",
}

INT_ATTRS = {"paywall_active"}

ALL_ATTRS = TEXT_ATTRS | INT_ATTRS


def get_attr_value(attributes: list, identifier: str) -> object:
    for attr in attributes:
        if attr["identifier"] != identifier:
            continue
        if identifier in INT_ATTRS:
            if attr["value_int"] is not None:
                return attr["value_int"]
        else:
            if attr["value_text"] is not None:
                return html.unescape(attr["value_text"])
    return None


def extract_article(article: dict) -> dict:
    attrs = article.get("attributes", [])
    record = {
        "content_id":     article.get("content_id"),
        "content_name":   article.get("content_name"),
        "published_date": article.get("published_date"),
    }
    for identifier in sorted(ALL_ATTRS):
        record[identifier] = get_attr_value(attrs, identifier)
    return record


def process_file(input_path: str) -> None:
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    extracted = [extract_article(article) for article in data]

    phase = os.path.basename(os.path.dirname(input_path))
    filename = f"{phase}_{os.path.basename(input_path)}"
    output_path = os.path.join(OUTPUT_DIR, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(extracted, f, ensure_ascii=False, indent=2)


def main():
    pattern = os.path.join(
        os.path.dirname(__file__), "..", "masterthesis", "phase_*", "*.json"
    )
    files = sorted(glob.glob(pattern))
    if not files:
        return

    for fpath in files:
        process_file(fpath)


if __name__ == "__main__":
    main()
