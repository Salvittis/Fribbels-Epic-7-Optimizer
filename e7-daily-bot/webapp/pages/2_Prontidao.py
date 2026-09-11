"""Prontidão — readiness por hero + plano de upgrade."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import pandas as pd
import streamlit as st

from shared import (
    GearScorer, ReadinessChecker, UpgradeRecommender, aggregate_by_recency,
    fmt_substats,
    get_client, get_meta, get_save, get_wishlist,
    render_save_picker, require_save, status_badge,
)


st.set_page_config(page_title="Prontidão", page_icon="⚔️", layout="wide")
st.title("⚔️ Prontidão de builds")

render_save_picker()
if not require_save():
    st.stop()

save = get_save()
meta = get_meta()
wishlist = get_wishlist()
client = get_client()


def readiness_for(hero_name: str):
    build = meta.get(hero_name)
    if build is None:
        return None, "(meta build não encontrado em data/meta_builds.yaml)"
    try:
        cached = client.fetch_builds(hero_name)
        builds = aggregate_by_recency(cached.builds, top_k=3, recent_n=1000)
    except Exception as e:
        return None, f"Erro buscando builds: {e}"
    rd = ReadinessChecker(save).check(build, builds=builds)
    return (rd, builds), None


# ---- target heroes
sources = ["Wishlist (priorities.yaml)", "Todos heroes próprios com meta"]
source = st.sidebar.radio("Fonte da lista", sources, index=0)

if source == sources[0]:
    targets = [e.name for e in wishlist.sorted_actionable()]
else:
    owned = {h.name for h in save.heroes}
    targets = sorted(b.name for b in meta.builds.values()
                     if not b.name.startswith("__") and b.name in owned)

if not targets:
    st.warning("Nenhum hero alvo. Adicione na Wishlist ou habilite 'Todos heroes próprios'.")
    st.stop()

# ---- list with status
rows = []
detail_data = {}
fetch_progress = st.progress(0.0, text="Calculando prontidão...")
for i, name in enumerate(targets):
    result, err = readiness_for(name)
    if err:
        rows.append({"Hero": name, "Status": "no_data", "Readiness": 0,
                     "Combo": err, "Slots ready": "-"})
        continue
    rd, builds = result
    rows.append({
        "Hero": name,
        "Status": rd.status,
        "Readiness": rd.readiness_pct,
        "Combo": builds.top_combos[0].label if builds and builds.top_combos else "-",
        "Slots ready": f"{rd.ready_slots}/6",
    })
    detail_data[name] = (rd, builds)
    fetch_progress.progress((i + 1) / len(targets), text=f"Calculando: {name}")
fetch_progress.empty()

# ---- summary table
for r in rows:
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
        c1.markdown(f"**{r['Hero']}**")
        c1.caption(r["Combo"])
        c2.markdown(status_badge(r["Status"]))
        c3.progress(r["Readiness"] / 100.0, text=f"{r['Readiness']:.0f}% ({r['Slots ready']})")
        if r["Hero"] in detail_data:
            with c4:
                if st.button("Detalhe", key=f"detail_{r['Hero']}", use_container_width=True):
                    st.session_state.selected_hero = r["Hero"]

st.divider()

# ---- detail view
if "selected_hero" in st.session_state and st.session_state.selected_hero in detail_data:
    name = st.session_state.selected_hero
    rd, builds = detail_data[name]
    st.subheader(f"🔎 Detalhe: {name}")

    # slot table
    slot_rows = []
    for gear in ("weapon", "helmet", "armor", "necklace", "ring", "boots"):
        s = rd.slots.get(gear)
        if s is None or s.item is None:
            slot_rows.append({
                "Slot": gear, "OK": "❌", "Score": "-",
                "Set requerido": s.set_required if s else "-",
                "Set picked": "(vazio)", "+": "-", "Substats": s.note if s else "",
            })
            continue
        slot_rows.append({
            "Slot": gear,
            "OK": "✅" if s.ready else "⚠️",
            "Score": f"{s.score:.1f}",
            "Set requerido": s.set_required or "-",
            "Set picked": s.item.set,
            "+": s.item.enhance,
            "Substats": fmt_substats(s.item),
        })
    st.dataframe(pd.DataFrame(slot_rows), use_container_width=True, hide_index=True)

    if rd.issues:
        st.warning("⚠️ Problemas:\n" + "\n".join(f"- {i}" for i in rd.issues))

    # upgrade plan
    st.markdown("### 🔧 Plano de upgrade")
    plan = UpgradeRecommender(save).plan(meta.get(name), readiness=rd, builds=builds)
    if not plan.actions:
        st.success("Build completa — nada a upar.")
    else:
        plan_rows = []
        for a in plan.actions[:20]:
            plan_rows.append({
                "Tipo": a.kind, "Slot": a.gear,
                "Ganho est.": f"+{a.estimated_score_gain:.0f}" if a.estimated_score_gain > 0 else "-",
                "Descrição": a.description,
            })
        st.dataframe(pd.DataFrame(plan_rows), use_container_width=True, hide_index=True)
