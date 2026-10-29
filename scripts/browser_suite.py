"""Run serial Chromium journeys with demo logins only and redacted console output."""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from scripts.sanitize_browser_artifacts import redact_text

DEMO_NAMES = ("DEMO_CUSTOMER_PASSWORD", "DEMO_SELLER_PASSWORD", "DEMO_OPERATOR_PASSWORD")


def browser_environment(env_file=None, environ=None):
    original = os.environ if environ is None else environ
    env = {
        name: value
        for name, value in original.items()
        if not name.startswith(("POSTGRES_", "MONGO_", "DJANGO_", "DATABASE_", "PG"))
    }
    if env_file:
        for line in Path(env_file).read_text().splitlines():
            name, separator, value = line.partition("=")
            if separator and name in DEMO_NAMES:
                env[name] = value
    if any(not env.get(name) for name in DEMO_NAMES):
        raise ValueError("All three demo passwords must be supplied through the environment or --env-file")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("test-results"))
    parser.add_argument("--force-browser-failure", action="store_true")
    parser.add_argument("--canary-only", action="store_true")
    args = parser.parse_args()
    address = urlsplit(args.base_url)
    if (
        address.scheme != "http"
        or address.hostname not in {"127.0.0.1", "localhost"}
        or address.username
        or address.password
    ):
        parser.error("Browser tests require an HTTP loopback URL without credentials")
    try:
        env = browser_environment(args.env_file)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--confcutdir=tests/browser",
        "-c",
        "tests/browser/pytest.ini",
        "tests/browser",
        "--base-url",
        args.base_url,
        "--browser",
        "chromium",
        "--tracing",
        "retain-on-failure",
        "--screenshot",
        "only-on-failure",
        "--output",
        str(args.output.resolve()),
    ]
    if args.force_browser_failure:
        command.append("--force-browser-failure")
    if args.canary_only:
        command += ["-k", "failure_artifact_canary"]
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with subprocess.Popen(
        command,
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    ) as child:
        for line in child.stdout:
            print(redact_text(line, [env[name] for name in DEMO_NAMES]), end="", flush=True)
        return child.wait()


if __name__ == "__main__":
    sys.exit(main())
