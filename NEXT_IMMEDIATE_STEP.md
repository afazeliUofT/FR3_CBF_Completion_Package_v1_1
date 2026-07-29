# Next Immediate Step

## Gate

`IMPLEMENT_LOCAL_STATIC_MYOPIC_AND_PREDICTIVE_CONTROLLERS`

## Work location

Local WSL. No new Nibi channel generation is needed.

## Required sequence

1. Use the validated full controller dataset under
   `data/real/full_topology_export_18696267_validated_v4`.
2. Implement and test, under the same information, delay, update period and
   slew limit:
   - common-scale oracle reference;
   - static nonuniform allocation;
   - myopic utility-aware safety;
   - virtual-queue baseline;
   - predictive/CBF safety filter.
3. Separate total-band and protected-band utility.
4. Include user-tail and outage metrics, not only network sum rate.
5. Construct the natural rate-limit counterexample around the steep coupling
   rise found in the frozen pass.
6. Do not launch a multi-seed campaign until the predictive method shows a
   safety-utility advantage over fair baselines.
