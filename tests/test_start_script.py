"""The one-command start script (scripts/start.py): which steps run for an empty and for a loaded database.

Host test, no database needed:
    python -m pytest --noconftest -q -p no:cacheprovider tests/test_start_script.py
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "start.py"
spec = importlib.util.spec_from_file_location("start", SCRIPT)
start = importlib.util.module_from_spec(spec)
spec.loader.exec_module(start)


def names(plan):
    return [" ".join(step) for step in plan]


def test_an_empty_database_is_imported_then_seeded_then_smoke_tested():
    import_step, seed_step, smoke_step = names(start.steps(loaded=False))
    assert import_step.endswith("manage.py import_olist")
    assert seed_step.endswith("manage.py seed_demo")
    assert smoke_step.endswith("/app/scripts/smoke_olist.py")


def test_a_loaded_database_is_never_imported_again():
    seed_step, smoke_step = names(start.steps(loaded=True))
    assert "import_olist" not in seed_step + smoke_step
    assert seed_step.endswith("seed_demo") and smoke_step.endswith("smoke_olist.py")


def test_the_import_source_is_passed_through():
    source = "/app/tests/fixtures/olist/clean"
    assert names(start.steps(False, source))[0].endswith("import_olist --source " + source)


def test_a_dry_run_prints_every_command_and_runs_nothing():
    result = subprocess.run([sys.executable, str(SCRIPT), "--dry-run"], capture_output=True, text=True, check=True)
    assert "init_env.py" in result.stdout and "--wait" in result.stdout and "import_olist" in result.stdout
    assert result.stdout.count("seed_demo") == 2  # once for an empty database, once for a loaded one


def test_the_files_the_script_runs_exist():
    root = SCRIPT.parent.parent
    assert (root / "src" / "tools" / "init_env.py").is_file() and (root / "scripts" / "smoke_olist.py").is_file()
