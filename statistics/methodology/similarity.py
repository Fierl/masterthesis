import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
from matplotlib import rcParams
from difflib import HtmlDiff
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

rcParams['font.family'] = 'serif'
rcParams['font.serif'] = ['Linux Libertine']
rcParams['axes.formatter.use_locale'] = False

BASE_DIR = Path(r"")

FILENAME_SUFFIX = "_matched.json"

OUTPUT_DIR = Path("output_similarity")
OUTPUT_DIR.mkdir(exist_ok=True)
PER_PARTICIPANT_DIR = OUTPUT_DIR / "per_participant"
PER_PARTICIPANT_DIR.mkdir(exist_ok=True)

COMBINED_DATA_PATH = Path(
    r""
)

N_DIFF_EXAMPLES = 3

KNOWN_MISMATCHES = {
    "20939914",
}

METRIC_COLS = [
    "word_error_rate",
    "jaccard_similarity",
    "tfidf_cosine_similarity_corpus",
    "length_ratio",
]


def exclude_known_mismatches(df):
    before = len(df)
    df = df[~df["content_id"].astype(str).isin(KNOWN_MISMATCHES)].reset_index(drop=True)
    removed = before - len(df)
    if removed:
              f"{sorted(KNOWN_MISMATCHES)}). Verbleibend: {len(df)} Artikel-Paare.")
    return df

def discover_files():
    if not BASE_DIR.exists():
        raise FileNotFoundError(f"BASE_DIR nicht gefunden: {BASE_DIR}")
    files = sorted(BASE_DIR.glob(f"*{FILENAME_SUFFIX}"))
    if not files:
        raise FileNotFoundError(
            f"Keine *{FILENAME_SUFFIX}-Dateien in {BASE_DIR} gefunden."
        )
    return files


def load_pairs(path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    journalist = raw.get("meta", {}).get("participant_username", path.stem)
    rows = []

    for item in raw.get("items", []):
        cms_text = (item.get("cms_article") or {}).get("text")
        ai_text = (
            (item.get("db_match") or {})
            .get("article", {})
            .get("match_fields", {})
            .get("text")
        )
        if not cms_text or not ai_text:
            continue

        rows.append({
            "journalist": journalist,
            "content_id": item.get("content_id"),
            "cms_text": cms_text,
            "ai_text": ai_text,
        })
    return rows


def load_all():
    files = discover_files()
    all_rows = []
    for path in files:
        rows = load_pairs(path)
        all_rows.extend(rows)

    if not all_rows:
        raise ValueError("")

    return pd.DataFrame(all_rows)


def tokenize(text):
    return re.findall(r"\w+", text.lower(), flags=re.UNICODE)


def levenshtein_distance(seq_a, seq_b):
    n, m = len(seq_a), len(seq_b)
    if n == 0:
        return m
    if m == 0:
        return n

    prev = list(range(m + 1))
    for i in range(1, n + 1):
        curr = [i] + [0] * m
        for j in range(1, m + 1):
            cost = 0 if seq_a[i - 1] == seq_b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,
                curr[j - 1] + 1,
                prev[j - 1] + cost,
            )
        prev = curr
    return prev[m]

def compute_metrics(cms_text, ai_text):
    cms_words = tokenize(cms_text)
    ai_words = tokenize(ai_text)

    dist = levenshtein_distance(ai_words, cms_words)
    wer = dist / len(cms_words) if len(cms_words) > 0 else np.nan

    set_cms, set_ai = set(cms_words), set(ai_words)
    union = set_cms | set_ai
    jaccard = len(set_cms & set_ai) / len(union) if union else np.nan

    length_ratio = len(ai_words) / len(cms_words) if len(cms_words) > 0 else np.nan

    return {
        "word_error_rate": wer,
        "jaccard_similarity": jaccard,
        "length_ratio": length_ratio,
        "n_words_cms": len(cms_words),
        "n_words_ai": len(ai_words),
    }

def compute_tfidf_corpus_wide(df):
    all_texts = pd.concat([df["cms_text"], df["ai_text"]]).tolist()

    vectorizer = TfidfVectorizer()
    vectorizer.fit(all_texts)

    cms_matrix = vectorizer.transform(df["cms_text"])
    ai_matrix = vectorizer.transform(df["ai_text"])

    sims = np.array([
        cosine_similarity(cms_matrix[i], ai_matrix[i])[0, 0]
        for i in range(cms_matrix.shape[0])
    ])
    return pd.Series(sims, index=df.index, name="tfidf_cosine_similarity_corpus")


