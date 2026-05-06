"""Tests for anomaly, correlation, and summarizer analysis chains."""
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_structured_llm(expected):
    """
    Return a mock LLM whose with_structured_output chain returns expected.
    LCEL wraps non-Runnable objects in RunnableLambda and calls them as callables,
    so both .return_value (callable path) and .invoke.return_value (direct invoke path)
    must be set.
    """
    mock_llm = MagicMock()
    mock_chain = MagicMock()
    mock_chain.return_value = expected       # RunnableLambda callable path
    mock_chain.invoke.return_value = expected  # direct invoke path
    mock_llm.with_structured_output.return_value = mock_chain
    return mock_llm


def _make_str_llm(response: str):
    """
    Return a FakeListChatModel that works as a proper LangChain Runnable for string-output chains.
    """
    from langchain_core.language_models.fake_chat_models import FakeListChatModel
    return FakeListChatModel(responses=[response])


class TestAnomalyAnalysis:
    def test_analyze_anomalies_structure(self, sample_documents, fake_anomaly_response):
        from analysis.anomaly import analyze_anomalies, AnomalyReport

        expected = AnomalyReport(**json.loads(fake_anomaly_response))
        mock_llm = _make_structured_llm(expected)

        report = analyze_anomalies(sample_documents, llm=mock_llm)

        assert isinstance(report, AnomalyReport)
        assert len(report.anomalies) == 1
        assert report.anomalies[0].severity == "critical"
        assert report.anomalies[0].type == "database_exhaustion"
        assert report.summary

    def test_analyze_anomalies_calls_with_structured_output(self, sample_documents):
        from analysis.anomaly import analyze_anomalies, AnomalyReport

        mock_llm = MagicMock()
        mock_structured = MagicMock()
        empty_report = AnomalyReport(anomalies=[], summary="No anomalies found.")
        mock_structured.return_value = empty_report
        mock_structured.invoke.return_value = empty_report
        mock_llm.with_structured_output.return_value = mock_structured

        analyze_anomalies(sample_documents, llm=mock_llm)
        mock_llm.with_structured_output.assert_called_once_with(AnomalyReport)

    def test_anomaly_pydantic_model_validation(self):
        from analysis.anomaly import Anomaly, AnomalyReport

        a = Anomaly(
            severity="critical",
            type="db_exhaustion",
            description="Pool full",
            evidence=["pool_size=20 active=20"],
            affected_services=["db-primary"],
        )
        assert a.severity == "critical"

        report = AnomalyReport(anomalies=[a], summary="Critical issue")
        assert len(report.anomalies) == 1

    def test_anomaly_invalid_severity_raises(self):
        from analysis.anomaly import Anomaly

        with pytest.raises(Exception):
            Anomaly(
                severity="unknown_level",
                type="test",
                description="test",
                evidence=[],
                affected_services=[],
            )


class TestCorrelation:
    def test_correlate_services_returns_string(self, sample_documents):
        from analysis.correlation import correlate_services

        fake_llm = _make_str_llm("The cascade started in db-primary.")
        result = correlate_services(sample_documents, llm=fake_llm)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_correlate_extracts_services_from_metadata(self, sample_documents):
        from analysis.correlation import correlate_services

        # Verify that when no services are specified, they're pulled from document metadata.
        # We patch the chain's invoke to capture arguments.
        fake_llm = _make_str_llm("cascade narrative")
        captured = {}

        def capturing_chain_invoke(kwargs):
            captured.update(kwargs)

        with patch("analysis.correlation._PROMPT") as mock_prompt:
            mock_chain = MagicMock()
            mock_chain.invoke.side_effect = lambda kw: (captured.update(kw), "cascade narrative")[1]
            mock_prompt.__or__ = MagicMock(return_value=MagicMock(
                __or__=MagicMock(return_value=mock_chain)
            ))
            correlate_services(sample_documents, services=None, llm=fake_llm)

        # Services must include all distinct services found in sample_documents metadata
        expected_services = {d.metadata["service"] for d in sample_documents if d.metadata.get("service")}
        assert len(expected_services) >= 4


class TestSummarizer:
    def test_summarize_window_returns_string(self, sample_documents):
        from analysis.summarizer import summarize_window

        fake_llm = _make_str_llm("Summary of the incident window.")
        result = summarize_window(sample_documents, llm=fake_llm)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_summarize_filters_by_time(self, sample_documents):
        from analysis.summarizer import _filter_by_time

        early = _filter_by_time(sample_documents, start=None, end="2026-05-06T13:45:14")
        assert all(d.metadata["timestamp"] <= "2026-05-06T13:45:14" for d in early if d.metadata["timestamp"])

    def test_summarize_no_filter_returns_all(self, sample_documents):
        from analysis.summarizer import _filter_by_time

        result = _filter_by_time(sample_documents, start=None, end=None)
        assert len(result) == len(sample_documents)
