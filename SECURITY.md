# Security

## Built-in protections

- Uses Synology's documented `authenticate.cgi` for DSM Cookie authentication
- Defaults to the DSM `administrators` group
- Keeps configuration paths and commands in server-side `editor.conf`
- Requires POST, `text/plain`, `X-Requested-With`, and same-origin request signals for saving
- Limits files and requests to 2 MiB
- Disables Shell pathname expansion and does not use `eval` or `sh -c`
- Uses an atomic lock, a private temporary file, three backups, and same-directory replacement
- Preserves the original numeric owner, group, and mode when replacing a file
- Escapes configuration text before syntax highlighting
- Sends CSP, `nosniff`, `no-referrer`, and `no-store` headers

## Boundary

- A non-empty `SynoToken` is only a request constraint; DSM Cookie authentication is the identity check.
- `ACCESS_MODE=authenticated` permits every signed-in DSM user to read, save, and trigger the configured post-save action.
- `CONFIG_FILE` must be a regular file, not a symbolic link.
- ACLs and extended attributes are not preserved portably by this dependency-free Shell implementation.
- `lifecycle` directly runs the package's own `start-stop-status`; deploy it only with a compatible package account.
- `script` mode trusts the server-side `RESTART_SCRIPT`.
- The editor does not validate configuration syntax or detect service port conflicts.
- Keep the package on DSM's lower-privilege package account whenever possible.

## Deployment checks

Test signed-out access, non-administrator access, saving, backup rotation, restart failure, and concurrent saves on the target DSM version.

Report security issues privately to the repository owner.
