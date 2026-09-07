import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
from matplotlib import rcParams
rcParams['font.family'] = 'serif'
rcParams['font.serif'] = ['Linux Libertine']
rcParams['axes.formatter.use_locale'] = False 
BASE_DIR = Path(r"")

PHASE_DIRS = {
    1: BASE_DIR / "phase1",
    2: BASE_DIR / "phase2",
}

FILENAME_SUFFIX = "_merged.json"
ID_PATTERN = re.compile(r"(p\d+)", re.IGNORECASE)

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)


def discover_files():
    found = []
    for phase, folder in PHASE_DIRS.items():
        if not folder.exists():
            continue
        matches = sorted(folder.glob(f"*{FILENAME_SUFFIX}"))
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
            ""
        )

    dfs = [load_dataset(path, journalist, phase) for path, journalist, phase in files]
    df = pd.concat(dfs, ignore_index=True)

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


def wilcoxon_test(summary):
    phase1 = summary["phase_1"].values
    phase2 = summary["phase_2"].values
    n = len(phase1)


    try:
        stat, p = stats.wilcoxon(phase1, phase2)
        return stat, p
    except ValueError as e:
        return None, None


def bootstrap_ci(df, journalist, value_col="min_per_100_words", n_boot=5000, seed=42, agg="median"):
    rng = np.random.default_rng(seed)
    p1 = df[(df.journalist == journalist) & (df.phase == 1)][value_col].dropna().values
    p2 = df[(df.journalist == journalist) & (df.phase == 2)][value_col].dropna().values

    if len(p1) == 0 or len(p2) == 0:
        return np.nan, np.nan, np.nan

    stat_func = np.median if agg == "median" else np.mean

    observed_diff = stat_func(p2) - stat_func(p1)

    diffs = np.empty(n_boot)
    for i in range(n_boot):
        s1 = rng.choice(p1, size=len(p1), replace=True)
        s2 = rng.choice(p2, size=len(p2), replace=True)
        diffs[i] = stat_func(s2) - stat_func(s1)

    lower, upper = np.percentile(diffs, [2.5, 97.5])
    return observed_diff, lower, upper


def bootstrap_ci_table(df, value_col, agg="median", n_boot=5000, seed=42):
    rows = []
    for journalist in df.journalist.unique():
        diff, lo, hi = bootstrap_ci(df, journalist, value_col=value_col, agg=agg, n_boot=n_boot, seed=seed)
        rows.append({"journalist": journalist, "diff": diff, "ci_lower": lo, "ci_upper": hi})
    return pd.DataFrame(rows).set_index("journalist")


def plot_slope_chart(summary, value_col_label, filename, title):
    fig, ax = plt.subplots(figsize=(6, 5))
    for journalist, row in summary.iterrows():
        ax.plot([1, 2], [row["phase_1"], row["phase_2"]], marker="o", label=journalist)
        ax.annotate(journalist, xy=(1, row["phase_1"]), xytext=(-8, 0),
                    textcoords="offset points", ha="right", va="center", fontsize=9)

    ax.set_xticks([1, 2])
    ax.set_xticklabels(["Phase 1\n(ohne GenAI)", "Phase 2\n(mit GenAI)"])
    ax.set_xlim(0.6, 2.2)
    ax.set_ylabel(value_col_label)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close(fig)


def plot_forest_chart(ci_table, filename, title, xlabel):
    ci_table = ci_table.sort_index(ascending=False)
    y_pos = np.arange(len(ci_table))

    xerr_lower = ci_table["diff"] - ci_table["ci_lower"]
    xerr_upper = ci_table["ci_upper"] - ci_table["diff"]

    fig, ax = plt.subplots(figsize=(6, 0.9 * len(ci_table) + 1.5))
    ax.errorbar(
        ci_table["diff"], y_pos,
        xerr=[xerr_lower, xerr_upper],
        fmt="o", color="black", ecolor="black", elinewidth=1.5,
        capsize=4, markersize=6,
    )
    ax.axvline(0, color="red", linestyle="--", linewidth=1)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(ci_table.index)
    ax.set_ylim(-0.7, len(ci_table) - 0.3)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close(fig)

