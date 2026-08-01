# Not executed in the build environment

The actual Rorqual H100 job cannot be executed from this build container because it has neither Alliance SSH credentials nor an H100. The package performs that single remote gate from the user's WSL session and always retrieves a compact success/failure return.
