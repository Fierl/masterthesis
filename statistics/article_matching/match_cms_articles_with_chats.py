from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


COPY_TARGETS = {
    "public.users",
    "public.articles",
    "public.chats",
}

USED_FIELD_CODE_MAP = {
    "AT": "text",
    "ARTIKELTEXT": "text",
    "ZÜ": "subheadings",
    "ZU": "subheadings",
    "ZWISCHENUBERSCHRIFTEN": "subheadings",
    "DZ": "roofline",
    "DACHZEILE": "roofline",
    "TT": "headline",
    "TITEL": "headline",
    "UT": "subline",
    "UNTERTITEL": "subline",
    "PT": "teaser",
    "PAYWALLTEASER": "teaser",
    "TAGS": "tags",
    "KÜ": "shorten_text",
    "KU": "shorten_text",
}

GERMAN_STOPWORDS = {
    "aber", "als", "am", "an", "auch", "auf", "aus", "bei", "bis", "das", "dass", "dem", "den",
    "der", "des", "die", "doch", "dort", "durch", "ein", "eine", "einem", "einen", "einer", "eines",
    "er", "es", "für", "gegen", "habe", "hat", "hatte", "hier", "im", "in", "ist", "kein", "keine",
    "mit", "nach", "nicht", "noch", "nur", "oder", "rund", "sei", "sich", "sie", "sind", "so", "um",
    "und", "von", "vor", "war", "waren", "was", "wie", "wird", "wir", "zu", "zum", "zur", "zwar",
}


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
        description=(
            "Match a participant CSV with extracted CMS articles and SQL-dump based "
            "article/chat records, then write a consolidated JSON export."
        )
    )
    parser.add_argument("--csv", required=True, help="Path to the participant CSV file")
    parser.add_argument("--cms-json", required=True, help="Path to the extracted CMS JSON file")
    parser.add_argument("--sql-dump", required=True, help="Path to prod_new.sql")
    parser.add_argument(
        "--username",
        help="Optional username override, for example P17. Defaults to the participant code from the CSV.",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path. Defaults to <csv-stem>_matched.json next to the CSV.",
    )
    parser.add_argument(
        "--lookahead",
        type=int,
        default=5,
        help="How many upcoming DB articles to consider when resolving order-based matches.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=1.0,
        help="Matches with a lower score are filtered out of the main result list.",
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
        if first == "Teilnehmer:" and len(row) > 1:
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


def parse_cms_json(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def decode_copy_value(value: str) -> Any:
    if value == r"\N":
        return None
    return (
        value.replace(r"\\", "\\")
        .replace(r"\t", "\t")
        .replace(r"\r", "\r")
        .replace(r"\n", "\n")
    )


def parse_copy_tables(path: Path) -> dict[str, list[dict[str, Any]]]:
    tables = {name: [] for name in COPY_TARGETS}
    current_table = None
    current_columns: list[str] = []

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if current_table is None:
                match = re.match(r"^COPY\s+(public\.(?:users|articles|chats))\s+\((.+)\)\s+FROM\s+stdin;$", line)
                if not match:
                    continue
                current_table = match.group(1)
                current_columns = [column.strip() for column in match.group(2).split(",")]
                continue

            if line == r"\.":
                current_table = None
                current_columns = []
                continue

            row = parse_copy_row(current_table, line, current_columns)
            tables[current_table].append(row)

    return tables


def parse_copy_row(table_name: str, line: str, current_columns: list[str]) -> dict[str, Any]:
    if table_name == "public.users":
        parts = line.split("\t")
        if len(parts) != len(current_columns):
            raise ValueError(
                f"Unexpected column count while parsing {table_name}: "
                f"expected {len(current_columns)}, got {len(parts)}"
            )
        return {
            current_columns[index]: decode_copy_value(parts[index])
            for index in range(len(current_columns))
        }

    if table_name == "public.chats":
        match = re.match(
            r"^(\d+)\t(\d+)\t([^\t]+)\t([^\t]+)\t(.*)\t(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)$",
            line,
        )
        if not match:
            raise ValueError(f"Could not parse chats COPY row: {line[:200]}")
        values = [
            match.group(1),
            match.group(2),
            match.group(3),
            match.group(4),
            match.group(5),
            match.group(6),
        ]
        return {
            current_columns[index]: decode_copy_value(values[index])
            for index in range(len(current_columns))
        }

    if table_name == "public.articles":
        match = re.match(
            r"^(\d+)\t(\d+)\t(.*)\t([tf])\t(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)\t(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)$",
            line,
        )
        if not match:
            raise ValueError(f"Could not parse articles COPY row: {line[:200]}")
        payload = decode_copy_value(match.group(3))
        return {
            "id": decode_copy_value(match.group(1)),
            "user_id": decode_copy_value(match.group(2)),
            "payload": payload,
            "is_hidden": decode_copy_value(match.group(4)),
            "created_at": decode_copy_value(match.group(5)),
            "updated_at": decode_copy_value(match.group(6)),
        }

    raise ValueError(f"Unsupported COPY target: {table_name}")


def parse_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if value in ("t", True):
        return True
    if value in ("f", False):
        return False
    return None


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))


