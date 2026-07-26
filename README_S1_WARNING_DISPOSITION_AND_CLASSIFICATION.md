# S1 P.530 warning disposition and operator-classification gate

## Purpose

This hotfix performs the next non-circular step after the lower-cap reframe run.
It does **not** choose an I/N cap and does **not** remove warning links.

It:

1. verifies the SHA-256 hashes recorded by `results/s1_cap_reframe/audit.json`;
2. retains all four P.530 warning records;
3. proves whether any warning record determines a scenario pass/fail edge;
4. records the slight 5-7.5 km regression-range limitation explicitly;
5. proves whether +10 dB is already rejected by a non-warning link;
6. creates a 70-row operator/administration classification template;
7. creates a concise request listing the exact information still required.

## Install

From the repository root:

```bash
unzip -o FR3_CBF_v1_1_S1_Warning_Disposition_Hotfix.zip -d .
sha256sum -c S1_WARNING_DISPOSITION_HOTFIX_MANIFEST.sha256
python3 -m py_compile scripts/04e_disposition_p530_warnings.py
```

## Run

```bash
set +e
set -o pipefail

python3 -X faulthandler -u \
  scripts/04e_disposition_p530_warnings.py \
  --config config/s1_warning_disposition.yaml \
  2>&1 | tee logs/04e_p530_warning_disposition.log

DISPOSITION_EXIT=${PIPESTATUS[0]}
set +o pipefail

echo "P.530 warning-disposition exit code: $DISPOSITION_EXIT"
```

Expected ending for the supplied cap-reframe evidence:

```text
P.530 WARNING DISPOSITION: PASS
Warning records retained: 4
Physical warning paths: 1
Binding link(s) at all scenario edges: 010031733-003__8100.000MHz
Minimum global-to-warning outage ratio: 123.228586
All-eight conditional interval: [-34.25, -34.0] dB
No cap or allocation was selected.
```

## Outputs

```text
results/s1_warning_disposition/P530_WARNING_LINKS_RETAINED.csv
results/s1_warning_disposition/P530_WARNING_THRESHOLD_EDGE_AUDIT.csv
results/s1_warning_disposition/P530_WARNING_DISPOSITION.json
results/s1_warning_disposition/P530_WARNING_DISPOSITION.md
data/real/S1_OPERATOR_CLASSIFICATION_TEMPLATE.csv
data/real/S1_OPERATOR_CLASSIFICATION_REQUEST.md
```

## Meaning of PASS

PASS means only that the four warning records are retained and do not determine any
reported threshold edge. It does not place the 7.293638 km path inside the 7.5-300 km
regression dataset, and it does not freeze a final cap.

## Required external decision

Send `data/real/S1_OPERATOR_CLASSIFICATION_REQUEST.md` and the CSV template to the
operator/administration reviewer. Do not run the final 81-case P.530 sensitivity campaign
until the network portion, interference-source class, F.1565 parameter choice, BER-event
mapping, and allocation scope are supplied.
