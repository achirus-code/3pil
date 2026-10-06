"""Lädt das Paket der App (saeulenwaechter/app) als „sw“."""

import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "saeulenwaechter" / "app"
pkg = types.ModuleType("sw")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("sw", pkg)
