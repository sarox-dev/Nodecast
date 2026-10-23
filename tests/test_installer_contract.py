import importlib.util
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _load_native_runner():
    path = ROOT / "scripts" / "run-nodecast.py"
    spec = importlib.util.spec_from_file_location("nodecast_native_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_native_runner_loads_env_without_evaluating_shell(tmp_path, monkeypatch):
    runner = _load_native_runner()
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_PORT=6123\n"
        "NODECAST_PUBLIC_ORIGIN='http://localhost:6123'\n"
        "NOT VALID=$(touch should-not-exist)\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("APP_PORT", raising=False)
    monkeypatch.delenv("NODECAST_PUBLIC_ORIGIN", raising=False)

    runner.load_env(env_file)

    assert os.environ["APP_PORT"] == "6123"
    assert os.environ["NODECAST_PUBLIC_ORIGIN"] == "http://localhost:6123"
    assert not (tmp_path / "should-not-exist").exists()
    os.environ.pop("APP_PORT", None)
    os.environ.pop("NODECAST_PUBLIC_ORIGIN", None)


def test_native_runner_preserves_service_environment(tmp_path, monkeypatch):
    runner = _load_native_runner()
    (tmp_path / ".env").write_text("APP_PORT=6123\n", encoding="utf-8")
    monkeypatch.setenv("APP_PORT", "7000")

    runner.load_env(tmp_path / ".env")

    assert os.environ["APP_PORT"] == "7000"


def test_installers_offer_both_modes_and_verify_health():
    bash = (ROOT / "install.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")

    for script in (bash, powershell):
        assert "Docker" in script
        assert "Native Python" in script
        assert "docker" in script
        assert "host" in script
        assert "NODECAST_ACCOUNT_MODE" in script
        assert "NODECAST_NETWORK_ACCESS" in script
        assert "/api/server/health" in script
        assert "run-nodecast.py" in script


def test_release_bundle_includes_native_runner():
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "git archive" in workflow
    assert (ROOT / "scripts" / "run-nodecast.py").is_file()
