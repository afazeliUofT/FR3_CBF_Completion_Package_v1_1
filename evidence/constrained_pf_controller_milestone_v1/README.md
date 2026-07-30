# Constrained proportional-fair controller milestone

This one-seed local milestone compares a static safe constrained-PF action, a delayed myopic constrained-PF controller, and a predictive reachability constrained-PF controller on the validated 228-user full-topology export.

Incumbent safety is hard. Twenty-one nominally coverage-limited users are reported separately. The 207 eligible users are checked against `max(0.1,0.9*R_nominal)` before PF utility is assessed.

This is not yet a formal CBF theorem or a TWC paper result.
