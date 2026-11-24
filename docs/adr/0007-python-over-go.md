# Python with Poetry and Click, not Go

`gh-inbox` is a Python CLI built with Poetry and Click, installed with `uv tool install` or `pipx`, and it calls the `gh` CLI for GitHub access. Go was the real alternative: a single binary, and `go-gh` handles Enterprise hosts natively. We chose Python because most of the work is editing markdown and frontmatter in place, which is easier there, and shelling out to `gh` gives the same multi-host auth without a client library. Switching later means a rewrite.
