"""init_env.py completes a .env without changing, printing or replacing what is already there."""
import stat

from tools.init_env import complete_env

EXAMPLE = "# comment\nA=fixed\nB=replace-b\nC=replace-c\nDJANGO_SECRET_KEY=replace-django-secret\n"


def test_a_missing_env_is_created_private_with_generated_secrets(tmp_path):
    example, env = tmp_path / ".env.example", tmp_path / ".env"
    example.write_text(EXAMPLE)

    added = complete_env(env, example)

    values = dict(line.split("=", 1) for line in env.read_text().splitlines() if "=" in line)
    assert added == ["A", "B", "C", "DJANGO_SECRET_KEY"]
    assert values["A"] == "fixed" and len({values["B"], values["C"]}) == 2
    assert not any(value.startswith("replace-") for value in values.values())
    assert len(values["DJANGO_SECRET_KEY"]) >= 50
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_missing_keys_are_added_and_existing_values_are_untouched(tmp_path):
    example, env = tmp_path / ".env.example", tmp_path / ".env"
    example.write_text(EXAMPLE)
    env.write_text("A=mine\nB=keep-this")      # no trailing newline, and an old key the example lacks
    env.write_text(env.read_text() + "\nOLD=stays\n")

    added = complete_env(env, example)

    lines = env.read_text().splitlines()
    assert added == ["C", "DJANGO_SECRET_KEY"]
    assert lines[:3] == ["A=mine", "B=keep-this", "OLD=stays"]
    assert lines[3].startswith("C=") and not lines[3].startswith("C=replace-")


def test_a_complete_env_is_left_alone(tmp_path):
    example, env = tmp_path / ".env.example", tmp_path / ".env"
    example.write_text(EXAMPLE)
    complete_env(env, example)
    before = env.read_text()

    assert complete_env(env, example) == []
    assert env.read_text() == before