def compute_all_metrics(df):
    metric_rows = df.apply(
        lambda row: compute_metrics(row["cms_text"], row["ai_text"]), axis=1
    )
    metrics_df = pd.DataFrame(metric_rows.tolist())
    result = pd.concat([df.reset_index(drop=True), metrics_df], axis=1)
    result["tfidf_cosine_similarity_corpus"] = compute_tfidf_corpus_wide(result).values
    return result


def summarize_metrics(df, groupby_cols=None):
    def q1(x):
        return np.percentile(x, 25)

    def q3(x):
        return np.percentile(x, 75)

    def iqr(x):
        return q3(x) - q1(x)

    agg_funcs = {col: ["count", "median", q1, q3, iqr] for col in METRIC_COLS}

    if groupby_cols:
        return df.groupby(groupby_cols).agg(agg_funcs)
    else:
        return df[METRIC_COLS].agg(["count", "median", q1, q3, iqr]).T


def check_skewness(df, export_csv=True):
    rows = []
    for col in METRIC_COLS:
        data = df[col].dropna().values
        if len(data) < 3:
            continue

        skew_val = stats.skew(data)
        abs_skew = abs(skew_val)
        verdict = (
            "1" if abs_skew < 0.5
            else "2" if abs_skew < 1.0
            else "3"
        )
        rows.append({
            "metric": col,
            "skewness": float(skew_val),
            "abs_skewness": float(abs_skew),
            "verdict": verdict,
            "recommended_summary": "Median + IQR",
        })

    summary = pd.DataFrame(rows)
    if summary.empty:
        return summary



    if export_csv:
        summary.to_csv(OUTPUT_DIR / "similarity_skewness_summary.csv", index=False)

    return summary

def plot_metric_distributions(df, filename):
    fig, ax = plt.subplots(figsize=(8, 5))
    data_to_plot = [df[col].dropna().values for col in METRIC_COLS]
    ax.boxplot(data_to_plot, tick_labels=METRIC_COLS, vert=True)
    ax.set_ylabel("Value (0–1, except WER and length_ratio)")
    ax.set_title("Distribution of AI-CMS similarity metrics across articles")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close(fig)


def plot_metric_by_journalist(df, metric, filename, title):
    journalists = sorted(df["journalist"].unique())
    data_to_plot = [df[df.journalist == j][metric].dropna().values for j in journalists]

    fig, ax = plt.subplots(figsize=(6, 0.8 * len(journalists) + 2))
    ax.boxplot(data_to_plot, tick_labels=journalists, vert=False)
    ax.set_xlabel(metric)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close(fig)


def plot_participant_metrics(df, journalist, output_dir):
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(journalist)).strip("_")
    metrics = [col for col in METRIC_COLS if col in df.columns]
    data_to_plot = [df[col].dropna().values for col in metrics]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.boxplot(data_to_plot, tick_labels=metrics, vert=True)
    ax.set_ylabel("Value")
    ax.set_title(f"{journalist} – Distribution of similarity metrics")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(output_dir / f"{safe_name}_metrics_boxplot.png", dpi=150)
    plt.close(fig)


