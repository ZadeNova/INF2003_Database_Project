"""Host-side standard-library runner: explicit isolated project, provenance and Docker resource sampling."""

import argparse
import gzip
import json
import os
import platform
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from benchmarks.resources import annotate
from benchmarks.source import ZONE

ROOT = Path(__file__).resolve().parents[1]


def command(arguments, *, capture=True, check=True):
    result = subprocess.run(arguments, cwd=ROOT, text=True, capture_output=capture, check=False)
    if check and result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {arguments[:3]}")
    return result.stdout.strip() if capture else result.returncode


PINNED_OVERRIDE = "benchmarks/compose.pinned.yaml"


def compose(project, pinned=False):
    if project == "mercer" or not re.fullmatch(r"mercer-(?:bench|ci-bench)[a-z0-9-]*", project):
        raise ValueError("Use an explicitly isolated mercer-bench... project, never mercer")
    files = ["-f", "compose.yaml", "-f", PINNED_OVERRIDE] if pinned else []
    return ["docker", "compose", "-p", project, "--profile", "bench", *files]


def container_states(project):
    """What Docker says about each container of the project: out-of-memory kills, restarts and whether it is running."""
    states = {}
    for identity in command(compose(project) + ["ps", "-a", "-q"]).splitlines():
        value = json.loads(
            command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"name":{{json .Name}},"state":{{json .State}},"restarts":{{json .RestartCount}}}',
                    identity,
                ]
            )
        )
        states[value["name"].lstrip("/")] = {
            "oom_killed": bool(value["state"].get("OOMKilled")),
            "restarts": value["restarts"],
            "status": value["state"].get("Status"),
            "exit_code": value["state"].get("ExitCode"),
        }
    return states


def container_events(before, after):
    """Out-of-memory kills (exit code 137 wasted a whole earlier run), restarts and stopped containers during a run.

    The load-client container is created for the run and removed by it, so only containers present before are compared."""
    events = []
    for name, start in sorted(before.items()):
        end = after.get(name)
        if end is None:
            events.append(f"{name} disappeared")
            continue
        if end["oom_killed"] and not start["oom_killed"]:
            events.append(f"{name} was killed for exceeding its memory limit")
        if end["restarts"] > start["restarts"]:
            events.append(f"{name} restarted {end['restarts'] - start['restarts']} time(s)")
        if start["status"] == "running" and end["status"] != "running":
            events.append(f"{name} is {end['status']}")
    return events


def collect_host(project, pinned=False, notes=None):
    info = json.loads(command(["docker", "info", "--format", "{{json .}}"]))
    version = json.loads(command(["docker", "version", "--format", "{{json .}}"]))
    identifiers = command(compose(project, pinned) + ["ps", "-q"]).splitlines()
    containers = []
    for identity in identifiers:
        value = json.loads(
            command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"name":{{json .Name}},"image":{{json .Config.Image}},"limits":{{json .HostConfig}}}',
                    identity,
                ]
            )
        )
        containers.append(
            {
                "name": value["name"],
                "image": value["image"],
                "limits": {
                    k: value["limits"][k] for k in ("NanoCpus", "Memory", "MemorySwap", "ShmSize", "CpusetCpus")
                },
                "image_digests": json.loads(
                    command(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", value["image"]])
                ),
            }
        )
    if platform.system() == "Windows":
        hardware = json.loads(
            command(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "@{cpu=(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors);ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory} | ConvertTo-Json -Depth 4",
                ]
            )
        )
    else:
        hardware = {"cpu": platform.processor(), "cores": os.cpu_count(), "ram": info["MemTotal"]}
        if Path("/proc/cpuinfo").exists():
            hardware["cpu"] = next(
                (
                    line.partition(":")[2].strip()
                    for line in Path("/proc/cpuinfo").read_text().splitlines()
                    if line.startswith("model name")
                ),
                hardware["cpu"],
            )
        if Path("/proc/meminfo").exists():
            hardware["ram"] = int(Path("/proc/meminfo").read_text().splitlines()[0].split()[1]) * 1024
    # Executes in the isolated MongoDB container. Environment variables remain inside mongosh.
    script = (
        "const a=db.getSiblingDB('admin'); print(JSON.stringify({options:a.runCommand({getCmdLineOpts:1}).parsed,"
        "cache_bytes:a.serverStatus().wiredTiger.cache['maximum bytes configured'],"
        "majority_journal_default:rs.conf().writeConcernMajorityJournalDefault,default_write_concern:a.runCommand({getDefaultRWConcern:1})}));"
    )
    mongo = json.loads(
        command(
            compose(project)
            + [
                "exec",
                "-T",
                "bench-mongo",
                "bash",
                "-c",
                'mongosh --quiet --norc --username="$MONGO_ROOT_USER" --password="$MONGO_ROOT_PASSWORD" --authenticationDatabase admin --eval "$1"',
                "bench-readback",
                script,
            ]
        )
    )
    return {
        "project": project,
        "os": platform.platform(),
        "hardware": hardware,
        "docker_version": version,
        "docker_vm": {key: info[key] for key in ("NCPU", "MemTotal", "OperatingSystem", "KernelVersion")}
        | {"SwapTotal": info.get("SwapTotal")},
        "pinned": pinned,
        "machine_notes": notes or {},  # recorded by hand: power plan, sleep, updates, storage type (amendment l1)
        "containers": containers,
        "runner_limits": {"cpus": 2, "memory_bytes": 2 * 1024**3, "memory_swap_bytes": 2 * 1024**3},
        "mongo_server_readback": mongo,
        "vm_meets_plan": info["NCPU"] >= 6 and info["MemTotal"] >= 8 * 1024**3,
    }


