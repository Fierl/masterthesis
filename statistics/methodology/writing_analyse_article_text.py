import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt

# ============================================================
# CONFIG: Pfade anpassen
# ============================================================
# Projektordner mit den Unterordnern phase1/ und phase2/
BASE_DIR = Path(r"")

PHASE_DIRS = {
    1: BASE_DIR / "phase1",
    2: BASE_DIR / "phase2",
}

# Nur die zusammengeführten Dateien verwenden (Text + csv_data kombiniert)
FILENAME_SUFFIX = "_merged.json"

# Extrahiert die Journalist:innen-ID aus dem Dateinamen,
# z. B. "p17" aus "output_p17_cms_article_merged.json"
ID_PATTERN = re.compile(r"(p\d+)", re.IGNORECASE)

OUTPUT_DIR = Path("output")   # Ordner für Ergebnisse (wird angelegt)
OUTPUT_DIR.mkdir(exist_ok=True)


def discover_files():
    found = []
    for phase, folder in PHASE_DIRS.items():
        if not folder.exists():
            continue
        matches = sorted(folder.glob(f"*{FILENAME_SUFFIX}"))
        if not matches:
            continue
        for path in matches:
            id_match = ID_PATTERN.search(path.name)
            journalist = id_match.group(1) if id_match else path.stem
            found.append((path, journalist, phase))
    return found

def _to_float(value):
    if value is None:
        return np.nan
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return np.nan


def load_dataset(path, journalist, phase):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    rows = []
    for entry in raw:
        csv = entry.get("csv_data", {})
        text = entry.get("text", "") or ""
        word_count = len(text.split())

        rows.append({
            "journalist": journalist,
            "phase": phase,
            "article_id": csv.get("CREATE-ID ( / NGEN-ID)", entry.get("id")),
            "word_count": word_count,
            "writing_time_text": _to_float(csv.get("Schreibzeit für Artikeltext")),
            "writing_time_fields": _to_float(csv.get("Schreibzeit für weitere Felder")),
            "accuracy": csv.get("Genauigkeit der Schreibzeit"),
            "recherche": csv.get("Recheche"),
            "complexity": _to_float(csv.get("Komplexität des Artikels (1-5)")),
            "quality": _to_float(csv.get("Qualitative Artikeleinschätzung (1-5)")),
        })
    return pd.DataFrame(rows)


def load_all():
    files = discover_files()
    if not files:
        raise FileNotFoundError(
            "Keine *_merged.json Dateien gefunden. Bitte BASE_DIR/PHASE_DIRS "
            "in der CONFIG prüfen."
        )


    dfs = [load_dataset(path, journalist, phase) for path, journalist, phase in files]
    df = pd.concat(dfs, ignore_index=True)

    # Gesamtzeit und Normalisierung (Effizienzmaße)
    df["writing_time_total"] = df["writing_time_text"] + df["writing_time_fields"]
    df["min_per_100_words"] = df["writing_time_text"] / df["word_count"] * 100
    df["words_per_min"] = df["word_count"] / df["writing_time_text"]

    return df

def aggregate_per_journalist(df, value_col="min_per_100_words", agg="median"):
    agg_func = np.median if agg == "median" else np.mean
    summary = (
        df.groupby(["journalist", "phase"])[value_col]
        .agg(agg_func)
        .reset_index()
        .pivot(index="journalist", columns="phase", values=value_col)
    )
    summary.columns = [f"phase_{c}" for c in summary.columns]
    summary["n_phase1"] = df[df.phase == 1].groupby("journalist").size()
    summary["n_phase2"] = df[df.phase == 2].groupby("journalist").size()
    summary["absolute_diff"] = summary["phase_2"] - summary["phase_1"]
    summary["pct_change"] = summary["absolute_diff"] / summary["phase_1"] * 100
    return summary


def skewness_check(df, value_col="min_per_100_words"):
    skew_rows = []
    for phase, grp in df.groupby("phase"):
        data = grp[value_col].dropna().values
        if len(data) < 3:
            continue
        skew_val = stats.skew(data)
        abs_skew = abs(skew_val)
        verdict = (
            "annähernd symmetrisch" if abs_skew < 0.5
            else "moderat schief" if abs_skew < 1.0
            else "deutlich schief"
        )
        skew_rows.append({
            "phase": phase,
            "n": len(data),
            "skewness": float(skew_val),
            "abs_skewness": float(abs_skew),
            "verdict": verdict,
        })

    overall = df[value_col].dropna().values
    overall_skew = stats.skew(overall)
    overall_verdict = (
        "" if abs(overall_skew) < 0.5
        else "" if abs(overall_skew) < 1.0
        else ""
    )

    return pd.DataFrame(skew_rows)


