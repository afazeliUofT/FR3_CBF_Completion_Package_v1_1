# E3 all-site P.452 MATLAB recovery

The previous all-site run successfully froze and prepared all 19 terrain
profiles, but MATLAB stopped before writing propagation results because the
`table` constructor used a double-quoted string for the `VariableNames`
parameter name. MATLAB treated that scalar string as a table variable and
reported unequal row counts.

This recovery:

- reuses the already frozen/reviewed terrain and prepared inputs;
- uses the backwards-compatible character-vector name-value syntax;
- runs a minimal MATLAB table-construction probe first;
- adds explicit column/table dimension assertions;
- reruns all 19 P.452 paths;
- validates all 798 rows;
- independently checks monotonicity and exact Site-18 regression;
- pushes the source and evidence to GitHub.

Run only:

```bash
bash RUN_E3_ALL_SITE_P452_MATLAB_RECOVERY_DROPIN.sh
```
