# WSL-to-Rorqual workflow

The outer WSL block verifies the package hash, ZIP CRC, and internal manifests,
then calls `RUN_V45_HOLDOUT_COMPLETION_R2_FROM_WSL.sh` in a child shell.

The local wrapper:

1. activates the repository virtual environment;
2. runs syntax, focused tests, the real R1-timeout audit, and the source-level
   pass-independence audit;
3. stages source without force-pushing;
4. uploads the hash-bound package to Rorqual;
5. submits a five-task CPU pass array and one assembly/merge job;
6. retrieves and verifies a compact return even after a nonzero exit;
7. pushes compact evidence and opens the Windows return folder.

The original WSL shell is never closed. All `exit` statements execute only in a
child Bash process.
