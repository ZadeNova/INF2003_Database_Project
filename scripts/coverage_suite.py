"""Run the Django suite once; retain branch reports and gate only line coverage."""
import argparse
import subprocess
import sys
from pathlib import Path

from coverage import Coverage, CoverageData


def report_coverage(data_file, config_file, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    measured = Coverage(config_file=str(config_file), data_file=str(data_file))
    measured.load()
    measured.xml_report(outfile=str(output / "coverage.xml"))
    measured.html_report(directory=str(output / "htmlcov"))
    measured.json_report(outfile=str(output / "coverage.json"))
    print("Branch coverage report (informational):", flush=True)
    measured.report()

    # The report CLI gates a combined percentage when arc data is present. Preserve the
    # original data/artifacts and derive a line-only data file with the public API.
    original = measured.get_data()
    lines_file = output / ".coverage-lines"
    lines = CoverageData(basename=str(lines_file))
    lines.erase()
    lines.add_lines({name: original.lines(name) or [] for name in original.measured_files()})
    lines.write()
    print("Line coverage gate (at least 80%):", flush=True)
    return subprocess.run([
        sys.executable, "-m", "coverage", "report", f"--rcfile={config_file}",
        f"--data-file={lines_file}", "--fail-under=80",
    ], check=False).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[1] / "pyproject.toml")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    data_file = args.output / ".coverage"
    result = subprocess.run([
        sys.executable, "-m", "coverage", "run", f"--rcfile={args.config}",
        f"--data-file={data_file}", "-m", "pytest", "-q", "-rs", "-p", "no:cacheprovider", "/app/tests",
    ], check=False).returncode
    if not data_file.is_file():
        return result or 1
    gate = report_coverage(data_file, args.config, args.output)
    return result or gate


if __name__ == "__main__":
    sys.exit(main())
