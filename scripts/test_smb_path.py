"""Unit tests for backend.utils.smb_path. Run with: python scripts/test_smb_path.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ["SMB_WIN_ROOT"] = r"D:\share"
os.environ["SMB_MAC_ROOT"] = "/Volumes/share"

from backend.utils.smb_path import get_roots, mac_to_win, win_to_mac  # noqa: E402


def check(label: str, got, want) -> bool:
    ok = got == want
    marker = "OK  " if ok else "FAIL"
    print(f"[test_smb_path] {marker} {label}: got={got!r} want={want!r}")
    return ok


def main() -> int:
    results: list[bool] = []

    results.append(check("get_roots", get_roots(), (r"D:\share", "/Volumes/share")))

    results.append(
        check(
            "win_to_mac nested forward slashes",
            win_to_mac("D:/share/copilot-cache/warmup.png"),
            "/Volumes/share/copilot-cache/warmup.png",
        )
    )
    results.append(
        check(
            "win_to_mac backslashes",
            win_to_mac(r"D:\share\copilot-cache\warmup.png"),
            "/Volumes/share/copilot-cache/warmup.png",
        )
    )
    results.append(
        check(
            "win_to_mac exact root",
            win_to_mac(r"D:\share"),
            "/Volumes/share",
        )
    )
    results.append(
        check(
            "win_to_mac outside root returns None",
            win_to_mac(r"C:\Users\Someone\foo.png"),
            None,
        )
    )
    results.append(
        check(
            "win_to_mac different drive returns None",
            win_to_mac(r"E:\share\foo.png"),
            None,
        )
    )

    results.append(
        check(
            "mac_to_win roundtrip",
            mac_to_win("/Volumes/share/copilot-cache/warmup.png"),
            r"D:\share\copilot-cache\warmup.png",
        )
    )
    results.append(
        check(
            "mac_to_win outside root returns None",
            mac_to_win("/Users/foo/bar.png"),
            None,
        )
    )

    os.environ.pop("SMB_WIN_ROOT", None)
    results.append(check("get_roots unset", get_roots(), None))
    results.append(check("win_to_mac unset", win_to_mac(r"D:\share\foo"), None))
    os.environ["SMB_WIN_ROOT"] = r"D:\share"

    total = len(results)
    passed = sum(results)
    print(f"[test_smb_path] {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
