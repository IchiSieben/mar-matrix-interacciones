# app.py — Dashboard Interacciones (robusto p/ Streamlit Cloud)
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import plotly.graph_objects as go

SEV_ORDER = ["Contraindicated", "Major", "Moderate", "Minor", "Unspecified"]
SEV_COLOR = {
    "Contraindicated": "#FF6B6B",
    "Major":           "#FF9C6E",
    "Moderate":        "#FFC000",
    "Minor":           "#FFFF99",
    "Unspecified":     "#ADD8E6",
}

st.set_page_config(page_title="Interacciones fármaco–fármaco", layout="wide")

BASE = Path(__file__).resolve().parent
OUT = BASE / "out"
OUT.mkdir(parents=True, exist_ok=True)  # asegura ./out

def _save_uploaded_to_out(file):
    dest = OUT / file.name
    with dest.open("wb") as f:
        f.write(file.getbuffer())
    return dest

def pick_input_file():
    # busca archivos conocidos
    xlsx = sorted(OUT.glob("*_matrix.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    csv  = sorted(OUT.glob("*_pairs.csv"),   key=lambda p: p.stat().st_mtime, reverse=True)
    files = xlsx + csv

    # si no hay, permitir subir
    if not files:
        st.warning("No hay `*_matrix.xlsx` ni `*_pairs.csv` en ./out.")
        up = st.file_uploader("Sube archivo (xlsx/csv) con la hoja/tabla 'pairs'", type=["xlsx","csv"])
        if up is None:
            st.stop()
        saved = _save_uploaded_to_out(up)
        st.success(f"Guardado en out/{saved.name}")
        files = [saved]

    path = st.sidebar.selectbox(
        "Archivo de entrada (./out)", files, index=0, format_func=lambda p: p.name
    )
    return Path(path)

def read_pairs(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path, sheet_name="pairs", engine="openpyxl")
    else:
        df = pd.read_csv(path)

    # nombres de columnas en minúsculas
    df.columns = [c.lower() for c in df.columns]

    # columnas mínimas
    need = {"drug_a", "drug_b", "severity", "documentation", "summary"}
    missing = need - set(df.columns)
    if missing:
        st.error(f"Faltan columnas en {path.name}: {missing}")
        st.stop()

    # --- Normalización robusta de 'severity' ---
    sev = df["severity"].astype("string").fillna("Unspecified")
    sev_cat = pd.Series(
        pd.Categorical(sev, categories=SEV_ORDER, ordered=True),
        index=df.index
    )
    df["severity"] = sev_cat.astype("string").fillna("Unspecified")

    # limpieza de strings (¡usa .str.strip()!)
    for c in ["drug_a", "drug_b", "documentation", "summary"]:
        df[c] = df[c].astype("string").str.strip()

    return df


path = pick_input_file()
df = read_pairs(path)
st.caption(f"Fuente: out/{path.name}")

# UI — selector de fármaco
all_drugs = sorted(set(df["drug_a"]).union(df["drug_b"]))
drug = st.selectbox("Fármaco", all_drugs, index=0)

sub = df[(df["drug_a"] == drug) | (df["drug_b"] == drug)].copy()
sub["other"] = np.where(sub["drug_a"] == drug, sub["drug_b"], sub["drug_a"])
sub = sub[["other", "severity", "documentation", "summary"]].sort_values(["severity", "other"])

c1, c2 = st.columns([1.2, 1.8])
with c1:
    st.subheader(f"{drug} vs otros")
    st.dataframe(sub, use_container_width=True, height=420)

with c2:
    pivot = (
        sub.assign(v=1)
        .pivot_table(index="other", columns="severity", values="v", aggfunc="max", fill_value=0)
        .reindex(columns=SEV_ORDER, fill_value=0)
    )
    rows = pivot.index.tolist()
    cols = pivot.columns.tolist()

    # z por columna (1..N) y 0 vacío
    Z = np.zeros_like(pivot.values, dtype=float)
    for j, sev in enumerate(cols, start=1):
        Z[:, j - 1] = np.where(pivot[sev].to_numpy() > 0, j, 0)

    # paleta discreta
    N = max(1, len(cols))
    colorscale = [(0.0, "#EEEEEE")]
    for j, sev in enumerate(cols, start=1):
        t0 = (j - 0.00001) / N
        t1 = j / N
        colorscale += [(t0, SEV_COLOR.get(sev, "#CCCCCC")), (t1, SEV_COLOR.get(sev, "#CCCCCC"))]

    # tooltips (snippet del summary)
    text = np.empty((len(rows), len(cols)), dtype=object)
    for i, oth in enumerate(rows):
        for j, sev in enumerate(cols):
            r = sub[(sub["other"] == oth) & (sub["severity"] == sev)]
            if not r.empty:
                s = str(r.iloc[0]["summary"] or "").replace("\n", " ")
                text[i, j] = s[:297] + "…" if len(s) > 300 else s
            else:
                text[i, j] = ""

    fig = go.Figure(
        data=go.Heatmap(
            z=Z, x=cols, y=rows, text=text, hoverinfo="text", colorscale=colorscale, showscale=False
        )
    )
    fig.update_layout(height=520, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption("Tip: si no hay archivos en `./out`, puedes subir un `*_pairs.csv` o `*_matrix.xlsx` con la hoja `pairs`.")
