"""Create the local .env, or add the keys it lacks, without printing secrets or changing existing values."""
import os
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[2]


def key_of(line):
    return line.partition("=")[0] if "=" in line and not line.startswith("#") else None


def fill(line):
    """The example line with a replace-* placeholder swapped for a new secret."""
    key, _, value = line.partition("=")
    if not value.startswith("replace-"):
        return line
    return f"{key}={secrets.token_urlsafe(64 if key == 'DJANGO_SECRET_KEY' else 32)}"


def complete_env(path, example):
    """Create path from the example, or append the example's keys that path lacks. Returns the keys added."""
    lines = Path(example).read_text().splitlines()
    path = Path(path)
    if not path.exists():
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write("\n".join(fill(line) for line in lines) + "\n")
        return [key_of(line) for line in lines if key_of(line)]
    text = path.read_text()
    present = {key_of(line) for line in text.splitlines()}
    missing = [fill(line) for line in lines if key_of(line) and key_of(line) not in present]
    if missing:
        with open(path, "a") as output:
            output.write(("" if text.endswith("\n") or not text else "\n") + "\n".join(missing) + "\n")
    return [key_of(line) for line in missing]


if __name__ == "__main__":
    existed = (ROOT / ".env").exists()
    added = complete_env(ROOT / ".env", ROOT / ".env.example")
    if not existed:
        print("Created .env; secrets were not printed.")
    else:
        print(f"Added {len(added)} missing key(s) to .env; existing values were not changed.")
