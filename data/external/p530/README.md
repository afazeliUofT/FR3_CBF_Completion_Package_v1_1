# Official P.530-19 integral products

Run:

```bash
python scripts/02_download_p530_products.py
```

or place the official English **Zip (Components)** file here as `P530_components.zip` and run:

```bash
python scripts/02_download_p530_products.py --zip data/external/p530/P530_components.zip
```

Required extracted files: `LogK.csv`, `dN75.csv`, `LatitudeQuarterDegree.csv`, and `LongitudeQuarterDegree.csv`. The script writes `download_manifest.json` with SHA-256 hashes.

The Recommendation PDF archive in `source_documents/` is not a substitute for these numerical grids.
