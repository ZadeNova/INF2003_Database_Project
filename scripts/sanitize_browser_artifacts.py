"""Redact demo passwords and authentication cookies from retained browser traces."""
import argparse
import base64
import json
import os
import zipfile
from pathlib import Path
from urllib.parse import quote_plus

PRIVATE_HEADERS = {"authorization", "proxy-authorization", "cookie", "set-cookie", "sessionid", "csrftoken"}


def demo_secrets():
    return [value for name, value in os.environ.items() if name.startswith("DEMO_") and name.endswith("_PASSWORD") and value]


def secret_variants(secrets):
    variants = set()
    for value in secrets:
        variants.update((value, quote_plus(value), json.dumps(value)[1:-1], base64.b64encode(value.encode()).decode()))
    return sorted(variants, key=len, reverse=True)


def redact_text(text, secrets):
    for value in secret_variants(secrets):
        text = text.replace(value, "<redacted>")
    return text


def redact_json(value):
    if isinstance(value, dict):
        if str(value.get("name", "")).lower() in PRIVATE_HEADERS and "value" in value:
            value["value"] = "<redacted>"
        return {key: "<redacted>" if key.lower() in PRIVATE_HEADERS else redact_json(child) for key, child in value.items()}
    if isinstance(value, list):
        return [redact_json(child) for child in value]
    return value


def redact_bytes(data, secrets):
    try:
        text = redact_text(data.decode("utf-8"), secrets)
    except UnicodeDecodeError:
        return data
    lines = []
    for line in text.splitlines(keepends=True):
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            lines.append(line)
        else:
            lines.append(json.dumps(redact_json(value), separators=(",", ":")) + "\n")
    return "".join(lines).encode("utf-8")


def sanitize(directory, secrets=None):
    root = Path(directory).resolve()
    if not root.exists():
        return 0
    secrets = demo_secrets() if secrets is None else secrets
    count = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        if path.suffix == ".zip":
            temporary = path.with_suffix(".redacted.tmp")
            with zipfile.ZipFile(path) as original, zipfile.ZipFile(temporary, "w") as cleaned:
                for entry in original.infolist():
                    cleaned.writestr(entry, redact_bytes(original.read(entry), secrets))
            temporary.replace(path)
            count += 1
        elif path.suffix in {".txt", ".log", ".json"}:
            path.write_bytes(redact_bytes(path.read_bytes(), secrets))
            count += 1
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(f"Browser artifacts sanitized: {sanitize(args.directory)} files")