def check_distribution_shape(df, value_col, label):

    for phase in sorted(df.phase.unique()):
        data = df[df.phase == phase][value_col].dropna().values
        n = len(data)

        mean_val = np.mean(data)
        median_val = np.median(data)
        skew_val = stats.skew(data)
        rel_gap = (mean_val - median_val) / median_val * 100 if median_val != 0 else np.nan

        if abs(skew_val) < 0.5:
            verdict = "1"
        elif abs(skew_val) < 1.0:
            verdict = "2"
        else:
            verdict = "3"


def plot_distribution_check(df, value_col, filename, title):
    phases = sorted(df.phase.unique())
    fig, axes = plt.subplots(2, len(phases), figsize=(5 * len(phases), 7))

    for col_idx, phase in enumerate(phases):
        data = df[df.phase == phase][value_col].dropna().values
        skew_val = stats.skew(data) if len(data) >= 3 else np.nan

        ax_hist = axes[0, col_idx] if len(phases) > 1 else axes[0]
        ax_hist.hist(data, bins=15, edgecolor="black", alpha=0.7)
        ax_hist.axvline(np.mean(data), color="red", linestyle="--", label=f"Mean={np.mean(data):.2f}")
        ax_hist.axvline(np.median(data), color="blue", linestyle="-", label=f"Median={np.median(data):.2f}")
        ax_hist.set_title(f"Phase {phase} - Histogram (skew={skew_val:.2f})")
        ax_hist.set_xlabel(value_col)
        ax_hist.legend(fontsize=8)
        ax_box = axes[1, col_idx] if len(phases) > 1 else axes[1]
        ax_box.boxplot(data, vert=False)
        ax_box.set_title(f"Phase {phase} - Boxplot")
        ax_box.set_xlabel(value_col)

    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close(fig)

def likert_summary_table(df, value_col, groupby_cols):

    def q1(x):
        return np.percentile(x, 25)

    def q3(x):
        return np.percentile(x, 75)

    summary = df.groupby(groupby_cols)[value_col].agg(n="count", median="median", q1=q1, q3=q3)
    summary["iqr"] = summary["q3"] - summary["q1"]
    return summary


def mannwhitney_test(df, value_col):
    p1 = df[df.phase == 1][value_col].dropna().values
    p2 = df[df.phase == 2][value_col].dropna().values

    try:
        stat, p = stats.mannwhitneyu(p1, p2, alternative="two-sided")
        return stat, p
    except ValueError as e:
        return None, None


def compute_likert_pct_table(df, value_col, groupby_cols, scale=(1, 2, 3, 4, 5)):
    counts = (
        df.groupby(groupby_cols)[value_col]
        .value_counts(normalize=True)
        .unstack(fill_value=0)
        * 100
    )
    counts = counts.reindex(columns=list(scale), fill_value=0)
    return counts


def plot_stacked_bar(pct_df, filename, title, category_labels=None):
    categories = list(pct_df.columns)
    n_cat = len(categories)

    if category_labels is None:
        category_labels = [str(c) for c in categories]

    category_colors = {
        categories[0]: "#b2182b",
        categories[1]: "#ef8a62",
        categories[2]: "#D9D9D9",
        categories[3]: "#67a9cf",
        categories[4]: "#2166ac",
    }
    colors = [category_colors[c] for c in categories]

    groups = pct_df.index.tolist()
    y_pos = np.arange(len(groups))[::-1]

    fig, ax = plt.subplots(figsize=(8, 0.8 * len(groups) + 1.5))

    for gi, group in zip(y_pos, groups):
        row = pct_df.loc[group]
        running = 0.0
        for ci in range(n_cat):
            val = row.iloc[ci]
            ax.barh(gi, val, left=running, color=colors[ci], edgecolor="white")
            running += val

    ax.set_yticks(y_pos)
    ax.set_yticklabels(groups)
    ax.set_xlabel("Percentage of ratings (%)")
    ax.set_title(title)

    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[i]) for i in range(n_cat)]
    ax.legend(handles, category_labels, bbox_to_anchor=(1.02, 1), loc="upper left", title="Rating")

    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150, bbox_inches="tight")
    plt.close(fig)

