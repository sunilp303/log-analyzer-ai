"""Tests for the Click CLI using CliRunner."""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from cli import cli
from analysis.anomaly import AnomalyReport, Anomaly
from analysis.postmortem import PostMortem

SAMPLE_DIR = Path(__file__).parent.parent / "sample_logs"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_vectorstore(sample_documents):
    """FAISS vectorstore mock that returns sample documents from docstore."""
    vs = MagicMock()
    mock_docstore = MagicMock()
    mock_docstore._dict = {str(i): doc for i, doc in enumerate(sample_documents)}
    vs.docstore = mock_docstore
    return vs


class TestIngestCommand:
    def test_ingest_local(self, runner, tmp_path):
        fake_vs = MagicMock()

        with patch("processing.vectorstore.build_vectorstore", return_value=fake_vs), \
             patch("processing.vectorstore.save_vectorstore") as mock_save:

            result = runner.invoke(cli, [
                "ingest",
                "--source", "local",
                "--path", str(SAMPLE_DIR / "app_errors.log"),
                "--vectorstore-path", str(tmp_path),
            ])

        assert result.exit_code == 0, result.output
        assert "Ingesting from local" in result.output
        mock_save.assert_called_once()

    def test_ingest_local_missing_path(self, runner, tmp_path):
        result = runner.invoke(cli, [
            "ingest", "--source", "local",
            "--vectorstore-path", str(tmp_path),
        ])
        assert result.exit_code != 0

    def test_ingest_cloudwatch_missing_log_group(self, runner, tmp_path):
        result = runner.invoke(cli, [
            "ingest", "--source", "cloudwatch",
            "--vectorstore-path", str(tmp_path),
        ])
        assert result.exit_code != 0


class TestAnalyzeCommands:
    def test_anomaly_command(self, runner, tmp_path, mock_vectorstore, sample_documents):
        mock_report = AnomalyReport(
            anomalies=[
                Anomaly(
                    severity="critical",
                    type="db_exhaustion",
                    description="Pool exhausted",
                    evidence=["pool_size=20"],
                    affected_services=["db-primary"],
                )
            ],
            summary="Critical DB issue.",
        )

        with patch("processing.vectorstore.load_vectorstore", return_value=mock_vectorstore), \
             patch("analysis.anomaly.analyze_anomalies", return_value=mock_report):

            result = runner.invoke(cli, [
                "analyze", "anomaly",
                "--vectorstore-path", str(tmp_path),
            ])

        assert result.exit_code == 0, result.output
        assert "1 anomalies" in result.output
        assert "Critical DB issue" in result.output

    def test_correlate_command(self, runner, tmp_path, mock_vectorstore):
        with patch("processing.vectorstore.load_vectorstore", return_value=mock_vectorstore), \
             patch("analysis.correlation.correlate_services", return_value="DB caused cascade."):

            result = runner.invoke(cli, [
                "analyze", "correlate",
                "--services", "db-primary,auth-service",
                "--vectorstore-path", str(tmp_path),
            ])

        assert result.exit_code == 0, result.output
        assert "DB caused cascade." in result.output

    def test_summarize_command(self, runner, tmp_path, mock_vectorstore):
        with patch("processing.vectorstore.load_vectorstore", return_value=mock_vectorstore), \
             patch("analysis.summarizer.summarize_window", return_value="Incident lasted 90 seconds."):

            result = runner.invoke(cli, [
                "analyze", "summarize",
                "--vectorstore-path", str(tmp_path),
            ])

        assert result.exit_code == 0, result.output
        assert "Incident lasted 90 seconds." in result.output

    def test_postmortem_command_stdout(self, runner, tmp_path, mock_vectorstore, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))

        with patch("processing.vectorstore.load_vectorstore", return_value=mock_vectorstore), \
             patch("analysis.postmortem.generate_postmortem", return_value=pm):

            result = runner.invoke(cli, [
                "analyze", "postmortem",
                "--vectorstore-path", str(tmp_path),
            ])

        assert result.exit_code == 0, result.output
        assert "# Post-Mortem:" in result.output

    def test_postmortem_command_file_output(self, runner, tmp_path, mock_vectorstore, fake_postmortem_response):
        pm = PostMortem(**json.loads(fake_postmortem_response))
        output_file = tmp_path / "report.md"

        with patch("processing.vectorstore.load_vectorstore", return_value=mock_vectorstore), \
             patch("analysis.postmortem.generate_postmortem", return_value=pm):

            result = runner.invoke(cli, [
                "analyze", "postmortem",
                "--output", str(output_file),
                "--vectorstore-path", str(tmp_path),
            ])

        assert result.exit_code == 0, result.output
        assert output_file.exists()
        assert "# Post-Mortem:" in output_file.read_text()

    def test_analyze_without_vectorstore_exits(self, runner, tmp_path):
        with patch("processing.vectorstore.load_vectorstore", return_value=None):
            result = runner.invoke(cli, [
                "analyze", "anomaly",
                "--vectorstore-path", str(tmp_path / "nonexistent"),
            ])
        assert result.exit_code == 1
