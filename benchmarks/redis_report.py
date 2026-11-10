"""Turn the samples of a Redis experiment into tables and a chart; nothing in the report is typed by hand.

    python -m benchmarks.redis_report benchmarks/results/<redis-experiment-folder>

Reads samples.csv and writes, beside it: summary.csv (per page and condition: median, range, tail percentiles only when
the sample is large enough), ratios.csv (the per-round paired ratios, the main evidence), verdicts.csv (what may be
claimed given the noise floor of the control pages), bootstrap.csv (labelled optimistic), refusals.csv (every sample the
gates refused, with the reason) and chart.svg.
"""

import argparse
import csv
import json
from pathlib import Path

from benchmarks.redis_stats import REQUEST_FIELDS, analyse
from benchmarks.report import svg, table

INTEGER_FIELDS = ("round", "status", "db_pg_queries", "db_mongo_commands", "redis_commands")
FLOAT_FIELDS = ("client_ms", "duration_ms", "db_pg_ms", "db_mongo_ms", "redis_ms")


def read_samples(directory):
    samples = []
    with (Path(directory) / "samples.csv").open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            for field in INTEGER_FIELDS:
                row[field] = int(float(row[field]))
            for field in FLOAT_FIELDS:
                row[field] = float(row[field])
            samples.append(row)
    return samples


def write_reports(directory):
    directory = Path(directory)
    analysis = analyse(read_samples(directory))
    table(directory / "summary.csv", analysis["cells"])
    table(directory / "ratios.csv", analysis["ratios"])
    table(directory / "verdicts.csv", analysis["verdicts"])
    table(directory / "bootstrap.csv", analysis["bootstrap"])
    table(directory / "refusals.csv", analysis["refusals"])
    bars = [(f"{c['page']} / {c['condition']}", c["p50_ms"], "passed") for c in analysis["cells"]]
    svg(directory / "chart.svg", "Median server time per request by page and cache condition", bars, "ms")
    (directory / "analysis.json").write_text(
        json.dumps(
            {
                "noise_floor": analysis["noise_floor"],
                "accepted": analysis["accepted"],
                "refused": analysis["refused"],
                "request_fields": list(REQUEST_FIELDS),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return analysis


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", type=Path)
    analysis = write_reports(parser.parse_args().directory)
    print(json.dumps({"accepted": analysis["accepted"], "refused": analysis["refused"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