def normalize_dump_tables(tables: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    users = []
    for row in tables["public.users"]:
        users.append(
            {
                **row,
                "id": parse_int(row["id"]),
                "created_at": parse_timestamp(row["created_at"]),
            }
        )

    articles = []
    for row in tables["public.articles"]:
        articles.append(
            {
                **row,
                "id": parse_int(row["id"]),
                "user_id": parse_int(row["user_id"]),
                "payload": row.get("payload"),
                "is_hidden": parse_bool(row["is_hidden"]),
                "created_at": parse_timestamp(row["created_at"]),
                "updated_at": parse_timestamp(row["updated_at"]),
            }
        )

    chats = []
    for row in tables["public.chats"]:
        chats.append(
            {
                **row,
                "id": parse_int(row["id"]),
                "article_id": parse_int(row["article_id"]),
                "created_at": parse_timestamp(row["created_at"]),
            }
        )

    return {
        "users": users,
        "articles": articles,
        "chats": chats,
    }


def normalize_text(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"embed\s+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"false\s*glomex\s*\(ohne\s*2\s*klick\)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"false\s*pinpoll\s*\(ohne\s*2\s*klick\)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\{\s*\"images\"\s*:\s*\[[^\]]*\]\s*\}", " ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.lower()
    text = re.sub(r"-\d+$", "", text)
    text = re.sub(r"\b[a-z]{2,4}\s*/\s*[a-z]{2,4}\b$", " ", text)
    text = re.sub(r"\b[a-z]{2,4}\b$", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_field_label(value: Any) -> str:
    if not value:
        return ""
    text = str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper()
    text = re.sub(r"[^A-Z0-9\s]", " ", text)
    text = re.sub(r"\s+", "", text)
    return text


def token_set(value: Any, limit: int = 120) -> set[str]:
    normalized = normalize_text(value)
    if not normalized:
        return set()
    return set(normalized.split()[:limit])


def content_token_set(value: Any, limit: int = 160) -> set[str]:
    normalized = normalize_text(value)
    if not normalized:
        return set()
    tokens: list[str] = []
    for token in normalized.split():
        if len(token) <= 3:
            continue
        if token in GERMAN_STOPWORDS:
            continue
        tokens.append(token)
        if len(tokens) >= limit:
            break
    return set(tokens)


def text_ratio(left: Any, right: Any) -> float:
    left_text = normalize_text(left)
    right_text = normalize_text(right)
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(a=left_text, b=right_text).ratio()


def jaccard_score(left: Any, right: Any) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(intersection) / len(union)


def overlap_score(left: Any, right: Any) -> float:
    left_tokens = content_token_set(left)
    right_tokens = content_token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    return len(intersection) / min(len(left_tokens), len(right_tokens))


def body_similarity(left: Any, right: Any) -> float:
    left_tokens = content_token_set(left)
    right_tokens = content_token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    keyword_jaccard = len(intersection) / len(left_tokens | right_tokens)
    keyword_overlap = len(intersection) / min(len(left_tokens), len(right_tokens))
    ratio = text_ratio(left, right)
    overlap = overlap_score(left, right)
    if keyword_overlap < 0.18 and keyword_jaccard < 0.12:
        return max(keyword_jaccard, overlap * 0.8)
    return max(keyword_jaccard * 1.35, keyword_overlap, ratio * 0.35)


def build_cms_index(cms_articles: list[dict[str, Any]]) -> dict[str, dict[int | str, list[dict[str, Any]]]]:
    index: dict[str, dict[int | str, list[dict[str, Any]]]] = {
        "content_id": defaultdict(list),
        "origin_id": defaultdict(list),
    }
    for article in cms_articles:
        content_id = article.get("content_id")
        if content_id is None:
            pass
        else:
            index["content_id"][int(content_id)].append(article)

        origin_id = article.get("origin_id")
        if origin_id:
            index["origin_id"][str(origin_id)].append(article)
    return index


def pick_cms_article(
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


def get_used_db_fields(csv_row: dict[str, str]) -> list[str]:
    used_fields_raw = csv_row.get("Verwendete Felder", "")
    if not used_fields_raw:
        return []

    fields: list[str] = []
    for part in used_fields_raw.split(","):
        normalized_part = normalize_field_label(part)
        if not normalized_part:
            continue

        candidates: list[str] = []
        compact_part = normalized_part
        if compact_part:
            candidates.append(compact_part)

        code_match = re.search(r"\(([^)]+)\)", str(part))
        if code_match:
            compact_code = normalize_field_label(code_match.group(1))
            if compact_code:
                candidates.insert(0, compact_code)

        for candidate in candidates:
            mapped = USED_FIELD_CODE_MAP.get(candidate)
            if mapped and mapped not in fields:
                fields.append(mapped)
                break
    return fields


def score_article_match(
    article: dict[str, Any],
    cms_article: dict[str, Any] | None,
    used_db_fields: list[str],
    offset: int,
) -> float:
    if cms_article is None:
        return max(0.0, 0.2 - (offset * 0.02))

    match_fields = article.get("match_fields", {})

    cms_titles = [
        cms_article.get("h1"),
        cms_article.get("line_head"),
        cms_article.get("seo_title"),
        cms_article.get("content_name"),
    ]
    score = 0.0
    active_fields = used_db_fields or ["headline", "roofline", "subline", "text", "teaser", "subheadings", "tags"]

    if "headline" in active_fields:
        title_score = max(text_ratio(match_fields.get("headline"), title) for title in cms_titles)
        score += title_score * 3.0

    if "roofline" in active_fields:
        roofline_score = text_ratio(match_fields.get("roofline"), cms_article.get("line_roof"))
        score += roofline_score * 1.5

    if "subline" in active_fields:
        subline_score = text_ratio(match_fields.get("subline"), cms_article.get("line_sub"))
        score += subline_score * 1.0

    if "text" in active_fields:
        body_source = match_fields.get("text") or article.get("payload")
        body_score = body_similarity(body_source, cms_article.get("text"))
        score += body_score * 2.5

    if "teaser" in active_fields:
        teaser_target = cms_article.get("paywall_teaser") or cms_article.get("text")
        teaser_score = jaccard_score(match_fields.get("teaser"), teaser_target)
        score += teaser_score * 0.75

    if "subheadings" in active_fields:
        subheading_score = jaccard_score(match_fields.get("subheadings"), cms_article.get("text"))
        score += subheading_score * 0.5

    if "tags" in active_fields:
        tag_score = jaccard_score(
            match_fields.get("tags"),
            " ".join(filter(None, [cms_article.get("h1"), cms_article.get("line_head"), cms_article.get("text")])),
        )
        score += tag_score * 0.25

    if "shorten_text" in active_fields:
        shortened_score = jaccard_score(match_fields.get("shorten_text"), cms_article.get("text"))
        score += shortened_score * 0.5

    score -= offset * 0.05
    return score


def serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(sep=" ")


def serializable_article(article: dict[str, Any]) -> dict[str, Any]:
    data = {
        **article,
        "created_at": serialize_datetime(article.get("created_at")),
        "updated_at": serialize_datetime(article.get("updated_at")),
    }
    return data


def serializable_chat(chat: dict[str, Any]) -> dict[str, Any]:
    return {
        **chat,
        "created_at": serialize_datetime(chat.get("created_at")),
    }


def build_output(
    username: str,
    csv_entries: list[CsvEntry],
    cms_index: dict[str, dict[int | str, list[dict[str, Any]]]],
    user_articles: list[dict[str, Any]],
    chats_by_article_id: dict[int, list[dict[str, Any]]],
    lookahead: int,
    min_score: float,
) -> dict[str, Any]:
    matched_items: list[dict[str, Any]] = []
    filtered_out_low_score_items: list[dict[str, Any]] = []
    unmatched_csv_entries: list[dict[str, Any]] = []
    skipped_articles: list[dict[str, Any]] = []
    available_articles = list(user_articles)
    article_rank_by_id = {article["id"]: index + 1 for index, article in enumerate(user_articles)}

    article_latest_chat_fields: dict[int, dict[str, str]] = {}
    for article in user_articles:
        sorted_chats = sorted(
            chats_by_article_id.get(article["id"], []),
            key=lambda chat: ((chat.get("created_at") or datetime.min), chat.get("id") or 0),
        )
        latest_by_field: dict[str, str] = {}
        latest_generate_by_field: dict[str, str] = {}
        for chat in sorted_chats:
            field_name = chat.get("field_name")
            content = chat.get("content")
            if not field_name or content is None:
                continue
            latest_by_field[field_name] = str(content)
            if chat.get("chat_type") == "generate":
                latest_generate_by_field[field_name] = str(content)
        match_fields = dict(latest_by_field)
        for key, value in latest_generate_by_field.items():
            match_fields[key] = value
        article["match_fields"] = match_fields
        article_latest_chat_fields[article["id"]] = match_fields

    for sequence_index, entry in enumerate(csv_entries, start=1):
        cms_article = pick_cms_article(
            cms_index,
            entry.cms_lookup_field,
            entry.cms_lookup_value,
            entry.occurrence,
        )
        used_db_fields = get_used_db_fields(entry.raw)
        remaining = available_articles
        candidate_slice = remaining[: max(lookahead, 1)]
        if remaining:
            candidate_slice = remaining

        selected_article = None
        selected_index = None
        selected_score = None
        candidate_scores: list[dict[str, Any]] = []

        for offset, article in enumerate(candidate_slice):
            score = score_article_match(article, cms_article, used_db_fields, offset)
            candidate_scores.append(
                {
                    "article_id": article["id"],
                    "offset": offset,
                    "score": round(score, 4),
                    "headline": article.get("match_fields", {}).get("headline"),
                }
            )
        visible_candidate_scores = [candidate for candidate in candidate_scores if candidate["score"] >= 1.0]
        if candidate_slice:
            best_candidate = max(candidate_scores, key=lambda candidate: candidate["score"])
            chosen_candidate = best_candidate
            best_offset = int(chosen_candidate["offset"])
            selected_article = candidate_slice[best_offset]
            selected_index = best_offset
            selected_score = chosen_candidate["score"]

        if selected_article is None:
            unmatched_csv_entries.append(
                {
                    "sequence_index": sequence_index,
                    "csv_row_number": entry.row_number,
                    "content_id": entry.create_id,
                    "content_id_occurrence": entry.occurrence,
                    "participant_username": username,
                    "csv": entry.raw,
                    "used_db_fields": used_db_fields,
                    "cms_article": cms_article,
                    "db_match": None,
                    "match_status": "no-db-article-left",
                }
            )
            continue

        article_chats = sorted(
            chats_by_article_id.get(selected_article["id"], []),
            key=lambda chat: ((chat.get("created_at") or datetime.min), chat.get("id") or 0),
        )
        generated_chats = [chat for chat in article_chats if chat.get("chat_type") == "generate"]
        latest_chat_by_field: dict[str, dict[str, Any]] = {}
        for chat in article_chats:
            field_name = chat.get("field_name")
            if field_name:
                latest_chat_by_field[field_name] = serializable_chat(chat)

        article_rank_for_user = article_rank_by_id.get(selected_article["id"]) if selected_article else None

        item = {
            "sequence_index": sequence_index,
            "csv_row_number": entry.row_number,
            "content_id": entry.create_id,
            "content_id_occurrence": entry.occurrence,
            "participant_username": username,
            "csv": entry.raw,
            "used_db_fields": used_db_fields,
            "cms_article": cms_article,
            "db_match": {
                "match_method": "order",
                "match_score": round(selected_score or 0.0, 4),
                "article_rank_for_user": article_rank_for_user,
                "candidate_scores": visible_candidate_scores,
                "article": serializable_article(selected_article),
                "match_fields": article_latest_chat_fields.get(selected_article["id"], {}),
                "all_chats": [serializable_chat(chat) for chat in article_chats],
                "generated_chats": [serializable_chat(chat) for chat in generated_chats],
                "latest_chat_by_field": latest_chat_by_field,
            },
            "match_status": "matched",
        }

        if (selected_score or 0.0) < min_score:
            item["match_status"] = "filtered-low-score"
            filtered_out_low_score_items.append(item)
        else:
            available_articles = [article for article in available_articles if article["id"] != selected_article["id"]]
            matched_items.append(item)

    unmatched_articles = [serializable_article(article) for article in available_articles]

    return {
        "meta": {
            "participant_username": username,
            "csv_entry_count": len(csv_entries),
            "db_article_count_for_user": len(user_articles),
            "matched_count": len([item for item in matched_items if item["db_match"] is not None]),
            "filtered_low_score_count": len(filtered_out_low_score_items),
            "unmatched_csv_entry_count": len(unmatched_csv_entries),
            "min_score": min_score,
            "unmatched_db_article_count": len(skipped_articles) + len(unmatched_articles),
            "generated_chat_count": sum(
                len(item["db_match"]["generated_chats"])
                for item in matched_items
                if item["db_match"] is not None
            ),
        },
        "items": matched_items,
        "filtered_out_low_score_items": filtered_out_low_score_items,
        "unmatched_csv_entries": unmatched_csv_entries,
        "unmatched_db_articles_before_or_between_matches": skipped_articles,
        "unmatched_db_articles_after_last_match": unmatched_articles,
    }


def main() -> None:
    args = parse_args()
    csv_path = Path(args.csv)
    cms_json_path = Path(args.cms_json)
    sql_dump_path = Path(args.sql_dump)
    output_path = Path(args.output) if args.output else csv_path.with_name(f"{csv_path.stem}_matched.json")

    participant_from_csv, csv_entries, csv_headers = parse_csv(csv_path)
    username = args.username or participant_from_csv
    if not username:
        raise ValueError("Could not determine participant username. Pass --username explicitly.")

    cms_articles = parse_cms_json(cms_json_path)
    cms_index = build_cms_index(cms_articles)

    raw_tables = parse_copy_tables(sql_dump_path)
    tables = normalize_dump_tables(raw_tables)

    users_by_username = {str(user["username"]).lower(): user for user in tables["users"]}
    user = users_by_username.get(username.lower())
    if user is None:
        raise ValueError(f"User {username!r} was not found in {sql_dump_path}")

    user_articles = sorted(
        [article for article in tables["articles"] if article.get("user_id") == user["id"]],
        key=lambda article: ((article.get("created_at") or datetime.min), article.get("id") or 0),
    )
    chats_by_article_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for chat in tables["chats"]:
        article_id = chat.get("article_id")
        if article_id is not None:
            chats_by_article_id[article_id].append(chat)
    user_articles = [article for article in user_articles if chats_by_article_id.get(article["id"])]

    output = build_output(
        username=username,
        csv_entries=csv_entries,
        cms_index=cms_index,
        user_articles=user_articles,
        chats_by_article_id=chats_by_article_id,
        lookahead=max(1, args.lookahead),
        min_score=args.min_score,
    )
    output["meta"]["csv_headers"] = csv_headers
    output["meta"]["csv_path"] = str(csv_path)
    output["meta"]["cms_json_path"] = str(cms_json_path)
    output["meta"]["sql_dump_path"] = str(sql_dump_path)
    output["meta"]["output_path"] = str(output_path)

    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()