import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.skipif(os.name == "nt" or shutil.which("bash") is None, reason="Windows origin checks run in PowerShell")
@pytest.mark.parametrize(("existing", "host", "port", "expected"), [
    ("", "localhost", 5000, "http://localhost:5000"),
    ("http://192.168.8.116:5000", "192.168.8.116", 5000, "http://192.168.8.116:5000"),
    ("https://nodecast.lan:8443", "nodecast.lan", 5000, "https://nodecast.lan:8443"),
    ("https://nodecast.lan/", "nodecast.lan", 5000, "https://nodecast.lan"),
    ("https://Nodecast.LAN:8443", "nodecast.lan", 5000, "https://Nodecast.LAN:8443"),
    ("https://old.lan:8443", "new.lan", 5000, "http://new.lan:5000"),
    ("https://nodecast.lan:8443", "localhost", 5000, "http://localhost:5000"),
    ("https://user:password@nodecast.lan", "nodecast.lan", 5000, "http://nodecast.lan:5000"),
    ("https://nodecast.lan/path", "nodecast.lan", 5000, "http://nodecast.lan:5000"),
    ("https://nodecast.lan/?key=secret", "nodecast.lan", 5000, "http://nodecast.lan:5000"),
])
def test_bash_installer_preserves_matching_https_origin(existing, host, port, expected):
    script = (ROOT / "install.sh").read_text(encoding="utf-8")
    helper = re.search(r"(?m)^public_origin_for\(\) \{[\s\S]*?^\}", script)
    assert helper
    result = subprocess.run(
        [shutil.which("bash"), "-c", helper.group() + '\npublic_origin_for "$1" "$2" "$3"',
         "origin-test", existing, host, str(port)],
        capture_output=True, text=True, check=True,
    )
    assert result.stdout == expected
