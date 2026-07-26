# P.452 Pilot Polarization Hotfix

## Why this hotfix exists

The frozen ISED TAFL record for pilot link
`010031733-003__8100.000MHz` contains polarization code `G` at both
endpoints.  In the official ISED Authorization Data Extract code list,
`G` means **co-channel dual polarization**.  The earlier pilot script
incorrectly assumed that TAFL used literal `H` and `V` values.  In the
same official code list, `A` means horizontal, `B` means vertical, and
`H` means elliptical; therefore prefix-based `H`/`V` parsing was unsafe.

ITU-R P.452 accepts only `pol=1` for horizontal and `pol=2` for vertical.
This hotfix therefore:

- maps TAFL `A` to P.452 horizontal (`1`);
- maps TAFL `B` to P.452 vertical (`2`);
- maps TAFL `G` to **two separate P.452 runs**, horizontal and vertical;
- exports the two `G` branches separately;
- performs no hidden dual-polarization power aggregation;
- rejects other non-H/V TAFL codes unless a documented override is given;
- updates the strict pilot validator for the two-branch export.

## Claim boundary

This remains a pipeline audit.  The two branch path gains are not a
complete co-channel dual-polarization power model.  A later real
cellular-to-incumbent experiment must specify the cellular polarization,
power split, cross-polar discrimination, and receiver response before
combining polarization contributions.

## Installed files

- `scripts/21_0_prepare_p452_pilot.py`
- `matlab/run_p452_pilot.m`
- `scripts/21_1_validate_p452_pilot.py`
- `tests/test_p452_pilot_polarization_hotfix.py`

Leave `pilot.polarization_override: null` in `config/p452_pilot.yaml` for
the current `G/G` record.  Do not force `H` or `V` merely to pass the
pipeline gate.
