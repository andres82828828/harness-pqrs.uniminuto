"""Piezas compartidas por la web del usuario y el panel: conexiones, sesion,
plantillas, esquema de la base y armado de cada caso con sus reglas."""
import os
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path

import boto3
import psycopg
from botocore.config import Config
from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from psycopg.rows import dict_row

import reglas

AQUI = Path(__file__).parent
BUCKET = "pqrs-raw"
BUCKET_REPORTES = "pqrs-reportes"
DSN = (
    f"host={os.environ.get('POSTGRES_HOST', 'postgres')} dbname=pqrs "
    f"user={os.environ['POSTGRES_USER']} password={os.environ['POSTGRES_PASSWORD']}"
)

plantillas = Jinja2Templates(directory=AQUI / "templates")
plantillas.env.globals.update(ETIQUETA_ESTADO=reglas.ETIQUETA_ESTADO, reglas=reglas)
plantillas.env.filters["et"] = lambda v: reglas.ETIQUETAS.get(v, (v or "").capitalize())
plantillas.env.filters["fecha"] = lambda d, f="%d/%m/%Y %H:%M": d.strftime(f) if d else ""


# ---------------------------------------------------------------- conexiones
def bd():
    return psycopg.connect(DSN, row_factory=dict_row)


def s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://rustfs:9000"),
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )


BUZON_LOCAL = (os.environ.get("BUZON_LOCAL_HOST", "mailpit"), int(os.environ.get("BUZON_LOCAL_PUERTO", "1025")))


def _mensaje(remitente: str, destino: str, asunto: str, cuerpo: str):
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = f"PQRS Inteligente <{remitente}>"
    msg["To"] = destino
    msg.set_content(cuerpo)
    return msg


def correo_real_configurado() -> bool:
    """Hay correo real solo si estan la cuenta y su contrasena de aplicacion."""
    return bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"))


def enviar_correo(destino: str, asunto: str, cuerpo: str) -> str:
    """Envia un correo y devuelve por donde salio: "real" o "buzon_local".

    Con SMTP_USER en el .env usa el correo real (p. ej. Gmail con contrasena de aplicacion).
    Si ese envio falla, o si no hay correo real configurado, lo deja en el buzon local de
    prueba (Mailpit, http://localhost:8025) para que nadie quede bloqueado sin su codigo.
    Si tambien falla el buzon local, lanza la excepcion.
    """
    if correo_real_configurado():
        usuario = os.environ["SMTP_USER"]
        try:
            with smtplib.SMTP(os.environ.get("SMTP_HOST", "smtp.gmail.com"),
                              int(os.environ.get("SMTP_PORT", "587")), timeout=15) as smtp:
                smtp.starttls()
                # Google muestra la contrasena de aplicacion en grupos con espacios: se ignoran
                smtp.login(usuario, os.environ.get("SMTP_PASSWORD", "").replace(" ", ""))
                # Gmail exige que el remitente sea la propia cuenta
                smtp.send_message(_mensaje(os.environ.get("SMTP_FROM") or usuario, destino, asunto, cuerpo))
            return "real"
        except Exception as e:  # se registra sin datos de la cuenta y se usa el respaldo
            print(f"AVISO: el correo real fallo ({type(e).__name__}: {str(e)[:120]}); "
                  f"se usa el buzon local de respaldo", flush=True)
    with smtplib.SMTP(*BUZON_LOCAL, timeout=10) as smtp:
        smtp.send_message(_mensaje(os.environ.get("SMTP_FROM_LOCAL", "pqrs@uniminuto.edu.co"), destino, asunto, cuerpo))
    return "buzon_local"


