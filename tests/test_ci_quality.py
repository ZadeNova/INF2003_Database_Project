"""Exercise the gates with real coverage data and exception files."""
import json
import subprocess
import sys
import zipfile
from datetime import date

import pytest

from scripts.audit_requirements import allowed_unfixed, ignore_flags, load_exceptions
from scripts.browser_suite import browser_environment
from scripts.coverage_suite import report_coverage
from scripts.sanitize_browser_artifacts import sanitize


def exception_file(tmp_path, *, added="2026-10-24", expires="2026-11-07", owner="Chee Long"):
    path = tmp_path / "exceptions.toml"
    path.write_text(
        '[[exceptions]]\nid = "GHSA-aaaa-bbbb-cccc"\nreason = "No upstream fix"\n'
        f'owner = "{owner}"\nadded = {added}\nexpires = {expires}\n', encoding="utf-8")
    return path


def test_valid_exception_has_accountability_and_becomes_ignore_flags(tmp_path):
    records = load_exceptions(exception_file(tmp_path), today=date(2026, 10, 24))
    assert ignore_flags(records) == ["--ignore-vuln", "GHSA-aaaa-bbbb-cccc"]
    assert records[0]["owner"] == "Chee Long"


@pytest.mark.parametrize("added,expires,owner", [
    ("2026-10-01", "2026-10-15", "Chee Long"),
    ("2026-10-24", "2026-11-08", "Chee Long"),
    ("2026-10-25", "2026-11-07", "Chee Long"),
    ("2026-10-24", "2026-11-07", " "),
])
def test_expired_long_future_or_unowned_exceptions_fail(tmp_path, added, expires, owner):
    with pytest.raises(ValueError):
        load_exceptions(exception_file(tmp_path, added=added, expires=expires, owner=owner), today=date(2026, 10, 24))


def test_missing_exception_metadata_fails(tmp_path):
    path = exception_file(tmp_path)
    path.write_text(path.read_text().replace('reason = "No upstream fix"\n', ""))
    with pytest.raises(ValueError, match="exactly"):
        load_exceptions(path, today=date(2026, 10, 24))


def test_exception_never_hides_a_fix_and_unlisted_advisories_fail(tmp_path):
    records = load_exceptions(exception_file(tmp_path), today=date(2026, 10, 24))
    advisory = {"id": "CVE-2026-12345", "aliases": [records[0]["id"]], "fix_versions": []}
    dependencies = [{"name": "example", "vulns": [advisory]}]
    assert allowed_unfixed(dependencies, records)
    advisory["fix_versions"] = ["2.0"]
    assert not allowed_unfixed(dependencies, records)
    advisory["fix_versions"] = []
    assert not allowed_unfixed(dependencies, [])
    assert not allowed_unfixed([{"name": "example", "skip_reason": "Unknown version"}], records)


@pytest.mark.parametrize("all_lines", [True, False])
def test_real_coverage_gates_lines_and_reports_branches(tmp_path, all_lines):
    source = tmp_path / "source"
    source.mkdir()
    script = source / "exercise.py"
    if all_lines:
        body = "def choose(value):\n" + "    if value:\n        value += 1\n" * 5 + "    return value\nchoose(1)\n"
    else:
        body = "def unused(value):\n" + "    value += 1\n" * 20 + "    return value\nprint('executed')\n"
    script.write_text(body, encoding="utf-8")
    config = tmp_path / "pyproject.toml"
    config.write_text(
        f'[tool.coverage.run]\nsource = [{json.dumps(str(source))}]\nbranch = true\n'
        '[tool.coverage.report]\nfail_under = 80\nprecision = 2\ninclude_namespace_packages = true\n', encoding="utf-8")
    data = tmp_path / ".coverage"
    subprocess.run([
        sys.executable, "-m", "coverage", "run", f"--rcfile={config}", f"--data-file={data}", str(script),
    ], check=True)
    output = tmp_path / "reports"
    result = report_coverage(data, config, output)
    totals = json.loads((output / "coverage.json").read_text())["totals"]
    if all_lines:
        assert totals["covered_lines"] == totals["num_statements"]
        assert totals["percent_covered"] < 80  # Combined line/branch coverage must not be the gate.
        assert result == 0
    else:
        assert totals["covered_lines"] / totals["num_statements"] < 0.8
        assert result != 0
    assert (output / "coverage.xml").is_file() and (output / "htmlcov/index.html").is_file()


def test_retained_trace_redacts_passwords_and_cookies_and_preserves_images(tmp_path):
    secret = "OnlyForTheArtifactRegression_123"
    trace = tmp_path / "trace.zip"
    record = {"params": {"value": secret}, "headers": [
        {"name": "Cookie", "value": "sessionid=private-cookie"},
        {"name": "Authorization", "value": "private-bearer"},
    ]}
    with zipfile.ZipFile(trace, "w") as archive:
        archive.writestr("trace.trace", json.dumps(record) + "\n")
        archive.writestr("resources/snapshot.html", f'<input type="password" value="{secret}">')
        archive.writestr("resources/screen.png", b"\x89PNG\r\n\x1a\n\x00\xff")
    assert sanitize(tmp_path, [secret]) == 1
    with zipfile.ZipFile(trace) as archive:
        row = json.loads(archive.read("trace.trace"))
        assert row["params"]["value"] == "<redacted>"
        assert all(header["value"] == "<redacted>" for header in row["headers"])
        assert secret.encode() not in archive.read("resources/snapshot.html")
        assert archive.read("resources/screen.png") == b"\x89PNG\r\n\x1a\n\x00\xff"


def test_browser_process_receives_demo_logins_without_owner_or_database_credentials(tmp_path):
    path = tmp_path / "browser.env"
    path.write_text("POSTGRES_OWNER_PASSWORD=private-owner\nDEMO_CUSTOMER_PASSWORD=customer-login\n"
                    "DEMO_SELLER_PASSWORD=seller-login\nDEMO_OPERATOR_PASSWORD=operator-login\n")
    env = browser_environment(path, {"PATH": "tools", "POSTGRES_PASSWORD": "private-owner", "MONGO_APP_PASSWORD": "private-mongo",
                                     "DATABASE_URL": "private-dsn", "DJANGO_SECRET_KEY": "private-key", "PGPASSWORD": "private-pg"})
    assert env["DEMO_CUSTOMER_PASSWORD"] == "customer-login" and env["PATH"] == "tools"
    assert not any(name.startswith(("POSTGRES_", "MONGO_", "DATABASE_", "DJANGO_", "PG")) for name in env)
    assert "private-owner" not in env.values()