def main():
    df = load_all()

    check_distribution_shape(df, "min_per_100_words", "Artikeltext")
    plot_distribution_check(
        df, "min_per_100_words",
        "distribution_check_article_text.png",
        "Distribution check: min. per 100 words (article text)",
    )

    check_distribution_shape(df, "writing_time_fields", "Weitere Felder")
    plot_distribution_check(
        df, "writing_time_fields",
        "distribution_check_additional_fields.png",
        "Distribution check: writing time for additional fields",
    )

    summary_text = aggregate_per_journalist(df, value_col="min_per_100_words", agg="median")

    wilcoxon_test(summary_text)

    ci_table_text = bootstrap_ci_table(df, value_col="min_per_100_words", agg="median")

    plot_forest_chart(
        ci_table_text,
        "forest_plot_article_text.png",
        "Median difference (Phase 2 - Phase 1): article text",
        "Difference in min. per 100 words (with 95% bootstrap CI)",
    )
    summary_text.to_csv(OUTPUT_DIR / "journalist_phase_summary_article_text.csv")
    ci_table_text.to_csv(OUTPUT_DIR / "bootstrap_ci_article_text.csv")

    summary_fields = aggregate_per_journalist(df, value_col="writing_time_fields", agg="median")

    wilcoxon_test(summary_fields)

    ci_table_fields = bootstrap_ci_table(df, value_col="writing_time_fields", agg="median")

    plot_forest_chart(
        ci_table_fields,
        "forest_plot_additional_fields.png",
        "Median difference (Phase 2 - Phase 1): additional fields",
        "Difference in minutes (with 95% bootstrap CI)",
    )
    summary_fields.to_csv(OUTPUT_DIR / "journalist_phase_summary_additional_fields.csv")
    ci_table_fields.to_csv(OUTPUT_DIR / "bootstrap_ci_additional_fields.csv")

    df.to_csv(OUTPUT_DIR / "combined_data.csv", index=False)


    quality_df = df.dropna(subset=["quality"]).copy()
    quality_df["quality"] = quality_df["quality"].astype(int)

    agg_summary = likert_summary_table(quality_df, "quality", ["phase"])
    agg_summary.to_csv(OUTPUT_DIR / "quality_summary_aggregated.csv")

    mannwhitney_test(quality_df, "quality")

    agg_pct = compute_likert_pct_table(quality_df, "quality", ["phase"])
    agg_pct.index = [f"Phase {p}" for p in agg_pct.index]
    agg_pct = agg_pct.reindex(["Phase 1", "Phase 2"]).dropna(how="all")
    plot_stacked_bar(
        agg_pct,
        "likert_quality_aggregated.png",
        "Article quality rating (aggregated across journalists)",
    )

    per_journalist_summary = likert_summary_table(quality_df, "quality", ["journalist", "phase"])
    per_journalist_summary.to_csv(OUTPUT_DIR / "quality_summary_per_journalist.csv")

    per_journalist_pct = compute_likert_pct_table(quality_df, "quality", ["journalist", "phase"])
    per_journalist_pct.index = [f"{j} - Phase {p}" for j, p in per_journalist_pct.index]
    per_journalist_pct = per_journalist_pct.sort_index(key=lambda idx: [(item.split(" - Phase ")[0], int(item.split(" - Phase ")[1])) for item in idx])
    plot_stacked_bar(
        per_journalist_pct,
        "likert_quality_per_journalist.png",
        "Article quality rating per journalist and phase",
    )


if __name__ == "__main__":
    main()