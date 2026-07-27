#!/usr/bin/env python3
"""
A3 extraction pipeline -- ISED SMS/TAFL -> FR3 study incumbent files.

Inputs : TAFL_LTAF_Fixe.csv, TAFL_LTAF_Satellite.csv
         SMS Authorization Data Extract, open.canada.ca record
         508040d7-6fa9-46e4-afbc-aa61f3ca317e

Outputs: incumbents_caseT_gta.csv,
         fixe_on_band.csv,
         satellite_es_survey.csv,
         provenance_A3.md

Layout : 61 columns = 1 undocumented leading TX/RX direction column
         + the 60 fields of tafl_description_ltaf.pdf,
         no header, UTF-8 BOM.

Cleaning: '' -> NaN, '-' -> NaN,
          leading/trailing-dot numerics parsed,
          0-as-NULL flagged, not dropped, for gain/hpbw,
          full-duplicate rows dropped.
"""

from pathlib import Path
import hashlib
import datetime

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

ROOT = Path(r"C:\Users\alifa\OneDrive\Projects\FR3_MainWork_For_Journal")

FIXE = ROOT / "TAFL_LTAF" / "TAFL_LTAF_Fixe.csv"
SAT = ROOT / "TAFL_LTAF" / "TAFL_LTAF_Satellite.csv"
OUT = ROOT / "outputs"

OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Study constants
# ---------------------------------------------------------------------

BAND_T = (7725.0, 8275.0)  # Case T FS band

BANDS_S = [
    (7250.0, 7750.0),
    (8025.0, 8400.0),
]  # Case S survey bands

GTA = {
    "lat": (43.2, 44.4),
    "lon": (-80.3, -78.3),
}  # bounding box

CARRIERS = {
    "fc8000_7950-8050": (7950.0, 8050.0),
    "fc7850_7800-7900": (7800.0, 7900.0),
}

CHANNEL_BW_SET = [1.25, 2.5, 5.0, 10.0, 20.0, 30.0]  # MHz


# ---------------------------------------------------------------------
# TAFL column names
# ---------------------------------------------------------------------

NAMES = [
    "txrx",
    "freq_mhz",
    "freq_rec_id",
    "reg_service",
    "comm_type",
    "conformity",
    "alloc_name",
    "channel",
    "intl_coord",
    "analog_digital",
    "occ_bw_khz",
    "emission_desig",
    "modulation",
    "filtration",
    "tx_erp_dbw",
    "tx_power_w",
    "total_losses_db",
    "analog_cap",
    "digital_cap",
    "rx_unfaded_dbw",
    "rx_thresh_ber1e3_dbw",
    "ant_manufacturer",
    "ant_model",
    "ant_gain_dbi",
    "ant_pattern",
    "hpbw_deg",
    "f2b_db",
    "polarization",
    "height_agl_m",
    "azimuth_deg",
    "elev_angle_deg",
    "station_loc",
    "licensee_ref",
    "call_sign",
    "station_type",
    "itu_class",
    "cost_cat",
    "n_identical",
    "ref_id",
    "province",
    "lat",
    "lon",
    "ground_elev_m",
    "struct_height_m",
    "congestion",
    "radius_km",
    "satellite_name",
    "auth_number",
    "service",
    "subservice",
    "licence_type",
    "auth_status",
    "in_service_date",
    "account",
    "licensee_name",
    "licensee_addr",
    "op_status",
    "stn_class",
    "h_pow_w",
    "v_pow_w",
    "standby",
]

NUMERIC = [
    "freq_mhz",
    "occ_bw_khz",
    "tx_erp_dbw",
    "tx_power_w",
    "total_losses_db",
    "rx_unfaded_dbw",
    "rx_thresh_ber1e3_dbw",
    "ant_gain_dbi",
    "hpbw_deg",
    "f2b_db",
    "height_agl_m",
    "azimuth_deg",
    "elev_angle_deg",
    "lat",
    "lon",
    "ground_elev_m",
    "struct_height_m",
    "radius_km",
]


# ---------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------

def sha256(path: Path) -> str:
    """Return SHA-256 hash of a file."""
    h = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)

    return h.hexdigest()


