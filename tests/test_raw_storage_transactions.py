import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.models.capture_package import CapturePackage
from app.services import raw_storage


def test_failed_snapshot_write_cleans_up_and_can_be_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(raw_storage, "CONTENTS_DIR", tmp_path)
    package = CapturePackage(capture_id="failed_capture_01")
    write = Path.write_text

    def fail_html(path, *args, **kwargs):
        if path.name == "page.html":
            raise OSError("Simulated disk write failure")
        return write(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "write_text", fail_html)
        with pytest.raises(OSError, match="Simulated"):
            raw_storage.save_raw_capture("member", package, html="<p>Saved content</p>")
    assert not raw_storage.raw_exists("member", package.capture_id)
    raw_storage.save_raw_capture("member", package, html="<p>Saved content</p>")
    assert raw_storage.get_raw_html("member", package.capture_id) == "<p>Saved content</p>"


def test_two_processes_cannot_overbook_raw_storage(tmp_path):
    worker = """
import json, sys, time
from pathlib import Path
from app.models.capture_package import CapturePackage
from app.services import raw_storage
root, index = Path(sys.argv[1]), sys.argv[2]
raw_storage.CONTENTS_DIR = root
package = CapturePackage(capture_id="worker_capture_" + index, captured_at="2026-11-18T12:00:00Z")
html = "x" * 8192
package_size = len(json.dumps(package.model_dump(exclude_none=True, mode="json"), indent=2, ensure_ascii=False).encode())
raw_storage.MAX_USER_STORAGE_BYTES = len(html) + 2 * package_size
write = Path.write_text
def slow_disk(path, *args, **kwargs):
    if path.name == "page.html":
        time.sleep(1)
    return write(path, *args, **kwargs)
Path.write_text = slow_disk
(root / ("ready-" + index)).touch()
deadline = time.monotonic() + 30
while not (root / "go").exists():
    if time.monotonic() > deadline:
        raise RuntimeError("Gate timeout")
    time.sleep(0.01)
try:
    raw_storage.save_raw_capture("member", package, html)
    print("saved")
except ValueError as error:
    if "quota" not in str(error):
        raise
    print("quota")
"""
    processes = [subprocess.Popen(
        [sys.executable, "-c", worker, str(tmp_path), str(index)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ) for index in range(2)]
    try:
        deadline = time.monotonic() + 30
        while not all((tmp_path / f"ready-{index}").exists() for index in range(2)):
            assert all(process.poll() is None for process in processes)
            assert time.monotonic() < deadline
            time.sleep(0.01)
        (tmp_path / "go").touch()
        results = [process.communicate(timeout=30) for process in processes]
        assert all(process.returncode == 0 for process in processes), results
        assert sorted(out.strip() for out, _ in results) == ["quota", "saved"]
        assert len(list((tmp_path / "users/member/raw").iterdir())) == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()
