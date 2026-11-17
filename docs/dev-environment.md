---
type: problem
updated: 2026-11-17
status: current
---

# Dev environment: iCloud hides the venv

Related: [[stack-decision]], [[design-preview]]

**Symptom.** After `uv sync`, `import rozprava` failed with `ModuleNotFoundError`, even though the editable install's `rozprava.pth` was in site-packages and pointed at `src/`.

**Cause.** The repo lives on the Desktop, which syncs to iCloud Drive. iCloud sets the macOS `hidden` flag on dot-files and dot-folders and on everything inside them, including `.venv`. Python 3.14 skips `.pth` files that carry the hidden flag, so the editable install was ignored.

**Tried first.** `chflags nohidden` on the `.pth` file worked, but iCloud set the flag again within minutes.

**Fix.** The virtualenv lives outside iCloud at `~/.local/share/venvs/rozprava`, and `.venv` in the repo is a symlink to it. `uv` follows the symlink. To recreate it:

```sh
rm -rf .venv
UV_PROJECT_ENVIRONMENT="$HOME/.local/share/venvs/rozprava" uv sync
ln -s "$HOME/.local/share/venvs/rozprava" .venv
```

Also on this machine: `uv` came from Homebrew (`brew install uv`) on 17 Nov 2026.
