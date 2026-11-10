"""Resumable offline Argos pt->en translation, isolated from the app and data tools.

Download is explicit (--download-model). Subsequent runs are entirely offline.
Argos 1.9.6 supplies the package loader/tokenizer; its CTranslate2 engine translates
whole review paragraphs in batches, without the optional Stanza/PyTorch segmenter.
CPU float32, beam 4 and one inference thread make execution reproducible. The CSV
is atomically rewritten in source-hash order after every batch, so SIGTERM loses
at most one batch. Portuguese text is never stripped or normalised.
"""

import argparse
import csv
import hashlib
import importlib.metadata
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_URL = "https://argos-net.com/v1/translate-pt_en-1_9.argosmodel"
MODEL_VERSION = "1.9"
ARGOS_VERSION = "1.9.6"
FIELDS = ["text_hash", "source_text", "english_text", "machine_translated"]


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_texts(raw):
    with (Path(raw) / "olist_order_reviews_dataset.csv").open(encoding="utf-8", newline="") as stream:
        return sorted(
            {
                row[field]
                for row in csv.DictReader(stream)
                for field in ("review_comment_title", "review_comment_message")
                if row[field]
            }
        )


def read_translations(path):
    if not Path(path).exists():
        return {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = {}
    for row in rows:
        if (
            row.get("text_hash") != text_hash(row.get("source_text", ""))
            or not row.get("english_text")
            or row.get("machine_translated") != "true"
        ):
            raise ValueError("Malformed translation row or incorrect source hash")
        if row["text_hash"] in result:
            raise ValueError("Duplicate translation hash")
        result[row["text_hash"]] = row
    return result


def save(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows[key] for key in sorted(rows))
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=ROOT / "data/raw/olist")
    parser.add_argument("--output", type=Path, default=ROOT / "data/derived/olist/translations.csv")
    parser.add_argument("--model", type=Path, default=ROOT / ".cache/translation/pt_en-1.9.argosmodel")
    parser.add_argument("--download-model", action="store_true")
    parser.add_argument(
        "--download-only",
        action="store_true",
        help="Fetch the pinned model with host Python, without translation dependencies",
    )
    parser.add_argument("--batch-size", type=int, default=128)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("batch size must be positive")
    if args.download_model and not args.model.exists():
        args.model.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "Mozilla/5.0"})
        with (
            urllib.request.urlopen(request, timeout=60) as source,  # noqa: S310 - fixed https MODEL_URL
            args.model.with_suffix(".download").open("wb") as target,
        ):
            import shutil

            shutil.copyfileobj(source, target)
        args.model.with_suffix(".download").replace(args.model)
    if not args.model.exists():
        parser.error("model missing; run once with --download-model in a network-enabled environment")
    if args.download_only:
        print("Pinned model is available locally; translation remains offline.")
        return
    if importlib.metadata.version("argostranslate") != ARGOS_VERSION:
        parser.error(f"requires argostranslate=={ARGOS_VERSION} in the translation environment")
    import ctranslate2
    from argostranslate import package

    model_sha = hashlib.sha256(args.model.read_bytes()).hexdigest()
    manifest_path = args.output.with_suffix(".model.json")
    manifest = {
        "argos_version": ARGOS_VERSION,
        "model_version": MODEL_VERSION,
        "model_url": MODEL_URL,
        "sha256": model_sha,
        "compute_type": "float32",
        "beam_size": 4,
        "segmentation": "whole newline-separated paragraphs",
        "threads": 1,
    }
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        raise ValueError("Translation model/settings differ from the recorded manifest")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    package.install_from_path(args.model)
    matches = [
        p
        for p in package.get_installed_packages()
        if p.from_code == "pt" and p.to_code == "en" and p.package_version == MODEL_VERSION
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly the pinned pt->en 1.9 package")
    pkg = matches[0]
    translator = ctranslate2.Translator(
        str(pkg.package_path / "model"), device="cpu", compute_type="float32", inter_threads=1, intra_threads=1
    )
    texts = source_texts(args.raw)
    rows = read_translations(args.output)
    wanted = {text_hash(text) for text in texts}
    rows = {key: row for key, row in rows.items() if key in wanted}
    missing = sorted((text_hash(t), t) for t in texts if text_hash(t) not in rows)
    save(args.output, rows)
    print(f"Distinct texts: {len(texts)}; cached: {len(texts) - len(missing)}; remaining: {len(missing)}", flush=True)
    for start in range(0, len(missing), args.batch_size):
        batch = missing[start : start + args.batch_size]
        paragraphs, positions = [], []
        for _, original in batch:
            pieces = original.split("\n")
            positions.append((len(paragraphs), len(pieces)))
            paragraphs.extend(pieces)
        tokens = [pkg.tokenizer.encode(p) for p in paragraphs]
        translated = translator.translate_batch(
            tokens, beam_size=4, max_batch_size=32, max_decoding_length=512, return_scores=False
        )
        decoded = [pkg.tokenizer.decode(r.hypotheses[0]).strip() for r in translated]
        for (key, original), (offset, count) in zip(batch, positions, strict=True):
            english = "\n".join(decoded[offset : offset + count])
            if not english:
                # Punctuation-only inputs can decode to an empty sequence. Preserve
                # them verbatim; this is still labelled as model-processed text.
                english = original
            rows[key] = dict(zip(FIELDS, (key, original, english, "true"), strict=True))
        save(args.output, rows)
        print(f"Translated {min(start + len(batch), len(missing))}/{len(missing)} remaining texts", flush=True)


if __name__ == "__main__":
    main()
