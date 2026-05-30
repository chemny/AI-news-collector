#!/usr/bin/env python3
import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--mode", choices=["collect", "curate", "briefing", "intelligence", "full"], default="full")
    parser.add_argument("--date")
    parser.add_argument("--source")
    args = parser.parse_args()

    if args.mode in {"collect", "full", "intelligence"}:
        cmd = [sys.executable, str(SCRIPT_DIR / "collect.py"), "--config", args.config, "--mode", "daily"]
        if args.source:
            cmd.extend(["--source", args.source])
        run(cmd)

    if args.mode in {"curate", "full", "intelligence", "briefing"}:
        cmd = [sys.executable, str(SCRIPT_DIR / "curate.py"), "--config", args.config]
        if args.date:
            cmd.extend(["--date", args.date])
        run(cmd)

    if args.mode in {"briefing", "full"}:
        cmd = [sys.executable, str(SCRIPT_DIR / "briefing.py"), "--config", args.config]
        if args.date:
            cmd.extend(["--date", args.date])
        run(cmd)


def run(cmd: list[str]) -> None:
    print("$ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
