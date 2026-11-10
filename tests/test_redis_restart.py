"""The Redis start-up script survives a stop, a start and a restart (Docker keeps /tmp between them).

An earlier version wrote the ACL file as root into a sticky /tmp, and root may not overwrite a file owned by another user
there, so the container exited the second time it started. The suite never restarts the Compose service, so this test
starts its own throwaway container from the pinned image and the real script. It needs Docker on the host; it runs in
the CI host job and is skipped inside the test container.

    python -m pytest --noconftest tests/test_redis_restart.py
"""

import re
import secrets
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "src" / "docker" / "redis-start.sh"
COMPOSE = ROOT / "compose.yaml"
needs_docker = pytest.mark.skipif(
    shutil.which("docker") is None or not SCRIPT.exists() or not COMPOSE.exists(),
    reason="needs Docker and the repository checkout",
)


def docker(*arguments, check=True):
    return subprocess.run(["docker", *arguments], capture_output=True, text=True, timeout=180, check=check)


def pinned_image():
    return re.search(r"image: (redis:\S+@sha256:[0-9a-f]{64})", COMPOSE.read_text(encoding="utf-8")).group(1)


def cli(name, password, *command):
    return docker(
        "exec",
        "-e",
        f"REDISCLI_AUTH={password}",
        name,
        "redis-cli",
        "--user",
        "mercer",
        "--no-auth-warning",
        *command,
        check=False,
    )


def wait_until_ready(name, password):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if "PONG" in cli(name, password, "ping").stdout:
            return
        time.sleep(0.5)
    raise AssertionError("Redis did not become ready: " + docker("logs", name, check=False).stdout[-500:])


@needs_docker
def test_the_start_up_script_works_again_after_stop_start_and_restart():
    name = f"mercer-redis-restart-{uuid.uuid4().hex[:8]}"
    password = secrets.token_urlsafe(24)
    docker(
        "run",
        "--detach",
        "--name",
        name,
        "--env",
        f"REDIS_PASSWORD={password}",
        "--entrypoint",
        "sh",
        "--mount",
        f"type=bind,source={SCRIPT},target=/docker/redis-start.sh,readonly",
        pinned_image(),
        "/docker/redis-start.sh",
    )
    try:
        wait_until_ready(name, password)
        anonymous = docker("exec", name, "redis-cli", "ping", check=False)
        assert "PONG" not in anonymous.stdout  # the default user is off
        for actions in (["restart"], ["stop", "start"], ["restart"]):  # ready only after the last action of each step
            for action in actions:
                docker(action, name)
            wait_until_ready(name, password)
        assert cli(name, password, "set", "mercer:v1:restart-check", "x", "EX", "30").stdout.strip() == "OK"
        assert "NOPERM" in cli(name, password, "flushall").stdout
    finally:
        docker("rm", "--force", name, check=False)
