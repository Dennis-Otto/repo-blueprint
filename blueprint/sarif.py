"""The findings of an analysis where code scanning can't keep them: on a private
repository without GitHub Code Security, CodeQL lists what it found in the summary of
its check and as annotations, and fails on what code scanning would stop in a pull
request (decision 0081)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from blueprint.annotate import Annotation
from blueprint.github import Json

# What the rules of main stop, by the thresholds of code scanning that the blueprint
# sets: an error, or a security alert of high or critical severity, whose
# security-severity is 7.0 or more.
HIGH = 7.0
# The names of the security severities, from their lowest score, as GitHub ranks them.
RANKS = ((9.0, "critical"), (7.0, "high"), (4.0, "medium"), (0.0, "low"))


@dataclass(frozen=True)
class Finding:
    tool: str
    rule: str
    # error, warning or note, as the result or its rule names it.
    level: str
    # The security-severity of a security alert, none for a problem of quality.
    severity: float | None
    message: str
    path: str
    line: int

    @property
    def stops(self) -> bool:
        """Whether code scanning would stop a pull request that adds it."""
        return self.level == "error" or (
            self.severity is not None and self.severity >= HIGH
        )

    @property
    def kind(self) -> str:
        if self.severity is None:
            return self.level
        rank = next(name for score, name in RANKS if self.severity >= score)
        return f"{rank} security alert"

    def annotation(self) -> Annotation:
        return Annotation(
            f"{self.tool}: {self.rule}", self.message, self.path, self.line
        )


def rules_of(run: Json) -> dict[str, Json]:
    """The rules of a run by their id: those of the tool and of its extensions, where
    CodeQL keeps the rules of its query packs."""
    tool = run.get("tool", {})
    parts = [tool.get("driver", {}), *tool.get("extensions", [])]
    return {rule["id"]: rule for part in parts for rule in part.get("rules", [])}


def severity_of(rule: Json) -> float | None:
    raw = rule.get("properties", {}).get("security-severity")
    try:
        return None if raw is None else float(raw)
    except (TypeError, ValueError):
        return None


def findings(sarif: Json) -> list[Finding]:
    """Every result of every run of a SARIF document."""
    if not isinstance(sarif, dict):
        raise ValueError("a SARIF document is an object of JSON")
    found = []
    for run in sarif.get("runs", []):
        tool = run.get("tool", {}).get("driver", {}).get("name", "The analysis")
        rules = rules_of(run)
        for result in run.get("results", []):
            name = result.get("ruleId") or result.get("rule", {}).get("id", "")
            rule = rules.get(name, {})
            level = result.get("level") or rule.get("defaultConfiguration", {}).get(
                "level", "warning"
            )
            place = (result.get("locations") or [{}])[0].get("physicalLocation", {})
            found.append(
                Finding(
                    tool=tool,
                    rule=name,
                    level=level,
                    severity=severity_of(rule),
                    message=result.get("message", {}).get("text", ""),
                    path=place.get("artifactLocation", {}).get("uri", ""),
                    line=place.get("region", {}).get("startLine", 0),
                )
            )
    return found


def cell(text: str) -> str:
    """Text for a cell of a table of Markdown, on one line."""
    return " ".join(text.split()).replace("|", "\\|")


def summary(found: Iterable[Finding], artifact: str) -> str:
    """The summary of the check: every finding, those that fail it first."""
    ordered = sorted(found, key=lambda item: (not item.stops, item.path, item.line))
    lines = [
        "### What the analysis found",
        "",
        "Code scanning isn't offered to this private repository, so the findings are"
        f" here and the SARIF files are the artifact `{artifact}` of this run. An"
        " error, or a security alert of high or critical severity, fails the check,"
        " as the rules of `main` would stop it with code scanning.",
        "",
    ]
    if not ordered:
        return "\n".join([*lines, "Nothing found."]) + "\n"
    lines += ["| Fails | Finding | Rule | Where |", "| --- | --- | --- | --- |"]
    for item in ordered:
        place = f"{item.path}:{item.line}" if item.line else item.path
        where = f"`{cell(place)}`" if place else "-"
        lines.append(
            f"| {'yes' if item.stops else 'no'} | {cell(item.message)}"
            f" | `{cell(item.rule)}` ({item.kind}) | {where} |"
        )
    return "\n".join(lines) + "\n"
