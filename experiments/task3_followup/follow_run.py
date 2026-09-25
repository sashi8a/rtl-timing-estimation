"""Independent persistent supervisor for the approved exploratory follow-ups."""

import argparse
import concurrent.futures
import fcntl
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

import bootstrap  # noqa: F401
from common import completed, read, require, write_json
from follow_data import load, prepare


def queue(run, jobs):
    for name, seed in jobs:
        logfile = run / "logs" / f"{name}-seed{seed}.log"
        logfile.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-run",
            read(run / "manifest.json")["base_run"],
            "--run",
            str(run),
            "--worker",
            name,
            "--seed",
            str(seed),
        ]
        print(f"Launching {name}, seed {seed}", flush=True)
        with logfile.open("a", buffering=1) as stream:
            result = subprocess.run(
                command, stdout=stream, stderr=subprocess.STDOUT, check=False
            )
        if result.returncode:
            write_json(
                run / "failures" / f"{name}-{seed}-{time.time_ns()}.json",
                {
                    "model": name,
                    "seed": seed,
                    "returncode": result.returncode,
                    "log": str(logfile),
                },
            )
            raise RuntimeError(f"{name} seed {seed} failed; see {logfile}")


def supervise(base, run):
    os.umask(0o077)
    run.mkdir(parents=True, exist_ok=True)
    with (run / "supervisor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            write_json(
                run / "status.json",
                {"state": "preflight", "updated_at": time.time(), "pid": os.getpid()},
            )
            prepare(base, run)
            _, _, frozen = load(run)
            if completed(run / "results", frozen["signature"]):
                write_json(
                    run / "status.json",
                    {
                        "state": "complete",
                        "signature": frozen["signature"],
                        "updated_at": time.time(),
                    },
                )
                return
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
                    pool.submit(queue, run, [("C0", 0)]),
                    pool.submit(
                        queue,
                        run,
                        [
                            ("N1-SOG", s)
                            for s in read(run / "manifest.json")["followup_config"][
                                "seeds"
                            ]
                        ],
                    ),
                ]
                errors = []
                for future in concurrent.futures.as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:  # noqa: BLE001 -- retain progress of the other queue
                        errors.append(str(exc))
                require(not errors, "; ".join(errors))
            write_json(
                run / "status.json",
                {"state": "final_evaluation", "updated_at": time.time()},
            )
            from follow_finish import finish

            finish(run)
            require(
                completed(run / "results", frozen["signature"]),
                "Unsealed final results",
            )
            write_json(
                run / "status.json",
                {
                    "state": "complete",
                    "signature": frozen["signature"],
                    "updated_at": time.time(),
                },
            )
            print("FOLLOW-UPS COMPLETE", flush=True)
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
    parser.add_argument("--base-run", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--worker", choices=["C0", "N1-SOG"])
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    if args.worker == "C0":
        from calibration import run_calibration

        run_calibration(args.run)
    elif args.worker:
        from follow_train import run_model

        run_model(args.run, "N1-SOG", args.seed, "cuda")
    else:
        supervise(args.base_run.resolve(), args.run.resolve())
