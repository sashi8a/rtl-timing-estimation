"""Reproducible Task 1 entry points."""

import argparse
import json
from pathlib import Path

from .sources import fetch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("fetch")
    p.add_argument("design")
    p = sub.add_parser("generate-labels")
    p.add_argument("design")
    p = sub.add_parser("generate")
    p.add_argument("design")
    p.add_argument(
        "--representation", choices=["sog", "aig", "aimg", "xag"], default="sog"
    )
    p = sub.add_parser("verify-equivalence")
    p.add_argument("design")
    p.add_argument(
        "--representation", choices=["sog", "aig", "aimg", "xag"], default="sog"
    )
    args = parser.parse_args()
    if args.command == "fetch":
        result = fetch(args.root, args.design)
    elif args.command == "generate-labels":
        from .labels import generate_labels

        result = generate_labels(args.root, args.design)
    elif args.command == "verify-equivalence":
        from .eda import verify_equivalence

        result = verify_equivalence(args.root, args.design, args.representation)
    else:
        from .eda import generate

        result = generate(args.root, args.design, args.representation)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
