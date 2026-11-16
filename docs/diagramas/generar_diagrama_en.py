"""Genera el diagrama de arquitectura del Sistema Inteligente de PQRS.

Uso:  python generar_diagrama.py
Crea arquitectura_pqrs.png (para Word) y arquitectura_pqrs.svg / .pdf (para LaTeX).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle

AQUI = Path(__file__).parent

# Colores por capa
AZUL = ("#E6F0FB", "#2F6DB5")      # presentacion
VERDE = ("#E7F5EC", "#2E8B57")     # datos
NARANJA = ("#FDF0E1", "#C9741A")   # harness
MORADO = ("#F0EAFA", "#6B4BB3")    # IA
GRIS = ("#F2F3F5", "#6B7280")      # apoyo
TINTA = "#1F2933"

fig, ax = plt.subplots(figsize=(11, 7.6))
ax.set_xlim(0, 160)
ax.set_ylim(0, 110)
ax.axis("off")


def caja(x, y, w, h, color, titulo, lineas=(), tam=9.5, tam_sub=8, punteada=False):
    fondo, borde = color
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=1.6",
        facecolor=fondo, edgecolor=borde, linewidth=1.4,
        linestyle="--" if punteada else "-", zorder=2))
    n = len(lineas)
    alto_total = 3.6 + n * 3.1
    y0 = y + h / 2 + alto_total / 2 - 1.9
    ax.text(x + w / 2, y0, titulo, ha="center", va="center", fontsize=tam,
            fontweight="bold", color=TINTA, zorder=3)
    for i, t in enumerate(lineas):
        ax.text(x + w / 2, y0 - 3.5 - i * 3.1, t, ha="center", va="center",
                fontsize=tam_sub, color=TINTA, zorder=3)


def flecha(p, q, num=None, texto="", dx=0, dy=0, ha="left", doble=False, color=TINTA, curva=0.0):
    ax.add_patch(FancyArrowPatch(
        p, q, arrowstyle="<|-|>" if doble else "-|>", mutation_scale=13,
        linewidth=1.3, color=color, zorder=4,
        connectionstyle=f"arc3,rad={curva}"))
    mx, my = (p[0] + q[0]) / 2 + dx, (p[1] + q[1]) / 2 + dy
    if num is not None:
        ax.add_patch(Circle((mx, my), 1.9, facecolor=TINTA, edgecolor="white",
                            linewidth=0.8, zorder=6))
        ax.text(mx, my - 0.1, str(num), ha="center", va="center", fontsize=7.5,
                color="white", fontweight="bold", zorder=7)
    if texto:
        desplaz = 2.8 if num is not None else 0
        ax.text(mx + (desplaz if ha == "left" else -desplaz), my, texto, ha=ha,
                va="center", fontsize=7.6, color=TINTA, zorder=6,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.6, alpha=0.9))


# ---------- Titulo ----------
ax.text(80, 107, "Architecture of the Intelligent PQRS System", ha="center",
        va="center", fontsize=13, fontweight="bold", color=TINTA)

# ---------- Usuarios ----------
caja(22, 92, 34, 10, GRIS, "User", ["student or lecturer", "phone or PC"])
caja(63, 92, 34, 10, GRIS, "Area officer", ["manages and answers", "the cases of their area"])
caja(104, 92, 34, 10, GRIS, "Administrator", ["management: dashboard", "and monthly report"])
ax.text(149, 97, "Access only with\nan @uniminuto.edu.co\nemail", ha="center", va="center",
        fontsize=7.8, style="italic", color=GRIS[1])

# ---------- Contenedor Docker ----------
ax.add_patch(FancyBboxPatch((3, 3), 154, 82, boxstyle="round,pad=0,rounding_size=2",
                            facecolor="#FBFCFD", edgecolor="#9AA5B1", linewidth=1.3,
                            linestyle=(0, (5, 4)), zorder=1))
ax.text(6, 5, "Laptop with Docker Compose  ·  processing and data stay on the machine",
        ha="left", va="center", fontsize=8.6, color="#52606D", fontweight="bold")

# ---------- Fila 1: presentacion ----------
caja(6, 64, 28, 13, GRIS, "Synthetic data", ["Python generator", "30 test cases"])
caja(42, 64, 76, 13, AZUL, "Web application  ·  FastAPI + responsive HTML  (port 8000)",
     ["Login  ·  New PQRS  ·  Tracking  ·  My cases  ·  Admin panel",
      "checks email domain, file limits and roles"])
caja(126, 64, 28, 13, GRIS, "Email", ["Gmail or local mailbox", "access code"])

# ---------- Fila 2: datos ----------
caja(6, 40, 58, 15, VERDE, "Data lake  ·  RustFS (S3-compatible)",
     ["pqrs-raw/   radicaciones/<filing>/  ·  textos  ·  audios  ·  fotos",
      "pqrs-reportes/   monthly PDF report"])
caja(96, 40, 58, 15, VERDE, "Database  ·  PostgreSQL 16",
     ["usuarios · radicaciones · pqrs_casos · pqrs_partes · gestion",
      "status, classification, deadline and timings of each case"])

# ---------- Fila 3: harness + IA ----------
ax.add_patch(FancyBboxPatch((6, 7), 108, 24, boxstyle="round,pad=0,rounding_size=1.6",
                            facecolor=NARANJA[0], edgecolor=NARANJA[1], linewidth=1.4, zorder=2))
ax.text(60, 27.6, "Harness  ·  Python container that processes each case (worker)",
        ha="center", va="center", fontsize=9.5, fontweight="bold", color=TINTA, zorder=3)
pasos = [
    ("Text extraction", ["direct reading", "Whisper (audio)", "Tesseract (photo)"]),
    ("Classification", ["prompt + validation", "type · topic", "urgency"]),
    ("Business rules", ["alert keywords", "responsible area", "response deadline"]),
    ("Report and evaluation", ["monthly PDF", "accuracy against", "labels"]),
]
x0, ancho, sep = 9, 23.5, 2.5
for i, (t, ls) in enumerate(pasos):
    x = x0 + i * (ancho + sep)
    ax.add_patch(FancyBboxPatch((x, 9.5), ancho, 15, boxstyle="round,pad=0,rounding_size=1.2",
                                facecolor="white", edgecolor=NARANJA[1], linewidth=1, zorder=3))
    ax.text(x + ancho / 2, 21.6, t, ha="center", va="center", fontsize=8.2,
            fontweight="bold", color=TINTA, zorder=4)
    for j, l in enumerate(ls):
        ax.text(x + ancho / 2, 18.2 - j * 2.9, l, ha="center", va="center", fontsize=7.4,
                color=TINTA, zorder=4)
    if i < 2:
        ax.add_patch(FancyArrowPatch((x + ancho, 17), (x + ancho + sep, 17), arrowstyle="-|>",
                                     mutation_scale=10, linewidth=1.1, color=NARANJA[1], zorder=5))

caja(124, 9, 30, 20, MORADO, "Local AI model", ["Ollama", "llama3.2:3b", "no internet needed"])

# ---------- Flechas ----------
# usuarios -> web
caja(42, 79.2, 76, 4.6, GRIS, "", [], tam=8)
ax.text(80, 81.5, "Access tunnel  ·  Cloudflare Tunnel  ·  HTTPS link + QR code", ha="center",
        va="center", fontsize=8.2, fontweight="bold", color=TINTA, zorder=5)
for xu in (39, 80, 121):
    flecha((xu, 92), (xu if xu == 80 else (62 if xu == 39 else 98), 83.8), doble=True, color="#52606D")
flecha((80, 79.2), (80, 77), doble=True, color="#52606D")
ax.text(84, 88.4, "browser (HTTPS)", ha="left", va="center", fontsize=7.6, color="#52606D",
        bbox=dict(facecolor="#FBFCFD", edgecolor="none", pad=0.4))

flecha((118, 70.5), (126, 70.5), color="#52606D")                       # web -> mailpit
flecha((20, 64), (20, 55), texto="initial load", dx=1.5, color="#52606D")  # generador -> lake

flecha((52, 64), (44, 55), 1, "stores the original", dx=0.5)             # web -> lake
flecha((104, 64), (112, 55), 2, "registers the filing", dx=-0.5, ha="right")
flecha((126, 55), (114, 64), 7, "reads status and timings", dx=0.5)    # web <- pg

flecha((18, 40), (18, 31), 4, "downloads the original", dx=0)             # lake -> harness
flecha((50, 31), (50, 40), 8, "uploads the report", dx=0, curva=0)         # harness -> lake (ver abajo)
flecha((102, 40), (102, 31), 3, "", dx=0)                               # pg -> harness
flecha((110, 31), (110, 40), 6, "", dx=0)                               # harness -> pg
flecha((114, 19), (124, 19), 5, "", dy=0, doble=True)                   # harness <-> ollama

# ---------- Leyenda de pasos ----------
ax.text(118, 36.6, "3  picks up the pending case\n6  stores result and timings", ha="left",
        va="center", fontsize=7.4, color=TINTA,
        bbox=dict(facecolor="white", edgecolor="none", pad=0.6, alpha=0.9))
ax.text(139, 5.6, "5  sends the text, receives\n    type, topic and urgency", ha="center",
        va="center", fontsize=7.4, color=TINTA)

fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
for ext, kw in (("png", {"dpi": 300}), ("svg", {}), ("pdf", {})):
    fig.savefig(AQUI / f"arquitectura_pqrs_en.{ext}", facecolor="white", **kw)
print("Listo: arquitectura_pqrs_en.png / .svg / .pdf")