def export_per_participant_results(df, output_dir, combined_data_path=None):
    output_dir.mkdir(exist_ok=True)
    participant_summaries = []
    correlation_rows = []

    for journalist in sorted(df["journalist"].astype(str).unique()):
        participant_df = df[df["journalist"].astype(str) == journalist].copy()

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", str(journalist)).strip("_")
        participant_output_dir = output_dir / safe_name
        participant_output_dir.mkdir(exist_ok=True)

        participant_df.to_csv(participant_output_dir / f"{safe_name}_similarity_metrics.csv", index=False)

        participant_summary = summarize_metrics(participant_df).reset_index()
        participant_summary.rename(columns={"index": "metric"}, inplace=True)
        participant_summary.insert(0, "journalist", journalist)
        participant_summaries.append(participant_summary)

        plot_participant_metrics(participant_df, journalist, participant_output_dir)

        if combined_data_path and Path(combined_data_path).exists():
            merged = merge_with_efficiency_quality(participant_df, combined_data_path)
            if not merged.empty:
                merged.to_csv(participant_output_dir / f"{safe_name}_merged_with_efficiency.csv", index=False)

                corr_res = correlation_analysis(merged, similarity_col="word_error_rate")

                plot_correlation_scatter(
                    merged, "word_error_rate", "quality", "Quality rating (1-5)",
                    f"{safe_name}_correlation_wer_quality.png",
                    f"{journalist} – Post-editing effort vs. quality rating",
                    output_dir=participant_output_dir,
                )
                plot_correlation_scatter(
                    merged, "word_error_rate", "min_per_100_words", "Writing time (min/100 words)",
                    f"{safe_name}_correlation_wer_writingtime.png",
                    f"{journalist} – Post-editing effort vs. writing time",
                    output_dir=participant_output_dir,
                )

                for target_col, stats_dict in corr_res.items():
                    correlation_rows.append({
                        "journalist": journalist,
                        "target": target_col,
                        "rho": stats_dict.get("rho"),
                        "p": stats_dict.get("p"),
                        "n": stats_dict.get("n"),
                    })

    if participant_summaries:
        combined_summary = pd.concat(participant_summaries, ignore_index=True)
        combined_summary.to_csv(output_dir / "similarity_summary_per_participant.csv", index=False)

    if correlation_rows:
        corr_df = pd.DataFrame(correlation_rows)
        corr_df.to_csv(output_dir / "similarity_correlation_per_participant.csv", index=False)

def save_html_diff(cms_text, ai_text, filename, title):
    cms_words = cms_text.split()
    ai_words = ai_text.split()

    differ = HtmlDiff(wrapcolumn=80)
    html_table = differ.make_table(
        ai_words, cms_words,
        fromdesc="ai", todesc="CMS-Text",
        context=True, numlines=2,
    )

    html_doc = f"""<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h2>{title}</h2>
{html_table}
</body>
</html>"""

    out_path = OUTPUT_DIR / filename
    out_path.write_text(html_doc, encoding="utf-8")


def save_lowest_similarity_examples(df, metric="jaccard_similarity", n=N_DIFF_EXAMPLES):
    lowest = df.nsmallest(n, metric)
    for rank, (_, row) in enumerate(lowest.iterrows(), start=1):
        filename = f"diff_example_{rank}_{row['journalist']}_{row['content_id']}.html"
        title = f"{row['journalist']} - content_id {row['content_id']} ({metric}={row[metric]:.2f})"
        save_html_diff(row["cms_text"], row["ai_text"], filename, title)

def merge_with_efficiency_quality(df, combined_data_path):
    eff_qual = pd.read_csv(combined_data_path)
    eff_qual_p2 = eff_qual[eff_qual["phase"] == 2].copy()

    df = df.copy()
    df["journalist_key"] = df["journalist"].astype(str).str.strip().str.lower()
    eff_qual_p2["journalist_key"] = eff_qual_p2["journalist"].astype(str).str.strip().str.lower()
    df["content_id_key"] = df["content_id"].astype(str).str.strip()
    eff_qual_p2["article_id_key"] = eff_qual_p2["article_id"].astype(str).str.strip()

    dupe_mask = eff_qual_p2.duplicated(subset=["journalist_key", "article_id_key"], keep=False)
    if dupe_mask.any():
        dupes = eff_qual_p2[dupe_mask]

        check_cols = ["journalist_key", "article_id_key", "quality", "min_per_100_words"]
        n_distinct = dupes[check_cols].drop_duplicates().shape[0]
        n_dupe_groups = dupes[["journalist_key", "article_id_key"]].drop_duplicates().shape[0]

    eff_qual_p2 = eff_qual_p2.drop_duplicates(subset=["journalist_key", "article_id_key"], keep="first")

    merged = df.merge(
        eff_qual_p2,
        left_on=["journalist_key", "content_id_key"],
        right_on=["journalist_key", "article_id_key"],
        how="inner",
        suffixes=("", "_eff"),
    )

    n_lost = len(df) - len(merged)
    return merged


def correlation_analysis(merged_df, similarity_col="word_error_rate"):

    results = {}
    for target_col, target_label in [
        ("quality", "Quality-Rating"),
        ("min_per_100_words", "Schreibzeit (min/100 Wörter)"),
    ]:
        pair = merged_df[[similarity_col, target_col]].dropna()
        if len(pair) < 3:
            continue

        rho, p = stats.spearmanr(pair[similarity_col], pair[target_col])
        results[target_col] = {"rho": rho, "p": p, "n": len(pair)}

    return results


