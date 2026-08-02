# WSL workflow contract

The user-facing drop-in executes strict work in a child Bash process. Any
`exit` occurs only inside that child. The original interactive WSL shell always
returns to its prompt and prints:

- `WSL_TERMINAL_CLOSE_REQUESTED=NO`
- `WSL_TERMINAL_REMAINS_OPEN=YES`
- `RETURNED_TO_ORIGINAL_WSL_PROMPT=YES`

The wrapper contacts Rorqual, requests CPU resources only, and reuses preserved
campaign channels. It neither regenerates a channel nor reruns a confirmatory
seed.
