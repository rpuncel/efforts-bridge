# gh-inbox: Personal GitHub Task System Spec

One config-driven Python CLI (`gh-inbox`) built on the `gh` CLI. Host is configurable (GitHub Enterprise at work, github.com at home). Obsidian is where I think and capture, and the Effort note is authoritative; GitHub is the published view of Effort status ([ADR 0001](docs/adr/0001-one-way-sync-effort-note-authoritative.md)).

Repo: `efforts-bridge` (personal public GitHub). Stack: Python, Poetry as the build system, Click for the CLI ([ADR 0007](docs/adr/0007-python-over-go.md)). Installed and run via `uv tool install` / `uvx` or `pipx`; launchd calls the installed command by its full path (e.g. `~/.local/bin/...`).

## Step 0: Docs site first, in parallel with the build

Kick off two Claude Code sessions today: one builds a Quarto docs site from this spec, the other starts on the daily inbox (step 1). Review later by checking the docs against real behaviour; each mismatch is a spec bug or an implementation bug.

Why Quarto over Obsidian Publish: free on GitHub Pages, and the `{{< include >}}` shortcode keeps each fact in one partial file reused across pages.

Prompt for Claude Code:

> Using this spec, build a Quarto website in my personal public repo, published to GitHub Pages via a GitHub Actions workflow. Organise it as an overview page (how the parts fit and the daily and weekly loops) plus one page per tool I check: GitHub settings and notifications, the GitHub Project, Obsidian (vault folders, Periodic Notes, Tasks plugin, frontmatter conventions, daily note template), macOS launchd and alerts, Apple Reminders and Calendar, and the gh-inbox config file. Each tool page says what to check there and how it must line up with the other tools, linking to them. Put every shared fact (folder names, marker comments, label scheme, effort states, config keys) once in a `_partials/` file and pull it in with `{{< include >}}`; never duplicate content. Use placeholders for my Enterprise hostname, org and repo names; real values live only in a gitignored local config. Document the system as if it already exists. Stop once the site builds locally and the Pages workflow passes.

Privacy: no work hostnames, org names or repo names in committed files ([ADR 0006](docs/adr/0006-public-repo-private-config.md)).

### Review and feedback loop

1. Read the overview, then walk each tool page as if setting it up.
2. Leave feedback as GitHub issues on the repo, one per mismatch or change, labelled `spec`.
3. Have Claude Code apply each issue to both the spec and the docs in the same pull request, so they never drift.
4. When the implementation lands, reconcile: anything the code does that the docs don't say (or vice versa) becomes a `spec` issue too.

## Build order

1. Daily inbox (`gh-inbox` default command) + launchd job with failure alerts
2. One-time watch cleanup (`cleanup`)
3. Weekly digest (`digest`)
4. Obsidian → GitHub sync (`sync`) with daily-note log comments and Project field
5. Later: promotion of personal issues to team repos

## Shared config

- GitHub host, personal repo, GitHub Project for efforts
- Vault path
- Daily notes folder (verify — roughly `Calendar/Daily Notes`), filename `YYYY-MM-DD.md` (Periodic Notes)
- Weekly notes folder and filename format (Periodic Notes)
- Effort folders: one per Intensity (on, ongoing, simmering, sleeping), plus done and canceled
- Repo tiers: `core` and `curious`
- Digest interest rules
- Inbox caps

## 1. Daily inbox

Prompt for Claude Code:

> Write a small Python script, `gh-inbox`, driven by a config file. The config sets the GitHub host (GitHub Enterprise or github.com), the vault path, the daily notes folder (default "Calendar/Daily Notes") and the filename format YYYY-MM-DD.md. Use the `gh` CLI with `--hostname` to fetch three things: pull requests requesting my review, unread notifications, and open issues assigned to me. Render them as markdown checkboxes, each line linking to the item and naming its repo. Show two capped lists: "Waiting on you" (review requests, mentions and direct replies from roughly the last week, max ~10) and "Oldest" (the 5 stalest items to close or bump), plus one line with the count of hidden items. Stamp "updated at <time>" inside the block. Replace only the text between `<!-- gh-inbox:start -->` and `<!-- gh-inbox:end -->` in today's note. If the markers are missing, add them at the end of the note. If the note doesn't exist, exit with a clear message and don't create it. Stop when it runs cleanly against my repo, and don't add scheduling yet.

### launchd and failure visibility

- launchd job each weekday morning (catches up after sleep), plus a shell alias for manual refresh.
- Wrapper script: on non-zero exit, fire a persistent macOS alert (not a banner) including the log path.
- Heartbeat: the "updated at" stamp in the daily note. Missing or stale stamp = it didn't run.

## 2. One-time watch cleanup

Manual step: in GitHub notification settings, turn off automatic watching of new repos.

Prompt for Claude Code:

> Extend `gh-inbox` with a `cleanup` command that uses the same config and host setting. `cleanup init` lists every repo I watch via the `gh` API and writes them into the config under a `curious` tier. It keeps any existing `core` entries and never overwrites my edits. `cleanup` with no flags is a dry run: it prints which curious repos would be unwatched and how many unread notifications each one has. `cleanup --apply` unwatches those repos and marks their notifications read. Stop after the dry run works, and show me its output before applying anything.

Notes:

