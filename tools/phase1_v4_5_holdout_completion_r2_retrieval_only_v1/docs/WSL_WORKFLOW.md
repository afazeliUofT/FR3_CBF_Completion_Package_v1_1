# WSL workflow

The outer block verifies this drop-in archive and executes the internal wrapper in a child Bash process. The internal wrapper performs one MFA-authenticated SSH transfer session, verifies the remote and local hashes, audits the final holdout, updates GitHub without force-pushing, and opens the Windows return folder. The original WSL terminal remains open on success or failure.
