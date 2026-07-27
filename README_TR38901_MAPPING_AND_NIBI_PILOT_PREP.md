# TR 38.901 mapping and Nibi DLP-RZF pilot preparation

Run only:

```bash
bash RUN_TR38901_MAPPING_AND_NIBI_PILOT_PREP_DROPIN.sh
```

The drop-in:

1. verifies the successful topology-readiness commit and frozen inputs;
2. freezes a clause-level V19.4.0 used-subset mapping for a non-paper pilot;
3. computes and records the 8x8 pilot-array far-field justification;
4. audits Sionna 2.0.1 dual-polarization port order, positions, and orthogonal
   polarization steering bases;
5. builds a self-contained Nibi H100 pilot package for 57 sectors, four users
   per sector, nine frequency samples, local RZF, full inter-cell interference,
   and DLP projection on the protected 10 MHz sample;
6. pushes all readable source and preparation evidence to GitHub;
7. opens the folder containing the Nibi ZIP and checksum.

The bundle is not executed by this drop-in. It must first be independently
reviewed from the generated GitHub commit.

Sionna 2.0.1 `PanelArray` is instantiated with the explicit `element_vertical_spacing` and `element_horizontal_spacing` keywords. A live API probe runs before the port audit and the future Nibi environment repeats the construction check.
