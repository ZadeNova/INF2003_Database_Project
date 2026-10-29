"""init_env.py completes a .env without changing, printing or replacing what is already there."""

import json
import shlex
import stat
import string
from pathlib import Path

from tools.init_env import complete_env, fill

EXAMPLE = "# comment\nA=fixed\nB=replace-b\nC=replace-c\nDJANGO_SECRET_KEY=replace-django-secret\n"


def test_a_missing_env_is_created_private_with_generated_secrets(tmp_path):
    example, env = tmp_path / ".env.example", tmp_path / ".env"
    example.write_text(EXAMPLE)

    added = complete_env(env, example)

    values = dict(line.split("=", 1) for line in env.read_text().splitlines() if "=" in line)
    assert added == ["A", "B", "C", "DJANGO_SECRET_KEY"]
    assert values["A"] == "fixed" and len({values["B"], values["C"]}) == 2
    assert not any(value.startswith("replace-") for value in values.values())
    assert not any(value.startswith("-") for value in values.values())
    assert len(values["DJANGO_SECRET_KEY"]) >= 50
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_missing_keys_are_added_and_existing_values_are_untouched(tmp_path):
    example, env = tmp_path / ".env.example", tmp_path / ".env"
    example.write_text(EXAMPLE)
    env.write_text("A=mine\nB=-keep-this")  # existing credentials, even leading dashes, are preserved
    env.write_text(env.read_text() + "\nOLD=stays\n")

    added = complete_env(env, example)

    lines = env.read_text().splitlines()
    assert added == ["C", "DJANGO_SECRET_KEY"]
    assert lines[:3] == ["A=mine", "B=-keep-this", "OLD=stays"]
    assert lines[3].startswith("C=") and not lines[3].startswith("C=replace-")


def test_a_complete_env_is_left_alone(tmp_path):
    example, env = tmp_path / ".env.example", tmp_path / ".env"
    example.write_text(EXAMPLE)
    complete_env(env, example)
    before = env.read_text()

    assert complete_env(env, example) == []
    assert env.read_text() == before


def test_generated_secrets_have_no_leading_dash_and_keep_urlsafe_size_and_alphabet():
    alphabet = set(string.ascii_letters + string.digits + "-_")
    for key, length in (("MONGO_ROOT_PASSWORD", 43), ("DJANGO_SECRET_KEY", 86)):
        for _ in range(2048):
            secret = fill(f"{key}=replace-secret").split("=", 1)[1]
            assert not secret.startswith("-")
            assert len(secret) == length
            assert set(secret) <= alphabet


def test_mongo_startup_and_healthcheck_attach_credentials_to_options():
    root = Path(__file__).resolve().parents[1]
    source = root / "src" if (root / "src").is_dir() else root
    script = (source / "docker" / "mongo-start.sh").read_text()
    startup = shlex.split(script)
    assert startup.count("--username=$MONGO_ROOT_USER") == 2
    assert startup.count("--password=$MONGO_ROOT_PASSWORD") == 2
    assert not {"-u", "-p", "--username", "--password"}.intersection(startup)
    # shlex drops quotes; the raw text keeps a hand-set password with spaces as one argument
    assert script.count('--username="$MONGO_ROOT_USER"') == 2
    assert script.count('--password="$MONGO_ROOT_PASSWORD"') == 2

    healthcheck = next(
        line.strip().removeprefix("test: ")
        for line in (root / "compose.yaml").read_text().splitlines()
        if "test:" in line and "mongosh" in line
    )
    command_type, command = json.loads(healthcheck)
    assert command_type == "CMD-SHELL"
    arguments = shlex.split(command)
    assert "--username=$$MONGO_ROOT_USER" in arguments
    assert "--password=$$MONGO_ROOT_PASSWORD" in arguments
    assert not {"-u", "-p", "--username", "--password"}.intersection(arguments)
    assert '--username="$$MONGO_ROOT_USER"' in command
    assert '--password="$$MONGO_ROOT_PASSWORD"' in command
