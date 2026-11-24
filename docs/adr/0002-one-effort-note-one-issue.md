# One Effort note is one Effort issue; Tasks stay checkboxes

Each Synced effort becomes exactly one Effort issue. The Tasks inside it stay checkboxes in the Owned block of the body, and a Task that outgrows a checkbox becomes a new Effort. We rejected the alternative of an issue or sub-issue per tagged task line: it is hard to reverse, because issue history, comments and Project items build up around whichever granularity you choose.

Hierarchy follows from the same rule. GitHub allows one parent per sub-issue, so only the first `up` link sets the Parent effort. Extra `up` links and all `related` links go in a "Related" line in the body.
