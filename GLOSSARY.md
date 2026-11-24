# Efforts Bridge

A personal task system. Obsidian is where efforts are thought about and captured, and the Effort note is authoritative, status included. GitHub is where that status is published and read, and `gh-inbox` carries attention from GitHub into the vault and efforts from the vault out to GitHub.

## Efforts

**Effort**:
A piece of personal work bigger than a checkbox, with its own lifecycle.
_Avoid_: Project, task, initiative

**Effort note**:
The Obsidian note that is the authoritative record of one Effort; its file name is the Effort's title.
_Avoid_: Effort file, page

**Effort issue**:
The GitHub issue in the Personal repo that mirrors one Synced effort. It never leaves the Personal repo; the Effort note stays your personal working copy regardless of what happens on Team repos.
_Avoid_: Ticket, task issue

**Synced effort**:
An Effort note that has opted in to Sync by carrying the `gh` tag.
_Avoid_: Tracked effort, public effort

**Effort state**:
Whether an Effort is still live: open, done or canceled. Done and canceled are terminal.
_Avoid_: Status, stage, column

**Intensity**:
How much attention an open Effort is getting: on, ongoing, simmering or sleeping. Only open Efforts have an Intensity.
_Avoid_: State, priority, heat

**Effort folder**:
A vault folder that holds Effort notes. There is one Intensity folder per Intensity, where open Efforts live, and one terminal folder each for done and canceled Efforts, which no longer have an Intensity.
_Avoid_: State folder, bucket

**Area**:
A standing domain of responsibility an Effort belongs to, written as an `area/…` tag and mirrored as a label of the same name.
_Avoid_: Category, topic

**Parent effort**:
The Effort named by an Effort note's first `up` link; its Effort issue becomes the parent of this one.
_Avoid_: Epic, up-effort

**Related effort**:
Any Effort linked from an Effort note by a `related` link or by an `up` link after the first.
_Avoid_: Linked effort, sibling

**Task**:
A checkbox inside an Effort note. Tasks never become issues of their own; one that outgrows a checkbox becomes a new Effort.
_Avoid_: Todo, sub-task, item

## Daily and weekly notes

**Daily note**:
The Periodic Notes note for one calendar day.
_Avoid_: Journal, today's page

**Weekly note**:
The Periodic Notes note for one calendar week.
_Avoid_: Weekly review

**Log**:
The `## Log` section of a Daily note, one bullet per update.

**Log entry**:
A bullet in a Log that links to an Effort note. Bullets without an Effort link are private and are not Log entries.
_Avoid_: Update, status note, log line

**Posted log entry**:
A Log entry already published as a comment on its Effort issue; it is never posted again.

**Owned block**:
Text between a pair of `gh-inbox` marker comments. `gh-inbox` owns it and replaces it on every run; anything outside it belongs to the user.
_Avoid_: Managed section, generated region

## Attention

**Inbox**:
The Owned block in a Daily note listing GitHub items that want attention today.
_Avoid_: Dashboard, feed, notifications

**Inbox item**:
One pull request, issue or notification thread shown in the Inbox, de-duplicated by URL.
_Avoid_: Notification, task, entry

**Waiting on you**:
The capped part of the Inbox holding recent Inbox items that ask something of the user directly: review requests, mentions and replies.
_Avoid_: Urgent, action items

**Oldest**:
The capped part of the Inbox holding the stalest Inbox items, to close or bump. Optional to handle.
_Avoid_: Stale, backlog

**Hidden items**:
Inbox items that fall outside both Waiting on you and Oldest; shown only as a count.

**Heartbeat**:
The "updated at" stamp inside the Inbox. Missing or not today's means the daily run didn't happen.
_Avoid_: Health check, last run

**Triage**:
The weekday habit of clearing Waiting on you.
_Avoid_: Inbox zero, review

## Repos

**Repo tier**:
How closely the user follows a repo: Core, Curious or Unsorted.
_Avoid_: Priority, watch level

**Core repo**:
A repo the user watches for all activity on GitHub.
_Avoid_: Main repo, watched repo

**Curious repo**:
A repo the user does not watch but wants to skim weekly through the Digest.
_Avoid_: Unwatched repo, optional repo

**Unsorted repo**:
A repo in one of the user's orgs that isn't yet a Core or Curious repo; treated as Curious until sorted.
_Avoid_: New repo

**Personal repo**:
The one repo that holds every Effort issue.
_Avoid_: Efforts repo, home repo

**Team repo**:
A repo owned by a team the user works with; the destination of Promotion.

**Team copy**:
The issue that Promotion creates on a Team repo. Sync never touches it.
_Avoid_: Promoted issue, team mirror

## Workflows

**Watch cleanup**:
The one-time sorting of watched repos into Core and Curious, and unwatching the Curious ones.
_Avoid_: Unsubscribe, prune

**Digest**:
The weekly Owned block in a Weekly note that flags notable releases, features and design discussions in Curious and Unsorted repos.
_Avoid_: Newsletter, summary, report

**Interest rule**:
A plain-language criterion for what the Digest flags.
_Avoid_: Filter, digest rule

**Sync**:
The one-way push from the vault to GitHub, made of parts that each push one kind of note to its issues. GitHub never writes back to the vault, except for issue URLs. Effort sync is the only part so far.
_Avoid_: Mirror, export, two-way sync

**Effort sync**:
The part of Sync that pushes Effort notes to Effort issues, the efforts Project, and Log entry comments.
_Avoid_: Sync, when only this part is meant

**Promotion**:
Copying an issue from the Personal repo to a Team repo as a Team copy, cross-linked to the original, which stays where it is. It is usually done for issues that aren't Effort issues; an Effort issue that gets promoted keeps syncing as before.
_Avoid_: Escalation, publish, transfer, move

**Habit nudge**:
A manually set up Reminder or Calendar block that prompts Triage or the Digest review.
_Avoid_: Notification, alarm
