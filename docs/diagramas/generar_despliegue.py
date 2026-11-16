"""Genera el diagrama de despliegue del Sistema Inteligente de PQRS.

Uso:  python generar_despliegue.py
Crea despliegue_pqrs.png (para Word) y despliegue_pqrs.svg / .pdf (para LaTeX).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle

AQUI = Path(__file__).parent
TINTA = "#1F2933"
SUAVE = "#52606D"
NODO = ("#F2F3F5", "#6B7280")
CONT = ("#FFFFFF", "#2F6DB5")
DATOS = ("#E7F5EC", "#2E8B57")
HARNESS = ("#FDF0E1", "#C9741A")
IA = ("#F0EAFA", "#6B4BB3")

fig, ax = plt.subplots(figsize=(11.5, 7.6))
ax.set_xlim(0, 172)
ax.set_ylim(0, 112)
ax.axis("off")


def nodo(x, y, w, h, titulo, lineas=(), d=2.2, tam=9, color=NODO):
    """Nodo de despliegue (caja 3D), como en UML."""
    fondo, borde = color
    ax.add_patch(Polygon([(x, y + h), (x + d, y + h + d), (x + w + d, y + h + d), (x + w, y + h)],
                         closed=True, facecolor="#E4E7EB", edgecolor=borde, linewidth=1.2, zorder=1))
    ax.add_patch(Polygon([(x + w, y), (x + w + d, y + d), (x + w + d, y + h + d), (x + w, y + h)],
                         closed=True, facecolor="#D9DDE3", edgecolor=borde, linewidth=1.2, zorder=1))
    ax.add_patch(Rectangle((x, y), w, h, facecolor=fondo, edgecolor=borde, linewidth=1.2, zorder=1))
    if titulo:
        texto_centrado(x, y, w, h, titulo, lineas, tam)


def contenedor(x, y, w, h, titulo, lineas=(), color=CONT, tam=8.6):
    fondo, borde = color
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.2",
                                facecolor=fondo, edgecolor=borde, linewidth=1.3, zorder=3))
    texto_centrado(x, y, w, h, titulo, lineas, tam)


def texto_centrado(x, y, w, h, titulo, lineas, tam=8.6):
    n = len(lineas)
    alto = 3.3 + n * 2.9
    y0 = y + h / 2 + alto / 2 - 1.7
    ax.text(x + w / 2, y0, titulo, ha="center", va="center", fontsize=tam, fontweight="bold",
            color=TINTA, zorder=5)
    for i, t in enumerate(lineas):
        ax.text(x + w / 2, y0 - 3.3 - i * 2.9, t, ha="center", va="center", fontsize=7.4,
                color=TINTA, zorder=5)


def flecha(p, q, texto="", doble=False, color=TINTA, lado="right", dx=0, dy=0, estilo="-"):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="<|-|>" if doble else "-|>", mutation_scale=11,
                                 linewidth=1.2, color=color, linestyle=estilo, zorder=6))
    if texto:
        mx, my = (p[0] + q[0]) / 2 + dx, (p[1] + q[1]) / 2 + dy
        ax.text(mx, my, texto, ha="left" if lado == "right" else "center", va="center",
                fontsize=7.4, color=color, zorder=7,
                bbox=dict(facecolor="white", edgecolor="none", pad=0.5, alpha=0.95))


def linea(puntos, color=SUAVE, ancho=1.2):
    xs, ys = zip(*puntos)
    ax.plot(xs, ys, color=color, linewidth=ancho, zorder=4, solid_capstyle="round")


# ---------- Titulo ----------
ax.text(86, 107.5, "Diagrama de despliegue del Sistema Inteligente de PQRS", ha="center", va="center",
        fontsize=13, fontweight="bold", color=TINTA)

# ---------- Izquierda: codigo ----------
nodo(4, 72, 27, 13, "Equipo de desarrollo", ["código del proyecto", "Git + GitHub Desktop"])
nodo(4, 44, 27, 13, "GitHub", ["harness-pqrs.uniminuto", "+ página de acceso (Pages)"])
flecha((17.5, 72), (17.5, 59.5), "git push", dx=1.5)
flecha((34, 50.5), (42, 50.5), "")
ax.text(38, 47, "git clone", ha="center", va="center", fontsize=7.4, color=TINTA)

ax.text(4, 33, "Cómo se despliega", ha="left", va="center", fontsize=8.6, fontweight="bold", color=TINTA)
pasos = [
    "1. El equipo sube el código a GitHub.",
    "2. En el portátil: git clone y",
    "    docker compose up.",
    "3. El túnel publica un enlace",
    "    HTTPS y un código QR.",
    "4. Los usuarios abren el enlace",
    "    en el PC o en el celular.",
]
for i, t in enumerate(pasos):
    ax.text(4, 28.6 - i * 3.1, t, ha="left", va="center", fontsize=7.4, color=TINTA)

# ---------- Centro: servidor ----------
nodo(42, 5, 94, 92, "")
ax.text(89, 93.2, "Portátil de demostración  ·  Windows + Docker Desktop", ha="center", va="center",
        fontsize=9.5, fontweight="bold", color=TINTA, zorder=5)
ax.add_patch(FancyBboxPatch((45, 9), 88, 80, boxstyle="round,pad=0,rounding_size=1.6",
                            facecolor="#FBFCFD", edgecolor="#9AA5B1", linewidth=1.1,
                            linestyle=(0, (5, 4)), zorder=2))
ax.text(48, 86.6, "Docker Compose  ·  un contenedor por servicio", ha="left", va="center",
        fontsize=8, color=SUAVE, fontweight="bold", zorder=5)

# Fila de acceso
contenedor(48, 72, 20, 11.5, "mailpit", ["correo de prueba", "puerto 8025"])
contenedor(72, 72, 32, 11.5, "web  ·  FastAPI", ["páginas para PC y celular", "puerto 8000"])
contenedor(108, 72, 21, 11.5, "cloudflared", ["túnel HTTPS", "enlace + QR"])
flecha((104, 77.75), (108, 77.75), doble=True)

# Red interna
BUS_Y = 66
linea([(50, BUS_Y), (131.5, BUS_Y)], color="#7B8794", ancho=2.4)
ax.text(59.5, BUS_Y + 1.9, "red interna de Docker", ha="left", va="center", fontsize=7.2,
        color=SUAVE, style="italic", zorder=5)
for xs in (58, 88):
    linea([(xs, 72), (xs, BUS_Y)])

# Harness: espacio de trabajo del agente
ax.add_patch(FancyBboxPatch((48, 13), 36, 46, boxstyle="round,pad=0,rounding_size=1.4",
                            facecolor=HARNESS[0], edgecolor=HARNESS[1], linewidth=1.4, zorder=3))
ax.text(66, 55.6, "harness", ha="center", va="center", fontsize=9, fontweight="bold", color=TINTA, zorder=5)
ax.text(66, 52.4, "espacio de trabajo del agente", ha="center", va="center", fontsize=7.4,
        color=TINTA, zorder=5)
tareas = [
    ("Tarea 1 · extraer texto", "Whisper · Tesseract"),
    ("Tarea 2 · clasificar", "tipo · tema · urgencia"),
    ("Tarea 3 · reporte mensual", "matplotlib → PDF"),
]
for i, (t, s) in enumerate(tareas):
    yb = 40.5 - i * 9.3
    ax.add_patch(FancyBboxPatch((50.5, yb), 31, 7.6, boxstyle="round,pad=0,rounding_size=1",
                                facecolor="white", edgecolor=HARNESS[1], linewidth=1, zorder=4))
    ax.text(66, yb + 5.2, t, ha="center", va="center", fontsize=7.6, fontweight="bold", color=TINTA, zorder=5)
    ax.text(66, yb + 2.2, s, ha="center", va="center", fontsize=7.2, color=TINTA, zorder=5)
ax.text(66, 15.4, "toma los casos pendientes en ciclo", ha="center", va="center", fontsize=7,
        color=SUAVE, style="italic", zorder=5)
linea([(66, 59), (66, BUS_Y)])

# Agente de IA
contenedor(87, 13, 14.5, 46, "Agente IA", ["Ollama", "", "llama3.2:3b", "", "modelo local", "puerto 11434"],
           color=IA, tam=8.4)
linea([(94.25, 59), (94.25, BUS_Y)])
flecha((84, 36), (87, 36), doble=True)

# Datos
contenedor(104.5, 39, 24.5, 20, "RustFS 1.0.0", ["data lake (S3)", "puertos 9000 · 9001", "vol. datalake_data"], color=DATOS)
contenedor(104.5, 13, 24.5, 20, "PostgreSQL 16", ["base de datos", "puerto 5432", "vol. pg_data"], color=DATOS)
linea([(116.75, 59), (116.75, BUS_Y)])
linea([(129, 23), (131.5, 23), (131.5, BUS_Y)])

# ---------- Derecha: acceso de usuarios ----------
ax.add_patch(Ellipse((154, 80), 30, 13, facecolor="#EEF2F7", edgecolor=SUAVE, linewidth=1.2, zorder=3))
ax.text(154, 81.6, "Internet", ha="center", va="center", fontsize=8.8, fontweight="bold", color=TINTA, zorder=5)
ax.text(154, 78.2, "Cloudflare", ha="center", va="center", fontsize=7.4, color=TINTA, zorder=5)
flecha((129, 80), (139, 80), doble=True)

nodo(139, 49, 13, 11, "PC", ["navegador"], d=1.6)
nodo(155.5, 49, 13, 11, "Celular", ["navegador"], d=1.6)
flecha((149, 73.6), (146, 62.5), "", doble=False)
flecha((159, 73.6), (162, 62.5), "", doble=False)
ax.text(154, 66.8, "HTTPS", ha="center", va="center", fontsize=7.4, color=TINTA, zorder=7,
        bbox=dict(facecolor="white", edgecolor="none", pad=0.4))
ax.text(154, 44, "Acceso solo con correo\n@uniminuto.edu.co", ha="center", va="center",
        fontsize=7.6, style="italic", color=SUAVE)
ax.text(154, 33, "Respaldo sin internet:\ncelular en la misma red WiFi\nhttp://IP-del-portátil:8000",
        ha="center", va="center", fontsize=7, color=SUAVE)

fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
for ext, kw in (("png", {"dpi": 300}), ("svg", {}), ("pdf", {})):
    fig.savefig(AQUI / f"despliegue_pqrs.{ext}", facecolor="white", **kw)
print("Listo: despliegue_pqrs.png / .svg / .pdf")
