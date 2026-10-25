"""Audit each installed environment's pins with short, accountable exceptions."""
import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = [
    ROOT / "src/requirements.txt", ROOT / "src/requirements-dev.txt",
    ROOT / "analytics/requirements.txt", ROOT / "scripts/translation-requirements.txt",
    ROOT / "scripts/translation-argos-requirements.txt",
]


def load_exceptions(path, today=None):
    today = today or datetime.now(timezone.utc).date()
    with Path(path).open("rb") as source:
        records = tomllib.load(source).get("exceptions", [])
    if not isinstance(records, list):
        raise ValueError("exceptions must be an array")
    found = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"id", "reason", "owner", "added", "expires"}:
            raise ValueError("Each exception needs exactly id, reason, owner, added and expires")
        if not all(isinstance(record[key], str) and record[key].strip() for key in ("id", "reason", "owner")):
            raise ValueError("Exception id, reason and owner must be nonblank")
        if not re.fullmatch(r"(?:CVE-\d{4}-\d+|PYSEC-\d{4}-\d+|GHSA-[a-z0-9-]+)", record["id"]):
            raise ValueError("Use a CVE, PYSEC or GHSA advisory ID")
        if record["id"] in found:
            raise ValueError("Duplicate advisory exception")
        found.add(record["id"])
        added, expires = record["added"], record["expires"]
        if type(added) is not date or type(expires) is not date:
            raise ValueError("Exception added and expires must be TOML dates")
        if added > today or expires < today or not added < expires <= added + timedelta(days=14):
            raise ValueError(f"{record['id']}: exception expired, future-dated or longer than fourteen days")
    return records


def ignore_flags(records):
    return [argument for record in records for argument in ("--ignore-vuln", record["id"])]


def allowed_unfixed(dependencies, records):
    ids = {record["id"] for record in records}
    for dependency in dependencies:
        if dependency.get("skip_reason"):
            return False
        for advisory in dependency.get("vulns", []):
            # An exception must stop applying as soon as a fix is available.
            if advisory.get("fix_versions") or not ({advisory["id"], *advisory.get("aliases", [])} & ids):
                return False
    return True


def audit(requirement, records):
    command = [sys.executable, "-m", "pip_audit", "--strict", "--progress-spinner=off", "--desc=off", "-r", str(requirement)]
    if requirement.name.startswith("translation-"):
        # Every installed translation component is pinned; Argos deliberately omits
        # its unused Torch/Stanza dependency tree. Audit exactly that environment.
        command += ["--no-deps", "--disable-pip"]
    checked = subprocess.run(command + ["--format=json"], check=False, text=True, stdout=subprocess.PIPE)
    try:
        dependencies = json.loads(checked.stdout)["dependencies"]
    except (json.JSONDecodeError, KeyError, TypeError):
        print(checked.stdout, end="")
        return checked.returncode or 1
    advisories = [advisory for dependency in dependencies for advisory in dependency.get("vulns", [])]
    fixed = sum(bool(advisory.get("fix_versions")) for advisory in advisories)
    print(f"{requirement.relative_to(ROOT)}: {len(dependencies)} dependencies, {len(advisories)} advisories, {fixed} with fixes", flush=True)
    if any(dependency.get("skip_reason") for dependency in dependencies):
        print("An unaudited dependency is not permitted.", file=sys.stderr)
        return 1
    if checked.returncode == 0:
        return 0
    if checked.returncode != 1 or not advisories or not allowed_unfixed(dependencies, records):
        print(checked.stdout, end="")
        return checked.returncode or 1
    # Empty exception files need only the single audit above. When exceptions exist,
    # first check the unfiltered report so --ignore-vuln can never hide a new fix.
    return subprocess.run(command + ignore_flags(records), check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exceptions", type=Path, default=ROOT / ".github/pip-audit-exceptions.toml")
    args = parser.parse_args()
    try:
        records = load_exceptions(args.exceptions)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"Invalid pip-audit exceptions: {error}", file=sys.stderr)
        return 1
    result = 0
    for requirement in REQUIREMENTS:
        result = audit(requirement, records) or result
    return result


if __name__ == "__main__":
    sys.exit(main())
