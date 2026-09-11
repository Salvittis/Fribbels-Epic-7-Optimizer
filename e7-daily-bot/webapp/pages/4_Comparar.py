"""Comparar — qual hero buildar primeiro?"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import streamlit as st

from shared import (
    HeroComparator,
    get_client, get_meta, get_save, render_save_picker, require_save,
    status_badge,
)


st.set_page_config(page_title="Comparar", page_icon="⚖️", layout="wide")
st.title("⚖️ Comparar dois heroes")
st.caption("Lado a lado: prontidão, gaps e veredito de qual buildar primeiro.")

render_save_picker()
if not require_save():
    st.stop()

save = get_save()
meta = get_meta()
client = get_client()

# Pickable heroes = those with meta builds
hero_options = sorted(b.name for b in meta.builds.values() if not b.name.startswith("__"))

c1, c2 = st.columns(2)
with c1:
    hero_a = st.selectbox("Hero A", hero_options, index=0)
with c2:
    default_b = 1 if len(hero_options) > 1 else 0
    hero_b = st.selectbox("Hero B", hero_options, index=default_b)

if hero_a == hero_b:
    st.warning("Escolha dois heroes diferentes.")
    st.stop()

with st.spinner("Buscando builds..."):
    try:
        result = HeroComparator(save, meta, client).compare(hero_a, hero_b)
    except ValueError as e:
        st.error(str(e))
        st.stop()

a, b = result.a, result.b

# ---- big verdict banner
st.divider()
st.success(f"## 🏆 Build **{result.winner}** primeiro")
st.markdown(f"**Por quê:** {result.reasoning}")

# ---- side-by-side cards
st.divider()
col1, col2 = st.columns(2)

def render_hero(col, summary):
    with col:
        st.subheader(summary.name)
        st.markdown(status_badge(summary.readiness.status))
        st.progress(summary.readiness.readiness_pct / 100.0,
                    text=f"{summary.readiness.readiness_pct:.0f}% ({summary.readiness.ready_slots}/6 slots)")
        st.metric("Score médio dos slots", f"{summary.avg_slot_score:.1f}")
        st.metric("Slots vazios (precisam farmar)", summary.farm_gaps)
        if summary.builds and summary.builds.top_combos:
            st.caption(f"Combo top da comunidade: **{summary.builds.top_combos[0].label}** "
                       f"({summary.builds.top_combos[0].pct:.1f}% das submissões)")
        # show issues
        if summary.readiness.issues:
            with st.expander(f"⚠️ {len(summary.readiness.issues)} problema(s) detectado(s)"):
                for issue in summary.readiness.issues:
                    st.markdown(f"- {issue}")

render_hero(col1, a)
render_hero(col2, b)