def plot_skewness_distribution(df, value_col="min_per_100_words",
                               filename="distribution_check_article_text.png"):
    overall = df[value_col].dropna().values
    overall_skew = stats.skew(overall)
    phases = sorted(df["phase"].dropna().unique())

    fig, axes = plt.subplots(2, len(phases), figsize=(10, 6), squeeze=False)
    phase_colors = {1: "#2166AC", 2: "#B2182B"}

    for column, phase in enumerate(phases):
        data = df.loc[df["phase"] == phase, value_col].dropna().values
        skew_val = stats.skew(data)
        color = phase_colors.get(phase, "#4D4D4D")
        label = f"Phase {phase}"

        histogram_axis = axes[0, column]
        histogram_axis.hist(data, bins="auto", color=color, alpha=0.78,
                            edgecolor="white", linewidth=0.7)
        histogram_axis.axvline(np.median(data), color="#111111", linewidth=2,
                               label=f"Median = {np.median(data):.2f}")
        histogram_axis.axvline(np.mean(data), color="#666666", linestyle="--",
                               linewidth=1.5, label=f"Mean = {np.mean(data):.2f}")
        histogram_axis.set_title(f"{label}  (n = {len(data)}, skew = {skew_val:.3f})")
        histogram_axis.set_xlabel("Minutes per 100 words")
        histogram_axis.set_ylabel("Articles")
        histogram_axis.legend(frameon=False, fontsize=8)
        histogram_axis.spines[["top", "right"]].set_visible(False)

        boxplot_axis = axes[1, column]
        boxplot_axis.boxplot(data, orientation="horizontal", patch_artist=True,
                             boxprops={"facecolor": color, "alpha": 0.78},
                             medianprops={"color": "#111111", "linewidth": 2},
                             flierprops={"marker": "o", "markerfacecolor": color,
                                         "markeredgecolor": color, "alpha": 0.65})
        boxplot_axis.set_yticks([])
        boxplot_axis.set_xlabel("Minutes per 100 words")
        boxplot_axis.spines[["top", "right", "left"]].set_visible(False)

    fig.suptitle(
        f"Distribution of article-writing time by phase\n"
        f"Overall skewness = {overall_skew:.3f}",
        fontsize=14,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    output_path = OUTPUT_DIR / filename
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def wilcoxon_test(summary):
    phase1 = summary["phase_1"].values
    phase2 = summary["phase_2"].values
    n = len(phase1)


    try:
        stat, p = stats.wilcoxon(phase1, phase2)
        return stat, p
    except ValueError as e:
        return None, None


def bootstrap_ci(df, journalist, value_col="min_per_100_words", n_boot=5000, seed=42):
    rng = np.random.default_rng(seed)
    p1 = df[(df.journalist == journalist) & (df.phase == 1)][value_col].dropna().values
    p2 = df[(df.journalist == journalist) & (df.phase == 2)][value_col].dropna().values

    if len(p1) == 0 or len(p2) == 0:
        return np.nan, np.nan, np.nan

    diffs = np.empty(n_boot)
    for i in range(n_boot):
        s1 = rng.choice(p1, size=len(p1), replace=True)
        s2 = rng.choice(p2, size=len(p2), replace=True)
        diffs[i] = np.median(s2) - np.median(s1)

    lower, upper = np.percentile(diffs, [2.5, 97.5])
    return np.median(diffs), lower, upper


def plot_slope_chart(summary, value_col_label="Min. pro 100 Wörter", filename="slope_chart.png"):
    fig, ax = plt.subplots(figsize=(6, 5))
    for journalist, row in summary.iterrows():
        ax.plot([1, 2], [row["phase_1"], row["phase_2"]], marker="o", label=journalist)
        ax.annotate(journalist, xy=(1, row["phase_1"]), xytext=(-8, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=9)

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Phase 1\n(ohne GenAI)", "Phase 2\n(mit GenAI)"])
    ax.set_xlim(0.6, 2.2)
    ax.set_ylabel(value_col_label)
    ax.set_title("Schreibzeit pro Journalist:in: Phase 1 vs. Phase 2")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close(fig)


# ============================================================
# Main
# ============================================================
def main():
    df = load_all()

    skewness_check(df, value_col="min_per_100_words")
    plot_skewness_distribution(df, value_col="min_per_100_words")

    summary = aggregate_per_journalist(df, value_col="min_per_100_words", agg="median")


    wilcoxon_test(summary)

    for journalist in df.journalist.unique():
        med_diff, lo, hi = bootstrap_ci(df, journalist)

    plot_slope_chart(summary)

    summary.to_csv(OUTPUT_DIR / "journalist_phase_summary.csv")
    df.to_csv(OUTPUT_DIR / "combined_data.csv", index=False)

if __name__ == "__main__":
    main()