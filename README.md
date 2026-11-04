# efforts-bridge

`gh-inbox`: a config-driven Python CLI that bridges an Obsidian vault and GitHub (github.com or GitHub Enterprise) via the `gh` CLI. See [SPEC.md](SPEC.md).

## Repo layout

| Path | Owner | What |
|---|---|---|
| `SPEC.md` | both | The spec. Change it in the same PR as the docs/code it affects. |
| `docs/` | docs site | Quarto website, published to GitHub Pages. Shared facts live in `docs/_partials/`. |
| `pyproject.toml`, `src/gh_inbox/`, `tests/` | CLI | Poetry-built Click CLI. |
| `config.example.toml` | CLI | Example config with placeholder values only. |
| `.github/workflows/docs.yml` | docs site | Builds `docs/` and deploys to Pages. |
| `.github/workflows/ci.yml` | CLI | Lint and tests. |

## Privacy

This repo and its Pages site are public. Never commit work hostnames, org names or repo names. Real values live in a local config outside the repo (default `~/.config/gh-inbox/config.toml`) or a gitignored `config.local.toml`.
