from __future__ import annotations

import argparse
import json
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


FIELD_MAP = {
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
    "PZ": "teaser",
    "TAGS": "tags",
    "KÜ": "shorten_text",
    "KU": "shorten_text",
    "KURZEN": "shorten_text",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze phase 1 and phase 2 matched exports and write a combined report."
    )
    parser.add_argument(
        "--phase1-dir",
        default="masterthesis/excel/phase1",
        help="Directory containing phase 1 *_matched.json files.",
    )
    parser.add_argument(
        "--phase2-dir",
        default="masterthesis/excel/phase2",
        help="Directory containing phase 2 *_matched.json files.",
    )
    parser.add_argument(
        "--output-json",
        default="masterthesis/phase_comparison_report.json",
        help="Output path for the machine-readable JSON report.",
    )
    parser.add_argument(
        "--output-md",
        default="masterthesis/phase_comparison_report.md",
        help="Output path for the human-readable Markdown report.",
    )
    return parser.parse_args()


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def mean_or_none(values: list[float | None]) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return round(statistics.mean(filtered), 2)


def median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values), 2)


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


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


def parse_used_fields(raw_value: Any) -> list[str]:
    if not raw_value:
        return []

    fields: list[str] = []
    for part in str(raw_value).split(","):
        raw_part = part.strip()
        if not raw_part:
            continue

        candidates: list[str] = []
        normalized_part = normalize_field_label(raw_part)
        if normalized_part:
            candidates.append(normalized_part)

        code_match = re.search(r"\(([^)]+)\)", raw_part)
        if code_match:
            normalized_code = normalize_field_label(code_match.group(1))
            if normalized_code:
                candidates.insert(0, normalized_code)

        for candidate in candidates:
            mapped = FIELD_MAP.get(candidate)
            if mapped and mapped not in fields:
                fields.append(mapped)
                break

    return fields


def coverage_pct(matched: int, total: int) -> float:
    if not total:
        return 0.0
    return round((matched / total) * 100, 1)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_phase1(path: Path) -> tuple[str, dict[str, Any]]:
    data = load_json(path)
    meta = data["meta"]
    participant = str(meta["participant_username"])
    matched_items = data["items"]
    unmatched_items = data["unmatched_csv_entries"]
    all_entries = matched_items + unmatched_items

    text_times = [to_float(entry["csv"].get("Schreibzeit für Artikeltext")) for entry in all_entries]
    extra_times = [to_float(entry["csv"].get("Schreibzeit für weitere Felder")) for entry in all_entries]
    total_times = [(text_time or 0.0) + (extra_time or 0.0) for text_time, extra_time in zip(text_times, extra_times)]
    complexities = [to_float(entry["csv"].get("Komplexität des Artikels (1-5)")) for entry in all_entries]
    qualities = [to_float(entry["csv"].get("Qualitative Artikeleinschätzung (1-5)")) for entry in all_entries]

    research_counts = Counter(
        str(entry["csv"].get("Recheche") or "").strip()
        for entry in all_entries
        if str(entry["csv"].get("Recheche") or "").strip()
    )
    accuracy_counts = Counter(
        str(entry["csv"].get("Genauigkeit der Schreibzeit") or "").strip()
        for entry in all_entries
        if str(entry["csv"].get("Genauigkeit der Schreibzeit") or "").strip()
    )

    return participant, {
        "csv_entries": meta["csv_entry_count"],
        "matched_entries": meta["matched_count"],
        "unmatched_entries": meta["unmatched_csv_entry_count"],
        "coverage_pct": coverage_pct(meta["matched_count"], meta["csv_entry_count"]),
        "text_time_sum": round(sum(value for value in text_times if value is not None), 2),
        "text_time_count": len([value for value in text_times if value is not None]),
        "extra_time_sum": round(sum(value for value in extra_times if value is not None), 2),
        "extra_time_count": len([value for value in extra_times if value is not None]),
        "complexity_sum": round(sum(value for value in complexities if value is not None), 2),
        "complexity_count": len([value for value in complexities if value is not None]),
        "quality_sum": round(sum(value for value in qualities if value is not None), 2),
        "quality_count": len([value for value in qualities if value is not None]),
        "avg_text_time": mean_or_none(text_times),
        "avg_extra_time": mean_or_none(extra_times),
        "avg_total_time": mean_or_none(total_times),
        "median_total_time": median_or_none(total_times),
        "total_minutes": round(sum(total_times), 2),
        "avg_complexity": mean_or_none(complexities),
        "avg_quality": mean_or_none(qualities),
        "research_counts": dict(research_counts),
        "accuracy_counts": dict(accuracy_counts),
        "matched_content_ids": [str(entry["content_id"]) for entry in matched_items],
        "unmatched_content_ids": [str(entry["content_id"]) for entry in unmatched_items],
        "source_file": str(path),
    }


