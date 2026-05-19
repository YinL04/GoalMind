from __future__ import annotations

import re


def build_football_queries(
    question: str,
    team_a: str | None,
    team_b: str | None,
    competition: str | None,
    date_context: str | None = None,
) -> list[str]:
    competition_part = f" {competition}" if competition else ""
    compact_date = _compact_date_context(date_context)
    date_part = f" {compact_date}" if compact_date else ""

    if team_a and team_b:
        match = f"{team_a} vs {team_b}"
        queries = [
            f"{team_a} latest team news injuries suspension{date_part}",
            f"{team_b} latest team news injuries suspension{date_part}",
            f"{match} match preview{competition_part}{date_part}",
            f"{match} expected lineups{date_part}",
            f"{match} tactical analysis{competition_part}{date_part}",
            f"{match} head to head{competition_part}",
            f"{team_a} recent form{date_part}",
            f"{team_b} recent form{date_part}",
        ]
    elif team_a:
        queries = [
            f"{team_a} latest team news injuries suspension{date_part}",
            f"{team_a} recent form{date_part}",
            f"{team_a} expected lineups tactical analysis{date_part}",
            f"{team_a} match preview{competition_part}{date_part}",
            f"{question} football news analysis{date_part}",
        ]
    else:
        queries = [
            f"{question} football match preview{date_part}",
            f"{question} latest team news injuries suspension{date_part}",
            f"{question} expected lineups{date_part}",
            f"{question} tactical analysis{date_part}",
            f"{question} recent form{date_part}",
        ]

    return _dedupe([query.strip() for query in queries if query.strip()])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            output.append(item)
    return output


def _compact_date_context(date_context: str | None) -> str:
    if not date_context:
        return ""
    match = re.search(r"\b20\d{2}-\d{2}-\d{2}\b", date_context)
    if match:
        return match.group(0)
    return date_context
