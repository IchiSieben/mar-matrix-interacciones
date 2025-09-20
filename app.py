# app.py  —  Dashboard simple: lee ./out/*_matrix.xlsx (hoja 'pairs') o *_pairs.csv
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from pathlib import Path

# ================== Config ==================
SEV_ORDER = ["Contraindicated", "Major", "Moderate", "Minor", "Unspecified"]
SEV_COLOR = {
    "Contraindicated": "#FF6B6B",  # rojo
    "Major":           "#FF9C6E",  # naranja
    "Moderate":        "#FFC000",  # ámbar
    "Minor":           "#FFFF99",  # amarillo
    "Unspecified":     "#ADD8E6",  # celeste
}

st.set_page_config(page_title="Interacciones fármaco–fármaco", layout="wide")

# ================== Carga de archivo ==================
def pick_input_file():
    out = Path(__file__).resolve().parent / "out"
    if not out.exists():
        st.error("No existe la carpeta **./out**. Corre primero `build_interaction_matrix.py`.")
        st.stop()
    xlsx = sorted(out.glob("*_matrix.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    csv  = sorted(out.glob("*_pairs.csv"),   key=lambda p: p.stat().st_mtime, reverse=True)
    files = xlsx + csv
    if not files:
        st.error("No hay `*_matrix.xlsx` ni `*_pairs.csv` en **./out**.")
        st.stop()
    default = 0
    path = st.sidebar.selectbox("Archivo de entrada (./out)", files, index=default, format_func=lambda p: p.name)
    return path

def read_pairs(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path, sheet_name="pairs", engine="openpyxl")
    else:
        df = pd.read_csv(path)
    # Normaliza severidad
    df["severity"] = pd.Categorical(df["severity"], SEV_ORDER, ordered=True)
    df["severity"] = df["severity"].astype(str).where(df["severity"].notna(), "Unspecified")
    # Asegura columnas esenciales
    need = {"drug_a","drug_b","severity","documentation","summary"}
    missing = need - set(df.columns)
    if missing:
        st.error(f"Faltan columnas en {path.name}: {missing}")
        st.stop()
    return df

path = pick_input_file()
df = read_pairs(path)
st.caption(f"Fuente: out/{path.name}")

# ================== UI: una droga vs todas ==================
all_drugs = sorted(set(df["drug_a"]).union(df["drug_b"]))
drug = st.selectbox("Fármaco", all_drugs, index=0)

sub = df[(df["drug_a"] == drug) | (df["drug_b"] == drug)].copy()
sub["other"] = sub.apply(lambda r: r["drug_b"] if r["drug_a"] == drug else r["drug_a"], axis=1)
sub = sub[["other", "severity", "documentation", "summary"]].sort_values(["severity", "other"])

c1, c2 = st.columns([1.2, 1.8])
with c1:
    st.subheader(f"{drug} vs otros")
    st.dataframe(sub, use_container_width=True, height=420)

with c2:
    # Heatmap por severidad (columnas = severidad, filas = 'other')
    # Matriz 0/1
    pivot = (sub.assign(v=1)
               .pivot_table(index="other", columns="severity", values="v",
                            aggfunc="max", fill_value=0)
               .reindex(columns=SEV_ORDER, fill_value=0))
    rows = pivot.index.tolist()
    cols = pivot.columns.tolist()

    # Para colorear por severidad: codificamos cada columna con un valor entero 1..N y 0=blanco
    Z = np.zeros_like(pivot.values, dtype=float)
    for j, sev in enumerate(cols, start=1):
        Z[:, j-1] = np.where(pivot[sev].to_numpy() > 0, j, 0)

    # Escala de color "discreta": 0 gris claro, 1..N colores por severidad
    N = max(1, len(cols))
    colorscale = [(0.0, "#EEEEEE")]
    for j, sev in enumerate(cols, start=1):
        t0 = (j-0.00001)/N; t1 = j/N  # pasos casi-discretos
        col = SEV_COLOR.get(sev, "#CCCCCC")
        colorscale += [(t0, col), (t1, col)]


    # Hover: mostramos severidad y un snippet de resumen
    text = np.empty((len(rows), len(cols)), dtype=object)
    for i, oth in enumerate(rows):
        for j, sev in enumerate(cols):
            r = sub[(sub["other"] == oth) & (sub["severity"] == sev)]
            if not r.empty:
                s = str(r.iloc[0]["summary"] or "")
                s = s.replace("\n", " ")
                # recorta a 300 chars máx
                text[i, j] = s if len(s) <= 300 else (s[:297] + "…")
            else:
                text[i, j] = ""