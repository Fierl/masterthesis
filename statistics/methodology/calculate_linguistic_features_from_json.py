import argparse
import csv
import json
import re
from pathlib import Path
import pandas as pd
import spacy
from lexicalrichness import LexicalRichness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "input_json",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="linguistic_features.json",
    )
    parser.add_argument(
        "--id-field",
        choices=["content_id", "create_id"],
        default=None
    )
    parser.add_argument(
        "--lang",
        choices=["en", "de"],
        default="de",
    )
    return parser.parse_args()


def load_input_data(input_path: Path):
    with input_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict) and "items" in data:
        data = data["items"]

    return data


def select_id(item: dict, id_field: str | None):
    if id_field:
        return item.get(id_field)
    return item.get("content_id") or item.get("create_id") or item.get("id")


def extract_text_rows(data: list[dict], id_field: str | None):
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue

        content_id = select_id(item, id_field)
        text = item.get("text")

        if content_id is None:
            content_id = item.get("content_id") or item.get("create_id")
        if text is None and "cms_article" in item:
            cms_article = item.get("cms_article")
            if isinstance(cms_article, dict):
                text = cms_article.get("text")

        if content_id is None or text is None:
            continue

        rows.append({"id": content_id, "text": text})

    return rows


def write_json(output_path: Path, rows: list[dict]):
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)


def write_csv(output_path: Path, rows: list[dict]):
    fieldnames = list(rows[0].keys()) if rows else ["id", "text"]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def num_of_sent(text_doc):
    return sum(1 for _ in text_doc.sents)


def num_of_words(doc):
    return sum(1 for tok in doc if not tok.is_punct and not tok.is_space)


def get_complexity_dep_labels(lang: str):
    if lang == "de":
        return {"acl", "advcl", "ccomp", "conj", "parataxis", "xcomp", "rc", "oc", "re", "appos", "relcl"}
    return {"acl", "conj", "advcl", "ccomp", "csubj", "discourse", "parataxis", "xcomp", "relcl"}


def sent_complexity_structure(doc, lang: str = "de"):
    labels = get_complexity_dep_labels(lang)
    return len([token for token in doc if token.dep_ in labels])


def calculate_dep_score(text_doc, lang: str = "de"):
    values = [sent_complexity_structure(sent, lang=lang) for sent in text_doc.sents]
    return sum(values) / len(values) if values else 0.0


def walk_tree(node, depth=0):
    if node.n_lefts + node.n_rights > 0:
        return max(walk_tree(child, depth + 1) for child in node.children)
    return depth


def calculate_dep_length(text_doc):
    values = [walk_tree(sent.root, 0) for sent in text_doc.sents]
    return sum(values) / len(values) if values else 0.0


def calculate_lex_richness(doc):
    tokens = [tok.text.lower() for tok in doc if tok.is_alpha]
    if not tokens:
        return 0.0
    text_clean = " ".join(tokens)
    lex = LexicalRichness(text_clean)
    return lex.mtld()


def load_discourse_markers(base_path: Path, lang: str):
    if lang == "de":
        discourse_file = base_path / "markers" / "connectives_discourse_markers_german.txt"
    else:
        discourse_file = base_path / "markers" / "connectives_discourse_markers_PDTB.txt"

    discourse = pd.read_csv(discourse_file, sep="'", encoding="utf-8", header=None, usecols=[1, 3])
    discourse[3] = discourse[3].apply(lambda x: x.replace("t_conn_", ""))
    discourse[1] = discourse[1].apply(lambda x: f" {x} ")
    return discourse


def count_discourse_markers(text: str, discourse: pd.DataFrame) -> int:
    if not text:
        return 0
    text_lower = text.lower()
    total = 0
    for marker in discourse[1].tolist():
        marker_clean = marker.strip().replace("_", " ").lower()
        pattern = r'(?<!\w)' + re.escape(marker_clean) + r'(?!\w)'
        total += len(re.findall(pattern, text_lower))
    return total


GERMAN_MODAL_CATEGORIES = ["sicher", "wahrscheinlich", "möglich", "unmöglich"]


