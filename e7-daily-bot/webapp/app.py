"""Home / Dashboard page for the e7-daily-bot webapp."""
from __future__ import annotations

import streamlit as st

from shared import (
    Analyzer, GearScorer, ReadinessChecker, aggregate_by_recency,
    get_client, get_meta, get_save, get_wishlist,
    render_save_picker, require_save, status_badge,
)


st.set_page_config(
    page_title="E7 Companion",
    page_icon="⚔️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("⚔️ Epic Seven Companion")
st.caption("Inventário, prioridades, prontidão e dropcheck — alimentado pelos dados do Fribbels e da comunidade.")

render_save_picker()

if not require_save():
    st.info("👈 Aponte para o save do Fribbels (geralmente em `~/Documents/FribbelsOptimizerSaves/`).")
    st.stop()

save = get_save()
meta = get_meta()
wishlist = get_wishlist()

# ---------- Summary cards ----------
analyzer = Analyzer(save=save, meta=meta, scorer=GearScorer())
report = analyzer.full_report()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Itens totais", report.summary["items_total"])
col2.metric("Heroes", report.summary["heroes_total"])
col3.metric(
    "Junk candidates",
    report.summary["junk_count"],
    f"{report.summary['junk_pct']:.1f}% do inventário",
    delta_color="inverse",
)
col4.metric(
    "Wishlist actionable",
    len([e for e in wishlist.entries if e.action != "skip"]),
)

st.divider()

# ---------- Wishlist readiness summary ----------
st.subheader("📋 Prontidão da wishlist")

actionable = wishlist.sorted_actionable()
if not actionable:
    st.info("Sua wishlist está vazia. Vá em **Wishlist** para adicionar heroes.")
else:
    client = get_client()
    checker = ReadinessChecker(save)
    rows = []
    with st.spinner("Calculando prontidão (cacheado, dura 14d)..."):
        for entry in actionable:
            build = meta.get(entry.name)
            if build is None:
                rows.append({
                    "Prio": entry.priority,
                    "Hero": entry.name,
                    "Status": "no_data",
                    "Readiness": 0,
                    "Combo": "(meta missing)",
                    "Notes": entry.notes,
                })
                continue
            try:
                cached = client.fetch_builds(entry.name)
                builds = aggregate_by_recency(cached.builds, top_k=3, recent_n=1000)
            except Exception as e:
                builds = None
                st.toast(f"⚠️ Falha ao buscar builds para {entry.name}: {e}", icon="⚠️")
            rd = checker.check(build, builds=builds)
            rows.append({
                "Prio": entry.priority,
                "Hero": entry.name,
                "Status": rd.status,
                "Readiness": rd.readiness_pct,
                "Combo": (builds.top_combos[0].label if builds and builds.top_combos else "(no community data)"),
                "Notes": entry.notes,
            })

    # Render as cards
    for row in rows:
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 3])
            c1.markdown(f"**#{row['Prio']} · {row['Hero']}**")
            c1.caption(row["Notes"] or "")
            c2.markdown(status_badge(row["Status"]))
            c2.progress(row["Readiness"] / 100.0, text=f"{row['Readiness']:.0f}%")
            c3.caption(f"Combo da comunidade: {row['Combo']}")

st.divider()

# ---------- Quick actions ----------
st.subheader("⚡ Ações rápidas")
c1, c2, c3 = st.columns(3)
with c1:
    st.page_link("pages/1_Inventario.py", label="📊 Inventário", icon="📊", use_container_width=True)
with c2:
    st.page_link("pages/3_Drop_Check.py", label="🎁 Drop Check", icon="🎁", use_container_width=True)
with c3:
    st.page_link("pages/4_Comparar.py", label="⚖️ Comparar", icon="⚖️", use_container_width=True)