def summarize_phase2(path: Path) -> tuple[str, dict[str, Any]]:
    data = load_json(path)
    meta = data["meta"]
    participant = str(meta["participant_username"])
    matched_items = data["items"]
    filtered_items = data["filtered_out_low_score_items"]
    unmatched_items = data["unmatched_csv_entries"]
    all_entries = matched_items + filtered_items + unmatched_items

    text_times = [to_float(entry["csv"].get("Schreibzeit für Artikeltext")) for entry in all_entries]
    extra_times = [to_float(entry["csv"].get("Schreibzeit für weitere Felder")) for entry in all_entries]
    total_times = [(text_time or 0.0) + (extra_time or 0.0) for text_time, extra_time in zip(text_times, extra_times)]
    complexities = [to_float(entry["csv"].get("Komplexität des Artikels (1-5)")) for entry in all_entries]
    qualities = [to_float(entry["csv"].get("Qualitative Artikeleinschätzung (1-5)")) for entry in all_entries]
    satisfaction_scores = [to_float(entry["csv"].get("Zufriedenheit mit KI-Tool (1-5)")) for entry in all_entries]

    research_counts = Counter(
        str(entry["csv"].get("Recheche") or "").strip()
        for entry in all_entries
        if str(entry["csv"].get("Recheche") or "").strip()
    )
    accuracy_counts = Counter(
        str(entry["csv"].get("Genauigkeit der Schreibzeit") or "").strip()
        for entry in all_entries
        if str(entry["csv"].get("Genauigkeit der Schreibzeit") or "").strip()
    )

    used_field_counts_csv = Counter()
    used_field_combo_counts = Counter()
    comments: list[str] = []
    for entry in all_entries:
        used_fields = parse_used_fields(entry["csv"].get("Verwendete Felder"))
        if used_fields:
            used_field_counts_csv.update(used_fields)
            used_field_combo_counts[",".join(used_fields)] += 1
        else:
            used_field_combo_counts["none/0"] += 1

        comment = str(entry["csv"].get("Kommentar") or "").strip()
        if comment:
            comments.append(comment)

    chat_type_counts = Counter()
    chat_field_generate_counts = Counter()
    chat_field_edit_counts = Counter()
    chat_field_all_counts = Counter()
    actual_final_fields_present = Counter()

    articles_with_any_chat = 0
    articles_with_generate = 0
    articles_with_edit = 0
    chats_per_article: list[int] = []
    generates_per_article: list[int] = []
    edits_per_article: list[int] = []
    match_scores: list[float] = []

    for entry in matched_items + filtered_items:
        db_match = entry.get("db_match") or {}
        all_chats = db_match.get("all_chats") or []
        per_article_chat_types = Counter(chat.get("chat_type") for chat in all_chats)

        if all_chats:
            articles_with_any_chat += 1
        if per_article_chat_types.get("generate"):
            articles_with_generate += 1
        if per_article_chat_types.get("edit"):
            articles_with_edit += 1

        chats_per_article.append(len(all_chats))
        generates_per_article.append(per_article_chat_types.get("generate", 0))
        edits_per_article.append(per_article_chat_types.get("edit", 0))

        for chat in all_chats:
            chat_type = chat.get("chat_type") or "unknown"
            field_name = chat.get("field_name") or "unknown"
            chat_type_counts[chat_type] += 1
            chat_field_all_counts[field_name] += 1
            if chat_type == "generate":
                chat_field_generate_counts[field_name] += 1
            elif chat_type == "edit":
                chat_field_edit_counts[field_name] += 1

        for field_name in (db_match.get("match_fields") or {}).keys():
            actual_final_fields_present[field_name] += 1

        match_score = db_match.get("match_score")
        if match_score is not None:
            match_scores.append(float(match_score))

    return participant, {
        "csv_entries": meta["csv_entry_count"],
        "matched_entries": meta["matched_count"],
        "filtered_low_score_entries": meta["filtered_low_score_count"],
        "unmatched_entries": meta["unmatched_csv_entry_count"],
        "db_article_count_for_user": meta["db_article_count_for_user"],
        "generated_chat_count_meta": meta["generated_chat_count"],
        "coverage_pct_matched_only": coverage_pct(meta["matched_count"], meta["csv_entry_count"]),
        "coverage_pct_including_filtered": coverage_pct(
            meta["matched_count"] + meta["filtered_low_score_count"],
            meta["csv_entry_count"],
        ),
        "text_time_sum": round(sum(value for value in text_times if value is not None), 2),
        "text_time_count": len([value for value in text_times if value is not None]),
        "extra_time_sum": round(sum(value for value in extra_times if value is not None), 2),
        "extra_time_count": len([value for value in extra_times if value is not None]),
        "complexity_sum": round(sum(value for value in complexities if value is not None), 2),
        "complexity_count": len([value for value in complexities if value is not None]),
        "quality_sum": round(sum(value for value in qualities if value is not None), 2),
        "quality_count": len([value for value in qualities if value is not None]),
        "satisfaction_sum": round(sum(value for value in satisfaction_scores if value is not None), 2),
        "satisfaction_count": len([value for value in satisfaction_scores if value is not None]),
        "avg_text_time": mean_or_none(text_times),
        "avg_extra_time": mean_or_none(extra_times),
        "avg_total_time": mean_or_none(total_times),
        "median_total_time": median_or_none(total_times),
        "total_minutes": round(sum(total_times), 2),
        "avg_complexity": mean_or_none(complexities),
        "avg_quality": mean_or_none(qualities),
        "avg_satisfaction": mean_or_none(satisfaction_scores),
        "research_counts": dict(research_counts),
        "accuracy_counts": dict(accuracy_counts),
        "used_field_counts_csv": dict(used_field_counts_csv),
        "used_field_combo_counts": dict(used_field_combo_counts),
        "chat_type_counts": dict(chat_type_counts),
        "chat_field_generate_counts": dict(chat_field_generate_counts),
        "chat_field_edit_counts": dict(chat_field_edit_counts),
        "chat_field_all_counts": dict(chat_field_all_counts),
        "actual_final_fields_present": dict(actual_final_fields_present),
        "articles_with_any_chat": articles_with_any_chat,
        "articles_with_generate": articles_with_generate,
        "articles_with_edit": articles_with_edit,
        "avg_chats_per_article_considered": round_or_none(mean_or_none(chats_per_article)),
        "avg_generates_per_article_considered": round_or_none(mean_or_none(generates_per_article)),
        "avg_edits_per_article_considered": round_or_none(mean_or_none(edits_per_article)),
        "avg_match_score_considered": round_or_none(mean_or_none(match_scores), 3),
        "comment_count": len(comments),
        "comments": comments,
        "source_file": str(path),
    }


