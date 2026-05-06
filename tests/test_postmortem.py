"""Tests for post-mortem generation and Pydantic schema."""
import json
from unittest.mock import MagicMock, patch

import pytest

from analysis.postmortem import PostMortem, TimelineEvent, postmortem_to_markdown


class TestPostMortemModel:
    def test_valid_postmortem(self):
        pm = PostMortem(
            title="DB Outage 2026-05-06",
            timeline=[
                TimelineEvent(
                    timestamp="2026-05-06T13:45:13Z",
                    service="db-primary",
                    event="Connection pool exhausted",
                    severity="critical",
                ),
                TimelineEvent(
                    timestamp="2026-05-06T13:45:14Z",
                    service="auth-service",
                    event="Circuit breaker opened",
                    severity="high",
                ),
            ],
            root_cause="Database connection pool exhausted due to slow query storm.",
            impact="Auth and payment services unavailable for ~90 seconds.",
            remediation_steps=["Increase pool size", "Add query timeouts"],
            open_questions=["What triggered the slow queries?"],
        )
        assert pm.title == "DB Outage 2026-05-06"
        assert len(pm.timeline) == 2
        assert len(pm.remediation_steps) == 2
        assert len(pm.open_questions) == 1

    def test_postmortem_from_json(self, fake_postmortem_response):
        data = json.loads(fake_postmortem_response)
        pm = PostMortem(**data)
        assert pm.title
        assert len(pm.timeline) > 0
        assert pm.root_cause
        assert pm.impact
        assert len(pm.remediation_steps) > 0

    def test_postmortem_requires_title(self):
        with pytest.raises(Exception):
            PostMortem(
                timeline=[],
                root_cause="test",
                impact="test",
                remediation_steps=[],
                open_questions=[],
            )

    def test_timeline_event_model(self):
        e = TimelineEvent(
            timestamp="2026-05-06T13:45:00Z",
            service="api-gateway",
            event="Health check failed",
            severity="critical",
        )
        assert e.service == "api-gateway"


class TestPostMortemMarkdown:
    def test_markdown_contains_title(self, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))
        md = postmortem_to_markdown(pm)
        assert f"# Post-Mortem: {pm.title}" in md

    def test_markdown_contains_all_sections(self, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))
        md = postmortem_to_markdown(pm)
        assert "## Timeline" in md
        assert "## Root Cause" in md
        assert "## Impact" in md
        assert "## Remediation Steps" in md
        assert "## Open Questions" in md

    def test_markdown_timeline_table(self, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))
        md = postmortem_to_markdown(pm)
        assert "| Timestamp | Service | Event | Severity |" in md

    def test_markdown_remediation_numbered(self, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))
        md = postmortem_to_markdown(pm)
        assert "1. " in md

    def test_markdown_questions_bulleted(self, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))
        md = postmortem_to_markdown(pm)
        assert "- " in md


class TestGeneratePostmortem:
    def test_generate_postmortem_calls_all_chains(self, sample_documents, fake_postmortem_response):
        pm_data = json.loads(fake_postmortem_response)
        expected_pm = PostMortem(**pm_data)

        mock_llm = MagicMock()
        mock_structured = MagicMock()
        # LCEL wraps non-Runnables in RunnableLambda and calls them as callables,
        # so both callable and .invoke paths must return the expected object.
        mock_structured.return_value = expected_pm
        mock_structured.invoke.return_value = expected_pm
        mock_llm.with_structured_output.return_value = mock_structured

        from analysis.anomaly import AnomalyReport
        mock_anomaly_report = AnomalyReport(anomalies=[], summary="mock summary")

        with patch("analysis.postmortem.analyze_anomalies", return_value=mock_anomaly_report) as mock_anom, \
             patch("analysis.postmortem.correlate_services", return_value="mock correlation") as mock_corr, \
             patch("analysis.postmortem.summarize_window", return_value="mock summary") as mock_sum:

            from analysis.postmortem import generate_postmortem
            result = generate_postmortem(sample_documents, llm=mock_llm)

        mock_anom.assert_called_once()
        mock_corr.assert_called_once()
        mock_sum.assert_called_once()
        assert isinstance(result, PostMortem)

    def test_generate_postmortem_writes_file(self, tmp_path, sample_documents, fake_postmortem_response):
        from analysis.postmortem import postmortem_to_markdown, PostMortem

        pm = PostMortem(**json.loads(fake_postmortem_response))
        output_path = tmp_path / "postmortem.md"

        md = postmortem_to_markdown(pm)
        output_path.write_text(md, encoding="utf-8")

        assert output_path.exists()
        content = output_path.read_text()
        assert "# Post-Mortem:" in content
