"""Drop Check — vale guardar este item dropado?"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import pandas as pd
import streamlit as st

from shared import (
    DropChecker, fmt_substats,
    get_client, get_meta, get_save, get_wishlist,
    render_save_picker, require_save,
)


st.set_page_config(page_title="Drop Check", page_icon="🎁", layout="wide")
st.title("🎁 Drop Check")
st.caption("Cole o ID de um item recém-dropado e veja se vale guardar ou descartar.")

render_save_picker()
if not require_save():
    st.stop()

save = get_save()
meta = get_meta()
wishlist = get_wishlist()
client = get_client()

# ---- input
col_input, col_help = st.columns([3, 1])
with col_input:
    # Search by ID OR by picking from a list of recent items
    search_mode = st.radio("Buscar por", ["ID exato", "Filtrar inventário"], horizontal=True)
    target_id = None
    if search_mode == "ID exato":
        target_id = st.text_input("Item ID", placeholder="ex: 5747de94-dd8a-45a0-9d08-43cab3a6c4b5")
    else:
        # Filter UI
        c1, c2, c3 = st.columns(3)
        gear_filter = c1.selectbox("Slot", ["(todos)", "weapon", "helmet", "armor", "necklace", "ring", "boots"])
        rank_filter = c2.selectbox("Rank", ["(todos)", "Epic", "Heroic", "Rare", "Good", "Normal"])
        enh_filter = c3.selectbox("Enhance", ["(todos)", "0", "9", "12", "15", "<15"])
        items = save.items
        if gear_filter != "(todos)":
            items = [i for i in items if i.gear == gear_filter]
        if rank_filter != "(todos)":
            items = [i for i in items if i.rank == rank_filter]
        if enh_filter == "<15":
            items = [i for i in items if i.enhance < 15]
        elif enh_filter != "(todos)":
            items = [i for i in items if i.enhance == int(enh_filter)]
        if items:
            options = [
                f"{it.gear:<10} {it.set:<14} +{it.enhance:<2} {it.rank:<7} {it.main_stat:<12} | {fmt_substats(it)} (id={it.id[:8]}...)"
                for it in items[:200]
            ]
            choice = st.selectbox(f"Item ({len(items)} candidatos, mostrando até 200)", options)
            if choice:
                idx = options.index(choice)
                target_id = items[idx].id

with col_help:
    st.info(
        "💡 Como achar o ID:\n\n"
        "• No Fribbels: ative coluna 'id' no grid de Gear\n"
        "• Ou use o filtro ao lado pra escolher por slot/rank"
    )

if not target_id:
    st.stop()

# ---- run analysis
checker = DropChecker(save, meta, wishlist, client)
try:
    analysis = checker.check_by_id(target_id)
except ValueError as e:
    st.error(f"❌ {e}")
    st.stop()

it = analysis.item

# ---- item info
st.divider()
st.subheader("Item analisado")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tipo", it.gear)
c2.metric("Set", it.set)
c3.metric("Rank", it.rank)
c4.metric("Enhance", f"+{it.enhance}")
c5.metric("Main", f"{it.main_stat}={int(it.main_value)}")
st.markdown(f"**Substats:** {fmt_substats(it)}")

# ---- verdict (big and obvious)
st.divider()
verdict = analysis.verdict
if verdict.startswith("KEEP"):
    st.success(f"## ✅ {verdict}")
    st.toast("Item vale guardar!", icon="✅")
else:
    st.error(f"## 🗑️ {verdict}")
    st.toast("Item pode ser descartado", icon="🗑️")

# ---- impact table
st.subheader("Impacto por hero da wishlist")
if not analysis.impacts:
    st.warning("Nenhum hero na wishlist tem meta build correspondente.")
else:
    rows = []
    for imp in analysis.impacts:
        rows.append({
            "Hero": imp.hero_name,
            "Item atual (score)": f"{imp.current_slot_score:.1f}",
            "Item novo (score)": f"{imp.new_score:.1f}",
            "Δ": f"{imp.delta:+.1f}",
            "Set bate?": "✅" if imp.fits_set else "❌",
            "Status": "🟢 UPGRADE" if imp.positive else "⚪ sem ganho",
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    if analysis.best_impact:
        bi = analysis.best_impact
        cur = bi.current_item
        st.info(
            f"💎 Melhor ganho: **{bi.hero_name}** ganha **+{bi.delta:.0f}** de score. "
            + (f"Substitui {cur.set} +{cur.enhance} (substats: {fmt_substats(cur)})." if cur else "Slot estava vazio.")
        )
