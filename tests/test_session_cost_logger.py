"""Tests for claude_costs data functions and statusline CSV upsert."""

import csv
import os
import tempfile
from unittest.mock import patch

from claude_costs import aggregate, load_rows, period_key, _cost_style, _sess, _tok, _duration


# ---------------------------------------------------------------------------
# period_key
# ---------------------------------------------------------------------------

class TestPeriodKey:
    def test_monthly(self):
        assert period_key("2026-03-07T16:00:20Z", "monthly") == "2026-03"

    def test_daily(self):
        assert period_key("2026-03-07T16:00:20Z", "daily") == "2026-03-07"

    def test_weekly(self):
        result = period_key("2026-03-07T16:00:20Z", "weekly")
        assert result.startswith("2026-W")

    def test_invalid_timestamp(self):
        assert period_key("not-a-date", "monthly") == "unknown"

    def test_utc_suffix(self):
        assert period_key("2026-01-15T00:00:00Z", "monthly") == "2026-01"

    def test_offset_timezone(self):
        assert period_key("2026-06-15T12:00:00+08:00", "daily") == "2026-06-15"


# ---------------------------------------------------------------------------
# _cost_style
# ---------------------------------------------------------------------------

class TestCostStyle:
    def test_high_cost(self):
        assert _cost_style(50) == "bold red"
        assert _cost_style(100) == "bold red"

    def test_medium_cost(self):
        assert _cost_style(10) == "yellow"
        assert _cost_style(49.99) == "yellow"

    def test_low_cost(self):
        assert _cost_style(0) == "green"
        assert _cost_style(9.99) == "green"


# ---------------------------------------------------------------------------
# _sess (pluralization)
# ---------------------------------------------------------------------------

class TestSess:
    def test_singular(self):
        assert _sess(1) == "1 session"

    def test_plural(self):
        assert _sess(0) == "0 sessions"
        assert _sess(2) == "2 sessions"
        assert _sess(100) == "100 sessions"


# ---------------------------------------------------------------------------
# _tok (token formatting)
# ---------------------------------------------------------------------------

class TestTok:
    def test_small(self):
        assert _tok(0) == "0"
        assert _tok(999) == "999"

    def test_thousands(self):
        assert _tok(1_000) == "1.0k"
        assert _tok(28_059) == "28.1k"

    def test_millions(self):
        assert _tok(1_000_000) == "1.0M"
        assert _tok(2_500_000) == "2.5M"


# ---------------------------------------------------------------------------
# _duration (time formatting)
# ---------------------------------------------------------------------------

class TestDuration:
    def test_seconds(self):
        assert _duration(0) == "0s"
        assert _duration(5000) == "5s"
        assert _duration(59000) == "59s"

    def test_minutes(self):
        assert _duration(60000) == "1m00s"
        assert _duration(90000) == "1m30s"
        assert _duration(3599000) == "59m59s"

    def test_hours(self):
        assert _duration(3600000) == "1h00m"
        assert _duration(5400000) == "1h30m"
        assert _duration(7200000) == "2h00m"


# ---------------------------------------------------------------------------
# load_rows
# ---------------------------------------------------------------------------

