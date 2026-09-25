"""Single locked supervisor; tree CPU and neural GPU queues run concurrently."""

import argparse
import concurrent.futures
import fcntl
import importlib.metadata
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

from common import ROOT, completed, digest, read, require, write_json

from data import load, prepare


def launch_queue(run, jobs, label):
    for model, seed in jobs:
        name = f"{model}-seed{seed}" if model.startswith("N") else model
        logfile = run / "logs" / f"{name}.log"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        with logfile.open("a", buffering=1) as stream:
            command = [
                sys.executable,
                str(ROOT / "modeling/train.py"),
                "--run",
                str(run),
                "--model",
                model,
                "--seed",
                str(seed),
            ]
            print(f"Launching {name} ({label})", flush=True)
            result = subprocess.run(
                command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False
            )
        if result.returncode:
            write_json(
                run / "failures" / f"{name}-{time.time_ns()}.json",
                {
                    "model": name,
                    "returncode": result.returncode,
                    "log": str(logfile),
                    "time": time.time(),
                },
            )
            raise RuntimeError(f"{name} exited {result.returncode}; see {logfile}")


def supervise(run):
    os.umask(0o077)
    run.mkdir(parents=True, exist_ok=True)
    with (run / "supervisor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            write_json(
                run / "status.json",
                {"state": "preflight", "updated_at": time.time(), "pid": os.getpid()},
            )
            if not (run / "task2_preflight.json").exists():
                subprocess.run(
                    [
                        str(ROOT / ".venv/bin/python"),
                        str(ROOT / "modeling/validate_task2.py"),
                        str(run),
                    ],
                    cwd=ROOT,
                    check=True,
                )
            require(
                read(run / "task2_preflight.json")["release_sha256"]
                == read(ROOT / "modeling/config.json")["release_sha256"],
                "Preflight used a different release",
            )
            prepare(run)
            _, _, frozen = load(run, full_check=True)
            runtime = {
                "python": sys.version,
                "platform": platform.platform(),
                "packages": {
                    p: importlib.metadata.version(p)
                    for p in (
                        "numpy",
                        "pandas",
                        "pyarrow",
                        "torch",
                        "scikit-learn",
                        "scipy",
                    )
                },
                "gpu": subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=name,driver_version,memory.total",
                        "--format=csv,noheader",
                    ],
                    text=True,
                ).strip(),
                "lock_sha256": digest(ROOT / "modeling/uv.lock"),
            }
            if (run / "runtime.json").exists():
                require(
                    read(run / "runtime.json") == runtime,
                    "Runtime changed during resume",
                )
            else:
                write_json(run / "runtime.json", runtime)
            write_json(
                run / "status.json",
                {
                    "state": "training",
                    "signature": frozen["signature"],
                    "updated_at": time.time(),
                    "pid": os.getpid(),
                },
            )
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(launch_queue, run, [("T0", 0), ("T1", 0)], "CPU"),
                    pool.submit(
                        launch_queue,
                        run,
                        [
                            (m, s)
                            for s in frozen["config"]["seeds"]
                            for m in ("N0", "N1", "N2")
                        ],
                        "GPU",
                    ),
                ]
                errors = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:  # noqa: BLE001 -- preserve the other queue and report all failures
                        errors.append(str(exc))
                require(not errors, "; ".join(errors))
            write_json(
                run / "status.json",
                {
                    "state": "final_evaluation",
                    "signature": frozen["signature"],
                    "updated_at": time.time(),
                },
            )
            from finish import finish

            finish(run)
            require(
                completed(run / "results", frozen["signature"]),
                "Final output not sealed",
            )
            write_json(
                run / "status.json",
                {
                    "state": "complete",
                    "signature": frozen["signature"],
                    "updated_at": time.time(),
                    "results": str(run / "results"),
                },
            )
            print("TASK 3 COMPLETE", flush=True)
        except Exception:
            error = traceback.format_exc()
            write_json(
                run / "status.json",
                {"state": "failed", "updated_at": time.time(), "error": error},
            )
            print(error, flush=True)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    supervise(args.run.resolve())
