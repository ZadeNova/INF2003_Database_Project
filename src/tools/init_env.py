"""Create the local .env, or add the keys it lacks, without printing secrets or changing existing values."""
import os
from pathlib import Path
import secrets

path = Path(__file__).resolve().parents[1] / ".env"
example = (path.parent / ".env.example").read_text().splitlines()


def key_of(line):
    return line.partition("=")[0] if "=" in line and not line.startswith("#") else None


def fill(line):
    """The example line with each replace-* placeholder swapped for a new secret."""
    key, _, value = line.partition("=")
    if not value.startswith("replace-"):
        return line
    return f"{key}={secrets.token_urlsafe(64 if key == 'DJANGO_SECRET_KEY' else 32)}"


if path.exists():
    present = {key_of(line) for line in path.read_text().splitlines()}
    missing = [fill(line) for line in example if key_of(line) and key_of(line) not in present]
    if missing:
        with open(path, "a") as output:
            output.write(("" if path.read_text().endswith("\n") else "\n") + "\n".join(missing) + "\n")
    print(f"Added {len(missing)} missing key(s) to .env; existing values were not changed.")
else:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        output.write("\n".join(fill(line) for line in example) + "\n")
    print("Created local .env; secrets were not printed.")
