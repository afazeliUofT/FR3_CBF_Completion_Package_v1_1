# Local steering hardening and Narval pilot preparation

All non-heavy work in this stage ran locally in WSL. No SSH, Slurm, Narval,
or Nibi job was started.

The generated pilot package targets Narval only, uses a Narval-specific
virtual environment and scratch directory, requests one full A100 40 GB GPU,
and generates Sionna channels in user chunks to fit that GPU.

The previously generated Nibi FR3 bundle with SHA-256
a6ad7c3e202b57ff002b330b1d2c4e0f5b58a90b10fb7e64d6ae86c7069bef69
is superseded and must not be run.
