"""Wishlist — editor CRUD da priorities.yaml."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import pandas as pd
import streamlit as st

from shared import (
    get_meta, get_save, get_wishlist,
    render_save_picker, require_save,
)
# save_wishlist é importado direto pra evitar caching
from e7bot.builder.wishlist import Wishlist, WishlistEntry, save_wishlist


st.set_page_config(page_title="Wishlist", page_icon="📝", layout="wide")
st.title("📝 Wishlist (priorities.yaml)")
st.caption("Sua lista personalizada de heroes pra buildar/melhorar, em ordem de prioridade.")

render_save_picker()
if not require_save():
    st.stop()

save = get_save()
meta = get_meta()
wishlist = get_wishlist()

owned_names = {h.name.strip().lower() for h in save.heroes}
hero_options = sorted(b.name for b in meta.builds.values() if not b.name.startswith("__"))

# ---- current wishlist as editable table
st.subheader("Wishlist atual")
if not wishlist.entries:
    st.info("Wishlist vazia. Use o formulário abaixo pra adicionar.")
else:
    df = pd.DataFrame([{
        "Prio": e.priority,
        "Hero": e.name,
        "Action": e.action,
        "Owned": "✅" if e.name.strip().lower() in owned_names else "❌",
        "Has meta": "✅" if meta.get(e.name) else "❌",
        "Notes": e.notes,
    } for e in sorted(wishlist.entries, key=lambda x: (x.priority, x.name))])
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Prio": st.column_config.NumberColumn(min_value=1, max_value=99, step=1),
            "Action": st.column_config.SelectboxColumn(
                options=["build", "improve", "maintain", "skip"],
            ),
            "Owned": st.column_config.TextColumn(disabled=True),
            "Has meta": st.column_config.TextColumn(disabled=True),
        },
        num_rows="dynamic",
        key="wishlist_editor",
    )
    if st.button("💾 Salvar alterações", type="primary"):
        new_entries: list[WishlistEntry] = []
        for _, row in edited.iterrows():
            if not row.get("Hero"):
                continue
            new_entries.append(WishlistEntry(
                name=str(row["Hero"]),
                action=str(row.get("Action", "build")),
                priority=int(row.get("Prio", 99)),
                notes=str(row.get("Notes", "") or ""),
            ))
        save_wishlist(Wishlist(entries=new_entries))
        st.cache_data.clear()
        st.success("✅ Wishlist salva! Recarregando...")
        st.rerun()

st.divider()

# ---- quick add form
st.subheader("Adicionar hero")
existing_names = {e.name for e in wishlist.entries}
candidates = [n for n in hero_options if n not in existing_names]
with st.form("add_hero", clear_on_submit=True):
    c1, c2, c3 = st.columns([3, 1, 1])
    name = c1.selectbox("Hero (ordenado por meta yaml)", candidates) if candidates else None
    action = c2.selectbox("Action", ["build", "improve", "maintain"])
    priority = c3.number_input("Prio", min_value=1, max_value=99, value=99, step=1)
    notes = st.text_input("Notes (opcional)")
    submitted = st.form_submit_button("➕ Adicionar")
    if submitted and name:
        new = WishlistEntry(name=name, action=action, priority=int(priority), notes=notes)
        save_wishlist(Wishlist(entries=wishlist.entries + [new]))
        st.cache_data.clear()
        st.success(f"✅ {name} adicionado à wishlist")
        st.rerun()

st.divider()

# ---- heroes that ARE owned but not yet in wishlist (suggestion list)
st.subheader("Sugestões — heroes seus que têm meta build mas não estão na wishlist")
suggested = []
for h in save.heroes:
    if h.name not in existing_names and meta.get(h.name) is not None:
        suggested.append({"Hero": h.name, "Rarity": h.rarity})
if suggested:
    st.dataframe(pd.DataFrame(suggested), use_container_width=True, hide_index=True)
else:
    st.caption("Você já adicionou todos os heroes próprios que estão no meta.")
