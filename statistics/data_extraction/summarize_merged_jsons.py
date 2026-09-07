import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PHASE_DIRS = {
    "phase1": BASE_DIR / "phase1",
    "phase2": BASE_DIR / "phase2",
}
FILENAME_PATTERN = "output_*_cms_article_merged.json"
ID_PATTERN = re.compile(r"output_(p\d+)_cms_article_merged\.json", re.IGNORECASE)

FIELD_NAMES = {
    "writing_time_text": "Schreibzeit für Artikeltext",
    "writing_time_fields": "Schreibzeit für weitere Felder",
    "quality": "Qualitative Artikeleinschätzung (1-5)",
    "ki_satisfaction": "Zufriedenheit mit KI-Tool (1-5)",
}


def to_float(value):
    if value is None:
        return np.nan
    try:
        return float(str(value).replace(",", ".").strip())
    except ValueError:
        return np.nan


def _q(x, p):
    arr = np.array(x.dropna(), dtype=float)
    return float(np.nanpercentile(arr, p)) if arr.size > 0 else np.nan


def _iqr(x):
    arr = np.array(x.dropna(), dtype=float)
    return float(np.nanpercentile(arr, 75) - np.nanpercentile(arr, 25)) if arr.size > 0 else np.nan


def load_phase_data(phase_name, phase_dir):
    if not phase_dir.exists():
        raise FileNotFoundError(f"Pfad nicht gefunden: {phase_dir}")

    rows = []
    for path in sorted(phase_dir.glob(FILENAME_PATTERN)):
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        match = ID_PATTERN.search(path.name)
        participant = match.group(1) if match else path.stem

        for entry in data:
            csv_data = entry.get("csv_data", {}) or {}
            rows.append({
                "phase": phase_name,
                "participant": participant,
                "file": path.name,
                "writing_time_text": to_float(csv_data.get(FIELD_NAMES["writing_time_text"])),
                "writing_time_fields": to_float(csv_data.get(FIELD_NAMES["writing_time_fields"])),
                "quality": to_float(csv_data.get(FIELD_NAMES["quality"])),
                "ki_satisfaction": to_float(csv_data.get(FIELD_NAMES["ki_satisfaction"])),
            })

    return pd.DataFrame(rows)


def summarize_per_participant(df):
    group = df.groupby(["phase", "participant"], dropna=False)
    summary = group.agg(
        article_count=("file", "count"),
        median_writing_time_text=("writing_time_text", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        writing_time_text_q1=("writing_time_text", lambda x: _q(x, 25)),
        writing_time_text_q3=("writing_time_text", lambda x: _q(x, 75)),
        writing_time_text_iqr=("writing_time_text", lambda x: _iqr(x)),

        median_writing_time_fields=("writing_time_fields", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        writing_time_fields_q1=("writing_time_fields", lambda x: _q(x, 25)),
        writing_time_fields_q3=("writing_time_fields", lambda x: _q(x, 75)),
        writing_time_fields_iqr=("writing_time_fields", lambda x: _iqr(x)),

        median_quality=("quality", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        quality_q1=("quality", lambda x: _q(x, 25)),
        quality_q3=("quality", lambda x: _q(x, 75)),
        quality_iqr=("quality", lambda x: _iqr(x)),

        median_ki_satisfaction=("ki_satisfaction", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        ki_satisfaction_q1=("ki_satisfaction", lambda x: _q(x, 25)),
        ki_satisfaction_q3=("ki_satisfaction", lambda x: _q(x, 75)),
        ki_satisfaction_iqr=("ki_satisfaction", lambda x: _iqr(x)),
    )
    summary = summary.reset_index()
    summary.loc[summary["phase"] != "phase2", [
        "median_ki_satisfaction",
        "ki_satisfaction_q1",
        "ki_satisfaction_q3",
        "ki_satisfaction_iqr",
    ]] = np.nan
    return summary


def summarize_overall(df):
    group = df.groupby("phase", dropna=False)
    summary = group.agg(
        article_count=("file", "count"),
        median_writing_time_text=("writing_time_text", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        writing_time_text_q1=("writing_time_text", lambda x: _q(x, 25)),
        writing_time_text_q3=("writing_time_text", lambda x: _q(x, 75)),
        writing_time_text_iqr=("writing_time_text", lambda x: _iqr(x)),

        median_writing_time_fields=("writing_time_fields", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        writing_time_fields_q1=("writing_time_fields", lambda x: _q(x, 25)),
        writing_time_fields_q3=("writing_time_fields", lambda x: _q(x, 75)),
        writing_time_fields_iqr=("writing_time_fields", lambda x: _iqr(x)),

        median_quality=("quality", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        quality_q1=("quality", lambda x: _q(x, 25)),
        quality_q3=("quality", lambda x: _q(x, 75)),
        quality_iqr=("quality", lambda x: _iqr(x)),

        median_ki_satisfaction=("ki_satisfaction", lambda x: float(np.nanmedian(x)) if x.dropna().size > 0 else np.nan),
        ki_satisfaction_q1=("ki_satisfaction", lambda x: _q(x, 25)),
        ki_satisfaction_q3=("ki_satisfaction", lambda x: _q(x, 75)),
        ki_satisfaction_iqr=("ki_satisfaction", lambda x: _iqr(x)),
    )
    summary = summary.reset_index()
    summary.loc[summary["phase"] != "phase2", "median_ki_satisfaction"] = np.nan
    return summary


def main():
    all_data = pd.concat(
        [load_phase_data(phase_name, phase_dir) for phase_name, phase_dir in PHASE_DIRS.items()],
        ignore_index=True,
    )

    if all_data.empty:
        return

    per_participant = summarize_per_participant(all_data)
    overall = summarize_overall(all_data)

    for frame, filename, title in [
        (per_participant, "summary_by_participant.csv", "Zusammenfassung pro Teilnehmer:"),
        (overall, "summary_overall.csv", "Gesamtzusammenfassung pro Phase:"),
    ]:
        frame["median_writing_time_text"] = frame["median_writing_time_text"].round(2)
        frame["median_writing_time_fields"] = frame["median_writing_time_fields"].round(2)
        frame["median_quality"] = frame["median_quality"].round(2)
        frame["median_ki_satisfaction"] = frame["median_ki_satisfaction"].round(2)

        output_file = BASE_DIR / filename
        frame.to_csv(output_file, index=False)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
