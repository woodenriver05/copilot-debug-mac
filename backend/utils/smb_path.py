"""Windows <-> Mac SMB path translation for RAG image handling.

Pure path conversion — does NO filesystem I/O. Callers check existence.
Used by diagnose_image to hand the Mac side a /Volumes/share/... path
instead of base64-inlining the bytes.
"""
from __future__ import annotations

import os
from pathlib import PurePosixPath, PureWindowsPath


def get_roots() -> tuple[str, str] | None:
    win = os.environ.get("SMB_WIN_ROOT")
    mac = os.environ.get("SMB_MAC_ROOT")
    if not win or not mac:
        return None
    return win, mac


def win_to_mac(win_path: str) -> str | None:
    """Translate a Windows absolute path to its Mac mount equivalent.

    Returns None if the path is not under SMB_WIN_ROOT, or if the roots
    are not configured. The caller is responsible for presenting a clear
    error to the user — this function never silently "best-effort"s.
    """
    roots = get_roots()
    if roots is None:
        return None
    win_root, mac_root = roots
    try:
        win_pure = PureWindowsPath(win_path)
        win_root_pure = PureWindowsPath(win_root)
        rel = win_pure.relative_to(win_root_pure)
    except ValueError:
        return None
    mac_root_pure = PurePosixPath(mac_root)
    return str(mac_root_pure.joinpath(*rel.parts))


def mac_to_win(mac_path: str) -> str | None:
    """Inverse of win_to_mac. Returns None if mac_path is not under SMB_MAC_ROOT."""
    roots = get_roots()
    if roots is None:
        return None
    win_root, mac_root = roots
    try:
        mac_pure = PurePosixPath(mac_path)
        mac_root_pure = PurePosixPath(mac_root)
        rel = mac_pure.relative_to(mac_root_pure)
    except ValueError:
        return None
    win_root_pure = PureWindowsPath(win_root)
    return str(win_root_pure.joinpath(*rel.parts))
