# E3 all-site terrain freeze and P.452 basic-loss drop-in

Run only:

```bash
bash RUN_E3_ALL_SITE_TERRAIN_FREEZE_AND_P452_DROPIN.sh
```

The master wrapper:

1. verifies the current branch and all 19 terrain inputs;
2. opens the 19-page terrain PDF;
3. requires an exact interactive human-review confirmation;
4. freezes the terrain decision;
5. creates one P.452 input for each of the 19 unique modelled BS sites;
6. runs the pinned validated P.452-18 v18.0 implementation under MATLAB R2026a;
7. validates all 798 basic-loss/path-gain rows;
8. generates site-level review tables and figures;
9. pushes source and evidence to the existing GitHub branch.

This stage does not apply final sector beam gains or earth-station tracking
gains and is not a paper or compliance result.
