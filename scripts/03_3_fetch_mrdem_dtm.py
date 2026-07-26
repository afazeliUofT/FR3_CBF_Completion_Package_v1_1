#!/usr/bin/env python3
"""Discover the official NRCan MRDEM DTM VRT and crop a local study-area GeoTIFF.

The script uses the Government of Canada CKAN metadata record rather than a
hard-coded data-file URL. It selects the non-hillshade DTM VRT resource, records
all provenance, normalizes relative VRT paths, and crops only the bounding box
needed by the supplied link table.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DATASET_ID_DEFAULT = "18752265-bda3-498c-a4ba-9dfe68cb98da"
API_ENDPOINTS = (
    "https://open.canada.ca/data/en/api/3/action/package_show",
    "https://open.canada.ca/data/api/3/action/package_show",
)
USER_AGENT = "FR3-CBF-MRDEM-terrain/1.0 (academic reproducibility workflow)"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(flatten_text(v) for v in value)
    return str(value)


def fetch_bytes(url: str, timeout_s: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return response.read()


def fetch_package_metadata(dataset_id: str) -> tuple[dict[str, Any], str]:
    errors: list[str] = []
    query = urllib.parse.urlencode({"id": dataset_id})
    for endpoint in API_ENDPOINTS:
        url = f"{endpoint}?{query}"
        try:
            payload = json.loads(fetch_bytes(url).decode("utf-8"))
            if not payload.get("success"):
                errors.append(f"{url}: API success=false")
                continue
            result = payload.get("result")
            if not isinstance(result, dict):
                errors.append(f"{url}: result is not an object")
                continue
            return payload, url
        except Exception as exc:  # retain all endpoint failures for diagnosis
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Could not retrieve Open Government metadata:\n" + "\n".join(errors))


def select_dtm_vrt_resource(resources: list[dict[str, Any]]) -> dict[str, Any]:
    scored: list[tuple[int, dict[str, Any], str]] = []
    for resource in resources:
        text = " ".join(
            flatten_text(resource.get(key))
            for key in ("name", "name_translated", "description", "format", "url")
        ).lower()
        score = 0
        if "dtm gdal virtual format" in text:
            score += 100
        if "digital terrain model" in text and "vrt" in text:
            score += 50
        if "dtm" in text and "vrt" in text:
            score += 20
        if "hillshade" in text:
            score -= 200
        if "dsm" in text:
            score -= 100
        if "source" in text and "mrdem source" in text:
            score -= 100
        if score > 0:
            scored.append((score, resource, text))
    if not scored:
        available = [
            {
                "name": flatten_text(r.get("name") or r.get("name_translated")),
                "format": flatten_text(r.get("format")),
                "url": r.get("url"),
            }
            for r in resources
        ]
        raise RuntimeError(
            "No non-hillshade MRDEM DTM VRT resource was found. Available resources:\n"
            + json.dumps(available, indent=2, ensure_ascii=False)
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score = scored[0][0]
    best = [item for item in scored if item[0] == best_score]
    if len(best) != 1:
        raise RuntimeError(
            "MRDEM DTM VRT selection is ambiguous:\n"
            + json.dumps(
                [
                    {
                        "score": score,
                        "name": flatten_text(resource.get("name") or resource.get("name_translated")),
                        "format": flatten_text(resource.get("format")),
                        "url": resource.get("url"),
                    }
                    for score, resource, _ in best
                ],
                indent=2,
                ensure_ascii=False,
            )
        )
    resource = best[0][1]
    if not str(resource.get("url", "")).strip():
        raise RuntimeError("Selected MRDEM DTM VRT resource has no URL")
    return resource


def normalize_vrt(vrt_bytes: bytes, resource_url: str) -> bytes:
    """Make relative remote source paths explicit so a downloaded VRT remains usable."""
    try:
        root = ET.fromstring(vrt_bytes)
    except ET.ParseError as exc:
        preview = vrt_bytes[:300].decode("utf-8", errors="replace")
        raise RuntimeError(f"Downloaded resource is not valid VRT XML: {exc}; preview={preview!r}") from exc
    if root.tag != "VRTDataset" and not root.tag.endswith("VRTDataset"):
        raise RuntimeError(f"Downloaded XML root is {root.tag!r}, not VRTDataset")
    for node in root.iter("SourceFilename"):
        text = (node.text or "").strip()
        if not text:
            continue
        if text.startswith(("/vsicurl/", "/vsis3/", "/vsigs/", "/vsiaz/")):
            node.set("relativeToVRT", "0")
            continue
        parsed = urllib.parse.urlparse(text)
        if parsed.scheme in {"http", "https"}:
            node.text = "/vsicurl/" + text
            node.set("relativeToVRT", "0")
            continue
        if parsed.scheme == "file":
            node.text = urllib.request.url2pathname(parsed.path)
            node.set("relativeToVRT", "0")
            continue
        if not os.path.isabs(text):
            absolute = urllib.parse.urljoin(resource_url, text)
            parsed_abs = urllib.parse.urlparse(absolute)
            if parsed_abs.scheme in {"http", "https"}:
                node.text = "/vsicurl/" + absolute
            elif parsed_abs.scheme == "file":
                node.text = urllib.request.url2pathname(parsed_abs.path)
            else:
                node.text = absolute
            node.set("relativeToVRT", "0")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--links", required=True, help="Frozen link CSV with TX/RX coordinates")
    parser.add_argument("--out-dir", default="data/external/mrdem")
    parser.add_argument("--dataset-id", default=DATASET_ID_DEFAULT)
    parser.add_argument("--padding-deg", type=float, default=0.05)
    parser.add_argument(
        "--metadata-json",
        help="Optional pre-fetched CKAN package_show JSON; intended for audited offline reruns/tests",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    links_path = Path(args.links).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    if not links_path.is_file():
        raise FileNotFoundError(links_path)
    if args.padding_deg < 0:
        raise ValueError("--padding-deg must be nonnegative")

    links = pd.read_csv(links_path)
    required = {"tx_lat_deg", "tx_lon_deg", "rx_lat_deg", "rx_lon_deg"}
    missing = sorted(required - set(links.columns))
    if missing:
        raise ValueError(f"Link CSV is missing columns: {missing}")
    coords = links[list(required)].apply(pd.to_numeric, errors="coerce")
    if coords.isna().any().any():
        raise ValueError("Link CSV contains missing/non-numeric coordinates")

    west = float(min(coords["tx_lon_deg"].min(), coords["rx_lon_deg"].min()) - args.padding_deg)
    east = float(max(coords["tx_lon_deg"].max(), coords["rx_lon_deg"].max()) + args.padding_deg)
    south = float(min(coords["tx_lat_deg"].min(), coords["rx_lat_deg"].min()) - args.padding_deg)
    north = float(max(coords["tx_lat_deg"].max(), coords["rx_lat_deg"].max()) + args.padding_deg)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError(f"Invalid study bbox: {(west, south, east, north)}")

    metadata_path = out_dir / "mrdem_package_metadata.json"
    if args.metadata_json:
        metadata_path_in = Path(args.metadata_json).expanduser().resolve()
        payload = json.loads(metadata_path_in.read_text(encoding="utf-8"))
        api_url = f"offline:{metadata_path_in}"
    else:
        payload, api_url = fetch_package_metadata(args.dataset_id)
    result = payload.get("result", payload)
    if not isinstance(result, dict):
        raise RuntimeError("Metadata does not contain a package object")
    resources = result.get("resources")
    if not isinstance(resources, list):
        raise RuntimeError("Metadata package has no resources list")
    resource = select_dtm_vrt_resource(resources)
    resource_url = str(resource["url"]).strip()

    metadata_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    resource_path = out_dir / "mrdem_dtm_resource.json"
    resource_path.write_text(json.dumps(resource, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    raw_vrt_path = out_dir / "mrdem_dtm_downloaded.vrt"
    normalized_vrt_path = out_dir / "mrdem_dtm_normalized.vrt"
    subset_path = out_dir / "mrdem_dtm_study_subset.tif"
    if subset_path.exists() and not args.force:
        raise FileExistsError(f"{subset_path} already exists; use --force to replace it")

    vrt_bytes = fetch_bytes(resource_url)
    raw_vrt_path.write_bytes(vrt_bytes)
    normalized_vrt_path.write_bytes(normalize_vrt(vrt_bytes, resource_url))

    try:
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import Window, from_bounds
    except ImportError as exc:
        raise SystemExit("Install requirements-full.txt before running this script") from exc

    env_options = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff,.vrt,.xml",
        "GDAL_HTTP_MULTIPLEX": "YES",
        "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
    }
    with rasterio.Env(**env_options):
        with rasterio.open(normalized_vrt_path) as src:
            if src.crs is None:
                raise RuntimeError("MRDEM DTM VRT has no CRS")
            src_bounds = transform_bounds(
                "EPSG:4326", src.crs, west, south, east, north, densify_pts=21
            )
            window = from_bounds(*src_bounds, transform=src.transform)
            window = window.round_offsets().round_lengths()
            full = Window(0, 0, src.width, src.height)
            try:
                window = window.intersection(full)
            except Exception as exc:
                raise RuntimeError("Study bbox does not intersect the MRDEM DTM") from exc
            arr = src.read(1, window=window, masked=True)
            if arr.size == 0 or np.ma.getmaskarray(arr).all():
                raise RuntimeError("MRDEM crop contains no valid DTM samples")
            nodata = -9999.0
            data = np.asarray(arr.filled(nodata), dtype=np.float32)
            profile = src.profile.copy()
            profile.update(
                driver="GTiff",
                dtype="float32",
                count=1,
                height=data.shape[0],
                width=data.shape[1],
                transform=src.window_transform(window),
                nodata=nodata,
                compress="DEFLATE",
                predictor=3,
                tiled=True,
                BIGTIFF="IF_SAFER",
            )
            with rasterio.open(subset_path, "w", **profile) as dst:
                dst.write(data, 1)
                dst.update_tags(
                    source_dataset="NRCan Medium Resolution Digital Elevation Model (MRDEM) DTM",
                    source_dataset_id=args.dataset_id,
                    source_resource_url=resource_url,
                    source_api_url=api_url,
                    requested_bbox_epsg4326=json.dumps([west, south, east, north]),
                    created_utc=datetime.now(timezone.utc).isoformat(),
                )

    record = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": args.dataset_id,
        "api_url": api_url,
        "resource": resource,
        "resource_url": resource_url,
        "links_csv": str(links_path),
        "links_csv_sha256": sha256_file(links_path),
        "bbox_epsg4326_with_padding": [west, south, east, north],
        "padding_deg": args.padding_deg,
        "metadata_json": str(metadata_path),
        "metadata_json_sha256": sha256_file(metadata_path),
        "resource_json": str(resource_path),
        "resource_json_sha256": sha256_file(resource_path),
        "downloaded_vrt": str(raw_vrt_path),
        "downloaded_vrt_sha256": sha256_file(raw_vrt_path),
        "normalized_vrt": str(normalized_vrt_path),
        "normalized_vrt_sha256": sha256_file(normalized_vrt_path),
        "subset_geotiff": str(subset_path),
        "subset_geotiff_sha256": sha256_file(subset_path),
    }
    source_record = out_dir / "MRDEM_SOURCE_RECORD.json"
    source_record.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with rasterio.open(subset_path) as ds:
        valid = ds.read(1, masked=True)
        print("MRDEM FETCH/CROP: PASS")
        print(f"Dataset ID: {args.dataset_id}")
        print(f"Resource: {flatten_text(resource.get('name') or resource.get('name_translated'))}")
        print(f"Subset: {subset_path}")
        print(f"CRS: {ds.crs}")
        print(f"Shape: {ds.height} x {ds.width}")
        print(f"Resolution: {ds.res}")
        print(f"Valid elevation range: {float(valid.min()):.3f} to {float(valid.max()):.3f} m")
        print(f"SHA-256: {sha256_file(subset_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
