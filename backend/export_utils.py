from io import BytesIO
from typing import List, Dict, Any, Tuple
import pandas as pd

# Usar backend headless para matplotlib (sin display)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader


def build_dataframe(rows: List[Dict[str, Any]]) -> pd.DataFrame:
    """Convierte una lista de dicts en DataFrame ordenado por ts (asc)."""
    if not rows:
        return pd.DataFrame(columns=["ts", "device_ip", "endpoint", "name", "value", "type"])
    df = pd.DataFrame(rows)
    # Asegurar columnas esperadas
    for col in ["ts", "device_ip", "endpoint", "name", "value", "type"]:
        if col not in df.columns:
            df[col] = None
    # Orden por timestamp ascendente si existe
    if "ts" in df.columns:
        df = df.sort_values("ts")
    return df[["ts", "device_ip", "endpoint", "name", "value", "type"]]


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "data") -> bytes:
    """Devuelve un archivo XLSX en bytes con el contenido del DataFrame.

    Intentamos usar openpyxl; si no está, probamos con xlsxwriter.
    """
    bio = BytesIO()
    try:
        with pd.ExcelWriter(bio, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
    except Exception:
        with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
    return bio.getvalue()


def plot_to_png_bytes(x, y, title: str) -> bytes:
    """Genera un PNG (bytes) de una serie simple."""
    bio = BytesIO()
    fig = plt.figure(figsize=(8, 3))
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel("Fecha/Hora")
    plt.ylabel("Valor")
    plt.grid(True, alpha=.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(bio, format="png", dpi=150)
    plt.close(fig)
    return bio.getvalue()


def make_pdf_with_charts(datasets: List[Tuple[str, pd.DataFrame]]) -> bytes:
    """Crea un PDF con una página por sensor (gráfico + resumen)."""
    pdf_bytes = BytesIO()
    c = canvas.Canvas(pdf_bytes, pagesize=A4)
    width, height = A4

    for name, df in datasets:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(40, height - 40, f"Sensor: {name}")

        if df.empty:
            c.setFont("Helvetica", 10)
            c.drawString(40, height - 60, "Sin datos en el rango seleccionado.")
            c.showPage()
            continue

        # Gráfico
        png = plot_to_png_bytes(df["ts"], df["value"], f"{name}")
        img = ImageReader(BytesIO(png))
        img_w = width - 80
        img_h = img_w * 0.4
        c.drawImage(img, 40, height - 80 - img_h, width=img_w, height=img_h)

        # Resumen
        c.setFont("Helvetica", 10)
        c.drawString(40, height - 90 - img_h, f"Observaciones: {len(df)}")
        if "value" in df.columns and len(df):
            try:
                vmin = float(pd.to_numeric(df["value"], errors="coerce").min())
                vmax = float(pd.to_numeric(df["value"], errors="coerce").max())
                vmean = float(pd.to_numeric(df["value"], errors="coerce").mean())
                c.drawString(40, height - 105 - img_h, f"Min: {vmin:.3f}  Max: {vmax:.3f}  Prom: {vmean:.3f}")
            except Exception:
                c.drawString(40, height - 105 - img_h, "Resumen no disponible (valores no numéricos).")

        c.showPage()

    c.save()
    return pdf_bytes.getvalue()
