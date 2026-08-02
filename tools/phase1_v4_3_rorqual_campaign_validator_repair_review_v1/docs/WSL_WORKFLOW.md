# WSL workflow

The outer copy-paste block runs this package inside a child Bash process. Any
`exit` occurs only in that child. The original interactive WSL terminal always
returns to its prompt. The workflow is local-only and requires no MFA or Slurm.