def load_modals(base_path: Path, lang: str) -> pd.DataFrame:
    if lang == "de":
        modals_file = base_path / "markers" / "modals_german.csv"
        modals = pd.read_csv(modals_file, sep=",", header=None, names=["term", "category"])
        modals["category"] = modals["category"].astype(str).str.strip().str.lower()
    else:
        modals_file = base_path / "markers" / "modals.csv"
        modals = pd.read_csv(modals_file, sep=",", engine="python", header=None, names=["term"])
        modals["category"] = "modal_verb"

    modals["term"] = modals["term"].apply(lambda x: str(x).replace("_", " ").strip().lower())
    return modals


def count_modals_total(text: str, modals: pd.DataFrame) -> int:
    if not text:
        return 0

    text_lower = text.lower()
    total = 0
    for _, row in modals.iterrows():
        term = row["term"]
        pattern = r'(?<!\w)' + re.escape(term) + r'(?!\w)'
        total += len(re.findall(pattern, text_lower))
    return total


def count_konjunktiv_i(doc):
    count = 0
    for token in doc:
        morph = token.morph.to_dict()
        if morph.get("Mood") == "Sub" and morph.get("Tense") == "Pres":
            count += 1
    return count


def count_attribution(text: str) -> int:
    attribution_patterns = [
        r"\blaut\s\w+",
        r"\b\w+\szufolge\b",
        r"\bnach\s(?:eigenen\s+)?Angaben\b",
        r"\bauf\s(?:PNP-|DK-|MZ-)?(?:Nachfrage|Anfrage)\b",
        r"\bim\s+Gespräch\s+mit\b",
        r"\bso\s+\w+\s+weiter\b",
        r"\bso\s+\w+\s+wörtlich\b",
        r"\b(?:Sprecher|Sprecherin|Pressesprecher|Pressesprecherin|Pressereferent|Pressereferentin)\b",
        r"\b(?:sagt|sagte|erklärt|erklärte|betont|betonte|berichtet|berichtete|teilt|teilte|bestätigt|bestätigte)\s+\w+",
    ]

    return sum(
        len(re.findall(pattern, text, flags=re.IGNORECASE))
        for pattern in attribution_patterns
    )


