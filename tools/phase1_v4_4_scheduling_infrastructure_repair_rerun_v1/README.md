# Candidate v4.4 scheduling infrastructure-repair rerun

This standalone package repairs one non-scientific failure in the first
candidate-v4.4 protected-subband scheduling development replay.

All eleven Rorqual workers completed all five pass evaluations and wrote the
cell summaries and trace archives, but each worker then failed while serializing
`PASS_AUDITS.json`: NumPy arrays were passed to Python's standard JSON encoder.
The merge consequently had no completed seed summaries.

The repair changes only the replay driver's JSON adapter. The protected-subband
scheduler, candidate-v4.4 controller, floor, EESS constraints, tolerances,
locality limits, fixed RZF directions, and objective hierarchy are byte-for-byte
unchanged.

Execution reuses the eleven preserved campaign channels. It requests no GPU and
regenerates no channel. It does not rerun or authorize the 30-seed campaign.