def plot_correlation_scatter(merged_df, similarity_col, target_col, target_label, filename, title, output_dir=OUTPUT_DIR):
    pair = merged_df[[similarity_col, target_col]].dropna()

    fig, ax = plt.subplots(figsize=(6, 5))
    ax.scatter(pair[similarity_col], pair[target_col], alpha=0.6, edgecolor="black", linewidth=0.3)

    if len(pair) >= 2:
        z = np.polyfit(pair[similarity_col], pair[target_col], 1)
        x_line = np.linspace(pair[similarity_col].min(), pair[similarity_col].max(), 100)
        ax.plot(x_line, np.polyval(z, x_line), color="red", linestyle="--", linewidth=1)

    ax.set_xlabel(similarity_col)
    ax.set_ylabel(target_label)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_dir / filename, dpi=150)
    plt.close(fig)

def load_phase_data(phase, base_dir_phase1=None, base_dir_phase2=None):

    if phase == 1:
        base_dir = base_dir_phase1 or Path(r"C:\Users\Simon\Desktop\projects\masterarbeit_writing_efficiency\excel\phase1")
    else:
        base_dir = base_dir_phase2 or Path(r"C:\Users\Simon\Desktop\projects\masterarbeit_writing_efficiency\excel\phase2")
    
    if not base_dir.exists():
        raise FileNotFoundError(f"BASE_DIR für Phase {phase} nicht gefunden: {base_dir}")
    
    files = sorted(base_dir.glob("*_matched.json"))
    if not files:
        raise FileNotFoundError(f"Keine *_matched.json-Dateien in {base_dir} gefunden.")
    
    all_rows = []
    for path in files:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        
        journalist = raw.get("meta", {}).get("participant_username", path.stem)
        
        for item in raw.get("items", []):
            create_id = item.get("csv", {}).get("CREATE-ID ( / NGEN-ID)")
            if not create_id:
                create_id = item.get("content_id")
            
            if phase == 1:
                text = (item.get("article") or {}).get("text")
            else:
                text = (item.get("cms_article") or {}).get("text")
            
            if not text or not create_id:
                continue
            
            all_rows.append({
                "journalist": journalist,
                "phase": phase,
                "content_id": create_id,
                "text": text,
            })
    
    if not all_rows:
        raise ValueError(f"Keine gültigen Artikel-Paare für Phase {phase} gefunden.")
    
    return pd.DataFrame(all_rows)


def compute_article_word_count(text):
    return len(tokenize(text))


def prepare_correlation_data(phase_data, combined_data_path):

    combined = pd.read_csv(combined_data_path)
    
    phase_data = phase_data.copy()
    phase_data["word_count"] = phase_data["text"].apply(compute_article_word_count)
    
    phase = phase_data["phase"].iloc[0]
    
    journalist_mapping = {}
    for journalist in phase_data["journalist"].unique():
        first_id = phase_data[phase_data["journalist"] == journalist]["content_id"].iloc[0]
        matching_row = combined[(combined["phase"] == phase) & 
                               (combined["article_id"].astype(str) == str(first_id))]
        if not matching_row.empty:
            correct_journalist = matching_row["journalist"].iloc[0]
            journalist_mapping[journalist] = correct_journalist

    if journalist_mapping:
        phase_data["journalist"] = phase_data["journalist"].map(
            lambda x: journalist_mapping.get(x, x)
        )
    
    combined_phase = combined[combined["phase"] == phase].copy()
    
    merged = phase_data.merge(
        combined_phase[["journalist", "article_id", "writing_time_total", "min_per_100_words"]],
        left_on=["journalist", "content_id"],
        right_on=["journalist", "article_id"],
        how="inner",
    )
    
    n_lost = len(phase_data) - len(merged)
    
    return merged[["journalist", "phase", "content_id", "word_count", "writing_time_total", "min_per_100_words"]]


def compute_spearman_correlation(df, journalist, phase, value_col="writing_time_total"):
    subset = df[(df.journalist == journalist) & (df.phase == phase)]
    if len(subset) < 3:
        return np.nan, np.nan, len(subset)
    
    pair = subset[["word_count", value_col]].dropna()
    if len(pair) < 3:
        return np.nan, np.nan, len(pair)
    
    rho, p = stats.spearmanr(pair["word_count"], pair[value_col])
    return rho, p, len(pair)


