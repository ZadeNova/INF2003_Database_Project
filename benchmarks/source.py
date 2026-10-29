"""Checksum-verified source files and exact Extended JSON without a database driver."""

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# All retained dates are after 1982: Singapore is UTC+08 without DST. A fixed offset also lets the
# standard-library host tools run on Windows without a separate IANA tzdata package.
ZONE = timezone(timedelta(hours=8), "Asia/Singapore")
SEED = 82


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(source):
    source = Path(source)
    found = {}
    for line in (source / "checksums.txt").read_text().splitlines():
        digest, name = line.split("  ", 1)
        if Path(name).name != name or name in found or sha256(source / name) != digest:
            raise ValueError("Source checksum mismatch or unsafe manifest")
        found[name] = digest
    if len(found) != 16:
        raise ValueError("Expected the complete clean manifest")
    return {"manifest_sha256": sha256(source / "checksums.txt"), "source": str(source), "files": found}


def decode(value):
    if set(value) == {"$date"}:
        return datetime.fromisoformat(value["$date"].replace("Z", "+00:00"))
    if set(value) == {"$numberDecimal"}:
        return Decimal(value["$numberDecimal"])
    return value


def ndjson(source, name):
    with (Path(source) / f"{name}.ndjson").open(encoding="utf-8") as stream:
        for line in stream:
            yield json.loads(line, object_hook=decode)


def csv_rows(source, name):
    with (Path(source) / f"{name}.csv").open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream)


def instant(value):
    return None if value in (None, "\\N", "") else datetime.fromisoformat(value)


def local_day(value):
    return value.astimezone(ZONE).date()
