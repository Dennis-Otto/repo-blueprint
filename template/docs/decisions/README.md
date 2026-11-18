# Decisions

The decisions that shape this project, each with its reasons, so that a later change can see why things are as they are. A decision that changes an earlier one gets a new record, and the earlier one says which record replaces it.

Copy [the template](0000-template.md) to a file named after the number of your pull request, or of the issue that the pull request fixes, such as `0312-the-new-way.md`, and describe the decision in the pull request that makes it.

- **The index:** leave the rows below alone. The release writes the row of each new record and the status of each record from its own, so the newest records wait here for the next release; the website lists them at once.
- **The check:** The step *Records of decisions* of `scripts/check.sh` fails when two records share a number, when a file is no record, or when this index lists a record twice, names a file that doesn't exist, names a record by another number or lists the records out of order, and in the CI of a pull request when a new record carries neither number, with the number to take.
- **The fix:** `python3 .github/blueprint.py decisions --fix` fixes what only this index gets wrong, such as the order of the rows.
- **The numbers** have gaps, since each record takes the number of its pull request or issue.

| Record | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-decisions.md) | Record the decisions that shape the project | accepted |