class TestLoadRows:
    def test_loads_csv(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,session_id,project,model,cost_usd,input_tokens,output_tokens,duration_api_ms\n")
            f.write("2026-03-01T17:00:33Z,abc123,myproj,claude-opus-4-6,4.15,1000,2000,60000\n")
            f.write("2026-03-01T18:00:00Z,def456,other,claude-opus-4-6,1.00,500,600,30000\n")
            path = f.name
        try:
            with patch("claude_costs.CSV_PATH", __import__("pathlib").Path(path)):
                rows = load_rows()
                assert len(rows) == 2
                assert rows[0]["project"] == "myproj"
                assert rows[0]["cost_usd"] == "4.15"
        finally:
            os.unlink(path)

    def test_project_filter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("timestamp,session_id,project,model,cost_usd,input_tokens,output_tokens,duration_api_ms\n")
            f.write("2026-03-01T17:00:33Z,abc,projA,opus,1.00,,,\n")
            f.write("2026-03-01T18:00:00Z,def,projB,opus,2.00,,,\n")
            f.write("2026-03-01T19:00:00Z,ghi,projA,opus,3.00,,,\n")
            path = f.name
        try:
            with patch("claude_costs.CSV_PATH", __import__("pathlib").Path(path)):
                rows = load_rows(project_filter="projA")
                assert len(rows) == 2
                assert all(r["project"] == "projA" for r in rows)
        finally:
            os.unlink(path)

    def test_missing_file(self):
        with patch("claude_costs.CSV_PATH", __import__("pathlib").Path("/nonexistent/path.csv")):
            assert load_rows() == []

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            path = f.name
        try:
            with patch("claude_costs.CSV_PATH", __import__("pathlib").Path(path)):
                assert load_rows() == []
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------

class TestAggregate:
    def _make_rows(self):
        return [
            {"timestamp": "2026-03-01T10:00:00Z", "project": "alpha", "cost_usd": "5.00", "input_tokens": "1000", "output_tokens": "2000", "duration_api_ms": "60000"},
            {"timestamp": "2026-03-01T12:00:00Z", "project": "alpha", "cost_usd": "3.00", "input_tokens": "500", "output_tokens": "800", "duration_api_ms": "45000"},
            {"timestamp": "2026-03-01T14:00:00Z", "project": "beta", "cost_usd": "2.00", "input_tokens": "200", "output_tokens": "300", "duration_api_ms": "30000"},
            {"timestamp": "2026-04-01T10:00:00Z", "project": "alpha", "cost_usd": "1.00", "input_tokens": "100", "output_tokens": "100", "duration_api_ms": "15000"},
        ]

    def test_monthly_grouping(self):
        data = aggregate(self._make_rows(), "monthly")
        assert "2026-03" in data
        assert "2026-04" in data
        assert "alpha" in data["2026-03"]
        assert "beta" in data["2026-03"]

    def test_daily_grouping(self):
        data = aggregate(self._make_rows(), "daily")
        assert "2026-03-01" in data
        assert "2026-04-01" in data

    def test_cost_aggregation(self):
        data = aggregate(self._make_rows(), "monthly")
        alpha_mar = data["2026-03"]["alpha"]
        assert alpha_mar["cost"] == 8.0
        assert alpha_mar["sessions"] == 2
        assert alpha_mar["in_tok"] == 1500
        assert alpha_mar["out_tok"] == 2800
        assert alpha_mar["duration_ms"] == 105000

    def test_rows_preserved(self):
        rows = self._make_rows()
        data = aggregate(rows, "monthly")
        alpha_mar = data["2026-03"]["alpha"]
        assert len(alpha_mar["rows"]) == 2
        assert alpha_mar["rows"][0]["cost_usd"] == "5.00"
        assert alpha_mar["rows"][1]["cost_usd"] == "3.00"

    def test_empty_tokens_handled(self):
        rows = [
            {"timestamp": "2026-03-01T10:00:00Z", "project": "x", "cost_usd": "1.00", "input_tokens": "", "output_tokens": ""},
        ]
        data = aggregate(rows, "monthly")
        assert data["2026-03"]["x"]["in_tok"] == 0
        assert data["2026-03"]["x"]["out_tok"] == 0

    def test_empty_input(self):
        assert aggregate([], "monthly") == {}


# ---------------------------------------------------------------------------
# statusline _upsert_csv
# ---------------------------------------------------------------------------

class TestUpsertCsv:
    def test_insert_new_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "session-costs.csv")
            # Import and patch CSV_PATH in statusline module
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            from pathlib import Path
            original = mod.CSV_PATH
            mod.CSV_PATH = Path(csv_path)
            try:
                mod._upsert_csv("sess1", "myproj", "opus", 4.15, "2026-03-01T10:00:00Z", 1000, 2000, 60000)
                with open(csv_path) as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 1
                assert rows[0]["session_id"] == "sess1"
                assert rows[0]["project"] == "myproj"
                assert rows[0]["cost_usd"] == "4.1500"
                assert rows[0]["input_tokens"] == "1000"
                assert rows[0]["output_tokens"] == "2000"
                assert rows[0]["duration_api_ms"] == "60000"
            finally:
                mod.CSV_PATH = original

    def test_update_existing_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "session-costs.csv")
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            from pathlib import Path
            original = mod.CSV_PATH
            mod.CSV_PATH = Path(csv_path)
            try:
                mod._upsert_csv("sess1", "proj", "opus", 1.00, "2026-03-01T10:00:00Z", 100, 200, 10000)
                mod._upsert_csv("sess1", "proj", "opus", 5.00, "2026-03-01T11:00:00Z", 500, 800, 50000)
                with open(csv_path) as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 1
                assert rows[0]["cost_usd"] == "5.0000"
                assert rows[0]["input_tokens"] == "500"
                assert rows[0]["output_tokens"] == "800"
                assert rows[0]["duration_api_ms"] == "50000"
            finally:
                mod.CSV_PATH = original

    def test_multiple_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = os.path.join(tmp, "session-costs.csv")
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            from pathlib import Path
            original = mod.CSV_PATH
            mod.CSV_PATH = Path(csv_path)
            try:
                mod._upsert_csv("sess1", "projA", "opus", 1.00, "2026-03-01T10:00:00Z", 100, 200, 10000)
                mod._upsert_csv("sess2", "projB", "opus", 2.00, "2026-03-01T11:00:00Z", 300, 400, 20000)
                with open(csv_path) as f:
                    rows = list(csv.DictReader(f))
                assert len(rows) == 2
                assert rows[0]["session_id"] == "sess1"
                assert rows[1]["session_id"] == "sess2"
            finally:
                mod.CSV_PATH = original


