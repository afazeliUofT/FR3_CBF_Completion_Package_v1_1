# ETSI 403 recovery for Sionna topology readiness

Run only:

```bash
bash RUN_SIONNA2_TOPOLOGY_READINESS_ETSI_RECOVERY_DROPIN.sh
```

This resumes after the already-passed energy-weighted Sionna delay/source audit.

The ETSI source wrapper:

1. accepts a previously validated repository copy;
2. searches Windows Downloads for an already downloaded official PDF;
3. attempts a browser-like HTTP session with user agent, referer, cookies, and
   compressed transfer;
4. when ETSI still returns HTTP 403, opens the official ETSI directory/PDF in
   the Windows browser and waits inside the same drop-in for the download;
5. verifies exact published byte count, PDF header, EOF marker, and SHA-256;
6. resumes the custom 57-sector adapter, final evidence build, Git commit, and
   GitHub push.

No delay audit rerun is required.
