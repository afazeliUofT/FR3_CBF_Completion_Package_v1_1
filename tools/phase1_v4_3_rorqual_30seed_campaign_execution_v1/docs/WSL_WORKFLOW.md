# WSL workflow

The outer block verifies the release ZIP and launches the package wrapper in a child Bash process. The original WSL shell never receives an `exit` command. The wrapper pushes source, connects to Rorqual once using SSH multiplexing, submits the array/merge/finalizer DAG, retrieves the return even on scientific failure, and pushes compact evidence to GitHub.

If the local terminal is interrupted, rerun the same block. The remote active-run binding prevents duplicate campaign submission and reconnects to the existing campaign.
