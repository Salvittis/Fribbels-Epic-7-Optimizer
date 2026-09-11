"""GW Meta — explore the Fribbels GW meta snapshot.

⚠️ Upstream backend stopped accepting fresh submissions ~Feb 2025.
   We surface the maxTimestamp prominently so you know what era this reflects.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "webapp") not in sys.path:
    sys.path.insert(0, str(ROOT / "webapp"))

import pandas as pd
import streamlit as st

from shared import (
    FribbelsClient, get_client,
    render_save_picker,
)
from e7bot.builder import GwMetaClient, HeroCodeBook


st.set_page_config(page_title="GW Meta", page_icon="🛡️", layout="wide")
st.title("🛡️ Guild War Meta")
st.caption("Snapshot do meta de defesas em GW + counters mais usados.")

render_save_picker()

# ---- Cached resources --------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _gw_client() -> GwMetaClient:
    return GwMetaClient()


@st.cache_data(ttl=86400, show_spinner="Carregando herodata (mapeamento c1022 → Ruele)...")
def _codebook() -> HeroCodeBook:
    fc = FribbelsClient()
    herodata = fc.fetch_herodata()
    return HeroCodeBook(herodata)


@st.cache_data(ttl=86400, show_spinner="Carregando snapshot do GW meta...")
def _snapshot(force: bool = False):
    return _gw_client().fetch_meta(force=force)


book = _codebook()
snap = _snapshot()

# ---- Banner com idade dos dados ---------------------------------------------

age_days = snap.data_age_days
data_date = snap.data_date
if age_days > 90:
    st.error(
        f"⚠️ **Dados antigos**: o backend do Fribbels parou de receber novas "
        f"submissões em **{data_date}** (há {age_days:.0f} dias). "
        f"Use os números como referência histórica — top defenses não mudam tão rápido, "
        f"mas heroes lançados depois de Fev/2025 não aparecem aqui."
    )
elif age_days > 30:
    st.warning(f"⚠️ Dados de {data_date} ({age_days:.0f} dias atrás).")
else:
    st.info(f"📅 Dados de {data_date} ({age_days:.0f} dias atrás).")

c1, c2, c3 = st.columns(3)
c1.metric("Defenses no snapshot", len(snap.defenses))
c2.metric("Heroes em offenseData", len(snap.offense_data))
c3.metric("Total matches", sum(d.total_matches for d in snap.defenses))


# ---- Tabs --------------------------------------------------------------------

tab_top, tab_search, tab_counter = st.tabs([
    "🏆 Top defenses", "🔍 Buscar por hero", "🎯 Counters de defesa"
])


# ---- Tab: Top defenses -------------------------------------------------------

with tab_top:
    st.markdown("Defenses mais vistas no top do ladder. WR = win rate da defesa "
                "(o quanto ela aguenta).")

    sort_options = {
        "Mais vistas (matches totais)": lambda d: -d.total_matches,
        "Maior win rate (defesas resilientes)": lambda d: -d.winrate,
        "Menor win rate (defesas frágeis)": lambda d: d.winrate,
    }
    sort_by = st.selectbox("Ordenar por", list(sort_options.keys()), index=0)

    rows = []
    for d in sorted(snap.defenses, key=sort_options[sort_by]):
        rows.append({
            "Hero 1": book.name_of(d.units[0]),
            "Hero 2": book.name_of(d.units[1]),
            "Hero 3": book.name_of(d.units[2]),
            "W": d.wins, "L": d.losses, "D": d.draws,
            "Total": d.total_matches,
            "WR%": round(d.winrate * 100, 1),
            "code_csv": ",".join(d.units),
        })
    df_top = pd.DataFrame(rows)
    st.dataframe(
        df_top,
        use_container_width=True,
        hide_index=True,
        height=600,
        column_config={
            "WR%": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100,
            ),
            "code_csv": st.column_config.TextColumn("Defense ID", width="small"),
        },
    )


# ---- Tab: Search by hero -----------------------------------------------------

with tab_search:
    st.markdown("Filtrar defenses que **contém** ou **excluem** um hero específico.")

    all_names = sorted({book.name_of(c) for d in snap.defenses for c in d.units})

    c1, c2 = st.columns(2)
    include = c1.selectbox("Deve ter este hero", ["(qualquer)"] + all_names, index=0)
    exclude = c2.selectbox("Não deve ter este hero", ["(nenhum)"] + all_names, index=0)

    filtered = snap.defenses
    if include != "(qualquer)":
        target = book.code_of(include)
        if target:
            filtered = [d for d in filtered if target in d.units]
    if exclude != "(nenhum)":
        target = book.code_of(exclude)
        if target:
            filtered = [d for d in filtered if target not in d.units]

    st.markdown(f"**{len(filtered)} defenses** correspondem ao filtro.")
    rows = [{
        "Hero 1": book.name_of(d.units[0]),
        "Hero 2": book.name_of(d.units[1]),
        "Hero 3": book.name_of(d.units[2]),
        "Total": d.total_matches,
        "WR%": round(d.winrate * 100, 1),
        "code_csv": ",".join(d.units),
    } for d in sorted(filtered, key=lambda x: -x.total_matches)]
    if rows:
        st.dataframe(
            pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500,
            column_config={"WR%": st.column_config.ProgressColumn(
                format="%.1f%%", min_value=0, max_value=100)},
        )
    else:
        st.info("Nenhuma defesa no snapshot com esse filtro.")


# ---- Tab: Counters -----------------------------------------------------------

with tab_counter:
    st.markdown("Cole o **Defense ID** (3 codes separados por vírgula) ou monte "
                "selecionando heroes. Veja os offenses mais usados contra essa defesa.")

    method = st.radio("Como informar", ["Selecionar 3 heroes", "Colar Defense ID"],
                      horizontal=True)

    units: list[str] = []
    if method == "Selecionar 3 heroes":
        all_names = sorted({book.name_of(c) for d in snap.defenses for c in d.units})
        cols = st.columns(3)
        for i, col in enumerate(cols):
            with col:
                pick = st.selectbox(f"Hero {i+1}", ["(escolha)"] + all_names,
                                    key=f"def_pick_{i}")
                if pick != "(escolha)":
                    code = book.code_of(pick)
                    if code:
                        units.append(code)
    else:
        s = st.text_input("Defense ID (ex: c1104,c1153,c1162)")
        if s:
            units = [p.strip() for p in s.split(",") if p.strip()]

    if len(units) == 3:
        with st.spinner("Buscando counters..."):
            try:
                resp = _gw_client().fetch_def(units)
            except Exception as e:
                st.error(f"Falha ao buscar: {e}")
                st.stop()

        offense_comps = resp.get("data") or []
        names = book.names_of(units)
        st.subheader(f"Defense: {' + '.join(names)}")

        if not offense_comps:
            st.warning("Sem dados de counter pra essa defense no snapshot atual.")
        else:
            rows = []
            for comp in offense_comps:
                # The API returns offense rows with similar w/l/d structure
                off_units = (comp.get("offense") or "").split(",")
                if len(off_units) != 3:
                    continue
                w, l, d = int(comp.get("w", 0) or 0), int(comp.get("l", 0) or 0), int(comp.get("d", 0) or 0)
                tot = w + l + d
                wr = (w / tot) * 100 if tot else 0
                rows.append({
                    "Off 1": book.name_of(off_units[0]),
                    "Off 2": book.name_of(off_units[1]),
                    "Off 3": book.name_of(off_units[2]),
                    "W": w, "L": l, "D": d, "Total": tot,
                    "WR%": round(wr, 1),
                })
            df = pd.DataFrame(rows).sort_values("Total", ascending=False)
            st.dataframe(
                df, use_container_width=True, hide_index=True,
                column_config={"WR%": st.column_config.ProgressColumn(
                    format="%.1f%%", min_value=0, max_value=100)},
            )
    elif units:
        st.info("Selecione 3 heroes pra buscar counters.")


# ---- Sidebar: refresh -------------------------------------------------------

with st.sidebar:
    st.divider()
    st.subheader("GW Meta cache")
    if st.button("🔄 Re-fetch snapshot (ignora cache)", use_container_width=True):
        _snapshot.clear()
        st.cache_data.clear()
        st.rerun()