def normalize_text(text: str) -> str:
    text = re.sub(r"(?<=[a-zäöüß])(?=[A-ZÄÖÜ])", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def nominalisation_counter(doc, lang: str = "de"):
    if lang == "de":
        suffixes_n = r"\b[A-Za-zÄÖÜäöüß]+(?:ung|keit|heit|schaft|nis|tum|ment|ion|ität)(?:e?n?|en|s)?\b"
    else:
        suffixes_n = r"\b[A-Z]*\w+(?:tion|ment|ance|ence|ion|it(?:y|ies)|ness|ship)(?:s|es)?\b"

    nouns = [token.text for token in doc if token.pos_ == "NOUN"]
    return len([noun for noun in nouns if re.search(suffixes_n, noun, flags=re.IGNORECASE)])


def count_passive_voice(doc, lang: str = "de", include_zustandspassiv: bool = False) -> int:
    if lang != "de":
        return sum(1 for tok in doc if tok.morph.get("Voice") == ["Pass"])

    count = 0

    for tok in doc:
        if tok.dep_ == "aux:pass":
            count += 1
            continue

        if tok.lemma_.lower() == "werden" and tok.tag_ in {"VAFIN", "VAINF"}:
            if any(child.tag_ in {"VVPP", "VAPP"} for child in tok.children):
                count += 1
                continue

        if tok.lemma_.lower() == "sein" and tok.tag_ in {"VAFIN", "VAINF"}:
            children = list(tok.children)
            has_participle = any(child.tag_ == "VVPP" for child in children)
            has_worden = any(
                child.tag_ == "VAPP" or child.lemma_.lower() == "worden"
                for child in children
            )

            if has_participle and has_worden:
                count += 1
                continue

            if include_zustandspassiv and has_participle and not has_worden:
                count += 1
                continue

    return count


def count_syllables_de(word: str) -> int:
    word = word.lower()
    vowel_groups = re.findall(r"[aeiouyäöü]+", word)
    return max(1, len(vowel_groups))


def count_syllables_en(word: str) -> int:
    word = word.lower()
    vowel_groups = re.findall(r"[aeiouy]+", word)
    count = len(vowel_groups)
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def calculate_readability(text: str, doc, lang: str = "de") -> dict:
    words = [tok.text for tok in doc if not tok.is_punct and not tok.is_space]
    sentences = list(doc.sents)
    n_words = len(words)
    n_sentences = len(sentences) or 1

    if n_words == 0:
        return {"readability_index": None, "readability_formula": None}

    if lang == "de":
        syllable_counts = [count_syllables_de(w) for w in words]
        ms = sum(1 for s in syllable_counts if s >= 3) / n_words * 100
        sl = n_words / n_sentences
        iw = sum(1 for w in words if len(w) > 6) / n_words * 100
        es = sum(1 for s in syllable_counts if s == 1) / n_words * 100
        wsf1 = 0.1935 * ms + 0.1672 * sl + 0.1297 * iw - 0.0327 * es - 0.875
        return {"readability_index": wsf1, "readability_formula": "wiener_sachtextformel_1"}
    else:
        syllable_counts = [count_syllables_en(w) for w in words]
        n_syllables = sum(syllable_counts)
        flesch = 206.835 - 1.015 * (n_words / n_sentences) - 84.6 * (n_syllables / n_words)
        return {"readability_index": flesch, "readability_formula": "flesch_reading_ease"}


def calculate_features(rows: list[dict], base_path: Path, lang: str = "de"):
    model_name = "de_core_news_lg" if lang == "de" else "en_core_web_sm"
    try:
        model = spacy.load(model_name)
    except Exception:
        raise RuntimeError(
            f"spaCy model {model_name} nicht gefunden. Bitte installieren: python -m spacy download {model_name}"
        )

    discourse = load_discourse_markers(base_path, lang)
    modals = load_modals(base_path, lang)

    enriched = []
    for item in rows:
        raw_text = item["text"]
        text = normalize_text(raw_text)
        doc = model(text)

        sentence_count = num_of_sent(doc)
        word_count = num_of_words(doc)
        discourse_count = count_discourse_markers(text, discourse)
        modals_count = count_modals_total(text, modals)
        konjunktiv_count = count_konjunktiv_i(doc)
        attribution_count = count_attribution(text)
        nominalisation_count = nominalisation_counter(doc, lang=lang)
        passive_count = count_passive_voice(doc, lang=lang)
        readability = calculate_readability(text, doc, lang=lang)
        words_factor = (100 / word_count) if word_count else 0.0

        avg_sentence_length = (word_count / sentence_count) if sentence_count else 0.0

        result = {
            "id": item["id"],
            "text": text,

            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_sentence_length": avg_sentence_length,

            "sent_complex_tags": calculate_dep_score(doc, lang=lang),
            "sent_complex_depth": calculate_dep_length(doc),
            "lexical_diversity_mtld": calculate_lex_richness(doc),
            "readability_index": readability["readability_index"],
            "readability_formula": readability["readability_formula"],

            "discourse_per_100w": discourse_count * words_factor,
            "modals_per_100w": modals_count * words_factor,
            "konjunktiv_per_100w": konjunktiv_count * words_factor,
            "attribution_per_100w": attribution_count * words_factor,
            "nominalisations_per_100w": nominalisation_count * words_factor,
            "passive_per_100w": passive_count * words_factor,
        }

        enriched.append(result)

    return enriched


def main() -> None:
    args = parse_args()
    input_path = Path(args.input_json)
    output_path = Path(args.output)
    base_path = Path(__file__).resolve().parent

    data = load_input_data(input_path)
    rows = extract_text_rows(data, args.id_field)

    enriched_rows = calculate_features(rows, base_path, lang=args.lang)

    if output_path.suffix.lower() == ".csv":
        write_csv(output_path, enriched_rows)
    else:
        write_json(output_path, enriched_rows)


if __name__ == "__main__":
    main()