- Hand-sort the generated list into core vs curious (ten-minute edit). Why tiers: [ADR 0005](docs/adr/0005-core-and-curious-repo-tiers.md).
- Unwatched repos still notify when I'm mentioned, assigned, review-requested, or participating.
- Add myself to CODEOWNERS on repos I collaborate on heavily. Mark repos I create as core.

## 3. Weekly digest

Interest rules (starting point): significant features; releases with non-empty notes; juicy architectural or design discussions.

Prompt for Claude Code:

> Add a `digest` command. For curious repos, plus any repos in my orgs that aren't in the config yet, fetch the last seven days of releases, issues and pull requests. Skip releases with empty notes. Have Claude flag significant features and architectural or design discussions, with one line each and a link. List unsorted repos separately at the top under "new repos, please sort" (treated as curious until sorted). Write the digest between `<!-- gh-digest:start -->` and `<!-- gh-digest:end -->` markers in the current Periodic Notes weekly note, using a configurable folder and filename format. Re-running in the same week refreshes that block, and earlier weeks are never touched. Stop once one run produces a readable digest.

Review: Thursdays ~3pm, optional, marked free. Skipping weeks is fine; old digests age out with their weekly note.

## 4. Obsidian → GitHub sync

Model: one note = one issue. Checkbox tasks stay checkboxes ([ADR 0002](docs/adr/0002-one-effort-note-one-issue.md)). A task that outgrows a checkbox becomes its own effort note. An open Effort has an Intensity; done and canceled are terminal and have none ([ADR 0009](docs/adr/0009-intensity-split-from-effort-state.md)). Effort issues never leave the personal repo ([ADR 0008](docs/adr/0008-effort-issues-stay-in-personal-repo.md)).

Prerequisites: `gh auth refresh -s project` on the Enterprise host; confirm the Enterprise version supports Projects; create the efforts Project with an Intensity single-select field (On, Ongoing, Simmering, Sleeping).

Prompt for Claude Code:

> Add a `sync` command to `gh-inbox`, using the same config and host. It syncs one way, from Obsidian to GitHub, into my personal repo.
>
> Notes: any note in my efforts folders whose frontmatter tags include `gh` becomes one issue. The note title becomes the issue title. A note in an Intensity folder (on, ongoing, simmering, sleeping) keeps its issue open, with exactly one `intensity/` label and the matching option of an "Intensity" single-select field on a configured GitHub Project. Moving a note to done closes its issue as completed, and moving it to canceled closes it as not planned; either way, clear the Intensity label and field. Moving a note back into an Intensity folder reopens its issue and sets them again. Frontmatter `area/...` tags become labels named exactly the same, created if missing in one colour. After creating an issue, write its full URL into the note's frontmatter, and use that URL to match on later runs.
>
> Links: the first `up` link becomes the parent issue via sub-issues. Create parents before children. Extra `up` links and all `related` links go in a "Related" line in the body.
>
> Body: the script owns the content between `<!-- obsidian:start -->` and `<!-- obsidian:end -->`. That holds the Tasks plugin checkboxes, done state included, and any due dates as plain text.
>
> Log: in daily notes, bullets under `## Log` that contain a link to a synced effort note get posted as a comment on that issue. Only post bullets from days before today. After posting, mark the bullet so it never posts twice.
>
> Start with a dry run that prints the planned actions. Stop once a dry run and one real run work on a single test effort.

Gotchas:

- GitHub allows one parent per sub-issue; first `up` wins ([ADR 0002](docs/adr/0002-one-effort-note-one-issue.md)).
- Edits to the owned body section on GitHub get overwritten; discuss in comments ([ADR 0001](docs/adr/0001-one-way-sync-effort-note-authoritative.md)).
- Match on full issue URLs, so renaming a note doesn't orphan its issue ([ADR 0003](docs/adr/0003-match-notes-by-issue-url.md)).
- Effort issues never leave the personal repo, and sync never touches team copies ([ADR 0008](docs/adr/0008-effort-issues-stay-in-personal-repo.md)).

### Daily note template addition

Add a `## Log` heading. One bullet per update, starting with an effort link, e.g. `- [[Effort name]] got the pipeline green, waiting on review`. Bullets without an effort link stay private. Effort notes' backlinks panel shows the per-effort log for free. Why updates live here: [ADR 0004](docs/adr/0004-status-updates-from-daily-log.md).

## Habit nudges (set up manually)

Apple Reminder:

- Title: "GitHub triage: clear Waiting on You"
- Weekdays, ~30 minutes after start of day (after the inbox job runs), including Fridays off
- Alert at that time, plus a follow-up 2 hours later if unticked
- URL: `obsidian://` link to today's daily note
- Notes: "Done means the Waiting on You list is handled. Oldest is optional."

Calendar:

- Weekday morning 15-minute "GitHub triage" block
- Thursday 3pm optional "GitHub weekly digest" block, marked free

## 5. Later: promotion

Promotion is copy only ([ADR 0008](docs/adr/0008-effort-issues-stay-in-personal-repo.md)):

- Create a new issue on the team repo (a team copy) and cross-link it with the personal one in both directions. The original stays in the personal repo.
- Usually for personal repo issues that aren't effort issues. A promoted effort issue keeps syncing from its effort note, sync never touches the team copy, and the note's frontmatter URL doesn't change.
- Team repo work, promoted or started there, never gets an effort note.