def bootstrap_ci_for_correlation_diff(df, journalist, value_col="writing_time_total", 
                                       n_boot=5000, seed=42):
    rng = np.random.default_rng(seed)
    
    p1_data = df[(df.journalist == journalist) & (df.phase == 1)][["word_count", value_col]].dropna().values
    p2_data = df[(df.journalist == journalist) & (df.phase == 2)][["word_count", value_col]].dropna().values
    
    if len(p1_data) < 3 or len(p2_data) < 3:
        return np.nan, np.nan, np.nan, len(p1_data), len(p2_data)
    
    rho_p1_obs, _ = stats.spearmanr(p1_data[:, 0], p1_data[:, 1])
    rho_p2_obs, _ = stats.spearmanr(p2_data[:, 0], p2_data[:, 1])
    observed_diff = rho_p2_obs - rho_p1_obs

    diffs = []
    valid_boot_count = 0
    max_attempts = n_boot * 2
    
    for i in range(max_attempts):
        if valid_boot_count >= n_boot:
            break
        
        idx1 = rng.choice(len(p1_data), size=len(p1_data), replace=True)
        p1_boot = p1_data[idx1]
        rho_p1_boot, _ = stats.spearmanr(p1_boot[:, 0], p1_boot[:, 1])
        
        idx2 = rng.choice(len(p2_data), size=len(p2_data), replace=True)
        p2_boot = p2_data[idx2]
        rho_p2_boot, _ = stats.spearmanr(p2_boot[:, 0], p2_boot[:, 1])
        
        if not np.isnan(rho_p1_boot) and not np.isnan(rho_p2_boot):
            diffs.append(rho_p2_boot - rho_p1_boot)
            valid_boot_count += 1
    
    if len(diffs) == 0:
        return np.nan, np.nan, np.nan, len(p1_data), len(p2_data)
    
    diffs = np.array(diffs)
    ci_lower, ci_upper = np.percentile(diffs, [2.5, 97.5])
    return observed_diff, ci_lower, ci_upper, len(p1_data), len(p2_data)


def analyze_correlation_differences(combined_data_path=None, output_dir=None):
    if combined_data_path is None:
        combined_data_path = COMBINED_DATA_PATH
    if output_dir is None:
        output_dir = OUTPUT_DIR
    
    if not Path(combined_data_path).exists():
        return

    
    try:
        p1_raw = load_phase_data(phase=1)
        p1_merged = prepare_correlation_data(p1_raw, combined_data_path)
    except Exception as e:
        return
    
    try:
        p2_raw = load_phase_data(phase=2)
        p2_merged = prepare_correlation_data(p2_raw, combined_data_path)
    except Exception as e:
        return

    p1_merged = p1_merged.copy()
    p2_merged = p2_merged.copy()
    
    p1_merged["journalist"] = p1_merged["journalist"].str.lower()
    p2_merged["journalist"] = p2_merged["journalist"].str.lower()
    
    combined_phases = pd.concat([p1_merged, p2_merged], ignore_index=True)
    
    correlation_rows = []
    for journalist in sorted(combined_phases["journalist"].unique()):
        for phase in [1, 2]:
            rho, p_val, n = compute_spearman_correlation(
                combined_phases, journalist, phase, value_col="writing_time_total"
            )
            correlation_rows.append({
                "journalist": journalist,
                "phase": phase,
                "spearman_rho": rho,
                "p_value": p_val,
                "n_articles": n,
            })
    
    corr_df = pd.DataFrame(correlation_rows)
    corr_df.to_csv(output_dir / "correlation_article_length_writing_time.csv", index=False)

    
    journalists_phase1 = set(combined_phases[combined_phases["phase"] == 1]["journalist"].unique())
    journalists_phase2 = set(combined_phases[combined_phases["phase"] == 2]["journalist"].unique())
    journalists_both = journalists_phase1 & journalists_phase2

    
    bootstrap_rows = []
    for journalist in sorted(journalists_both):
        diff, ci_lo, ci_hi, n1, n2 = bootstrap_ci_for_correlation_diff(
            combined_phases, journalist, value_col="writing_time_total", n_boot=5000, seed=42
        )
        
        if not np.isnan(diff):
            contains_zero = (ci_lo <= 0 <= ci_hi)
            bootstrap_rows.append({
                "journalist": journalist,
                "n_articles_phase1": n1,
                "n_articles_phase2": n2,
                "delta_rho": diff,
                "ci_lower": ci_lo,
                "ci_upper": ci_hi,
                "ci_contains_zero": contains_zero,
            })
            
            ci_str = f"[{ci_lo:.4f}, {ci_hi:.4f}]"
            sig_str = "" if contains_zero else " (signifikant)"
    
    bootstrap_df = pd.DataFrame(bootstrap_rows)
    bootstrap_df.to_csv(output_dir / "bootstrap_ci_correlation_diff.csv", index=False)
    
    plot_correlation_diff_forest(bootstrap_df, output_dir)
    
    return bootstrap_df


