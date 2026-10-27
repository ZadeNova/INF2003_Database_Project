"""Generate CSV tables and standalone SVG figures from retained evidence; standard library only."""
import argparse
import csv
import gzip
import html
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def table(path, rows):
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def svg(path, title, bars, unit):
    width, height = 1050, 100 + len(bars) * 36
    scale = max((float(value) for label, value, status in bars if value is not None), default=1) or 1
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="#fff"/>', '<g font-family="Arial,sans-serif" fill="#152536">',
             f'<text x="20" y="30" font-size="18">{html.escape(title)}</text>']
    for index, (label, value, status) in enumerate(bars):
        y = 60 + index * 36
        parts.append(f'<text x="20" y="{y+17}" font-size="12">{html.escape(label)}</text>')
        if value is not None and status == "passed":
            length = float(value) / scale * 420
            parts.append(f'<rect x="475" y="{y}" width="{length:.2f}" height="23" fill="#357b89"/>')
            text = f"{float(value):.6g} {unit}"
        else:
            length, text = 0, "FAILED" if status == "failed" else "correctness only"
        parts.append(f'<text x="{485+length:.2f}" y="{y+17}" font-size="12">{html.escape(text)}</text>')
    parts.append('</g></svg>')
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def noise(rows):
    groups = defaultdict(list)
    baseline = {row["clients"]: row for row in rows if row["output"] == "baseline" and row["p50_ms"] and row["status"] == "passed"}
    for row in rows:
        if row["output"].startswith(("B1_", "B4_")) and row["p50_ms"] and row["status"] == "passed":
            groups[row["output"], row["clients"]].append(row)
    result = []
    for (output, clients), group in sorted(groups.items()):
        if len(group) < 2 or clients not in baseline:
            continue
        fast, slow = min(group, key=lambda r: float(r["p50_ms"])), max(group, key=lambda r: float(r["p50_ms"]))
        gap = float(slow["p50_ms"]) - float(fast["p50_ms"])
        base = baseline[clients]
        baseline_noise = float(base["p95_ms"]) - float(base["p50_ms"])
        fast_range = float(fast["p50_ms_max"]) - float(fast["p50_ms_min"])
        threshold = max(baseline_noise, fast_range)
        result.append({"output": output, "clients": clients, "fastest": fast["engine"] + "/" + fast["variant"], "slowest": slow["engine"] + "/" + slow["variant"],
                       "fastest_p50_ms": fast["p50_ms"], "slowest_p50_ms": slow["p50_ms"], "gap_ms": gap,
                       "baseline_p95_minus_p50_ms": baseline_noise, "fastest_p50_range_ms": fast_range, "threshold_ms": threshold, "inside_noise": "yes" if gap <= threshold else "no"})
    return result


def report(directory):
    directory = Path(directory)
    destination = directory / "report"
    destination.mkdir(exist_ok=True)
    rows = read_csv(directory / "summary.csv")
    outputs = defaultdict(list)
    for row in rows:
        outputs[row["output"]].append(row)
    ratios = []
    for output, group in outputs.items():
        rendered = []
        for row in group:
            comparable = [r for r in group if r["clients"] == row["clients"] and r["p50_ms"] and r["status"] == "passed" and r["variant"] != "restore"]
            fastest = min((float(r["p50_ms"]) for r in comparable), default=0)
            before = next((r for r in comparable if r["variant"] == "before"), None)
            pg_live = next((r for r in comparable if r["engine"] == "postgres" and r["variant"] == "live"), None)
            value = float(row["p50_ms"]) if row["p50_ms"] and row["status"] == "passed" else None
            ratio = (float(before["p50_ms"]) / value if before and value else float(pg_live["p50_ms"]) / value if pg_live and value else value / fastest if value and fastest else None)
            enriched = {**row, "ratio": ratio, "ratio_basis": "before/variant" if before else "postgres_live/variant" if pg_live else "variant/fastest"}
            rendered.append(enriched)
            ratios.append(enriched)
        table(destination / (output + ".csv"), rendered)
        svg(destination / (output + ".svg"), output + " ratios (see CSV for ranges and absolute ms)",
            [(r["engine"] + "/" + r["variant"] + " c=" + r["clients"], r["ratio"], r["status"]) for r in rendered], "x")
    table(destination / "ratios.csv", ratios)
    table(destination / "amendment-j.csv", noise(rows))
    raw = directory / "raw.jsonl"
    opener = raw.open if raw.exists() else lambda **kwargs: gzip.open(str(raw) + ".gz", "rt", **kwargs)
    checks, demonstrations, races = [], [], []
    with opener(encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line)
            if record["kind"] != "check":
                continue
            checks.append({key: record.get(key) for key in ("output", "engine", "variant", "clients", "run", "phase", "status", "accepted")})
            if record["output"] == "B6":
                demonstrations.append({"engine": record["engine"], "strategy": record["variant"], "status": record["status"], **record["evidence"]})
            if record["output"] == "B3":
                evidence = record.get("evidence") or {}
                races.append({**{key: record.get(key) for key in ("engine", "variant", "clients", "run", "phase", "status", "retries")},
                              **{key: evidence.get(key) for key in ("successes", "refusals", "stock", "orders", "initial_verified", "restored")}})
    table(destination / "checks.csv", checks)
    if races:
        table(destination / "B3-states.csv", races)
        svg(destination / "B3-outcomes.svg", "B3 accepted and refused buyers (all checks must pass)",
            [(r["engine"] + "/" + r["variant"] + " c=" + str(r["clients"]) + "/" + key, r.get(key), r["status"]) for r in races for key in ("successes", "refusals")], "buyers")
    if demonstrations:
        table(destination / "B6-states.csv", demonstrations)
        svg(destination / "B6.svg", "B6 expected and observed final stock", [(r["engine"] + "/" + r["strategy"], r.get("observed_stock"), r["status"]) for r in demonstrations], "units")
    if (directory / "storage.csv").exists():
        storage = read_csv(directory / "storage.csv")
        table(destination / "B5.csv", storage)
        svg(destination / "B5.svg", "B5 physical data and indexes (different representations; see model contract)",
            [(row["engine"] + "/" + row["representation"] + "/" + kind, float(row[kind + "_bytes"]), "passed") for row in storage for kind in ("data", "index")], "bytes")
    print(json.dumps({"report": str(destination), "outputs": sorted(outputs), "amendment_j": noise(rows)}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    report(parser.parse_args().directory)


if __name__ == "__main__":
    main()
