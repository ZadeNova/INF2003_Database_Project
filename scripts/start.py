"""One command from a fresh clone to a running, loaded application (backlog item #42).

    python scripts/start.py

It writes `.env` if it is missing, builds and starts the stack (the `web` service waits for the migrations), loads the
Olist data and the demo accounts when the database is still empty, and smoke-tests the running site. Run again at any time:
a loaded database is never imported twice, and every step it repeats is safe to repeat. It prints no secret.

Standard library only, so it runs on the same Python 3.8 or later as `src/tools/init_env.py`.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_ENV = ROOT / "src" / "tools" / "init_env.py"
LOADED_PROBE = "from catalogue.models import Product; print('LOADED=%d' % Product.objects.exists())"


def manage(*arguments):
    return ["run", "--rm", "migrate", "python", "manage.py", *arguments]


def steps(loaded, source=None):
    """The ordered `docker compose` arguments after the stack is up: import only an empty database."""
    plan = []
    if not loaded:
        plan.append(manage("import_olist", *(["--source", source] if source else [])))
    plan.append(manage("seed_demo"))
    plan.append(["run", "--rm", "migrate", "python", "/app/scripts/smoke_olist.py"])
    return plan


def compose(*arguments, capture=False):
    command = ["docker", "compose", *arguments]
    return subprocess.run(
        command, cwd=ROOT, check=True, universal_newlines=True, stdout=subprocess.PIPE if capture else None
    )


def app_port():
    """APP_PORT from the environment, else from .env (the only key read), else the default."""
    if os.environ.get("APP_PORT", "").isdigit():
        return os.environ["APP_PORT"]
    try:
        match = re.search(r"^APP_PORT=(\d+)\s*$", (ROOT / ".env").read_text(), re.MULTILINE)
    except OSError:
        match = None
    return match.group(1) if match else "8000"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", help="import_olist source inside the container (default: the full clean data)")
    parser.add_argument("--dry-run", action="store_true", help="print the commands that would run, run nothing")
    args = parser.parse_args(argv)

    if args.dry_run:
        print("python src/tools/init_env.py")
        print("docker compose up --build --detach --wait --wait-timeout 600 web")
        for loaded in (False, True):
            print("# database %s:" % ("loaded" if loaded else "empty"))
            for step in steps(loaded, args.source):
                print("docker compose " + " ".join(step))
        return 0

    try:
        subprocess.run(["docker", "info"], cwd=ROOT, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        print("Docker is not running. Start Docker Desktop, wait until it reports the engine is running, and retry.")
        return 1
    subprocess.run([sys.executable, str(INIT_ENV)], cwd=ROOT, check=True)
    print("Building and starting the stack (the first start takes a few minutes)...")
    compose("up", "--build", "--detach", "--wait", "--wait-timeout", "600", "web")
    probe = compose(*manage("shell", "-c", LOADED_PROBE), capture=True).stdout
    loaded = "LOADED=1" in probe
    print("The database already holds the data." if loaded else "Loading the Olist data (under ten minutes)...")
    for step in steps(loaded, args.source):
        compose(*step)
    print("\nReady: http://127.0.0.1:%s/  (demo logins: README, section 'Demo logins')" % app_port())
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        print("A step failed (exit code %s): %s" % (error.returncode, " ".join(map(str, error.cmd[:6]))))
        sys.exit(error.returncode or 1)
