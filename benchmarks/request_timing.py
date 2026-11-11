"""Collect sequential HTTP/database timing evidence from an isolated app stack; standard library only."""

import argparse
import csv
import http.cookiejar
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener

from benchmarks.source import ZONE, sha256

ROOT = Path(__file__).resolve().parents[1]
METRICS = ("duration_ms", "db_pg_ms", "db_pg_queries", "db_mongo_ms", "db_mongo_commands")
REQUESTS_PER_PAGE = 20


class TimingError(ValueError):
    """A diagnostic written here, safe to display without HTTP/CLI data or credentials."""


def parse_request_logs(text, request_ids):
    """Ignore Compose prefixes and unrelated traffic; retain only the selected request fields."""
    result = {}
    for line in text.splitlines():
        start = line.find("{")
        if start < 0:
            continue
        try:
            row = json.loads(line[start:])
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("logger") != "mercer.request" or row.get("message") != "request":
            continue
        identity = row.get("request_id")
        if not isinstance(identity, str) or identity not in request_ids:
            continue
        if identity in result:
            raise TimingError("Duplicate request log ID")
        result[identity] = {
            key: row.get(key) for key in ("request_id", "method", "path", "status", "user_id", *METRICS)
        }
    return result


def join_requests(responses, logs):
    """Require an exact, successful response/log match before accepting any timing."""
    joined, seen = [], set()
    for response in responses:
        identity = response["request_id"]
        if identity in seen:
            raise TimingError("Duplicate response ID")
        seen.add(identity)
        if identity not in logs:
            raise TimingError("Missing request log")
        row = logs[identity]
        if (row["method"], row["path"], row["status"]) != ("GET", urlsplit(response["path"]).path, response["status"]):
            raise TimingError("Response and request log disagree")
        if response["page"] == "operator_dashboard" and not row.get("user_id"):
            raise TimingError("Dashboard request was not authenticated")
        for key in METRICS:
            value = row[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise TimingError("Missing or invalid request metric")
            if key in ("db_pg_queries", "db_mongo_commands") and not isinstance(value, int):
                raise TimingError("Database counts must be integers")
        database_ms = row["db_pg_ms"] + row["db_mongo_ms"]
        if row["duration_ms"] == 0 and database_ms:
            raise TimingError("Nonzero database time with zero request duration")
        joined.append(
            {
                **response,
                **{key: row[key] for key in METRICS},
                "db_share_percent": 100 * database_ms / row["duration_ms"] if row["duration_ms"] else 0,
            }
        )
    return joined


def aggregate(samples):
    if not samples:
        raise TimingError("No request samples")
    result = {"requests": len(samples)}
    for key in (*METRICS, "db_share_percent"):
        values = sorted(row[key] for row in samples)
        result[key + "_median"] = statistics.median(values)
        result[key + "_p95"] = values[math.ceil(len(values) * 0.95) - 1]
    for key in ("db_pg_queries", "db_mongo_commands"):
        result[key + "_total"] = sum(row[key] for row in samples)
    duration = sum(row["duration_ms"] for row in samples)
    database = sum(row["db_pg_ms"] + row["db_mongo_ms"] for row in samples)
    result["db_share_percent_total"] = 100 * database / duration if duration else 0
    return result


def command(arguments):
    completed = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)
    if completed.returncode:
        # CLI output can include environment details; never echo it on failures.
        raise RuntimeError("Required command failed")
    return completed.stdout.strip()


def compose(project, env_file):
    if project == "mercer" or not re.fullmatch(r"mercer-[a-z0-9-]+", project):
        raise TimingError("Use an explicitly isolated mercer-... app project")
    return ["docker", "compose", "--env-file", str(env_file.resolve()), "-p", project]


