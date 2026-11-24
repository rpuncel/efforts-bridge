# Effort issues stay in the Personal repo; Promotion is copy-only

Every Effort issue lives in the Personal repo for its whole life. Promotion copies an issue to a Team repo as a Team copy, cross-linked both ways, and the original stays where it is. An Effort issue that gets promoted keeps syncing from its Effort note as before, and Sync never touches the Team copy. More broadly, Team repo work never gets an Effort note, whether it was promoted or started on a Team repo: the Effort note is authoritative only within the Personal repo ([ADR 0001](0001-one-way-sync-effort-note-authoritative.md)). We rejected moving the issue to the Team repo (`gh issue transfer`), because Sync would then write into a repo the team owns, the note's issue URL would have to be rewritten after every move, and personal labels would be dropped on the way.

## Consequences

- The note's `gh-issue` URL is never updated after Promotion, so [ADR 0003](0003-match-notes-by-issue-url.md) rests on note renames alone.
- A Team copy and its original can drift apart; the cross-links are the only tie between them.
- Reversing this means teaching Sync to write to Team repos and to follow issues that moved.
