"""Reglas de negocio de la capa web (los codigos RN-xx son los del documento)."""
import os
from datetime import datetime, timedelta

# RN-07: limites de entrada
LIMITES = {
    "texto": {"min": 20, "max": 2000},
    "audio": {"max_bytes": 10 * 1024 * 1024, "extensiones": ["mp3", "wav", "m4a", "ogg", "webm", "aac", "opus"]},
    "foto": {"max_bytes": 5 * 1024 * 1024, "extensiones": ["png", "jpg", "jpeg"]},
}
# Carpetas del bucket pqrs-raw que lee el harness
CARPETAS = {"texto": "textos", "audio": "audios", "foto": "fotos"}
# PQRS de la web: una carpeta por radicado con sus partes y un manifiesto
CARPETA_PAQUETES = "radicaciones"
MANIFIESTO = "manifiesto.json"

# RN-15: plazo de respuesta en dias habiles segun la urgencia
PLAZO_DIAS_HABILES = {"alta": 1, "media": 5, "baja": 15}

MINUTOS_CODIGO = 10
INTENTOS_CODIGO = 5


def dominios_permitidos():
    return [d.strip().lower() for d in os.environ.get("DOMINIOS_PERMITIDOS", "uniminuto.edu.co").split(",") if d.strip()]


def correos_admin():
    return {c.strip().lower() for c in os.environ.get("CORREOS_ADMIN", "").split(",") if c.strip()}


def max_radicaciones_dia():
    return int(os.environ.get("MAX_RADICACIONES_DIA", "5"))  # RN-08


def correo_permitido(correo: str) -> bool:
    """RN-01: el correo debe ser de un dominio institucional exacto."""
    if correo.count("@") != 1 or " " in correo or len(correo) > 120:
        return False
    nombre, dominio = correo.split("@")
    return bool(nombre) and dominio in dominios_permitidos()


def formato_radicado(anio: int, numero: int) -> str:
    return f"PQRS-{anio}-{numero:06d}"  # RN-05


def validar_texto(texto: str, con_adjuntos: bool = False):
    """Devuelve (contenido, extension, error). Con audio o foto, el texto puede ser una nota corta."""
    texto = texto.strip()
    lim = LIMITES["texto"]
    if len(texto) < lim["min"] and not con_adjuntos:
        return None, None, f"El texto es muy corto: escribe al menos {lim['min']} caracteres."
    if len(texto) > lim["max"]:
        return None, None, f"El texto supera los {lim['max']} caracteres."
    return texto.encode("utf-8"), "txt", None


def validar_archivo(canal: str, nombre: str, datos: bytes):
    """Devuelve (contenido, extension, error)."""
    lim = LIMITES[canal]
    extension = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if extension not in lim["extensiones"]:
        return None, None, "Formato no permitido. Usa: " + ", ".join(lim["extensiones"]) + "."
    if len(datos) > lim["max_bytes"]:
        return None, None, f"El archivo supera el máximo de {lim['max_bytes'] // (1024 * 1024)} MB."
    if len(datos) == 0:
        return None, None, "El archivo está vacío."
    return datos, extension, None


def fecha_limite(recibido: datetime, urgencia: str) -> datetime:
    """RN-15: suma dias habiles (lunes a viernes; no descuenta festivos)."""
    faltan = PLAZO_DIAS_HABILES[urgencia]
    fecha = recibido
    while faltan > 0:
        fecha += timedelta(days=1)
        if fecha.weekday() < 5:
            faltan -= 1
    return fecha


def semaforo(recibido: datetime, limite: datetime, ahora: datetime) -> str:
    """RN-16: verde en plazo, amarillo con menos del 25 % del plazo, rojo vencido."""
    total = (limite - recibido).total_seconds()
    resta = (limite - ahora).total_seconds()
    if resta < 0:
        return "rojo"
    if total > 0 and resta / total < 0.25:
        return "amarillo"
    return "verde"


# ------------------------------------------------------------------ catalogos
# RN-09: valores cerrados que puede tomar la clasificacion
TIPOS = ["peticion", "queja", "reclamo", "sugerencia"]
URGENCIAS = ["alta", "media", "baja"]

# RN-10: area responsable segun el tema (la misma tabla que aplica el harness)
AREA_POR_TEMA = {
    "notas": "Registro Académico",
    "finanzas": "Tesorería",
    "infraestructura": "Infraestructura",
    "bienestar": "Bienestar Universitario",
    "servicios": "Servicios Generales",
    "docentes": "Decanatura",
    "tecnologia": "Soporte TI",
    "biblioteca": "Biblioteca",
}
TEMAS = list(AREA_POR_TEMA)
AREAS = sorted(set(AREA_POR_TEMA.values()))

# RN-14: estados del caso
ETIQUETA_ESTADO = {
    "en_proceso": "En proceso",
    "revision_manual": "Revisión manual",
    "clasificada": "Clasificada",
    "en_gestion": "En gestión",
    "respondida": "Respondida",
    "cerrada": "Cerrada",
}
ESTADOS_GESTION = ["en_gestion", "respondida", "cerrada"]
MIN_RESPUESTA = 10

ETIQUETAS = {
    "peticion": "Petición", "queja": "Queja", "reclamo": "Reclamo", "sugerencia": "Sugerencia",
    "notas": "Notas", "finanzas": "Finanzas", "infraestructura": "Infraestructura",
    "bienestar": "Bienestar", "servicios": "Servicios", "docentes": "Docentes",
    "tecnologia": "Tecnología", "biblioteca": "Biblioteca",
    "alta": "Alta", "media": "Media", "baja": "Baja",
    "usuario": "Usuario", "funcionario": "Funcionario de área", "admin": "Administrador",
}
ROLES = ["usuario", "funcionario", "admin"]


def validar_clasificacion(tipo: str, tema: str, urgencia: str):
    """RN-09: la correccion de un funcionario tambien usa los catalogos cerrados."""
    if tipo not in TIPOS or tema not in TEMAS or urgencia not in URGENCIAS:
        return "Selecciona tipo, tema y urgencia de las listas."
    return None


def validar_cambio_estado(actual: str, nuevo: str, respuesta: str):
    """RN-14: el caso avanza clasificada -> en gestion -> respondida -> cerrada."""
    if actual in ("en_proceso", "revision_manual"):
        return "Primero hay que clasificar el caso."
    if actual == "cerrada":
        return "El caso ya está cerrado."
    if nuevo not in ESTADOS_GESTION:
        return "Estado no válido."
    if nuevo == "respondida" and len(respuesta.strip()) < MIN_RESPUESTA:
        return f"Escribe la respuesta al usuario (mínimo {MIN_RESPUESTA} caracteres)."
    if nuevo == "cerrada" and actual != "respondida":
        return "Solo se puede cerrar un caso que ya fue respondido."
    return None