# ---------------------------------------------------------------------------
# _sum_transcript_usage
# ---------------------------------------------------------------------------

class TestSumTranscriptTokens:
    def _load_mod(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "statusline", os.path.join(os.path.dirname(__file__), "..", "config", "statusline-command.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_sums_all_token_types(self):
        mod = self._load_mod()
        import json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "msg_1", "usage": {
                    "input_tokens": 10, "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 1000, "output_tokens": 50,
                }}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "msg_2", "usage": {
                    "input_tokens": 20, "cache_creation_input_tokens": 200,
                    "cache_read_input_tokens": 2000, "output_tokens": 80,
                }}}) + "\n")
            path = f.name
        try:
            in_tok, out_tok = mod._sum_transcript_tokens(path)
            assert in_tok == 10 + 100 + 1000 + 20 + 200 + 2000  # 3330
            assert out_tok == 50 + 80  # 130
        finally:
            os.unlink(path)

    def test_deduplicates_by_message_id(self):
        mod = self._load_mod()
        import json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "msg_1", "usage": {
                    "input_tokens": 10, "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 1000, "output_tokens": 5,
                }}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "msg_1", "usage": {
                    "input_tokens": 10, "cache_creation_input_tokens": 100,
                    "cache_read_input_tokens": 1000, "output_tokens": 420,
                }}}) + "\n")
            path = f.name
        try:
            in_tok, out_tok = mod._sum_transcript_tokens(path)
            assert in_tok == 10 + 100 + 1000  # 1110
            assert out_tok == 420
        finally:
            os.unlink(path)

    def test_excludes_subagent_transcripts(self):
        mod = self._load_mod()
        import json
        with tempfile.TemporaryDirectory() as tmp:
            # Main transcript
            main_path = os.path.join(tmp, "session.jsonl")
            with open(main_path, "w") as f:
                f.write(json.dumps({"type": "assistant", "message": {
                    "id": "msg_1", "usage": {
                        "input_tokens": 10, "cache_read_input_tokens": 1000,
                        "output_tokens": 50,
                    }}}) + "\n")
            # Subagent transcript (should NOT be counted)
            sub_dir = os.path.join(tmp, "session", "subagents")
            os.makedirs(sub_dir)
            with open(os.path.join(sub_dir, "agent-compact.jsonl"), "w") as f:
                f.write(json.dumps({"type": "assistant", "message": {
                    "id": "msg_sub1", "usage": {
                        "input_tokens": 5, "cache_read_input_tokens": 500,
                        "output_tokens": 30,
                    }}}) + "\n")
            in_tok, out_tok = mod._sum_transcript_tokens(main_path)
            assert in_tok == 10 + 1000  # 1010, subagent excluded
            assert out_tok == 50  # subagent excluded

    def test_missing_file(self):
        mod = self._load_mod()
        assert mod._sum_transcript_tokens("/nonexistent/path.jsonl") == (0, 0)

    def test_skips_non_usage_lines(self):
        mod = self._load_mod()
        import json
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(json.dumps({"type": "file-history-snapshot", "snapshot": {}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {
                "id": "msg_1", "usage": {
                    "input_tokens": 5, "output_tokens": 10,
                }}}) + "\n")
            path = f.name
        try:
            in_tok, out_tok = mod._sum_transcript_tokens(path)
            assert in_tok == 5
            assert out_tok == 10
        finally:
            os.unlink(path)
