# The repo is public; work identifiers live only in a gitignored config

The repo and its Pages site are public, so committed files use placeholders for the Enterprise hostname, org and repo names. The real values live only in a gitignored local config. We rejected a private repo because GitHub Pages hosts the docs site for free only from a public repo. A leaked hostname or org name can't be un-leaked, which is why the rule is absolute: no work identifiers in any committed file, including examples and tests.
