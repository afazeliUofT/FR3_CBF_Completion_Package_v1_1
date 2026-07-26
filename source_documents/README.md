# Source documents included in this package

- `R-REC-P.530-19-202509.zip` - the official ITU-R P.530-19 Recommendation archive supplied by the user. Its SHA-256 is recorded in `config/regulatory_constants.yaml`.

The archive contains the Recommendation PDF. The official numerical integral products (`LogK.csv`, `dN75.csv`, and coordinate grids) are distributed separately by ITU. Use `scripts/02_download_p530_products.py`; do not infer grid values from the PDF.
