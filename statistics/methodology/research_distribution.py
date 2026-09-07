import json
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
try:
    import seaborn as sns
    _USE_SEABORN = True
except Exception:
    _USE_SEABORN = False


BASE_DIR = Path(__file__).resolve().parent
PHASE_DIRS = {
    "phase1": BASE_DIR / "phase1",
    "phase2": BASE_DIR / "phase2",
}
FILENAME_PATTERN = "output_*_cms_article_merged.json"
ID_PATTERN = re.compile(r"output_(p\d+)_cms_article_merged\.json", re.IGNORECASE)


def normalize_methods(raw):
    if raw is None:
        return ["(not specified)"]
    s = str(raw).strip()
    if s == "":
        return ["(not specified)"]
    parts = re.split(r"[,;/\\|]+", s)
    parts = [p.strip() for p in parts if p.strip()]
    return parts if parts else ["(not specified)"]


def load_all():
    rows = []
    for phase, folder in PHASE_DIRS.items():
        if not folder.exists():
            continue
        for path in sorted(folder.glob(FILENAME_PATTERN)):
            match = ID_PATTERN.search(path.name)
            participant = match.group(1) if match else path.stem
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)

            for entry in data:
                csv = (entry.get("csv_data") or {})
                raw_recherche = csv.get("Recheche") or csv.get("Recherche") or csv.get("recherche")
                methods = normalize_methods(raw_recherche)
                rows.append({
                    "phase": phase,
                    "participant": participant,
                    "article_id": csv.get("CREATE-ID ( / NGEN-ID)") or entry.get("id"),
                    "methods": methods,
                })

    df = pd.DataFrame(rows)
    return df


def plot_for_participant(df, participant, out_dir):
    participant_dir = out_dir / participant
    participant_dir.mkdir(parents=True, exist_ok=True)

    for phase in df["phase"].unique():
        sub = df[(df.participant == participant) & (df.phase == phase)]
        if sub.empty:
            continue

        exploded = sub.explode("methods")
        counts = exploded["methods"].value_counts().sort_values(ascending=False)

        plt.figure(figsize=(8, 4 + 0.25 * len(counts)))
        if _USE_SEABORN:
            sns.barplot(x=counts.values, y=counts.index, palette="viridis")
        else:
            y_pos = np.arange(len(counts))
            colors = plt.cm.viridis(np.linspace(0, 1, len(counts)))
            plt.barh(y_pos, counts.values, color=colors)
            plt.yticks(y_pos, counts.index)

        plt.xlabel("Article count")
        plt.ylabel("Research method")
        plt.title(f"{participant} — {phase}: Research distribution")
        plt.tight_layout()

        out_file = participant_dir / f"{participant}_{phase}_recherche.png"
        plt.savefig(out_file, dpi=150)
        plt.close()


def run():
    df = load_all()
    if df.empty:
        return

    out_dir = BASE_DIR / "research_plots"
    out_dir.mkdir(exist_ok=True)

    participants = sorted(df["participant"].unique())

    for p in participants:
        plot_for_participant(df, p, out_dir)

    exploded = df.explode("methods")
    table = (
        exploded.groupby(["participant", "phase", "methods"])    
        .size()
        .reset_index(name="count")
        .sort_values(["participant", "phase", "count"], ascending=[True, True, False])
    )
    table.to_csv(out_dir / "research_counts_by_participant.csv", index=False)


if __name__ == "__main__":
    run()
