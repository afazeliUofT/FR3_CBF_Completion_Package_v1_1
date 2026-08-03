# Wall-time and resource policy

R1 established a censored lower bound: the monolithic five-pass job did not
finish in 12 minutes. Requesting only a small increase for the same monolithic
job would risk another avoidable timeout.

R2 uses pass parallelization and requests `00:20:00` per pass. This is a fair
upper bound because:

1. it is only 1.67 times the observed 12-minute lower bound;
2. each job computes one pass rather than all five;
3. the mode library is six times larger than the highest completed reference
   (`7776` versus `1296` modes);
4. only about 0.73 GiB was used in R1, so memory is reduced to 4 GiB;
5. a failure affects only one pass and does not force rerunning completed passes.

No multi-hour request is made.