def require_file(path: Path) -> None:
    """Stop early with a clear error if an input file is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found:\n{path}")


def load(path: Path) -> tuple[pd.DataFrame, int]:
    """
    Load one TAFL CSV file.

    Returns:
        df: cleaned dataframe
        ndup: number of exact duplicate rows dropped
    """
    require_file(path)

    df = pd.read_csv(
        path,
        header=None,
        names=NAMES,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
    )

    if df.shape[1] != 61:
        raise ValueError(
            f"Unexpected column count in {path.name}: "
            f"got {df.shape[1]}, expected 61"
        )

    df = df.apply(lambda s: s.str.strip())
    df = df.replace({"": np.nan, "-": np.nan})

    n0 = len(df)
    df = df.drop_duplicates()
    ndup = n0 - len(df)

    for c in NUMERIC:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Zero-as-NULL flags.
    # Some documented fields may use zero as a null/missing placeholder.
    # We flag these values but do not drop them.
    df["flag_gain_zero"] = df["ant_gain_dbi"].eq(0)
    df["flag_hpbw_zero"] = df["hpbw_deg"].eq(0)

    return df, ndup


def raster_check(f: float) -> tuple[bool, str]:
    """
    Return:
        on_1p25_grid: True if centre frequency lies on 1.25 MHz raster
        plan_bw_match_list: pipe-separated matching domestic channel plans
    """
    if not np.isfinite(f):
        return False, ""

    on_grid = (
        abs((f - 7725.0) / 1.25 - round((f - 7725.0) / 1.25)) < 1e-6
        or abs((f - 8025.0) / 1.25 - round((f - 8025.0) / 1.25)) < 1e-6
    )

    plans = []

    checks = {
        30: [(7710.0, 30.0, 8), (8010.0, 30.0, 8)],
        20: [(7715.0, 20.0, 12), (8015.0, 20.0, 12)],
        10: [(7720.0, 10.0, 25), (8020.0, 10.0, 25)],
        5: [(7722.5, 5.0, 50), (8022.5, 5.0, 50)],
        2.5: [(7723.75, 2.5, 100), (8023.75, 2.5, 100)],
        1.25: [(7725.0, 1.25, 200), (8025.0, 1.25, 200)],
    }

    for bw, fmls in checks.items():
        for f0, step, nmax in fmls:
            n = (f - f0) / step
            if abs(n - round(n)) < 1e-6 and 1 <= round(n) <= nmax:
                plans.append(str(bw))

    return on_grid, "|".join(sorted(set(plans)))


def infer_channel_bw(occ_khz: float) -> float:
    """
    Infer nominal channel bandwidth from occupied bandwidth.

    Input:
        occ_khz: occupied bandwidth in kHz

    Output:
        channel bandwidth in MHz, or NaN if unavailable/exceeds max
    """
    if not np.isfinite(occ_khz):
        return np.nan

    occ_mhz = occ_khz / 1000.0

    for bw in CHANNEL_BW_SET:
        if occ_mhz <= bw + 1e-9:
            return bw

    return np.nan


def overlap_mhz(fc: float, bw: float, lo: float, hi: float) -> float:
    """
    Compute spectral overlap in MHz between a channel and [lo, hi].
    """
    if not (np.isfinite(fc) and np.isfinite(bw)):
        return 0.0

    a = fc - bw / 2.0
    b = fc + bw / 2.0

    return max(0.0, min(b, hi) - max(a, lo))


# ---------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------

def main() -> None:
    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    prov = [
        f"# A3 provenance -- generated {stamp}",
        f"- source Fixe: {FIXE}  sha256={sha256(FIXE)}",
        f"- source Satellite: {SAT}  sha256={sha256(SAT)}",
        "- portal record: open.canada.ca 508040d7-6fa9-46e4-afbc-aa61f3ca317e "
        "(SMS Authorization Data Extract, monthly refresh)",
        "- layout finding: 61 columns = undocumented leading TX/RX direction "
        "column + 60 documented fields; no header row; UTF-8 BOM.",
        "- cleaning: ''/'-' -> NULL; duplicates dropped; gain/hpbw zero "
        "flagged as possible NULL-as-zero per field-description note.",
    ]

    # -----------------------------------------------------------------
    # Fixed service, Case T
    # -----------------------------------------------------------------

    fx, ndup = load(FIXE)

    prov.append(
        f"- Fixe rows: {len(fx) + ndup} raw, "
        f"{ndup} exact duplicates dropped."
    )

    inb = fx[
        (fx["freq_mhz"] >= BAND_T[0])
        & (fx["freq_mhz"] <= BAND_T[1])
    ].copy()

    prov.append(
        f"- in 7725-8275 MHz: {len(inb)} rows "
        f"(TX {int((inb['txrx'] == 'TX').sum())} / "
        f"RX {int((inb['txrx'] == 'RX').sum())})."
    )

    # Status filter:
    # Keep Granted ('G') and Authorized ('11'); flag/exclude others.
    keep = inb[inb["auth_status"].isin(["G", "11"])].copy()

    excluded_status_counts = (
        inb[~inb["auth_status"].isin(["G", "11"])]
        ["auth_status"]
        .value_counts()
        .to_dict()
    )

    prov.append(
        f"- auth_status kept G/11: {len(keep)} "
        f"(excluded {len(inb) - len(keep)}: {excluded_status_counts})."
    )

    # Derived columns
    rc = keep["freq_mhz"].apply(raster_check)

    keep["on_1p25_grid"] = [r[0] for r in rc]
    keep["plan_bw_match"] = [r[1] for r in rc]
    keep["channel_bw_mhz"] = keep["occ_bw_khz"].apply(infer_channel_bw)
    keep["envelope"] = np.where(keep["congestion"].isin(["H", "M"]), "A", "B")

    for name, (lo, hi) in CARRIERS.items():
        keep[f"ovl_{name}_mhz"] = [
            overlap_mhz(f, b, lo, hi)
            for f, b in zip(keep["freq_mhz"], keep["channel_bw_mhz"])
        ]

    on_band = keep[keep["province"].eq("ON")].copy()

    gta = on_band[
        on_band["lat"].between(*GTA["lat"])
        & on_band["lon"].between(*GTA["lon"])
    ].copy()

    victims = gta[gta["txrx"].eq("RX")].copy()

    prov.append(
        f"- Ontario in-band (kept): {len(on_band)}; "
        f"GTA bbox lat{GTA['lat']} lon{GTA['lon']}: {len(gta)} rows, "
        f"{len(victims)} RX (victim) stations."
    )

    for name in CARRIERS:
        n = int((victims[f"ovl_{name}_mhz"] > 0).sum())
        prov.append(f"- victims co-channel with carrier {name}: {n}")

    prov.append(
        f"- raster: {int((~gta['on_1p25_grid']).sum())} GTA rows "
        "NOT on the 1.25 MHz SRSP grid (flagged, not dropped)."
    )

    prov.append(
        f"- conformity in GTA: "
        f"{gta['conformity'].value_counts(dropna=False).to_dict()}"
    )

    prov.append(
        f"- congestion in GTA: "
        f"{gta['congestion'].value_counts(dropna=False).to_dict()} "
        f"-> envelope: {gta['envelope'].value_counts().to_dict()}"
    )

    cols = [
        "txrx",
        "freq_mhz",
        "channel_bw_mhz",
        "occ_bw_khz",
        "emission_desig",
        "modulation",
        "on_1p25_grid",
        "plan_bw_match",
        "conformity",
        "congestion",
        "envelope",
        "lat",
        "lon",
        "ground_elev_m",
        "height_agl_m",
        "struct_height_m",
        "azimuth_deg",
        "elev_angle_deg",
        "ant_gain_dbi",
        "hpbw_deg",
        "f2b_db",
        "ant_pattern",
        "ant_manufacturer",
        "ant_model",
        "polarization",
        "tx_power_w",
        "tx_erp_dbw",
        "total_losses_db",
        "rx_unfaded_dbw",
        "rx_thresh_ber1e3_dbw",
        "station_loc",
        "call_sign",
        "auth_number",
        "licensee_name",
        "in_service_date",
        "flag_gain_zero",
        "flag_hpbw_zero",
    ] + [f"ovl_{n}_mhz" for n in CARRIERS]

    victims[cols].to_csv(
        OUT / "incumbents_caseT_gta.csv",
        index=False,
        encoding="utf-8",
    )

    on_band[cols].to_csv(
        OUT / "fixe_on_band.csv",
        index=False,
        encoding="utf-8",
    )

    # -----------------------------------------------------------------
    # Satellite earth stations, Case S survey
    # -----------------------------------------------------------------

    st, sdup = load(SAT)

    prov.append(
        f"- Satellite rows: {len(st) + sdup} raw, "
        f"{sdup} duplicates dropped; "
        f"txrx: {st['txrx'].value_counts().to_dict()}"
    )

    m = np.zeros(len(st), dtype=bool)

    for lo, hi in BANDS_S:
        m |= st["freq_mhz"].between(lo, hi).fillna(False).values

    ses = st[m].copy()
    ses_rx = ses[ses["txrx"].eq("RX")].copy()

    prov.append(
        f"- ES rows in 7250-7750 or 8025-8400: {len(ses)} "
        f"({len(ses_rx)} RX); provinces: "
        f"{ses_rx['province'].value_counts().head(6).to_dict()}"
    )

    on_es = ses_rx[ses_rx["province"].eq("ON")]

    prov.append(
        f"- Ontario RX earth stations in survey bands: {len(on_es)}; "
        f"ITU classes: {on_es['itu_class'].value_counts().to_dict()}; "
        f"satellites: {on_es['satellite_name'].value_counts().head(8).to_dict()}"
    )

    scols = [
        "txrx",
        "freq_mhz",
        "occ_bw_khz",
        "itu_class",
        "satellite_name",
        "lat",
        "lon",
        "ground_elev_m",
        "height_agl_m",
        "azimuth_deg",
        "elev_angle_deg",
        "ant_gain_dbi",
        "hpbw_deg",
        "ant_manufacturer",
        "ant_model",
        "station_loc",
        "call_sign",
        "auth_number",
        "licensee_name",
        "subservice",
        "auth_status",
        "in_service_date",
        "province",
    ]

    ses_rx[scols].to_csv(
        OUT / "satellite_es_survey.csv",
        index=False,
        encoding="utf-8",
    )

    with (OUT / "provenance_A3.md").open("w", encoding="utf-8") as f:
        f.write("\n".join(prov) + "\n")

    print("\n".join(prov))


if __name__ == "__main__":
    main()
