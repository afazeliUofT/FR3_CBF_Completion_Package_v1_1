# E3 reference intake

This patch begins the first real headline E3 case after the validated P.452 pilot.
It does **not** generate paper-ready interference results.

It performs four fail-closed steps:

1. rebuilds the P.452 pilot evidence manifest in canonical GNU SHA-256 format;
2. creates an earth-station staging record with explicit public/model boundaries and samples official MRDEM ground elevation;
3. fetches one CelesTrak TLE query, validates catalog number, checksums, epoch, and age, then archives it;
4. generates a Skyfield coarse track, selects the highest complete pass above 5 degrees, and creates a one-second detailed track.

The station case uses the public NRCan Gatineau facility and 13 m S/X dish description. The coordinate is an OSM-derived building centroid, not an official survey. The phase-centre height, carrier, future cellular deployment, and antenna pattern are model decisions/open items. The RCM orbital record is used only to generate changing geometry; it is not evidence of an actual 8.15 GHz pass received by the station.

## Run

```bash
source .venv/bin/activate
python3 -m pip install -r requirements-full.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_e3_reference_intake.py
bash RUN_E3_REFERENCE_INTAKE.sh
```

## Stop gate

Required final markers:

```text
P.452 PILOT EVIDENCE MANIFEST REBUILD: PASS
E3 REFERENCE STATION PREPARATION: PASS
E3 TLE FETCH/VALIDATION: PASS
E3 PASS GENERATION/SELECTION: PASS
E3 REFERENCE INTAKE: PASS
```

Do not run the final E3 controller at this point. The next stage is to freeze the earth-station antenna pattern and modelled 19-site/57-sector deployment, then validate one actual cellular-sector-to-station P.452 path before scaling.
