"""Inventário — junk pile + sumário por raridade."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import pandas as pd
import streamlit as st

from shared import (
    Analyzer, GearScorer, fmt_substats,
    get_meta, get_save, render_save_picker, require_save,
)


st.set_page_config(page_title="Inventário", page_icon="📊", layout="wide")
st.title("📊 Inventário")

render_save_picker()
if not require_save():
    st.stop()

save = get_save()
meta = get_meta()

# ---- threshold control
threshold = st.sidebar.slider(
    "Junk threshold",
    min_value=-50, max_value=100, value=30, step=5,
    help="Itens com score máximo abaixo deste valor (em toda a roster) são candidatos a descarte.",
)
include_locked = st.sidebar.checkbox("Incluir itens locked", value=False)

analyzer = Analyzer(save=save, meta=meta, scorer=GearScorer(), junk_threshold=float(threshold))
report = analyzer.full_report()

# ---- summary
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total", report.summary["items_total"])
col2.metric("Locked", report.summary["items_locked"])
col3.metric("Unlocked", report.summary["items_unlocked"])
col4.metric("Junk", report.summary["junk_count"], f"{report.summary['junk_pct']:.1f}%", delta_color="inverse")

# ---- tabs
tab_junk, tab_priorities, tab_breakdown = st.tabs(["🗑️ Junk pile", "⭐ Build priorities", "📈 Breakdown"])

with tab_junk:
    st.markdown(f"Itens cujo melhor uso em toda sua roster gera score < **{threshold}**.")
    junk = analyzer.junk_candidates(only_unlocked=not include_locked)
    if not junk:
        st.success("🎉 Inventário limpo — nenhum item abaixo do threshold.")
    else:
        df = pd.DataFrame([{
            "Score": round(c.best_score, 1),
            "Gear": c.item.gear,
            "Set": c.item.set,
            "Rank": c.item.rank,
            "+": c.item.enhance,
            "Main": f"{c.item.main_stat}={int(c.item.main_value)}",
            "Substats": fmt_substats(c.item),
            "Best for": c.best_for or "-",
            "ID": c.item.id,
            "Locked": "🔒" if c.item.locked else "",
        } for c in junk])
        st.dataframe(df, use_container_width=True, height=600, hide_index=True)
        st.download_button(
            "📥 Baixar lista (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"junk_threshold_{int(threshold)}.csv",
            mime="text/csv",
        )

with tab_priorities:
    prios = analyzer.build_priorities()
    if not prios:
        st.info("Nenhum dos seus heroes tem build registrado em `data/meta_builds.yaml`.")
    else:
        df = pd.DataFrame([{
            "Tier": p.tier, "Hero": p.name, "Rarity": p.rarity,
            "Slots equipados": f"{p.current_gear_completion}/6",
            "Role": p.role_label,
        } for p in prios])
        st.dataframe(df, use_container_width=True, hide_index=True)

with tab_breakdown:
    items = save.items
    df_items = pd.DataFrame([{
        "Gear": it.gear, "Set": it.set, "Rank": it.rank, "+": it.enhance,
    } for it in items])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Por raridade:**")
        st.bar_chart(df_items["Rank"].value_counts())
    with c2:
        st.markdown("**Por tipo:**")
        st.bar_chart(df_items["Gear"].value_counts())
    st.markdown("**Top 15 sets:**")
    st.bar_chart(df_items["Set"].value_counts().head(15))
