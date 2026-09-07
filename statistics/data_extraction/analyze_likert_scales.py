from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence, cast
from xml.sax.saxutils import escape


QUALITY_KEY = "QUALITATIVEARTIKELEINSCHATZUNG15"
COMPLEXITY_KEY = "KOMPLEXITATDESARTIKELS15"
SATISFACTION_KEY = "ZUFRIEDENHEITMITKITOOL15"
PARTICIPANT_KEY = "TEILNEHMER"
HEADER_PREFIX = "CREATEIDNGENID"
LIKERT_LEVELS = [1, 2, 3, 4, 5]
PHASE_QUALITY_LABELS = {
    "phase1": "Phase 1",
    "phase2": "Phase 2",
}


@dataclass(slots=True)
class Entry:
    participant: str
    phase: str
    quality: int | None
    complexity: int | None
    satisfaction: int | None
    source_file: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Likert-scale CSV exports for phase 1 and phase 2 and generate SVG charts."
    )
    parser.add_argument(
        "--phase1-dir",
        default="masterthesis/excel/phase1",
        help="Directory containing phase 1 CSV files.",
    )
    parser.add_argument(
        "--phase2-dir",
        default="masterthesis/excel/phase2",
        help="Directory containing phase 2 CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        default="masterthesis/likert_analysis",
        help="Directory for generated reports and SVG charts.",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.upper()
    return "".join(char for char in text if char.isalnum())


def to_int(value: str) -> int | None:
    text = (value or "").strip()
    if not text:
        return None
    text = text.strip("()[]{}")
    try:
        number = int(float(text.replace(",", ".")))
    except ValueError:
        return None
    if number not in LIKERT_LEVELS:
        return None
    return number


def safe_mean(values: Iterable[int | float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(statistics.mean(filtered), 2)


def iter_csv_paths(directory: Path) -> list[Path]:
    return sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".csv")


def read_csv_rows(path: Path) -> list[list[str]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = path.read_text(encoding=encoding)
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;")
                delimiter = dialect.delimiter
            except csv.Error:
                delimiter = ";" if text.count(";") > text.count(",") else ","
            return list(csv.reader(text.splitlines(), delimiter=delimiter))
        except UnicodeDecodeError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    raise ValueError(f"Could not read CSV file {path}")


def parse_csv_file(path: Path, phase: str) -> list[Entry]:
    rows = read_csv_rows(path)

    participant = "UNKNOWN"
    header_row_index: int | None = None
    normalized_header_map: dict[int, str] = {}

    for index, row in enumerate(rows):
        if not row:
            continue
        first_cell = normalize_text(row[0])
        if first_cell == PARTICIPANT_KEY and len(row) > 1 and row[1].strip():
            participant = row[1].strip().upper()
        if first_cell == HEADER_PREFIX:
            header_row_index = index
            normalized_header_map = {
                column_index: normalize_text(header)
                for column_index, header in enumerate(row)
                if header.strip()
            }
            break

    if header_row_index is None:
        raise ValueError(f"No data header found in {path}")

    entries: list[Entry] = []
    for row in rows[header_row_index + 1 :]:
        if not row or not any(cell.strip() for cell in row):
            continue

        cells = {normalized_header_map[index]: value.strip() for index, value in enumerate(row) if index in normalized_header_map}
        content_id = cells.get(HEADER_PREFIX, "")
        if not content_id:
            continue

        entries.append(
            Entry(
                participant=participant,
                phase=phase,
                quality=to_int(cells.get(QUALITY_KEY, "")),
                complexity=to_int(cells.get(COMPLEXITY_KEY, "")),
                satisfaction=to_int(cells.get(SATISFACTION_KEY, "")),
                source_file=path.name,
            )
        )

    return entries


def load_phase_entries(directory: Path, phase: str) -> list[Entry]:
    entries: list[Entry] = []
    for path in iter_csv_paths(directory):
        entries.extend(parse_csv_file(path, phase))
    return entries


def distribution(values: Iterable[int | None]) -> dict[str, int]:
    counts = Counter(value for value in values if value is not None)
    return {str(level): counts.get(level, 0) for level in LIKERT_LEVELS}


def metric_values(entries: Iterable[Entry], metric: str) -> list[int]:
    values: list[int] = []
    for entry in entries:
        value = getattr(entry, metric)
        if value is not None:
            values.append(int(value))
    return values


def mean_by_complexity(entries: Iterable[Entry], metric: str) -> dict[str, float | None]:
    grouped: dict[int, list[int]] = defaultdict(list)
    for entry in entries:
        complexity = entry.complexity
        value = getattr(entry, metric)
        if complexity is None or value is None:
            continue
        grouped[complexity].append(value)
    return {str(level): safe_mean(grouped.get(level, [])) for level in LIKERT_LEVELS}


def summarize_entries(entries: list[Entry]) -> dict[str, object]:
    return {
        "count": len(entries),
        "quality_mean": safe_mean(entry.quality for entry in entries),
        "complexity_mean": safe_mean(entry.complexity for entry in entries),
        "satisfaction_mean": safe_mean(entry.satisfaction for entry in entries),
        "quality_distribution": distribution(entry.quality for entry in entries),
        "satisfaction_distribution": distribution(entry.satisfaction for entry in entries),
        "quality_by_complexity": mean_by_complexity(entries, "quality"),
    }


def build_summary(phase1_entries: list[Entry], phase2_entries: list[Entry]) -> dict[str, object]:
    participants = sorted({entry.participant for entry in phase1_entries + phase2_entries})

    overall = {
        "phase1": summarize_entries(phase1_entries),
        "phase2": summarize_entries(phase2_entries),
        "participants": participants,
    }

    by_participant: dict[str, object] = {}
    for participant in participants:
        participant_phase1 = [entry for entry in phase1_entries if entry.participant == participant]
        participant_phase2 = [entry for entry in phase2_entries if entry.participant == participant]
        by_participant[participant] = {
            "phase1": summarize_entries(participant_phase1),
            "phase2": summarize_entries(participant_phase2),
        }

    return {
        "overall": overall,
        "by_participant": by_participant,
    }


def format_mean(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def write_summary_files(summary: dict[str, Any], output_dir: Path) -> None:
    summary_json = output_dir / "summary.json"
    summary_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    overall = cast(dict[str, Any], summary["overall"])
    overall_phase1 = cast(dict[str, Any], overall["phase1"])
    overall_phase2 = cast(dict[str, Any], overall["phase2"])
    participants = cast(list[str], overall["participants"])

    lines = [
        "# Likert analysis",
        "",
        "## Overall",
        "",
        f"- Phase 1 quality mean: {format_mean(overall_phase1['quality_mean'])}",
        f"- Phase 2 quality mean: {format_mean(overall_phase2['quality_mean'])}",
        f"- Phase 1 complexity mean: {format_mean(overall_phase1['complexity_mean'])}",
        f"- Phase 2 complexity mean: {format_mean(overall_phase2['complexity_mean'])}",
        f"- Phase 2 satisfaction mean: {format_mean(overall_phase2['satisfaction_mean'])}",
        "",
        "## Participants",
        "",
    ]

    by_participant = cast(dict[str, Any], summary["by_participant"])
    for participant in participants:
        participant_summary = cast(dict[str, Any], by_participant[participant])
        phase1 = cast(dict[str, Any], participant_summary["phase1"])
        phase2 = cast(dict[str, Any], participant_summary["phase2"])
        lines.extend(
            [
                f"### {participant}",
                "",
                f"- Phase 1 quality mean: {format_mean(phase1['quality_mean'])}",
                f"- Phase 2 quality mean: {format_mean(phase2['quality_mean'])}",
                f"- Phase 1 complexity mean: {format_mean(phase1['complexity_mean'])}",
                f"- Phase 2 complexity mean: {format_mean(phase2['complexity_mean'])}",
                f"- Phase 2 satisfaction mean: {format_mean(phase2['satisfaction_mean'])}",
                "",
            ]
        )

    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def svg_document(title: str, width: int, height: int, body: list[str]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#fbfaf7" />',
            f'<text x="40" y="35" font-family="Verdana, sans-serif" font-size="22" font-weight="700" fill="#1f2937">{escape(title)}</text>',
            *body,
            "</svg>",
        ]
    )


def write_svg(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def density_points(values: Sequence[int], y_steps: int = 160, bandwidth: float = 0.32) -> list[tuple[float, float]]:
    if not values:
        return []

    points: list[tuple[float, float]] = []
    for step in range(y_steps + 1):
        y_value = 1.0 + (4.0 * step / y_steps)
        density = 0.0
        for value in values:
            z_value = (y_value - value) / bandwidth
            density += math.exp(-0.5 * z_value * z_value)
        density /= len(values)
        points.append((y_value, density))
    return points


def quartiles(values: Sequence[int]) -> tuple[float, float, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = statistics.median(ordered)
    lower_half = ordered[: len(ordered) // 2]
    upper_half = ordered[(len(ordered) + 1) // 2 :]
    q1 = statistics.median(lower_half) if lower_half else ordered[0]
    q3 = statistics.median(upper_half) if upper_half else ordered[-1]
    return float(q1), float(midpoint), float(q3)


def describe_values(values: Sequence[int]) -> tuple[int, float | None, float | None]:
    if not values:
        return 0, None, None
    mean_value = statistics.mean(values)
    sd_value = statistics.stdev(values) if len(values) > 1 else 0.0
    return len(values), mean_value, sd_value


def format_stat(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def render_box_summary(
    body: list[str],
    *,
    center_x: float,
    y_to_svg: Any,
    values: Sequence[int],
    side: str,
    color: str,
) -> None:
    if not values:
        return

    stats = quartiles(values)
    if stats is None:
        return

    q1, median_value, q3 = stats
    min_value = float(min(values))
    max_value = float(max(values))
    box_width = 12.0
    whisker_offset = 4.0

    if side == "left":
        x0 = center_x - box_width - 2.0
        x1 = center_x - 2.0
        whisker_x = x0 + whisker_offset
    else:
        x0 = center_x + 2.0
        x1 = center_x + box_width + 2.0
        whisker_x = x1 - whisker_offset

    body.append(
        f'<rect x="{x0:.2f}" y="{y_to_svg(q3):.2f}" width="{(x1 - x0):.2f}" height="{(y_to_svg(q1) - y_to_svg(q3)):.2f}" fill="white" stroke="#4b5563" stroke-width="1.2" />'
    )
    body.append(
        f'<line x1="{x0:.2f}" y1="{y_to_svg(median_value):.2f}" x2="{x1:.2f}" y2="{y_to_svg(median_value):.2f}" stroke="#111827" stroke-width="1.6" />'
    )
    body.append(
        f'<line x1="{whisker_x:.2f}" y1="{y_to_svg(max_value):.2f}" x2="{whisker_x:.2f}" y2="{y_to_svg(q3):.2f}" stroke="#4b5563" stroke-width="1.1" />'
    )
    body.append(
        f'<line x1="{whisker_x:.2f}" y1="{y_to_svg(q1):.2f}" x2="{whisker_x:.2f}" y2="{y_to_svg(min_value):.2f}" stroke="#4b5563" stroke-width="1.1" />'
    )
    body.append(
        f'<line x1="{whisker_x - 4:.2f}" y1="{y_to_svg(max_value):.2f}" x2="{whisker_x + 4:.2f}" y2="{y_to_svg(max_value):.2f}" stroke="#4b5563" stroke-width="1.1" />'
    )
    body.append(
        f'<line x1="{whisker_x - 4:.2f}" y1="{y_to_svg(min_value):.2f}" x2="{whisker_x + 4:.2f}" y2="{y_to_svg(min_value):.2f}" stroke="#4b5563" stroke-width="1.1" />'
    )


def render_split_violin_plot(
    *,
    title: str,
    left_group: tuple[str, Sequence[int], str],
    right_group: tuple[str, Sequence[int], str],
    y_label: str,
    output_path: Path,
) -> None:
    width = 980
    height = 560
    left = 90
    right = 40
    top = 70
    bottom = 130
    plot_width = width - left - right
    plot_height = height - top - bottom
    y_min = 1.0
    y_max = 5.0
    center_x = left + plot_width / 2
    max_half_width = min(120.0, plot_width * 0.16)

    def y_to_svg(value: float) -> float:
        return top + plot_height - ((value - y_min) / (y_max - y_min)) * plot_height

    left_density = density_points(left_group[1])
    right_density = density_points(right_group[1])
    max_density = 1.0
    for density in (left_density, right_density):
        if density:
            max_density = max(max_density, max(current_density for _, current_density in density))

    body: list[str] = []
    body.append('<rect x="0" y="0" width="100%" height="100%" fill="#ffffff" />')

    for tick in LIKERT_LEVELS:
        y = y_to_svg(float(tick))
        body.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#d1d5db" stroke-width="1" />')
        body.append(f'<text x="{left - 14}" y="{y + 5:.2f}" text-anchor="end" font-family="Arial, sans-serif" font-size="12" fill="#374151">{tick}</text>')

    body.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827" stroke-width="1.5" />')
    body.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#111827" stroke-width="1.5" />')
    body.append(f'<line x1="{center_x:.2f}" y1="{top}" x2="{center_x:.2f}" y2="{top + plot_height}" stroke="#4b5563" stroke-width="1.2" />')
    body.append(f'<text x="28" y="{top + plot_height / 2:.2f}" transform="rotate(-90 28 {top + plot_height / 2:.2f})" font-family="Arial, sans-serif" font-size="13" fill="#111827">{escape(y_label)}</text>')
    body.append(f'<text x="{center_x:.2f}" y="{height - 25}" text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="#111827">Group</text>')

    if left_density:
        left_points = []
        center_points = []
        for y_value, density_value in left_density:
            half_width = (density_value / max_density) * max_half_width
            y = y_to_svg(y_value)
            left_points.append(f"{center_x - half_width:.2f},{y:.2f}")
            center_points.append(f"{center_x:.2f},{y:.2f}")
        body.append(
            f'<polygon points="{" ".join(left_points + list(reversed(center_points)))}" fill="{left_group[2]}" fill-opacity="0.9" stroke="#4b5563" stroke-width="1.2" />'
        )

    if right_density:
        center_points = []
        right_points = []
        for y_value, density_value in right_density:
            half_width = (density_value / max_density) * max_half_width
            y = y_to_svg(y_value)
            center_points.append(f"{center_x:.2f},{y:.2f}")
            right_points.append(f"{center_x + half_width:.2f},{y:.2f}")
        body.append(
            f'<polygon points="{" ".join(center_points + list(reversed(right_points)))}" fill="{right_group[2]}" fill-opacity="0.9" stroke="#4b5563" stroke-width="1.2" />'
        )

    render_box_summary(body, center_x=center_x, y_to_svg=y_to_svg, values=left_group[1], side="left", color=left_group[2])
    render_box_summary(body, center_x=center_x, y_to_svg=y_to_svg, values=right_group[1], side="right", color=right_group[2])

    left_stats = describe_values(left_group[1])
    right_stats = describe_values(right_group[1])
    left_label_x = center_x - max_half_width * 0.68
    right_label_x = center_x + max_half_width * 0.68

    body.append(f'<text x="{left_label_x:.2f}" y="{height - 62}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12.5" fill="#111827">{escape(left_group[0])}</text>')
    body.append(f'<text x="{right_label_x:.2f}" y="{height - 62}" text-anchor="middle" font-family="Arial, sans-serif" font-size="12.5" fill="#111827">{escape(right_group[0])}</text>')
    body.append(
        f'<text x="{left_label_x:.2f}" y="{height - 44}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11.5" fill="#374151">n={left_stats[0]}, M={format_stat(left_stats[1])}, SD={format_stat(left_stats[2])}</text>'
    )
    body.append(
        f'<text x="{right_label_x:.2f}" y="{height - 44}" text-anchor="middle" font-family="Arial, sans-serif" font-size="11.5" fill="#374151">n={right_stats[0]}, M={format_stat(right_stats[1])}, SD={format_stat(right_stats[2])}</text>'
    )

    content = "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            *body,
            f'<text x="{width / 2:.2f}" y="30" text-anchor="middle" font-family="Arial, sans-serif" font-size="22" fill="#111827">{escape(title)}</text>',
            "</svg>",
        ]
    )
    write_svg(output_path, content)


def render_violin_plot(
    *,
    title: str,
    groups: Sequence[tuple[str, Sequence[int], str]],
    y_label: str,
    output_path: Path,
) -> None:
    width = 980
    height = 560
    left = 80
    right = 40
    top = 80
    bottom = 90
    plot_width = width - left - right
    plot_height = height - top - bottom
    y_min = 1.0
    y_max = 5.0

    def y_to_svg(value: float) -> float:
        return top + plot_height - ((value - y_min) / (y_max - y_min)) * plot_height

    max_density = 1.0
    densities: list[list[tuple[float, float]]] = []
    for _, values, _ in groups:
        current = density_points(values)
        densities.append(current)
        if current:
            max_density = max(max_density, max(density for _, density in current))

    body: list[str] = []
    for tick in LIKERT_LEVELS:
        y = y_to_svg(float(tick))
        body.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#d1d5db" stroke-width="1" />')
        body.append(f'<text x="{left - 12}" y="{y + 5:.2f}" text-anchor="end" font-family="Verdana, sans-serif" font-size="12" fill="#4b5563">{tick}</text>')

    body.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827" stroke-width="2" />')
    body.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#111827" stroke-width="2" />')
    body.append(f'<text x="22" y="{top + plot_height / 2:.2f}" transform="rotate(-90 22 {top + plot_height / 2:.2f})" font-family="Verdana, sans-serif" font-size="13" fill="#374151">{escape(y_label)}</text>')

    group_width = plot_width / max(len(groups), 1)
    max_half_width = min(46.0, group_width * 0.28)

    for index, (label, values, color) in enumerate(groups):
        center_x = left + group_width * index + group_width / 2
        body.append(f'<text x="{center_x:.2f}" y="{height - 45}" text-anchor="middle" font-family="Verdana, sans-serif" font-size="12" fill="#374151">{escape(label)}</text>')

        density = densities[index]
        if density:
            left_points: list[str] = []
            right_points: list[str] = []
            for y_value, density_value in density:
                half_width = (density_value / max_density) * max_half_width
                y = y_to_svg(y_value)
                left_points.append(f"{center_x - half_width:.2f},{y:.2f}")
                right_points.append(f"{center_x + half_width:.2f},{y:.2f}")
            polygon_points = " ".join(left_points + list(reversed(right_points)))
            body.append(f'<polygon points="{polygon_points}" fill="{color}" fill-opacity="0.35" stroke="{color}" stroke-width="2" />')

        for value in values:
            body.append(f'<circle cx="{center_x:.2f}" cy="{y_to_svg(float(value)):.2f}" r="3.2" fill="{color}" fill-opacity="0.75" />')

        stats = quartiles(values)
        if stats is not None:
            q1, median_value, q3 = stats
            body.append(
                f'<line x1="{center_x - 12:.2f}" y1="{y_to_svg(median_value):.2f}" x2="{center_x + 12:.2f}" y2="{y_to_svg(median_value):.2f}" stroke="#111827" stroke-width="2.5" />'
            )
            body.append(
                f'<line x1="{center_x:.2f}" y1="{y_to_svg(q1):.2f}" x2="{center_x:.2f}" y2="{y_to_svg(q3):.2f}" stroke="#111827" stroke-width="1.5" stroke-dasharray="4 3" />'
            )
            body.append(
                f'<text x="{center_x:.2f}" y="{max(top - 6, y_to_svg(median_value) - 10):.2f}" text-anchor="middle" font-family="Verdana, sans-serif" font-size="11" fill="#111827">M {statistics.mean(values):.2f}</text>'
            )

    legend_x = width - right - 180
    legend_y = 30
    for legend_index, (label, _, color) in enumerate(groups):
        y = legend_y + legend_index * 24
        body.append(f'<rect x="{legend_x}" y="{y - 10}" width="16" height="16" rx="3" fill="{color}" fill-opacity="0.55" stroke="{color}" />')
        body.append(f'<text x="{legend_x + 24}" y="{y + 3}" font-family="Verdana, sans-serif" font-size="12" fill="#374151">{escape(label)}</text>')

    write_svg(output_path, svg_document(title, width, height, body))


def render_grouped_bar_chart(
    *,
    title: str,
    categories: list[str],
    series: Sequence[tuple[str, Sequence[float | int | None], str]],
    y_label: str,
    output_path: Path,
    y_max: float | None = None,
) -> None:
    width = 980
    height = 560
    left = 80
    right = 40
    top = 80
    bottom = 90
    plot_width = width - left - right
    plot_height = height - top - bottom

    numeric_values = [float(value) for _, values, _ in series for value in values if value is not None]
    upper = y_max or (max(numeric_values) if numeric_values else 1.0)
    upper = max(upper, 1.0)
    upper = math.ceil(upper)

    body: list[str] = []
    for tick in range(0, int(upper) + 1):
        y = top + plot_height - (tick / upper) * plot_height
        body.append(f'<line x1="{left}" y1="{y:.2f}" x2="{width - right}" y2="{y:.2f}" stroke="#d1d5db" stroke-width="1" />')
        body.append(f'<text x="{left - 12}" y="{y + 5:.2f}" text-anchor="end" font-family="Verdana, sans-serif" font-size="12" fill="#4b5563">{tick}</text>')

    body.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#111827" stroke-width="2" />')
    body.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#111827" stroke-width="2" />')
    body.append(f'<text x="22" y="{top + plot_height / 2:.2f}" transform="rotate(-90 22 {top + plot_height / 2:.2f})" font-family="Verdana, sans-serif" font-size="13" fill="#374151">{escape(y_label)}</text>')

    if categories:
        group_width = plot_width / len(categories)
        inner_padding = group_width * 0.15
        bar_width = (group_width - inner_padding * 2) / max(len(series), 1)
        for index, category in enumerate(categories):
            group_x = left + index * group_width + inner_padding
            category_center = left + index * group_width + group_width / 2
            body.append(f'<text x="{category_center:.2f}" y="{height - 45}" text-anchor="middle" font-family="Verdana, sans-serif" font-size="12" fill="#374151">{escape(category)}</text>')
            for series_index, (_, values, color) in enumerate(series):
                value = values[index]
                if value is None:
                    continue
                numeric = float(value)
                bar_height = 0 if upper == 0 else (numeric / upper) * plot_height
                x = group_x + series_index * bar_width
                y = top + plot_height - bar_height
                body.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width * 0.84:.2f}" height="{bar_height:.2f}" rx="4" fill="{color}" />')
                body.append(f'<text x="{x + bar_width * 0.42:.2f}" y="{max(y - 8, top - 4):.2f}" text-anchor="middle" font-family="Verdana, sans-serif" font-size="11" fill="#111827">{numeric:.2f}' + '</text>')

    legend_x = width - right - 180
    legend_y = 30
    for legend_index, (label, _, color) in enumerate(series):
        y = legend_y + legend_index * 24
        body.append(f'<rect x="{legend_x}" y="{y - 10}" width="16" height="16" rx="3" fill="{color}" />')
        body.append(f'<text x="{legend_x + 24}" y="{y + 3}" font-family="Verdana, sans-serif" font-size="12" fill="#374151">{escape(label)}</text>')

    write_svg(output_path, svg_document(title, width, height, body))


def render_distribution_chart(
    *,
    title: str,
    distributions: list[tuple[str, dict[str, int], str]],
    output_path: Path,
) -> None:
    categories = [str(level) for level in LIKERT_LEVELS]
    series = [(label, [distribution_map[category] for category in categories], color) for label, distribution_map, color in distributions]
    max_value = max((value for _, values, _ in series for value in values), default=1)
    render_grouped_bar_chart(
        title=title,
        categories=categories,
        series=series,
        y_label="Count",
        output_path=output_path,
        y_max=float(max_value),
    )


def generate_quality_charts(summary: dict[str, Any], phase1_entries: list[Entry], phase2_entries: list[Entry], output_dir: Path) -> None:
    overall = cast(dict[str, Any], summary["overall"])
    by_participant = cast(dict[str, Any], summary["by_participant"])
    participants = cast(list[str], overall["participants"])

    render_distribution_chart(
        title="Article quality distribution: phase comparison",
        distributions=[
            ("Phase 1", overall["phase1"]["quality_distribution"], "#b45309"),
            ("Phase 2", overall["phase2"]["quality_distribution"], "#0f766e"),
        ],
        output_path=output_dir / "overall_quality_distribution.svg",
    )

    render_split_violin_plot(
        title="Article quality: phase comparison",
        left_group=("Phase 1", metric_values(phase1_entries, "quality"), "#3b82b6"),
        right_group=("Phase 2", metric_values(phase2_entries, "quality"), "#f28e2b"),
        y_label="Quality (1-5)",
        output_path=output_dir / "overall_quality_violin.svg",
    )

    render_grouped_bar_chart(
        title="Mean article quality by participant",
        categories=participants,
        series=[
            ("Phase 1", [by_participant[participant]["phase1"]["quality_mean"] for participant in participants], "#b45309"),
            ("Phase 2", [by_participant[participant]["phase2"]["quality_mean"] for participant in participants], "#0f766e"),
        ],
        y_label="Mean quality (1-5)",
        output_path=output_dir / "overall_quality_mean_by_participant.svg",
        y_max=5.0,
    )

    render_grouped_bar_chart(
        title="Mean article quality by complexity",
        categories=[str(level) for level in LIKERT_LEVELS],
        series=[
            ("Phase 1", [overall["phase1"]["quality_by_complexity"][str(level)] for level in LIKERT_LEVELS], "#b45309"),
            ("Phase 2", [overall["phase2"]["quality_by_complexity"][str(level)] for level in LIKERT_LEVELS], "#0f766e"),
        ],
        y_label="Mean quality (1-5)",
        output_path=output_dir / "overall_quality_by_complexity.svg",
        y_max=5.0,
    )

    participant_dir = output_dir / "participants"
    participant_dir.mkdir(parents=True, exist_ok=True)
    for participant in participants:
        participant_summary = cast(dict[str, Any], by_participant[participant])
        participant_phase1 = [entry for entry in phase1_entries if entry.participant == participant]
        participant_phase2 = [entry for entry in phase2_entries if entry.participant == participant]
        render_distribution_chart(
            title=f"{participant}: article quality distribution",
            distributions=[
                ("Phase 1", participant_summary["phase1"]["quality_distribution"], "#b45309"),
                ("Phase 2", participant_summary["phase2"]["quality_distribution"], "#0f766e"),
            ],
            output_path=participant_dir / f"{participant.lower()}_quality_distribution.svg",
        )
        render_split_violin_plot(
            title=f"{participant}: article quality",
            left_group=("Phase 1", metric_values(participant_phase1, "quality"), "#3b82b6"),
            right_group=("Phase 2", metric_values(participant_phase2, "quality"), "#f28e2b"),
            y_label="Quality (1-5)",
            output_path=participant_dir / f"{participant.lower()}_quality_violin.svg",
        )
        render_grouped_bar_chart(
            title=f"{participant}: mean quality by complexity",
            categories=[str(level) for level in LIKERT_LEVELS],
            series=[
                ("Phase 1", [participant_summary["phase1"]["quality_by_complexity"][str(level)] for level in LIKERT_LEVELS], "#b45309"),
                ("Phase 2", [participant_summary["phase2"]["quality_by_complexity"][str(level)] for level in LIKERT_LEVELS], "#0f766e"),
            ],
            y_label="Mean quality (1-5)",
            output_path=participant_dir / f"{participant.lower()}_quality_by_complexity.svg",
            y_max=5.0,
        )


def generate_satisfaction_charts(summary: dict[str, Any], phase2_entries: list[Entry], output_dir: Path) -> None:
    overall = cast(dict[str, Any], summary["overall"])
    by_participant = cast(dict[str, Any], summary["by_participant"])
    participants = cast(list[str], overall["participants"])

    render_distribution_chart(
        title="Phase 2: tool satisfaction distribution",
        distributions=[("All participants", overall["phase2"]["satisfaction_distribution"], "#1d4ed8")],
        output_path=output_dir / "overall_satisfaction_distribution.svg",
    )

    render_violin_plot(
        title="Phase 2: tool satisfaction",
        groups=[("All participants", metric_values(phase2_entries, "satisfaction"), "#1d4ed8")],
        y_label="Satisfaction (1-5)",
        output_path=output_dir / "overall_satisfaction_violin.svg",
    )

    render_grouped_bar_chart(
        title="Phase 2: mean tool satisfaction by participant",
        categories=participants,
        series=[
            ("Phase 2", [by_participant[participant]["phase2"]["satisfaction_mean"] for participant in participants], "#1d4ed8"),
        ],
        y_label="Mean satisfaction (1-5)",
        output_path=output_dir / "overall_satisfaction_mean_by_participant.svg",
        y_max=5.0,
    )

    participant_dir = output_dir / "participants"
    participant_dir.mkdir(parents=True, exist_ok=True)
    for participant in participants:
        participant_summary = cast(dict[str, Any], by_participant[participant])
        participant_phase2 = [entry for entry in phase2_entries if entry.participant == participant]
        render_distribution_chart(
            title=f"{participant}: phase 2 tool satisfaction distribution",
            distributions=[("Phase 2", participant_summary["phase2"]["satisfaction_distribution"], "#1d4ed8")],
            output_path=participant_dir / f"{participant.lower()}_satisfaction_distribution.svg",
        )
        render_violin_plot(
            title=f"{participant}: phase 2 tool satisfaction",
            groups=[("Phase 2", metric_values(participant_phase2, "satisfaction"), "#1d4ed8")],
            y_label="Satisfaction (1-5)",
            output_path=participant_dir / f"{participant.lower()}_satisfaction_violin.svg",
        )


def ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    args = parse_args()
    phase1_dir = Path(args.phase1_dir)
    phase2_dir = Path(args.phase2_dir)
    output_dir = Path(args.output_dir)

    phase1_entries = load_phase_entries(phase1_dir, "phase1")
    phase2_entries = load_phase_entries(phase2_dir, "phase2")
    ensure_output_dir(output_dir)

    summary = build_summary(phase1_entries, phase2_entries)
    write_summary_files(summary, output_dir)
    generate_quality_charts(summary, phase1_entries, phase2_entries, output_dir)
    generate_satisfaction_charts(summary, phase2_entries, output_dir)


if __name__ == "__main__":
    main()