# ------------------------------------------------------------------ esquema
ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id         SERIAL PRIMARY KEY,
    correo     TEXT UNIQUE NOT NULL,
    rol        TEXT NOT NULL DEFAULT 'usuario' CHECK (rol IN ('usuario', 'funcionario', 'admin')),
    area       TEXT,
    creado_en  TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS codigos_acceso (
    correo      TEXT PRIMARY KEY,
    codigo_hash TEXT NOT NULL,
    expira_en   TIMESTAMP NOT NULL,
    intentos    INT NOT NULL DEFAULT 0
);
CREATE SEQUENCE IF NOT EXISTS radicado_seq;
-- Una fila por cada PQRS radicada desde la web. La clasificacion del modelo
-- queda en pqrs_casos (la escribe el harness) y se une por archivo_origen.
CREATE TABLE IF NOT EXISTS radicaciones (
    id             SERIAL PRIMARY KEY,
    radicado       TEXT UNIQUE NOT NULL,
    usuario_id     INT NOT NULL REFERENCES usuarios (id),
    canal          TEXT NOT NULL CHECK (canal IN ('texto', 'audio', 'foto')),
    archivo_origen TEXT UNIQUE NOT NULL,
    sha256         TEXT NOT NULL,
    acepta_datos   BOOLEAN NOT NULL,
    recibido_en    TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_radicaciones_usuario ON radicaciones (usuario_id);
-- Desde que una PQRS puede traer texto, audio y foto juntos
ALTER TABLE radicaciones DROP CONSTRAINT IF EXISTS radicaciones_canal_check;
ALTER TABLE radicaciones ADD CONSTRAINT radicaciones_canal_check CHECK (canal IN ('texto', 'audio', 'foto', 'mixto'));
ALTER TABLE radicaciones ADD COLUMN IF NOT EXISTS partes JSONB;
-- Misma definicion que db/init.sql y el harness, por si la web arranca primero
ALTER TABLE pqrs_casos ADD COLUMN IF NOT EXISTS segundos_clasificacion REAL;
CREATE TABLE IF NOT EXISTS pqrs_partes (
    id              SERIAL PRIMARY KEY,
    archivo_origen  TEXT NOT NULL REFERENCES pqrs_casos (archivo_origen) ON DELETE CASCADE,
    tipo            TEXT NOT NULL CHECK (tipo IN ('texto', 'audio', 'foto')),
    archivo         TEXT NOT NULL,
    texto_extraido  TEXT,
    segundos        REAL,
    error           TEXT
);
-- Gestion humana del caso. La correccion se guarda aparte para no perder
-- la respuesta original del modelo (RN-13).
CREATE TABLE IF NOT EXISTS gestion (
    radicado        TEXT PRIMARY KEY REFERENCES radicaciones (radicado),
    tipo            TEXT CHECK (tipo IN ('peticion', 'queja', 'reclamo', 'sugerencia')),
    tema            TEXT,
    urgencia        TEXT CHECK (urgencia IN ('baja', 'media', 'alta')),
    estado          TEXT CHECK (estado IN ('en_gestion', 'respondida', 'cerrada')),
    respuesta       TEXT,
    respondida_en   TIMESTAMP,
    actualizado_por INT REFERENCES usuarios (id),
    actualizado_en  TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS historial (
    id          SERIAL PRIMARY KEY,
    radicado    TEXT NOT NULL REFERENCES radicaciones (radicado),
    usuario_id  INT REFERENCES usuarios (id),
    accion      TEXT NOT NULL,
    detalle     TEXT,
    creado_en   TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_historial_radicado ON historial (radicado);
"""


# ------------------------------------------------------------------- sesion
def usuario_actual(request: Request):
    return request.session.get("usuario")


def usuario_bd(request: Request):
    """Relee el usuario desde la base, para que un cambio de rol aplique de inmediato."""
    u = usuario_actual(request)
    if not u:
        return None
    with bd() as con:
        fila = con.execute("SELECT id, correo, rol, area FROM usuarios WHERE id = %s", (u["id"],)).fetchone()
    if not fila:
        request.session.clear()
        return None
    request.session["usuario"] = {"id": fila["id"], "correo": fila["correo"], "rol": fila["rol"]}
    return dict(fila)


def pagina(request: Request, nombre: str, **datos):
    datos.setdefault("usuario", usuario_actual(request))
    return plantillas.TemplateResponse(request, nombre, datos)


def ir(ruta: str):
    return RedirectResponse(ruta, status_code=303)


# -------------------------------------------------------------------- casos
LOCAL = "(({col}) AT TIME ZONE current_setting('TimeZone')) AT TIME ZONE 'America/Bogota'"
CONSULTA_CASO = f"""
SELECT r.radicado, r.canal, r.archivo_origen, r.usuario_id, u.correo, r.partes AS partes_radicadas,
       c.archivo_origen AS archivo_caso, c.segundos_clasificacion,
       {LOCAL.format(col='r.recibido_en')} AS recibido_local,
       EXTRACT(EPOCH FROM (LOCALTIMESTAMP - r.recibido_en)) AS segundos_desde,
       c.id AS caso_id, c.tipo AS tipo_modelo, c.tema AS tema_modelo, c.urgencia AS urgencia_modelo,
       c.area_destino AS area_modelo, c.clasificador, c.texto_extraido,
       EXTRACT(EPOCH FROM (c.creado_en - r.recibido_en)) AS segundos_proceso,
       g.tipo AS tipo_corr, g.tema AS tema_corr, g.urgencia AS urgencia_corr,
       g.estado AS estado_gestion, g.respuesta,
       {LOCAL.format(col='g.respondida_en')} AS respondida_local
FROM radicaciones r
JOIN usuarios u ON u.id = r.usuario_id
LEFT JOIN pqrs_casos c
       ON c.archivo_origen = r.archivo_origen
       OR c.archivo_origen LIKE '%%/' || r.archivo_origen
LEFT JOIN gestion g ON g.radicado = r.radicado
"""


def armar_caso(fila):
    """Combina la salida del modelo con la gestion humana y aplica estado, plazo y semaforo."""
    caso = dict(fila)
    corregido = any(fila[f"{c}_corr"] for c in ("tipo", "tema", "urgencia"))
    for campo in ("tipo", "tema", "urgencia"):
        caso[campo] = fila[f"{campo}_corr"] or fila[f"{campo}_modelo"]
    caso["corregido"] = corregido and any(
        fila[f"{c}_corr"] != fila[f"{c}_modelo"] for c in ("tipo", "tema", "urgencia"))
    if fila["tema_corr"]:  # RN-10: si un funcionario cambia el tema, el area sale de la tabla
        caso["area_destino"] = reglas.AREA_POR_TEMA.get(fila["tema_corr"])
    else:
        caso["area_destino"] = fila["area_modelo"] or reglas.AREA_POR_TEMA.get(fila["tema_modelo"])

    if fila["caso_id"] is None and not corregido:
        caso["estado"] = "en_proceso"
    elif not (caso["tipo"] and caso["tema"] and caso["urgencia"]):
        caso["estado"] = "revision_manual"  # RN-12
    else:
        caso["estado"] = fila["estado_gestion"] or "clasificada"

    caso["segundos_desde"] = int(fila["segundos_desde"])
    ahora = fila["recibido_local"] + timedelta(seconds=float(fila["segundos_desde"]))
    caso["semaforo"] = None
    if caso["urgencia"] and caso["estado"] not in ("en_proceso", "revision_manual"):
        limite = reglas.fecha_limite(fila["recibido_local"], caso["urgencia"])  # RN-15
        caso["fecha_limite"] = limite
        caso["dias_plazo"] = reglas.PLAZO_DIAS_HABILES[caso["urgencia"]]
        if caso["estado"] in ("respondida", "cerrada"):
            caso["a_tiempo"] = bool(fila["respondida_local"] and fila["respondida_local"] <= limite)
        else:
            caso["semaforo"] = reglas.semaforo(fila["recibido_local"], limite, ahora)  # RN-16
    if fila["segundos_proceso"] is not None:
        caso["segundos_proceso"] = max(0.0, round(float(fila["segundos_proceso"]), 1))
    return caso


def partes_de(c: dict):
    """Partes de una PQRS: lo que el harness extrajo de cada una, o lo radicado si aun no lo procesa."""
    if c.get("archivo_caso"):
        with bd() as con:
            filas = con.execute(
                """SELECT tipo, archivo, texto_extraido, segundos, error FROM pqrs_partes
                   WHERE archivo_origen = %s
                   ORDER BY array_position(ARRAY['texto', 'audio', 'foto'], tipo)""",
                (c["archivo_caso"],),
            ).fetchall()
        if filas:
            return [dict(f) for f in filas]
    if c.get("partes_radicadas"):
        return [{"tipo": p["tipo"], "archivo": p["archivo"], "texto_extraido": None, "segundos": None, "error": None}
                for p in c["partes_radicadas"]]
    # PQRS de un solo archivo (datos sinteticos o radicadas antes de los paquetes)
    return [{"tipo": c["canal"], "archivo": c["archivo_origen"], "texto_extraido": c.get("texto_extraido"),
             "segundos": None, "error": None}]


def clave_parte(c: dict, tipo: str):
    """Clave en el bucket pqrs-raw del archivo original de una parte."""
    if c.get("partes_radicadas"):
        carpeta = c["archivo_origen"].rsplit("/", 1)[0]
        for p in c["partes_radicadas"]:
            if p["tipo"] == tipo:
                return f"{carpeta}/{p['archivo']}"
        return None
    return c["archivo_origen"] if c["canal"] == tipo else None


def casos(where: str = "", params=(), orden: str = "r.recibido_en DESC"):
    with bd() as con:
        filas = con.execute(f"{CONSULTA_CASO} {where} ORDER BY {orden}", params).fetchall()
    return [armar_caso(f) for f in filas]


def caso(radicado: str):
    lista = casos("WHERE r.radicado = %s", (radicado,))
    return lista[0] if lista else None


def puede_ver(u: dict, c: dict) -> bool:
    """El usuario ve sus casos; el funcionario, los de su area; el administrador, todos."""
    if u["rol"] == "admin" or c["usuario_id"] == u["id"]:
        return True
    return u["rol"] == "funcionario" and bool(u.get("area")) and c["area_destino"] == u.get("area")
