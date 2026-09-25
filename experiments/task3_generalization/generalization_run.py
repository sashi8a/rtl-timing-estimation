"""Independent bounded-restart supervisor; all independent jobs survive failures."""

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
from generalization_data import load_manifest, prepare


def queue(base, run, jobs):
    errors = []
    for fold, name, seed in jobs:
        log = run / "logs" / f"fold{fold}-{name}-seed{seed}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--base-run",
            str(base),
            "--run",
            str(run),
            "--worker",
            name,
            "--fold",
            str(fold),
            "--seed",
            str(seed),
        ]
        print(f"Launching fold{fold} {name} seed{seed}", flush=True)
        try:
            with log.open("a", buffering=1) as stream:
                result = subprocess.run(
                    command, stdout=stream, stderr=subprocess.STDOUT, check=False
                )
            require(result.returncode == 0, f"Exit {result.returncode}; see {log}")
        except Exception as exc:  # noqa: BLE001 -- preserve independent completed jobs
            failure = {
                "fold": fold,
                "model": name,
                "seed": seed,
                "error": str(exc),
                "log": str(log),
            }
            write_json(
                run / "failures" / f"{fold}-{name}-{seed}-{time.time_ns()}.json",
                failure,
            )
            status_path = (
                run
                / "models"
                / f"fold{fold}"
                / (f"{name}-seed{seed}" if name.startswith("N") else name)
                / "status.json"
            )
            if status_path.exists():
                state = read(status_path)
                state.update(state="failed", error=str(exc), updated_at=time.time())
                write_json(status_path, state)
            errors.append(failure)
    return errors


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
            m = load_manifest(run)
            if not completed(run / "results", m["signature"]):
                write_json(
                    run / "status.json",
                    {
                        "state": "training",
                        "signature": m["signature"],
                        "updated_at": time.time(),
                        "pid": os.getpid(),
                    },
                )
                cpu = [(f, "T1", 0) for f in range(1, 5)]
                gpu = [
                    (f, n, s)
                    for f in range(1, 5)
                    for s in m["config"]["seeds"]
                    for n in m["config"]["neural_models"]
                ]
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(queue, base, run, q) for q in [cpu, gpu]]
                    errors = [
                        error
                        for future in concurrent.futures.as_completed(futures)
                        for error in future.result()
                    ]
                require(not errors, f"Incomplete required jobs: {errors}")
                write_json(
                    run / "status.json",
                    {"state": "evaluation", "updated_at": time.time()},
                )
                from generalization_finish import finish

                finish(run)
            require(completed(run / "results", m["signature"]), "Results unsealed")
            from verify_package import verify

            verify(run)
            write_json(
                run / "status.json",
                {
                    "state": "complete",
                    "signature": m["signature"],
                    "updated_at": time.time(),
                },
            )
            print("GENERALIZATION STUDY COMPLETE", flush=True)
        except Exception:
            error = traceback.format_exc()
            write_json(
                run / "status.json",
                {"state": "failed", "error": error, "updated_at": time.time()},
            )
            raise


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base-run", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--worker", choices=["T1", "N0", "N1", "N1-NoContext"])
    p.add_argument("--fold", type=int, choices=range(1, 5))
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    if a.worker:
        from generalization_train import run_model

        require(a.fold is not None, "Worker needs fold")
        run_model(a.run, a.fold, a.worker, a.seed)
    else:
        supervise(a.base_run.resolve(), a.run.resolve())
