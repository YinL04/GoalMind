from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch

from app import agent
from app.prompts import ANSWER_PROMPT, JSON_REPAIR_PROMPT, PLANNER_PROMPT, REPLAN_PROMPT
from app.schemas import ExecutedStep, FootballFanAnswer, QuestionExtraction
from app.services.query_builder import build_football_queries


class AgentCoreTests(unittest.TestCase):
    def test_prompts_format_without_json_brace_errors(self) -> None:
        PLANNER_PROMPT.format(
            date_context="2026-05-19",
            question="q",
            extraction="{}",
            fallback_queries="- query",
        )
        REPLAN_PROMPT.format(
            date_context="2026-05-19",
            question="q",
            extraction="{}",
            execution_summary="summary",
            fallback_queries="- query",
        )
        ANSWER_PROMPT.format(
            question="q",
            date_context="2026-05-19",
            extraction="{}",
            plan="{}",
            context="context",
            sources="source",
        )
        JSON_REPAIR_PROMPT.format(schema_name="Schema", bad_content="bad")

    def test_query_builder_uses_date_context(self) -> None:
        queries = build_football_queries(
            "今晚阿森纳对拜仁怎么看",
            "Arsenal",
            "Bayern Munich",
            "UEFA Champions League",
            date_context="2026-05-19 (当前日期 2026-05-19)",
        )

        self.assertTrue(any("2026-05-19" in query for query in queries))
        self.assertTrue(any("Arsenal vs Bayern Munich" in query for query in queries))

    def test_relative_date_resolution(self) -> None:
        today = date(2026, 5, 19)

        self.assertEqual(agent._resolve_question_date("今晚", today), today)
        self.assertEqual(agent._resolve_question_date("明天", today), date(2026, 5, 20))
        self.assertEqual(agent._resolve_question_date("5月21日", today), date(2026, 5, 21))

    def test_fallback_plan_uses_fetch_top_n_env_with_bounds(self) -> None:
        extraction = QuestionExtraction(team_a="Arsenal")

        with patch.dict(os.environ, {"FOOTBALL_AGENT_FETCH_TOP_N": "5"}, clear=False):
            plan = agent._fallback_plan("阿森纳怎么看", extraction, ["Arsenal team news"])

        self.assertEqual(plan.steps[0].fetch_top_n, 3)

    def test_select_urls_ranks_trusted_sources_and_filters_low_value(self) -> None:
        results = [
            {"title": "Video highlights", "href": "https://youtube.com/watch?v=1", "snippet": "highlights"},
            {
                "title": "Arsenal team news and injury update 2026",
                "href": "https://www.bbc.com/sport/football/example",
                "snippet": "latest injury and lineup preview",
            },
            {
                "title": "Forum preview",
                "href": "https://example-blog.invalid/post",
                "snippet": "match preview",
            },
        ]

        urls = agent._select_urls(results, limit=2)

        self.assertEqual(urls[0], "https://www.bbc.com/sport/football/example")
        self.assertNotIn("https://youtube.com/watch?v=1", urls)

    def test_execution_quality_check_requests_replan_for_thin_material(self) -> None:
        thin_steps = [
            ExecutedStep(
                id="search_1",
                purpose="test",
                query="Arsenal news",
                search_results=[],
                fetched_pages=[],
            )
        ]

        self.assertTrue(agent._execution_needs_replan(thin_steps))

    def test_sanitize_answer_removes_betting_language_variants(self) -> None:
        answer = FootballFanAnswer(
            short_answer="This is a guaranteed win and good odds angle.",
            match="A vs B",
            teams=["A", "B"],
            likely_game_flow="不要下注，也不要看盘口。",
            fan_takeaway="No betting advice.",
            uncertainty_note="避免稳赚表达。",
        )

        sanitized = agent._sanitize_answer(answer)
        combined = " ".join(
            [
                sanitized.short_answer,
                sanitized.likely_game_flow,
                sanitized.fan_takeaway,
                sanitized.uncertainty_note,
            ]
        )

        self.assertNotIn("guaranteed win", combined.lower())
        self.assertNotIn("odds", combined.lower())
        self.assertNotIn("下注", combined)
        self.assertNotIn("盘口", combined)
        self.assertNotIn("稳赚", combined)


if __name__ == "__main__":
    unittest.main()