def ensure_no_benchmark():
    if command(["docker", "ps", "--filter", "label=com.docker.compose.service=bench-runner", "--format", "{{.ID}}"]):
        raise TimingError("Stop benchmark runners before collecting HTTP timings")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def fetch(opener, base_url, path, *, data=None):
    identity = "k2-" + uuid.uuid4().hex
    request = Request(base_url + path, data=data, headers={"X-Request-ID": identity})  # noqa: S310 - the local stack
    try:
        response = opener.open(request, timeout=120)
    except HTTPError as error:
        response = error
    with response:
        body = response.read().decode("utf-8")
        if response.headers.get("X-Request-ID") != identity:
            raise TimingError("Response did not preserve request ID")
        return (
            {
                "request_id": identity,
                "path": path,
                "status": response.status,
            },
            body,
            response.headers,
        )


def login_operator(opener, cookies, base_url, env_file):
    response, body, headers = fetch(opener, base_url, "/login/")
    if response["status"] != 200:
        raise TimingError("Login page unavailable")
    csrf = next((cookie.value for cookie in cookies if cookie.name == "csrftoken"), None)
    password = None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() == "DEMO_OPERATOR_PASSWORD":
            password = value.strip()
    if not csrf or not password or password.startswith("replace-"):
        raise TimingError("Demo operator login configuration is missing")
    # Matches seed_demo; neither credentials nor the in-memory cookie jar are retained.
    data = urlencode(
        {
            "username": "demo-operator",
            "password": password,
            "csrfmiddlewaretoken": csrf,
            "next": "/operator/dashboard/",
        }
    ).encode()
    response, body, headers = fetch(opener, base_url, "/login/", data=data)
    if response["status"] != 302 or headers.get("Location") != "/operator/dashboard/":
        raise TimingError("Demo operator login failed")


