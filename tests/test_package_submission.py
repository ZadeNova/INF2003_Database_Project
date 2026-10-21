"""scripts/package_submission.py accepts the four deliverables and refuses what the brief would reject."""
import importlib.util
import io
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "package_submission.py"
spec = importlib.util.spec_from_file_location("package_submission", SCRIPT)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def source_zip(extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as source:
        source.writestr("README.md", "# Mercer\n")
        source.writestr("compose.yaml", "services: {}\n")
        source.writestr("src/manage.py", "")
        for name, text in (extra or {}).items():
            source.writestr(name, text)
    return buffer.getvalue()


def submission(tmp_path, **overrides):
    files = {"report.pdf": b"%PDF-1.7 dummy", "slides.pptx": b"PK\x03\x04 dummy", "demo.mp4": b"\0\0\0\x18ftypmp42",
             "source.zip": source_zip()}
    files.update(overrides)
    path = tmp_path / "submission.zip"
    with zipfile.ZipFile(path, "w") as outer:
        for name, data in files.items():
            if data is not None:
                outer.writestr(name, data)
    return path


def levels(results, level):
    return [message for found, message in results if found == level]


def test_a_dummy_zip_with_the_four_files_passes(tmp_path):
    results = package.check(submission(tmp_path))
    assert levels(results, "FAIL") == [] and levels(results, "WARN") == []
    assert package.main(["--check-only", str(submission(tmp_path))]) == 0


@pytest.mark.parametrize("missing, expected", [
    ("report.pdf", "final report"), ("slides.pptx", "presentation slides"),
    ("demo.mp4", "presentation video"), ("source.zip", "source code zip"),
])
def test_each_missing_deliverable_fails(tmp_path, missing, expected):
    path = submission(tmp_path, **{missing: None})
    (failure,) = levels(package.check(path), "FAIL")
    assert expected in failure
    assert package.main(["--check-only", str(path)]) == 1


def test_two_files_of_one_kind_are_ambiguous(tmp_path):
    (failure,) = levels(package.check(submission(tmp_path, **{"second.pdf": b"%PDF-1.7"})), "FAIL")
    assert "2 .pdf files" in failure


def test_old_powerpoint_extension_is_refused(tmp_path):
    results = package.check(submission(tmp_path, **{"slides.pptx": None, "slides.ppt": b"x"}))
    assert any(".ppt file" in message for message in levels(results, "FAIL"))


def test_env_files_and_keys_in_the_source_zip_fail(tmp_path):
    leaky = source_zip({".env": "A=b", "docs/key.txt": "-----BEGIN " + "PRIVATE KEY-----"})
    failures = levels(package.check(submission(tmp_path, **{"source.zip": leaky})), "FAIL")
    assert len(failures) == 2 and any(".env" in message for message in failures)
    example = package.check(submission(tmp_path, **{"source.zip": source_zip({".env.example": "A=b"})}))
    assert levels(example, "FAIL") == []


def test_content_that_does_not_match_the_extension_warns_without_failing(tmp_path):
    results = package.check(submission(tmp_path, **{"report.pdf": b"not a pdf", "demo.mp4": b""}))
    assert levels(results, "FAIL") == []
    assert len(levels(results, "WARN")) == 2


def test_something_that_is_not_a_zip_fails(tmp_path):
    path = tmp_path / "plain.zip"
    path.write_bytes(b"nothing")
    assert levels(package.check(path), "FAIL")
