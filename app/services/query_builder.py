from __future__ import annotations


def build_football_queries(
    question: str,
    team_a: str | None,
    team_b: str | None,
    competition: str | None,
) -> list[str]:
    competition_part = f" {competition}" if competition else ""

    if team_a and team_b:
        match = f"{team_a} vs {team_b}"
        queries = [
            f"{team_a} latest team news injuries suspension",
            f"{team_b} latest team news injuries suspension",
            f"{match} match preview{competition_part}",
            f"{match} expected lineups",
            f"{match} tactical analysis",
            f"{match} head to head",
            f"{team_a} recent form",
            f"{team_b} recent form",
        ]
    elif team_a:
        queries = [
            f"{team_a} latest team news injuries suspension",
            f"{team_a} recent form",
            f"{team_a} expected lineups tactical analysis",
            f"{team_a} match preview{competition_part}",
            f"{question} football news analysis",
        ]
    else:
        queries = [
            f"{question} football match preview",
            f"{question} latest team news injuries suspension",
            f"{question} expected lineups",
            f"{question} tactical analysis",
            f"{question} recent form",
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
