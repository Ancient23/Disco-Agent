import pytest

from ue_agent.discord_bot import parse_command


def test_parse_build_command():
    cmd = parse_command("!build CitySample")
    assert cmd is not None
    assert cmd["workflow"] == "compile"
    assert cmd["project"] == "CitySample"
    assert cmd["platform"] == "Win64"


def test_parse_package_command():
    cmd = parse_command("!package CitySample Linux")
    assert cmd is not None
    assert cmd["workflow"] == "package"
    assert cmd["project"] == "CitySample"
    assert cmd["platform"] == "Linux"


def test_parse_package_default_platform():
    cmd = parse_command("!package CitySample")
    assert cmd["platform"] == "Win64"


def test_parse_submit_command():
    cmd = parse_command("!submit CitySample --dry-run --app citysample")
    assert cmd is not None
    assert cmd["workflow"] == "submit"
    assert cmd["project"] == "CitySample"
    assert cmd["params"]["options"] == "--dry-run --app citysample"


def test_parse_analyze_command():
    cmd = parse_command('!analyze "why does the 4D capture crash"')
    assert cmd is not None
    assert cmd["workflow"] == "analyze"
    assert "4D capture crash" in cmd["params"]["prompt"]


def test_parse_run_command():
    cmd = parse_command('!run "add error handling to s3_upload.py"')
    assert cmd is not None
    assert cmd["workflow"] == "custom"
    assert "error handling" in cmd["params"]["prompt"]


def test_parse_status_command():
    cmd = parse_command("!status")
    assert cmd is not None
    assert cmd["workflow"] == "__status"


def test_parse_cancel_command():
    cmd = parse_command("!cancel")
    assert cmd is not None
    assert cmd["workflow"] == "__cancel"


def test_parse_unknown_command():
    cmd = parse_command("!unknown something")
    assert cmd is None


def test_parse_non_command():
    cmd = parse_command("hello everyone")
    assert cmd is None


def test_parse_build_missing_project():
    cmd = parse_command("!build")
    assert cmd is None
