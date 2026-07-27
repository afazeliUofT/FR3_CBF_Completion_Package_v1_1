from __future__ import annotations

import argparse
import shutil
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from _bootstrap import ROOT
from fr3_cbf.grids import P530GridProducts, REQUIRED_NAMES
from fr3_cbf.io import load_yaml, sha256_file, write_json


def find_one(root: Path, filename: str) -> Path:
    matches = [p for p in root.rglob("*") if p.is_file() and p.name.lower() == filename.lower()]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one {filename}; found {len(matches)} in {root}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download/extract official P.530-19 integral products")
    parser.add_argument("--zip", dest="zip_path", help="Manual components ZIP path")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    reg = load_yaml(ROOT / "config/regulatory_constants.yaml")
    url = reg["standards_versions"]["itu_r_p530"]["integral_products_url"]
    out_dir = ROOT / "data/external/p530"
    out_dir.mkdir(parents=True, exist_ok=True)
    components_zip = Path(args.zip_path).resolve() if args.zip_path else out_dir / "P530_components.zip"

    if not components_zip.exists():
        print("Downloading official P.530-19 components ZIP...")
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 FR3-CBF-research"})
            with urllib.request.urlopen(request, timeout=90) as response, components_zip.open("wb") as fh:
                shutil.copyfileobj(response, fh)
        except Exception as exc:
            print("DOWNLOAD FAILED:", exc)
            print("Manual action:")
            print("1. Open the official P.530-19 page.")
            print("2. Download English 'Zip (Components)'.")
            print(f"3. Save it as {out_dir / 'P530_components.zip'}")
            print("4. Re-run this script with --zip <path>.")
            return 2

    extract_dir = out_dir / "_components_extracted"
    if extract_dir.exists() and args.force:
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(components_zip) as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile as exc:
        print(f"Invalid components ZIP: {exc}")
        return 2

    copied: dict[str, str] = {}
    for key, filename in REQUIRED_NAMES.items():
        src = find_one(extract_dir, filename)
        dst = out_dir / filename
        shutil.copy2(src, dst)
        copied[key] = str(dst.relative_to(ROOT))

    try:
        grids = P530GridProducts.from_directory(out_dir)
    except Exception as exc:
        print("PRODUCT VALIDATION FAILED:", exc)
        return 2

    manifest = {
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": url,
        "components_zip": str(components_zip),
        "components_zip_sha256": sha256_file(components_zip),
        "files": {
            name: {"path": rel, "sha256": sha256_file(ROOT / rel)} for name, rel in copied.items()
        },
        "grid_shape": list(grids.logk_grid.shape),
        "latitude_range": [float(grids.latitude_axis_deg[0]), float(grids.latitude_axis_deg[-1])],
        "longitude_range": [float(grids.longitude_axis_deg[0]), float(grids.longitude_axis_deg[-1])],
    }
    write_json(out_dir / "download_manifest.json", manifest)
    print("P.530 PRODUCTS: PASS")
    print("Grid shape:", grids.logk_grid.shape)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
