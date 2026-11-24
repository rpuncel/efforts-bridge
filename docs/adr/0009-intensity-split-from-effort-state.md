# Intensity is split from Effort state

An Effort has an Effort state (open, done or canceled) and, only while open, an Intensity (on, ongoing, simmering or sleeping). Open Effort issues carry exactly one `intensity/` label and the matching option of the Project's Intensity field. Done and canceled show only in how the issue was closed, as completed or as not planned; there are no state labels and no Done or Canceled options on the field. We rejected a single six-value state carried by labels and a Project field, because it repeated what GitHub's own open and closed state already says, and let a closed issue keep a label or board column that looked live.

## Consequences

- When an issue closes, Sync clears its Intensity label and field. Moving the note back into an Intensity folder reopens the issue and sets them again.
- A board grouped by Intensity has no done or canceled columns; closed issues land in the "No Intensity" column unless the view filters them out.
- The `[efforts]` config keys still name all six Effort folders. Only the Project field key changed, from `project.state_field` to `project.intensity_field`.
