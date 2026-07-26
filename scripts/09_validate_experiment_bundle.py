from __future__ import annotations

import argparse

from _bootstrap import ROOT
from fr3_cbf.bundle import validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle")
    args = parser.parse_args()
    result = validate_bundle(args.bundle)
    print("EXPERIMENT BUNDLE: PASS")
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
