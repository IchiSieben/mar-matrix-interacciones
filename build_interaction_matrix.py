# app.py
import io
import os
from pathlib import Path
import numpy as np
import pandas as pd
import streamlit as st

# ====== Apariencia básica ======
st.set_page_config(page_title="Matriz de Interacciones", layout="wide")
st.title("Matriz de Interacciones - Vista Rápida")

# ====== Utilidades ======
SEV_CODE = {
    "Contraindicated": "CI",
    "Major": "MAJ",
    "Moderate": "MOD",
    "Minor": "MIN",
    "Unspecified": "UNS"
}
# Paleta (celdas solo para CI/MAJ/MOD; MIN/UNS en blanco)
COLOR = {"CI": "#ff6b6b", "MAJ": "#ff9c6e", "MOD": "#ffc000"}

def read_pairs_from_upload(uploaded_file: st.runtime.uploaded_file_manager.UploadedFile) -> pd.DataFrame:
    """Lee 'pairs' desde CSV o Excel (hoja 'pairs')."""
    name = uploaded_file.name.lower()
    buf = io.BytesIO(uploaded_file.getvalue())
    if name.endswith(".csv"):
        df = pd.read_csv(buf)
    elif name.endswith(".xlsx") or name.endswith(".xlsm"):
        # Intentar hoja 'pairs'
        df = pd.read_excel(buf, sheet_name="pairs", engine="openpyxl")
    else:
        raise ValueError("Formato no soportado. Sube un CSV 'pairs' o un Excel con hoja 'pairs'.")
    required = {"drug_a", "drug_b", "severity", "summary"}
    faltan = required - set(map(str.lower, df.columns))
    if faltan:
        # Tolerar capitalización distinta:
        cols = {c.lower(): c for c in df.columns}
        try:
            df = df[[cols["drug_a"], cols["drug_b"], cols["severity"], cols["summary"]]].rename(
                columns={cols["drug_a"]: "drug_a", cols["drug_b"]: "drug_b",
                         cols["severity"]: "severity", cols["summary"]: "summary"}
            )
        except Exception:
            st.stop()
    return df

def sev_code(s):
    return SEV_CODE.get(str(s), "UNS")

def build_matrices(df_pairs: pd.DataFrame):
    """Desde pairs -> matriz de códigos y conteos por fármaco."""
    # Solo nos interesan CI/MAJ/MOD para colorear
    df_pairs["code"] = df_pairs["severity"].map(sev_code)

    drugs = sorted(set(df_pairs["drug_a"]).union(df_pairs["drug_b"]))
    mat = pd.DataFrame("", index=drugs, columns=drugs)

    for _, r in df_pairs.iterrows():
        a, b, code = r["drug_a"], r["drug_b"], r["code"]
        # Solo pintamos CI/MAJ/MOD
        if code in {"CI", "MAJ", "MOD"}:
            mat.at[a, b] = code
            mat.at[b, a] = code

    # índice (recuento por fármaco)
    # Contamos por fila + columna (evitar duplicado, usamos pairs directamente)
    def pack_counts(g):
        vals = g["code"].value_counts()
        return pd.Series({
            "CI": int(vals.get("CI", 0)),
            "MAJ": int(vals.get("MAJ", 0)),
            "MOD": int(vals.get("MOD", 0)),
        })

    g1 = df_pairs[df_pairs["code"].isin(["CI","MAJ","MOD"])].groupby("drug_a").apply(pack_counts)
    g2 = df_pairs[df_pairs["code"].isin(["CI","MAJ","MOD"])].groupby("drug_b").apply(pack_counts)
    idx = pd.DataFrame(index=drugs, columns=["CI","MAJ","MOD"]).fillna(0).astype(int)
    for g in (g1, g2):
        idx = (idx.fillna(0) + g.reindex(idx.index).fillna(0)).astype(int)
    idx["Total"] = idx[["CI","MAJ","MOD"]].sum(axis=1)
    idx = idx.sort_values(["CI","MAJ","MOD","Total"], ascending=False)

    return mat, idx

def style_matrix(mat: pd.DataFrame) -> pd.io.formats.style.Styler:
    def colorize(v):
        c = COLOR.get(str(v), None)
        return f"background-color: {c}" if c else ""
    sty = mat.style.applymap(colorize)
    sty = sty.set_properties(**{"text-align": "center"}).set_table_styles(
        [{"selector":"th","props":[("text-align","center")]}]
    )
    return sty

# ====== UI: carga de archivo ======
with st.sidebar:
    st.header("Entrada")
    up = st.file_uploader(
        "Sube un CSV 'pairs' o un Excel con hoja 'pairs'",
        type=["csv","xlsx","xlsm"]
    )
    st.markdown("**Leyenda:**")
    cols = st.columns(3)
    cols[0].markdown(f"<div style='background:{COLOR['CI']};padding:6px;border-radius:4px;text-align:center;'>CI</div>", unsafe_allow_html=True)
    cols[1].markdown(f"<div style='background:{COLOR['MAJ']};padding:6px;border-radius:4px;text-align:center;'>MAJ</div>", unsafe_allow_html=True)
    cols[2].markdown(f"<div style='background:{COLOR['MOD']};padding:6px;border-radius:4px;text-align:center;'>MOD</div>", unsafe_allow_html=True)
    st.caption("Solo se colorean CI, MAJ y MOD. MIN/UNS quedan en blanco.")

if not up:
    st.info("Sube un archivo para comenzar (CSV `pairs` o Excel con hoja `pairs`).")
    st.stop()

# ====== Load & build ======
try:
    pairs = read_pairs_from_upload(up)
except Exception as e:
    st.error(f"No pude leer el archivo: {e}")
    st.stop()

mat, idx = build_matrices(pairs)

# ====== Vista rápida (matriz) ======
st.subheader("Matriz de severidad (CI/MAJ/MOD)")
st.dataframe(style_matrix(mat), use_container_width=True, height=650)

# ====== Índice por fármaco ======
st.subheader("Índice por fármaco (recuento de interacciones CI/MAJ/MOD)")
st.dataframe(idx, use_container_width=True)

# ====== Explorador por fármaco ======
st.subheader("Explorar un fármaco")
drug = st.selectbox("Fármaco", mat.index.tolist())
if drug:
    sub = pairs.copy()
    sub["code"] = sub["severity"].map(sev_code)
    sub = sub[sub["code"].isin(["CI","MAJ","MOD"])]
    sub["otro"] = np.where(sub["drug_a"] == drug, sub["drug_b"], sub["drug_a"])
    sub = sub[(sub["drug_a"] == drug) | (sub["drug_b"] == drug)]
    sub = sub[["otro","code","severity","summary"]].sort_values(["code","otro"])
    st.write(f"Interacciones **graves o moderadas** de **{drug}**:")
    st.dataframe(sub, use_container_width=True)
