#!/usr/bin/env python3
"""Build and check the INF2003 submission zip (RUBRICS.md, Final submission): one zip holding the final report PDF,
the slides (.pptx), the presentation video (.mp4) and the source code zip.

  python scripts/package_submission.py --report report.pdf --slides slides.pptx --video demo.mp4
  python scripts/package_submission.py --report report.pdf --slides slides.pptx --video demo.mp4 --ref main --out ../Team82.zip
  python scripts/package_submission.py --check-only Team82.zip

Building packs the committed files at --ref (git archive, so ignored files such as .env can never be included) into a
source zip, then puts it beside the three deliverables in the outer zip and checks the result. Exit status 1 when a
check FAILS; WARN lines need a human look. Standard library only; no network.
"""
import argparse
import io
import re
import subprocess
import sys
import zipfile
from pathlib import Path

REQUIRED = {".pdf": "final report", ".pptx": "presentation slides", ".mp4": "presentation video",
            ".zip": "source code zip"}
SOURCE_REQUIRED = ["README.md", "compose.yaml", "src"]
LIMIT_BYTES = 2 * 1024 ** 3       # the brief allows a GitHub link instead above 2 GB
TEXT = {".md", ".yaml", ".yml", ".txt", ".py", ".sh", ".json", ".toml", ".cfg", ".ini", ".html", ".css", ".js", ".example"}
SECRET_FILES = re.compile(r"(^|/)\.env($|\.(?!example$))|\.pem$|\.key$|\.p12$|\.pfx$|\.tfstate")
SECRET_TEXT = [
    ("private key", re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY")),
    ("cloud access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub or Slack token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|xox[abprs]-[A-Za-z0-9-]{10,})")),
]


def build(ref, report, slides, video, dest):
    """Write the outer zip at dest with the source zip made from ref; returns the commit it packed."""
    source = subprocess.run(["git", "archive", "--format=zip", ref], check=True, capture_output=True).stdout
    commit = subprocess.run(["git", "rev-parse", ref], check=True, capture_output=True, text=True).stdout.strip()
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as outer:
        for path in (report, slides, video):
            outer.write(path, Path(path).name)
        outer.writestr("source_code.zip", source)
    return commit


def top_level(names):
    return [name for name in names if "/" not in name.rstrip("/") and not name.endswith("/")]


def check_source(data):
    """Checks on the nested source zip; returns (level, message) pairs."""
    results = []
    try:
        source = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return [("WARN", "the source code zip is not a readable zip file")]
    names = set(source.namelist())
    for required in SOURCE_REQUIRED:
        present = required in names or any(name.startswith(required + "/") for name in names)
        results.append(("PASS" if present else "WARN", f"source zip contains {required}"))
    secret_files = sorted(name for name in names if SECRET_FILES.search(name))
    results.append(("PASS" if not secret_files else "FAIL",
                    "source zip has no .env, key or state files" + (f": {secret_files[:5]}" if secret_files else "")))
    leaks = []
    for name in sorted(names):
        if Path(name).suffix.lower() in TEXT and not name.endswith("/"):
            text = source.read(name).decode("utf-8", "replace")
            leaks += [f"{name}: {label}" for label, pattern in SECRET_TEXT if pattern.search(text)]
    results.append(("PASS" if not leaks else "FAIL",
                    "source zip has no private keys or access tokens" + (f": {leaks[:5]}" if leaks else "")))
    return results


def check(zip_path):
    results = []

    def say(level, message):
        results.append((level, message))

    try:
        outer = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError):
        return [("FAIL", f"{zip_path} is not a readable zip file")]
    files = top_level(outer.namelist())
    for suffix, what in REQUIRED.items():
        found = [name for name in files if name.lower().endswith(suffix)]
        if len(found) == 1:
            say("PASS", f"{what}: {found[0]}")
        elif not found:
            hint = " (the brief says .ppt in one place and .pptx in another; submit .pptx)" if suffix == ".pptx" else ""
            say("FAIL", f"{what}: no {suffix} file at the top level of the zip{hint}")
        else:
            say("FAIL", f"{what}: {len(found)} {suffix} files at the top level, expected one: {found}")
    if any(name.lower().endswith(".ppt") for name in files):
        say("FAIL", "a .ppt file is present; submit the slides as .pptx")
    extra = [name for name in files if Path(name).suffix.lower() not in REQUIRED]
    nested = [name for name in outer.namelist() if "/" in name.rstrip("/")]
    if extra or nested:
        say("WARN", f"files beyond the four deliverables: {(extra + nested)[:6]}")
    for name in files:
        suffix = Path(name).suffix.lower()
        data = outer.read(name)
        if not data:
            say("WARN", f"{name} is empty")
        elif suffix == ".pdf" and not data.startswith(b"%PDF-"):
            say("WARN", f"{name} does not look like a PDF")
        elif suffix == ".pptx" and not data.startswith(b"PK"):
            say("WARN", f"{name} does not look like a .pptx file")
        elif suffix == ".mp4" and data[4:8] != b"ftyp":
            say("WARN", f"{name} does not look like an MP4 file")
        elif suffix == ".zip":
            for level, message in check_source(data):
                say(level, message)
    size = Path(zip_path).stat().st_size
    say("PASS" if size < LIMIT_BYTES else "WARN",
        f"size {size / 1e6:.1f} MB" + ("" if size < LIMIT_BYTES else " is over 2 GB: the brief allows a GitHub link with access granted instead"))
    return results


def report(results):
    for level, message in results:
        print(f"{level:4}  {message}")
    failures = sum(level == "FAIL" for level, _ in results)
    print(f"\n{failures} FAIL, {sum(level == 'WARN' for level, _ in results)} WARN")
    return 1 if failures else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", help="the final report PDF")
    parser.add_argument("--slides", help="the presentation slides (.pptx)")
    parser.add_argument("--video", help="the presentation video (.mp4)")
    parser.add_argument("--ref", default="HEAD", help="git ref whose committed files become the source zip")
    parser.add_argument("--out", default="INF2003_Team82_Submission.zip")
    parser.add_argument("--check-only", metavar="ZIP", help="check an existing zip instead of building one")
    args = parser.parse_args(argv)
    if args.check_only:
        return report(check(args.check_only))
    if not (args.report and args.slides and args.video):
        parser.error("--report, --slides and --video are required (or use --check-only ZIP)")
    for path in (args.report, args.slides, args.video):
        if not Path(path).is_file():
            parser.error(f"{path} does not exist")
    commit = build(args.ref, args.report, args.slides, args.video, args.out)
    print(f"Wrote {args.out} (source from commit {commit[:12]})")
    return report(check(args.out))


if __name__ == "__main__":
    sys.exit(main())
