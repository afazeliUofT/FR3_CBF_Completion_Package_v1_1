# TAFL scope-limited pairing-freeze hotfix

This adds `scripts/03_2_freeze_tafl_gta_pairs.py`.

It consumes the successful detailed TAFL audit and validates that:

- the expected GTA-study population count is present;
- every retained row is an exact one-TX/one-RX, same-frequency, point-to-point, authorized pair;
- the GTA exception table and GTA ambiguous-group table are empty;
- endpoint coordinates, antenna altitudes, record IDs, positive TAFL fade margins, and azimuth cross-checks are valid;
- source and audit hashes match the reviewed evidence when the expected hashes are supplied.

Without `--confirm`, the script performs a read-only preflight. With `--confirm`, it writes:

- `data/real/tafl_fs_endpoints.csv`;
- `data/real/paired_fs_links_before_terrain.csv`;
- `data/real/TAFL_PAIRING_DECISION.json`;
- `data/real/TAFL_PAIRING_DECISION.md`.

The unfinished link file deliberately leaves mean path terrain and incremental-outage allocation blank. It must not be submitted to the real S1 validator until those two fields are completed and documented.

The frozen rule is limited to the cited source snapshot and study filter. It does not claim that authorization number plus frequency is a universal TAFL link identifier, and geometry is never used to invent a partner.