def plot_correlation_diff_forest(bootstrap_df, output_dir=OUTPUT_DIR):
    if bootstrap_df.empty:
        return
    
    bootstrap_df = bootstrap_df.sort_values("delta_rho")
    
    fig, ax = plt.subplots(figsize=(8, max(4, 0.6 * len(bootstrap_df))))
    
    y_pos = np.arange(len(bootstrap_df))
    ax.scatter(bootstrap_df["delta_rho"], y_pos, color="navy", s=100, zorder=3, label="Delta-Rho")
    
    for i, (_, row) in enumerate(bootstrap_df.iterrows()):
        ax.plot(
            [row["ci_lower"], row["ci_upper"]], [i, i],
            color="darkgray", linewidth=2, zorder=2
        )
    
    ax.axvline(0, color="red", linestyle="--", linewidth=1, alpha=0.7, label="Delta-Rho = 0")
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(bootstrap_df["journalist"])
    ax.set_xlabel("Delta-Rho (Phase 2 - Phase 1)")
    ax.set_title("Bootstrap-95%-CI für Differenz der Spearman-Korrelationen\n(Article Length x Writing Time)")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3, axis="x")
    
    fig.tight_layout()
    fig.savefig(output_dir / "forest_plot_correlation_diff.png", dpi=150)
    plt.close(fig)


def main():
    df = load_all()
          f"({df.journalist.nunique()} Journalist:innen)\n")
    df = exclude_known_mismatches(df)
    df = compute_all_metrics(df)
    df.to_csv(OUTPUT_DIR / "similarity_metrics_per_article.csv", index=False)

    check_skewness(df, export_csv=True)

    agg_summary = summarize_metrics(df)

    agg_summary.to_csv(OUTPUT_DIR / "similarity_summary_aggregated.csv")

    per_journalist_summary = summarize_metrics(df, groupby_cols=["journalist"])
    per_journalist_summary.to_csv(OUTPUT_DIR / "similarity_summary_per_journalist.csv")

    export_per_participant_results(df, PER_PARTICIPANT_DIR, COMBINED_DATA_PATH)

    plot_metric_distributions(df, "similarity_metrics_boxplot.png")
    plot_metric_by_journalist(
        df, "word_error_rate",
        "word_error_rate_per_journalist.png",
        "Word Error Rate (post-editing effort) by journalist",
    )

    save_lowest_similarity_examples(df, metric="jaccard_similarity", n=N_DIFF_EXAMPLES)

    if COMBINED_DATA_PATH.exists():
        merged = merge_with_efficiency_quality(df, COMBINED_DATA_PATH)
        merged.to_csv(OUTPUT_DIR / "similarity_merged_with_efficiency_quality.csv", index=False)

        correlation_analysis(merged, similarity_col="word_error_rate")

        plot_correlation_scatter(
            merged, "word_error_rate", "quality", "Quality rating (1-5)",
            "correlation_wer_quality.png",
            "Post-editing effort vs. quality rating",
            output_dir=OUTPUT_DIR,
        )
        plot_correlation_scatter(
            merged, "word_error_rate", "min_per_100_words", "Writing time (min/100 words)",
            "correlation_wer_writingtime.png",
            "Post-editing effort vs. writing time",
            output_dir=OUTPUT_DIR,
        )


    analyze_correlation_differences(combined_data_path=COMBINED_DATA_PATH, output_dir=OUTPUT_DIR)



if __name__ == "__main__":
    main()