def pages_for_product(body, source):
    """Use the first visible product backed by source attributes, skipping showcase-only products."""
    product_ids = dict.fromkeys(int(value) for value in re.findall(r'href="/products/(\d+)/"', body))
    if not product_ids:
        raise TimingError("The product list has no visible product")
    with (source / "product_specs.ndjson").open(encoding="utf-8") as stream:
        specs = {
            row["_id"]: row for line in stream if (row := json.loads(line))["_id"] in product_ids and row["attributes"]
        }
    spec = next((specs[product_id] for product_id in product_ids if product_id in specs), None)
    if not spec:
        raise TimingError("No visible product matches source specifications with attributes")
    product_id = spec["_id"]
    with (source / "categories.csv").open(encoding="utf-8", newline="") as stream:
        category = next((row for row in csv.DictReader(stream) if int(row["id"]) == spec["category_id"]), None)
    if not category or not re.fullmatch(r"[a-z0-9_-]+", category["slug"]):
        raise TimingError("Visible product does not match a source category")
    key, value = sorted(spec["attributes"].items())[0]
    query = urlencode(
        {"category": spec["category_id"], "attr_" + key: str(value).lower() if isinstance(value, bool) else value}
    )
    return {
        "category": f"/products/category/{category['slug']}/",
        "product_list": "/products/",
        "faceted_search": "/products/?" + query,
        "product_detail": f"/products/{product_id}/",
        "operator_dashboard": "/operator/dashboard/",
    }


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def collect(args):
    address = urlsplit(args.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in {"localhost", "127.0.0.1"}
        or address.username
        or address.password
        or address.path not in ("", "/")
        or address.query
        or address.fragment
    ):
        raise TimingError("Use an HTTP loopback base URL without credentials or a path")
    base_url = args.base_url.rstrip("/")
    dc = compose(args.project, args.env_file)
    ports = command(dc + ["port", "web", "8000"])
    if (address.port or 80) not in {int(line.rsplit(":", 1)[1]) for line in ports.splitlines()}:
        raise TimingError("Base URL does not match this Compose project's web port")
    ensure_no_benchmark()
    started = datetime.now(timezone.utc).isoformat()
    anonymous = build_opener(NoRedirect(), HTTPCookieProcessor(http.cookiejar.CookieJar()))
    cookies = http.cookiejar.CookieJar()
    operator = build_opener(NoRedirect(), HTTPCookieProcessor(cookies))
    login_operator(operator, cookies, base_url, args.env_file)
    response, body, headers = fetch(anonymous, base_url, "/products/")
    if response["status"] != 200:
        raise TimingError("Product list unavailable")
    pages = pages_for_product(body, args.source)

    def request_page(name, path):
        opener = operator if name == "operator_dashboard" else anonymous
        row, body, headers = fetch(opener, base_url, path)
        if row["status"] != 200:
            raise TimingError("Unexpected page response")
        return {"page": name, **row}

    for name, path in pages.items():
        request_page(name, path)  # One untimed warm-up pass, excluded from joins and aggregates.
    responses = []
    for name, path in pages.items():
        ensure_no_benchmark()
        for _ in range(REQUESTS_PER_PAGE):
            responses.append(request_page(name, path))
    ensure_no_benchmark()
    identities = {row["request_id"] for row in responses}
    # Docker stamps log lines with the daemon's clock, which can sit seconds off the host's, so an exact --since can
    # drop the first requests; request IDs are unique, so a wider window loses nothing.
    log_window = (datetime.fromisoformat(started) - timedelta(minutes=2)).isoformat()
    for _attempt in range(20):
        logs = parse_request_logs(
            command(dc + ["logs", "--no-color", "--no-log-prefix", "--since", log_window, "web"]), identities
        )
        if identities <= logs.keys():
            break
        time.sleep(0.25)  # Allow Docker's log collection to catch up.
    joined = join_requests(responses, logs)
    commit = command(["git", "rev-parse", "HEAD"])
    dirty = bool(command(["git", "status", "--porcelain"]))
    docker_info = json.loads(command(["docker", "info", "--format", "{{json .}}"]))
    host = {
        "os": platform.platform(),
        "cpu": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "docker_version": json.loads(command(["docker", "version", "--format", "{{json .}}"])),
        "docker_vm": {key: docker_info[key] for key in ("NCPU", "MemTotal", "OperatingSystem", "KernelVersion")},
    }
    host["python"] = platform.python_version()
    if platform.system() == "Windows":
        host["hardware"] = json.loads(
            command(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "@{cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory} | ConvertTo-Json -Depth 4",
                ]
            )
        )
    stamp = datetime.now(ZONE).strftime("%Y-%m-%dT%H%M%S")
    output = ROOT / "benchmarks/results" / f"{stamp}_{commit[:8]}{'-dirty' if dirty else ''}_request-timing"
    output.mkdir(parents=True, exist_ok=False)
    for name, path in pages.items():
        samples = [row for row in joined if row["page"] == name]
        write_csv(output / f"{name}.csv", [{"page": name, "path": path, **aggregate(samples)}])
    write_csv(output / "requests.csv", joined)
    provenance = {
        "commit": commit + ("-dirty" if dirty else ""),
        "project": args.project,
        "host": host,
        "started_at": started,
        "finished_at": datetime.now(ZONE).isoformat(),
        "base_url": base_url,
        "source_manifest_sha256": sha256(args.source / "checksums.txt"),
        "pages": pages,
        "warmup_passes": 1,
        "requests_per_page": REQUESTS_PER_PAGE,
        "sequential": True,
        "p95_method": "nearest rank",
        "median_method": "arithmetic midpoint for even sample counts",
        "page_selection": "category, facet and detail use the first visible product with source attributes, in page order",
        "db_share": "100 * (db_pg_ms + db_mongo_ms) / duration_ms; zero when both are zero",
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"results": str(output), "requests": len(joined), "state": "complete"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--source", type=Path, default=ROOT / "data/derived/olist/clean")
    args = parser.parse_args()
    try:
        collect(args)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Exception messages, HTTP bodies and command output may contain secrets.
        reason = str(error) if isinstance(error, TimingError) else type(error).__name__
        print(f"request timing failed: {reason}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
