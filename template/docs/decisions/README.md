# Decisions

The decisions that shape this project, each with its reasons, so that a later change can see why things are as they are. A decision that changes an earlier one gets a new record, and the earlier one says which record replaces it.

Copy [the template](0000-template.md) to the next free number, add its row below, and describe the decision in the pull request that makes it. The step *Records of decisions* of `scripts/check.sh` fails when two records share a number, when the numbers skip one, or when this index lists a record twice, misses one, names a file that doesn't exist or lists the records out of order, with the numbers and the files it found: once `main` is merged into a pull request whose number another one took first, take the next free number, for the file and its row. `python3 .github/blueprint.py decisions --fix` fixes what only this index gets wrong, such as a missing row or the order of the rows.

| Record | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-decisions.md) | Record the decisions that shape the project | accepted |
