# Repository Layout

This is a single Git repository with one submodule. Setup, workflow, and
resource docs: `SETUP.md`, `WORKFLOW.md`, `RESOURCES.md`.

- Root repository: project documentation, `workspace.yaml`, `pyproject.toml`
  / `uv.lock`, and the production code in `code/ba-production`. Commit code
  changes here, not in a nested repo.
- `code/carocut` is a Git submodule of https://github.com/bilibili/carocut.
  Run `git submodule update --init` after cloning. Do not commit local carocut
  patches into the submodule pin without pushing them upstream.
- Dependencies are installed per checkout: `uv sync` (Python, root `.venv`)
  and `npm ci` in `code/ba-production`. Do not symlink `.venv`,
  `node_modules`, or the submodule from another checkout.
- `data`, `videos`, `attachments`, `local`, and `temp` under the repository
  root are local resources and are not versioned. A fresh clone does not have
  them; they live only in the primary checkout on the production machine.
  In another checkout, point scripts at the shared asset library with
  `BA_ASSETS_ROOT` or an untracked `.ba-assets-root` file (see `SETUP.md`);
  `data/` and `local/` are read from there, `videos/` and `temp/` are
  written in the current checkout. Do not symlink these directories.
- Never commit secrets from `local/.env`, downloaded media, caches, or dependencies.