def build_weighted_phase1_summary(phase1_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_articles = sum(item["csv_entries"] for item in phase1_data.values())
    total_matched = sum(item["matched_entries"] for item in phase1_data.values())
    total_unmatched = sum(item["unmatched_entries"] for item in phase1_data.values())
    total_minutes = round(sum(item["total_minutes"] for item in phase1_data.values()), 2)

    avg_total_time = total_minutes / total_articles if total_articles else None
    text_sum = sum(item["text_time_sum"] for item in phase1_data.values())
    text_count = sum(item["text_time_count"] for item in phase1_data.values())
    extra_sum = sum(item["extra_time_sum"] for item in phase1_data.values())
    extra_count = sum(item["extra_time_count"] for item in phase1_data.values())
    complexity_sum = sum(item["complexity_sum"] for item in phase1_data.values())
    complexity_count = sum(item["complexity_count"] for item in phase1_data.values())
    quality_sum = sum(item["quality_sum"] for item in phase1_data.values())
    quality_count = sum(item["quality_count"] for item in phase1_data.values())

    return {
        "total_articles": total_articles,
        "total_matched": total_matched,
        "total_unmatched": total_unmatched,
        "total_minutes": total_minutes,
        "weighted_avg_total_time": round_or_none(avg_total_time),
        "weighted_avg_text_time": round_or_none(text_sum / text_count if text_count else None),
        "weighted_avg_extra_time": round_or_none(extra_sum / extra_count if extra_count else None),
        "weighted_avg_complexity": round_or_none(complexity_sum / complexity_count if complexity_count else None),
        "weighted_avg_quality": round_or_none(quality_sum / quality_count if quality_count else None),
    }


def build_weighted_phase2_summary(phase2_data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    total_articles = sum(item["csv_entries"] for item in phase2_data.values())
    total_matched = sum(item["matched_entries"] for item in phase2_data.values())
    total_filtered = sum(item["filtered_low_score_entries"] for item in phase2_data.values())
    total_unmatched = sum(item["unmatched_entries"] for item in phase2_data.values())
    total_minutes = round(sum(item["total_minutes"] for item in phase2_data.values()), 2)
    total_generated_chats = sum(item["generated_chat_count_meta"] for item in phase2_data.values())
    total_chat_actions = sum(sum(item["chat_type_counts"].values()) for item in phase2_data.values())
    total_generate_actions = sum(item["chat_type_counts"].get("generate", 0) for item in phase2_data.values())
    total_edit_actions = sum(item["chat_type_counts"].get("edit", 0) for item in phase2_data.values())

    text_sum = sum(item["text_time_sum"] for item in phase2_data.values())
    text_count = sum(item["text_time_count"] for item in phase2_data.values())
    extra_sum = sum(item["extra_time_sum"] for item in phase2_data.values())
    extra_count = sum(item["extra_time_count"] for item in phase2_data.values())
    complexity_sum = sum(item["complexity_sum"] for item in phase2_data.values())
    complexity_count = sum(item["complexity_count"] for item in phase2_data.values())
    quality_sum = sum(item["quality_sum"] for item in phase2_data.values())
    quality_count = sum(item["quality_count"] for item in phase2_data.values())
    satisfaction_sum = sum(item["satisfaction_sum"] for item in phase2_data.values())
    satisfaction_count = sum(item["satisfaction_count"] for item in phase2_data.values())

    used_field_counts_total = Counter()
    used_field_combos_total = Counter()
    chat_generate_total_by_field = Counter()
    chat_edit_total_by_field = Counter()
    chat_all_total_by_field = Counter()

    for item in phase2_data.values():
        used_field_counts_total.update(item["used_field_counts_csv"])
        used_field_combos_total.update(item["used_field_combo_counts"])
        chat_generate_total_by_field.update(item["chat_field_generate_counts"])
        chat_edit_total_by_field.update(item["chat_field_edit_counts"])
        chat_all_total_by_field.update(item["chat_field_all_counts"])

    return {
        "total_articles": total_articles,
        "total_matched": total_matched,
        "total_filtered": total_filtered,
        "total_unmatched": total_unmatched,
        "total_minutes": total_minutes,
        "total_generated_chats_meta": total_generated_chats,
        "total_chat_actions": total_chat_actions,
        "total_generate_actions": total_generate_actions,
        "total_edit_actions": total_edit_actions,
        "weighted_avg_total_time": round_or_none(total_minutes / total_articles if total_articles else None),
        "weighted_avg_text_time": round_or_none(text_sum / text_count if text_count else None),
        "weighted_avg_extra_time": round_or_none(extra_sum / extra_count if extra_count else None),
        "weighted_avg_complexity": round_or_none(complexity_sum / complexity_count if complexity_count else None),
        "weighted_avg_quality": round_or_none(quality_sum / quality_count if quality_count else None),
        "weighted_avg_satisfaction": round_or_none(satisfaction_sum / satisfaction_count if satisfaction_count else None),
        "used_field_counts_total": dict(used_field_counts_total),
        "used_field_combos_total": dict(used_field_combos_total),
        "chat_generate_total_by_field": dict(chat_generate_total_by_field),
        "chat_edit_total_by_field": dict(chat_edit_total_by_field),
        "chat_all_total_by_field": dict(chat_all_total_by_field),
    }


def build_comparison(phase1_data: dict[str, dict[str, Any]], phase2_data: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    participants = sorted(set(phase1_data) | set(phase2_data))
    comparison: dict[str, dict[str, Any]] = {}
    for participant in participants:
        phase1 = phase1_data.get(participant, {})
        phase2 = phase2_data.get(participant, {})

        phase1_avg_total = phase1.get("avg_total_time")
        phase2_avg_total = phase2.get("avg_total_time")
        phase1_avg_text = phase1.get("avg_text_time")
        phase2_avg_text = phase2.get("avg_text_time")
        phase1_avg_extra = phase1.get("avg_extra_time")
        phase2_avg_extra = phase2.get("avg_extra_time")
        phase1_avg_complexity = phase1.get("avg_complexity")
        phase2_avg_complexity = phase2.get("avg_complexity")
        phase1_avg_quality = phase1.get("avg_quality")
        phase2_avg_quality = phase2.get("avg_quality")

        comparison[participant] = {
            "phase1_articles": phase1.get("csv_entries"),
            "phase2_articles": phase2.get("csv_entries"),
            "article_delta": (phase2.get("csv_entries", 0) - phase1.get("csv_entries", 0)) if phase1 or phase2 else None,
            "phase1_avg_total_time": phase1_avg_total,
            "phase2_avg_total_time": phase2_avg_total,
            "avg_total_time_delta": round_or_none((phase2_avg_total or 0.0) - (phase1_avg_total or 0.0)) if phase1 and phase2 else None,
            "phase1_avg_text_time": phase1_avg_text,
            "phase2_avg_text_time": phase2_avg_text,
            "text_time_delta": round_or_none((phase2_avg_text or 0.0) - (phase1_avg_text or 0.0)) if phase1 and phase2 else None,
            "phase1_avg_extra_time": phase1_avg_extra,
            "phase2_avg_extra_time": phase2_avg_extra,
            "extra_time_delta": round_or_none((phase2_avg_extra or 0.0) - (phase1_avg_extra or 0.0)) if phase1 and phase2 else None,
            "phase1_avg_complexity": phase1_avg_complexity,
            "phase2_avg_complexity": phase2_avg_complexity,
            "complexity_delta": round_or_none((phase2_avg_complexity or 0.0) - (phase1_avg_complexity or 0.0)) if phase1 and phase2 else None,
            "phase1_avg_quality": phase1_avg_quality,
            "phase2_avg_quality": phase2_avg_quality,
            "quality_delta": round_or_none((phase2_avg_quality or 0.0) - (phase1_avg_quality or 0.0)) if phase1 and phase2 else None,
        }
    return comparison


def build_report(phase1_dir: Path, phase2_dir: Path) -> dict[str, Any]:
    phase1_files = sorted(phase1_dir.glob("*_matched.json"))
    phase2_files = sorted(phase2_dir.glob("*_matched.json"))
    if not phase1_files:
        raise ValueError(f"No phase 1 matched JSON files found in {phase1_dir}")
    if not phase2_files:
        raise ValueError(f"No phase 2 matched JSON files found in {phase2_dir}")

    phase1_data: dict[str, dict[str, Any]] = {}
    phase2_data: dict[str, dict[str, Any]] = {}

    for path in phase1_files:
        participant, summary = summarize_phase1(path)
        phase1_data[participant] = summary

    for path in phase2_files:
        participant, summary = summarize_phase2(path)
        phase2_data[participant] = summary

    return {
        "aggregate": {
            "phase1": build_weighted_phase1_summary(phase1_data),
            "phase2": build_weighted_phase2_summary(phase2_data),
        },
        "comparison": build_comparison(phase1_data, phase2_data),
        "phase1": phase1_data,
        "phase2": phase2_data,
    }


def format_counter(counter_data: dict[str, int]) -> str:
    if not counter_data:
        return "keine"
    ordered = sorted(counter_data.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{key}: {value}" for key, value in ordered)


def format_comments(comments: list[str]) -> str:
    if not comments:
        return "Keine Kommentare erfasst."
    return "\n".join(f"- {comment}" for comment in comments)


def render_markdown(report: dict[str, Any]) -> str:
    aggregate_phase1 = report["aggregate"]["phase1"]
    aggregate_phase2 = report["aggregate"]["phase2"]
    comparison = report["comparison"]
    phase1 = report["phase1"]
    phase2 = report["phase2"]

    lines = [
    ]

    for participant, values in comparison.items():
        lines.append(
            f"| {participant} | {values['phase1_articles']} | {values['phase2_articles']} | {values['article_delta']} | {values['phase1_avg_total_time']} | {values['phase2_avg_total_time']} | {values['avg_total_time_delta']} | {values['phase1_avg_quality']} | {values['phase2_avg_quality']} |"
        )

    for participant in sorted(comparison):
        phase1_item = phase1.get(participant, {})
        phase2_item = phase2.get(participant, {})
        lines.extend(
            [
            
            ]
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    phase1_dir = Path(args.phase1_dir)
    phase2_dir = Path(args.phase2_dir)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)

    report = build_report(phase1_dir, phase2_dir)

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.write_text(render_markdown(report), encoding="utf-8")


if __name__ == "__main__":
    main()