def sample_stats(project, destination, stop):
    """A streaming docker stats process; each JSON record is timestamped as received (~one second)."""
    process = subprocess.Popen(
        ["docker", "stats", "--format", "{{json .}}"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    def finish():
        stop.wait()
        process.terminate()

    watcher = threading.Thread(target=finish, daemon=True)
    watcher.start()
    last_second = {}
    with destination.open("w", encoding="utf-8") as output:
        for line in process.stdout:
            try:
                # Docker may clear an interactive terminal before its first JSON record.
                clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line)
                record = json.loads(clean[clean.find("{") :])
                if not record.get("Name", "").startswith(project + "-"):
                    continue
                now = time.time_ns()
                second = now // 1_000_000_000
                if last_second.get(record["Name"]) == second:
                    continue
                last_second[record["Name"]] = second
                output.write(json.dumps({"time_ns": now, **record}, sort_keys=True) + "\n")
                output.flush()
            except (ValueError, TypeError):
                continue
    process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--source", default="/app/data/derived/olist/clean")
    parser.add_argument("--golden", choices=("full", "fixture"), default="full")
    parser.add_argument("--mode", choices=("correctness", "measure"), required=True)
    parser.add_argument("--only", default="baseline,B1,B2,B3,B4,B5,B6")
    parser.add_argument("--operations-per-client", type=int, default=5)
    parser.add_argument("--b2-operations-per-client", type=int, default=20)
    parser.add_argument("--label", default="correctness")
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--require-clean", action="store_true")
    parser.add_argument(
        "--pin", action="store_true", help="the project was started with benchmarks/compose.pinned.yaml"
    )
    parser.add_argument(
        "--note", action="append", default=[], metavar="KEY=VALUE", help="a machine fact for the provenance, repeatable"
    )
    args = parser.parse_args()
    notes = {}
    for item in args.note:
        key, separator, value = item.partition("=")
        if not separator or not key:
            parser.error("--note takes KEY=VALUE")
        notes[key] = value
    if min(args.operations_per_client, args.b2_operations_per_client) < 5:
        parser.error("Use at least five operations per client for default and B2 workloads")
    dc = compose(args.project, args.pin)
    if not re.fullmatch(r"[a-z0-9-]+", args.label):
        parser.error("Label must be lowercase letters, digits and hyphens")
    commit = command(["git", "rev-parse", "HEAD"])
    dirty = bool(command(["git", "status", "--porcelain"]))
    if (args.final or args.require_clean) and dirty:
        parser.error("This run requires a clean committed tree")
    host = collect_host(args.project, args.pin, notes)
    if args.pin and not all(c["limits"].get("CpusetCpus") for c in host["containers"]):
        parser.error("--pin needs the project started with benchmarks/compose.pinned.yaml (see the file)")
    states_before = container_states(args.project)
    host.update(
        commit=commit + ("-dirty" if dirty else ""), final=args.final, started_at=datetime.now(ZONE).isoformat()
    )
    stamp = datetime.now(ZONE).strftime("%Y-%m-%dT%H%M%S")
    name = f"{stamp}_{commit[:8]}{'-dirty' if dirty else ''}_{args.label}"
    output = ROOT / "benchmarks" / "results" / name
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(
        0o777
    )  # The Linux runner UID differs from the host user's UID; only this evidence directory is shared.
    (output / "host.json").write_text(json.dumps(host, indent=2, sort_keys=True) + "\n", newline="\n")
    print(json.dumps({"results": str(output), "commit": host["commit"], "state": "started"}), flush=True)
    if not host["vm_meets_plan"]:
        print(
            f"VM below plan minimum: {host['docker_vm']['NCPU']} CPUs, {host['docker_vm']['MemTotal']} bytes; trial/correctness evidence only.",
            flush=True,
        )
        if args.final:
            parser.error("Final measurements require at least six VM CPUs and eight GiB")
    stop = threading.Event()
    sampler = threading.Thread(target=sample_stats, args=(args.project, output / "stats.jsonl", stop), daemon=True)
    sampler.start()
    started = time.perf_counter()
    try:
        arguments = dc + [
            "run",
            "--rm",
            "--name",
            args.project + "-load-client",
            "bench-runner",
            "python",
            "-m",
            "benchmarks.harness",
            "--source",
            args.source,
            "--golden",
            "/app/benchmarks/golden/" + args.golden,
            "--mode",
            args.mode,
            "--only",
            args.only,
            "--operations-per-client",
            str(args.operations_per_client),
            "--b2-operations-per-client",
            str(args.b2_operations_per_client),
            "--label",
            args.label,
            "--output",
            "/app/benchmarks/results/" + name,
        ]
        # Tee exact printed output into a file without swallowing live progress.
        process = subprocess.Popen(arguments, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        with (output / "console.txt").open("w", encoding="utf-8", newline="\n") as stream:
            for line in process.stdout:
                print(line, end="", flush=True)
                stream.write(line)
                if args.project + "-load-client Created" in line:
                    actual = json.loads(
                        command(
                            ["docker", "inspect", "--format", "{{json .HostConfig}}", args.project + "-load-client"]
                        )
                    )
                    host["runner_actual_limits"] = {
                        key: actual[key] for key in ("NanoCpus", "Memory", "MemorySwap", "ShmSize")
                    }
        result = process.wait()
    finally:
        time.sleep(1.1)  # Retain the sample interval covering the final, potentially sub-second timed window.
        stop.set()
        sampler.join(timeout=10)
    events = container_events(states_before, container_states(args.project))
    if events:
        print("CONTAINER EVENT during the run: " + "; ".join(events), flush=True)
        result = result or 1
    host.update(
        duration_seconds=time.perf_counter() - started,
        exit_code=result,
        container_state_before=states_before,
        container_events=events,
    )
    samples = [json.loads(line) for line in (output / "stats.jsonl").read_text().splitlines()]
    host["sampled_containers"] = sorted({row["Name"] for row in samples})
    host["resource_sample_count"] = len(samples)
    (output / "host.json").write_text(json.dumps(host, indent=2, sort_keys=True) + "\n", newline="\n")
    provenance_file = output / "provenance.json"
    if provenance_file.exists():
        provenance = json.loads(provenance_file.read_text())
        provenance.update(host=host, final=args.final)
        temporary = provenance_file.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", newline="\n")
        temporary.replace(
            provenance_file
        )  # Directory permission permits replacing a file written by the container UID.
    raw = output / "raw.jsonl"
    annotate(output)
    if raw.exists() and raw.stat().st_size > 5 * 1024 * 1024:
        with raw.open("rb") as source, gzip.open(str(raw) + ".gz", "wb") as target:
            import shutil

            shutil.copyfileobj(source, target)
        raw.unlink()
    command([sys.executable, "-m", "benchmarks.report", str(output)], capture=False)
    print(
        json.dumps(
            {
                "results": str(output),
                "commit": host["commit"],
                "exit_code": result,
                "duration_seconds": host["duration_seconds"],
            }
        ),
        flush=True,
    )
    return result


if __name__ == "__main__":
    raise SystemExit(main())
