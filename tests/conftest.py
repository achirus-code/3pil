"""Lädt die reinen Module (ohne Home Assistant) als Paket „sw“."""

import sys
import types
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "saeulenwaechter"
pkg = types.ModuleType("sw")
pkg.__path__ = [str(PKG)]
sys.modules.setdefault("sw", pkg)
