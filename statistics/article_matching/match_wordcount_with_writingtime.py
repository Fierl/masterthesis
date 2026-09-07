import csv
import glob
import json
import os
import re

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "masterthesis", "data", "excel", "phase2")
WORD_COUNT_DIR = os.path.join(BASE_DIR, "word_count")
OUTPUT_DIR = WORD_COUNT_DIR


def read_text_file(path: str) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            with open(path, encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Could not decode {path}")


def detect_delimiter(text: str) -> str:
    sample = "\n".join(line for line in text.splitlines()[:10] if line.strip())
    if not sample:
        return ";"
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        return dialect.delimiter
    except csv.Error:
        return ";" if text.count(";") >= text.count(",") else ","


def parse_writing_times(csv_path: str) -> dict[str, int | None]:
    text = read_text_file(csv_path)
    delimiter = detect_delimiter(text)
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))

    header_row_index = None
    headers: list[str] = []

    for i, row in enumerate(rows):
        first = row[0].strip() if row else ""
        if first.startswith("CREATE-ID"):
            header_row_index = i
            headers = [cell.strip() for cell in row]
            break

    if header_row_index is None:
        raise ValueError(f"CREATE-ID header not found in {csv_path}")

    create_id_col = next(
        (i for i, h in enumerate(headers) if h.startswith("CREATE-ID")), None
    )
    time_col = next(
        (i for i, h in enumerate(headers) if "Schreibzeit" in h and "Artikeltext" in h), None
    )

    if create_id_col is None or time_col is None:
        raise ValueError(f"Required columns not found in {csv_path}")

    result: dict[str, int | None] = {}
    for row in rows[header_row_index + 1:]:
        if not row:
            continue
        create_id = row[create_id_col].strip() if create_id_col < len(row) else ""
        if not create_id:
            continue
        if not (re.fullmatch(r"\d+", create_id) or "-" in create_id):
            continue
        raw_time = row[time_col].strip() if time_col < len(row) else ""
        try:
            result[create_id] = int(raw_time)
        except ValueError:
            result[create_id] = None

    return result


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    wc_files = sorted(glob.glob(os.path.join(WORD_COUNT_DIR, "*_word_count.json")))
    if not wc_files:
        return

    csv_files = glob.glob(os.path.join(BASE_DIR, "*.CSV")) + glob.glob(
        os.path.join(BASE_DIR, "*.csv")
    )
    csv_by_participant: dict[str, str] = {}
    for csv_path in csv_files:
        name = os.path.basename(csv_path).lower()
        match = re.search(r"_(p\d+)\.", name)
        if match:
            csv_by_participant[match.group(1)] = csv_path

    for wc_file in wc_files:
        filename = os.path.basename(wc_file)
        participant_key = filename.split("_")[0]

        with open(wc_file, encoding="utf-8") as f:
            wc_entries = json.load(f)

        csv_path = csv_by_participant.get(participant_key)
        if not csv_path:
            continue

        writing_times = parse_writing_times(csv_path)

        results = []
        for entry in wc_entries:
            content_id = str(entry["content_id"])
            schreibzeit = writing_times.get(content_id)
            results.append({
                "content_id": entry["content_id"],
                "participant_username": entry["participant_username"],
                "cms_text_word_count": entry["cms_text_word_count"],
                "schreibzeit_artikeltext": schreibzeit,
            })

        out_file = os.path.join(OUTPUT_DIR, f"{participant_key}_wordcount_writingtime.json")
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        matched = sum(1 for r in results if r["schreibzeit_artikeltext"] is not None)


if __name__ == "__main__":
    main()
