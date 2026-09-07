from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class CsvEntry:
    row_number: int
    create_id: str
    cms_lookup_field: str
    cms_lookup_value: int | str
    occurrence: int
    raw: dict[str, str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Match a phase 1 participant CSV with extracted article JSON and write a consolidated export."
    )
    parser.add_argument("--csv", required=True, help="Path to the participant CSV file")
    parser.add_argument("--articles-json", required=True, help="Path to the extracted articles JSON file")
    parser.add_argument(
        "--output",
        help="Optional output JSON path. Defaults to <csv-stem>_matched.json next to the CSV.",
    )
    return parser.parse_args()


def read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Could not decode {path}")


def detect_csv_delimiter(text: str) -> str:
    sample_lines = [line for line in text.splitlines()[:10] if line.strip()]
    sample = "\n".join(sample_lines)
    if not sample:
        return ";"

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,")
        return dialect.delimiter
    except csv.Error:
        semicolon_count = sample.count(";")
        comma_count = sample.count(",")
        return "," if comma_count > semicolon_count else ";"


def parse_csv(path: Path) -> tuple[str | None, list[CsvEntry], list[str]]:
    text = read_text_file(path)
    delimiter = detect_csv_delimiter(text)
    rows = list(csv.reader(text.splitlines(), delimiter=delimiter))

    participant = None
    header_row_index = None
    headers: list[str] = []

    for index, row in enumerate(rows):
        first = row[0].strip() if row else ""
        normalized_first = first.rstrip(":").strip().lower()
        if normalized_first == "teilnehmer" and len(row) > 1:
            participant = row[1].strip() or None
        if first.startswith("CREATE-ID"):
            header_row_index = index
            headers = [cell.strip() for cell in row]
            break

    if header_row_index is None:
        raise ValueError(f"Header row with CREATE-ID not found in {path}")

    entries: list[CsvEntry] = []
    occurrence_by_lookup_key: dict[tuple[str, int | str], int] = defaultdict(int)

    for offset, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
        if not row:
            continue
        first = row[0].strip()
        if not first:
            continue
        if re.fullmatch(r"\d+", first):
            cms_lookup_field = "content_id"
            cms_lookup_value: int | str = int(first)
        elif "-" in first:
            cms_lookup_field = "origin_id"
            cms_lookup_value = first
        else:
            continue

        lookup_key = (cms_lookup_field, cms_lookup_value)
        occurrence_by_lookup_key[lookup_key] += 1
        normalized_row = list(row) + [""] * (len(headers) - len(row))
        raw = {headers[i]: normalized_row[i].strip() for i in range(len(headers))}
        entries.append(
            CsvEntry(
                row_number=offset,
                create_id=first,
                cms_lookup_field=cms_lookup_field,
                cms_lookup_value=cms_lookup_value,
                occurrence=occurrence_by_lookup_key[lookup_key],
                raw=raw,
            )
        )

    return participant, entries, headers


def parse_articles_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array in {path}")
    return data


def build_article_index(articles: list[dict[str, Any]]) -> dict[str, dict[int | str, list[dict[str, Any]]]]:
    index: dict[str, dict[int | str, list[dict[str, Any]]]] = {
        "content_id": defaultdict(list),
        "origin_id": defaultdict(list),
    }
    for article in articles:
        content_id = article.get("content_id")
        if content_id is not None:
            index["content_id"][int(content_id)].append(article)

        origin_id = article.get("origin_id")
        if origin_id:
            index["origin_id"][str(origin_id)].append(article)
    return index


def pick_article(
    index: dict[str, dict[int | str, list[dict[str, Any]]]],
    lookup_field: str,
    lookup_value: int | str,
    occurrence: int,
) -> dict[str, Any] | None:
    matches = index.get(lookup_field, {}).get(lookup_value, [])
    if not matches:
        return None
    if occurrence <= len(matches):
        return matches[occurrence - 1]
    return matches[-1]


def build_output(
    participant_username: str | None,
    csv_entries: list[CsvEntry],
    article_index: dict[str, dict[int | str, list[dict[str, Any]]]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    unmatched_csv_entries: list[dict[str, Any]] = []

    for sequence_index, entry in enumerate(csv_entries, start=1):
        article = pick_article(
            article_index,
            entry.cms_lookup_field,
            entry.cms_lookup_value,
            entry.occurrence,
        )

        item = {
            "sequence_index": sequence_index,
            "csv_row_number": entry.row_number,
            "content_id": entry.create_id,
            "content_id_occurrence": entry.occurrence,
            "participant_username": participant_username,
            "csv": entry.raw,
            "article": article,
            "match_status": "matched" if article is not None else "no-article-match",
        }

        if article is None:
            unmatched_csv_entries.append(item)
        else:
            items.append(item)

    return {
        "meta": {
            "participant_username": participant_username,
            "csv_entry_count": len(csv_entries),
            "matched_count": len(items),
            "unmatched_csv_entry_count": len(unmatched_csv_entries),
        },
        "items": items,
        "unmatched_csv_entries": unmatched_csv_entries,
    }


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)
    articles_json_path = Path(args.articles_json)
    output_path = Path(args.output) if args.output else csv_path.with_name(f"{csv_path.stem}_matched.json")

    participant, csv_entries, csv_headers = parse_csv(csv_path)
    articles = parse_articles_json(articles_json_path)
    article_index = build_article_index(articles)

    output = build_output(
        participant_username=participant,
        csv_entries=csv_entries,
        article_index=article_index,
    )
    output["meta"]["csv_headers"] = csv_headers
    output["meta"]["csv_path"] = str(csv_path)
    output["meta"]["articles_json_path"] = str(articles_json_path)
    output["meta"]["output_path"] = str(output_path)

    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()