"""Shared helpers for the Streamlit webapp.

Centralizes:
  - path bootstrapping (so we can `import e7bot` from any page)
  - cached loaders (save, meta, wishlist) keyed by file mtime
  - common UI fragments (summary cards, badges)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# Make `e7bot` importable when streamlit runs files from webapp/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from e7bot.builder import (  # noqa: E402
    Analyzer, DropChecker, FribbelsClient, GearScorer, HeroComparator,
    ReadinessChecker, UpgradeRecommender, aggregate_by_recency,
    default_save_path, load_meta, load_save, load_wishlist, save_wishlist,
)


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def load_save_cached(save_path: str, mtime: float):
    """Reload save when its mtime changes (handled via cache key)."""
    return load_save(save_path)


@st.cache_data(ttl=3600, show_spinner=False)
def load_meta_cached(meta_path: str | None, mtime: float):
    return load_meta(meta_path) if meta_path else load_meta()


@st.cache_data(ttl=300, show_spinner=False)
def load_wishlist_cached(wishlist_path: str | None, mtime: float):
    return load_wishlist(wishlist_path) if wishlist_path else load_wishlist()


def get_save_path() -> str:
    if "save_path" not in st.session_state:
        default = default_save_path()
        st.session_state.save_path = str(default) if default.exists() else ""
    return st.session_state.save_path


def get_save():
    """Return the loaded FribbelsSave or None if no path."""
    p = get_save_path()
    if not p or not Path(p).exists():
        return None
    return load_save_cached(p, Path(p).stat().st_mtime)


def get_meta():
    p = st.session_state.get("meta_path")
    mtime = Path(p).stat().st_mtime if p and Path(p).exists() else 0.0
    return load_meta_cached(p, mtime)


def get_wishlist():
    p = st.session_state.get("wishlist_path")
    if not p:
        from e7bot.builder.wishlist import default_wishlist_path
        p = str(default_wishlist_path())
    mtime = Path(p).stat().st_mtime if Path(p).exists() else 0.0
    return load_wishlist_cached(p, mtime)


def get_client() -> FribbelsClient:
    """Singleton client (cache for the session)."""
    if "client" not in st.session_state:
        st.session_state.client = FribbelsClient()
    return st.session_state.client


# ---------------------------------------------------------------------------
# UI fragments
# ---------------------------------------------------------------------------

def render_save_picker():
    """Sidebar widget — pick the Fribbels save path."""
    st.sidebar.header("Configuração")
    current = get_save_path()
    st.sidebar.text_input(
        "Save do Fribbels",
        value=current,
        key="save_path",
        help="Caminho para o arquivo .json/.txt exportado pelo Fribbels Optimizer",
    )
    if st.sidebar.button("🔄 Recarregar dados", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


def status_badge(status: str) -> str:
    """Return a colored markdown badge for readiness status strings."""
    colors = {
        "READY":     ("🟢", "READY"),
        "ALMOST":    ("🟡", "ALMOST"),
        "PARTIAL":   ("🟠", "PARTIAL"),
        "NOT_READY": ("🔴", "NOT READY"),
        "no_data":   ("⚪", "NO DATA"),
    }
    icon, label = colors.get(status, ("⚪", status))
    return f"{icon} **{label}**"


def fmt_substats(item) -> str:
    return ", ".join(f"{s.stat}={int(s.value)}" for s in item.substats)


def require_save() -> bool:
    """Return True if a save is loaded; otherwise show a warning + return False."""
    save = get_save()
    if save is None:
        st.error("⚠️ Nenhum save do Fribbels carregado. Configure o caminho na barra lateral.")
        return False
    return True
