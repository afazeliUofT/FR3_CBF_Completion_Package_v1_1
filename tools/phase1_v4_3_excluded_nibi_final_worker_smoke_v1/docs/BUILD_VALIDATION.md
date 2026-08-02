# Build validation

The release build performs:

- Python and Bash syntax checks;
- focused tests of locked inputs, native authorization, exact scientific
  reconstruction, deliberate trace-tamper detection, success and diagnostic
  return packaging, Git concurrency/stale-push behavior, and scope guards;
- exact verification of the returned locked-package build/review archive;
- exact version binding to Python 3.12.4, NumPy 2.4.2, Pandas 2.3.3, SciPy
  1.17.0, PyTorch 2.9.1/CUDA 12.6, and Sionna-no-RT 2.0.1;
- normal, concurrent-rebase, and stale non-force Git simulations;
- child-process terminal-continuation simulation for success and nonzero exits;
- ZIP CRC, internal manifests, clean-extraction tests, and forbidden-artifact
  scans.

The real Nibi H100 job is not executable in the build environment. It is the
purpose of this package.
