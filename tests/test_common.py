"""Tests for common.py utilities."""
import json
import time
from pathlib import Path

import pytest

import common


def test_iso_now_format():
    result = common.iso_now()
    assert "T" in result
    assert result.endswith("+00:00")


def test_new_run_id_format():
    rid = common.new_run_id("test")
    assert rid.startswith("test-")
    parts = rid.split("-")
    assert len(parts) == 3
    assert int(parts[1]) > 0


def test_has_real_value():
    assert common.has_real_value("sk-ant-real-key") is True
    assert common.has_real_value("") is False
    assert common.has_real_value(None) is False
    assert common.has_real_value("replace_me") is False
    assert common.has_real_value("your_private_key_here") is False


def test_read_write_json(tmp_path):
    path = tmp_path / "test.json"
    payload = {"key": "value", "num": 42}
    common.write_json(path, payload)
    result = common.read_json(path)
    assert result == payload


def test_append_jsonl(tmp_path):
    path = tmp_path / "test.jsonl"
    common.append_jsonl(path, {"event": "first"})
    common.append_jsonl(path, {"event": "second"})
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "first"
    assert json.loads(lines[1])["event"] == "second"


def test_log_event_writes_to_file(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EVENT_LOG_PATH", tmp_path / "event_log.jsonl")
    common.log_event("test_script", "run-123", "test_event", foo="bar")
    entries = (tmp_path / "event_log.jsonl").read_text().strip().split("\n")
    assert len(entries) == 1
    entry = json.loads(entries[0])
    assert entry["event"] == "test_event"
    assert entry["script"] == "test_script"
    assert entry["details"]["foo"] == "bar"


def test_load_execution_state_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EXECUTION_STATE_PATH", tmp_path / "execution_state.json")
    state = common.load_execution_state()
    assert state["schema_version"] == 1
    assert state["active_positions"] == {}
    assert state["daily_trade_log"] == []


def test_count_todays_trades():
    today = common.iso_now()[:10]
    state = {"daily_trade_log": [f"{today}T10:00:00+00:00", f"{today}T11:00:00+00:00", "2020-01-01T00:00:00+00:00"]}
    assert common.count_todays_trades(state) == 2


def test_record_trade_today():
    state = {"daily_trade_log": []}
    common.record_trade_today(state)
    common.record_trade_today(state)
    assert common.count_todays_trades(state) == 2


def test_save_load_execution_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "EXECUTION_STATE_PATH", tmp_path / "execution_state.json")
    state = common.load_execution_state()
    state["active_positions"]["pos-1"] = {"token_id": "abc", "status": "open"}
    common.save_execution_state(state)
    loaded = common.load_execution_state()
    assert "pos-1" in loaded["active_positions"]
    assert loaded["active_positions"]["pos-1"]["token_id"] == "abc"


def test_load_save_monitor_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "MONITOR_STATE_PATH", tmp_path / "monitor_state.json")
    state = common.load_monitor_state()
    state["last_seen_trade_ids"]["0xabc"] = ["trade1", "trade2"]
    common.save_monitor_state(state)
    loaded = common.load_monitor_state()
    assert loaded["last_seen_trade_ids"]["0xabc"] == ["trade1", "trade2"]
