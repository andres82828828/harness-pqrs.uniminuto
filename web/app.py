"""Aplicacion web del Sistema Inteligente de PQRS.

Lo que hace:
  - Ingreso solo con correo institucional y un codigo de un solo uso.
  - Radicacion por texto, audio o foto: guarda el original en el data lake
    (bucket pqrs-raw) y registra el caso en PostgreSQL.
  - Seguimiento: muestra la clasificacion que deja el harness en pqrs_casos,
    el estado, el plazo de respuesta y cuanto tardo el sistema.
  - Panel para funcionarios y administradores (panel.py).

La web NO clasifica: eso lo hace el harness, que lee del data lake.
"""
import hashlib
import json
import os
import re
import secrets
import urllib.request
from datetime import datetime, timedelta, timezone

import segno
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import panel
import reglas
from comun import (AQUI, BUCKET, ESQUEMA, bd, caso, casos, enviar_correo, ir, pagina, partes_de, s3,
                   usuario_actual)

app = FastAPI(title="PQRS Inteligente")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
    max_age=8 * 3600,
)
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
app.include_router(panel.router)


@app.on_event("startup")
def preparar():
    with bd() as con:
        con.execute(ESQUEMA)
    cliente = s3()
    existentes = {b["Name"] for b in cliente.list_buckets().get("Buckets", [])}
    if BUCKET not in existentes:
        cliente.create_bucket(Bucket=BUCKET)


# ------------------------------------------------------------------ ingreso
def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


@app.get("/")
def inicio(request: Request):
    return ir("/nueva" if usuario_actual(request) else "/ingreso")


@app.get("/ingreso")
def ingreso(request: Request):
    return pagina(request, "ingreso.html", dominios=reglas.dominios_permitidos())


@app.post("/ingreso")
def pedir_codigo(request: Request, correo: str = Form(...)):
    correo = correo.strip().lower()
    if not reglas.correo_permitido(correo):  # RN-01
        return pagina(
            request, "ingreso.html", dominios=reglas.dominios_permitidos(), correo=correo,
            error="Solo se permite el ingreso con correo institucional "
                  + " o ".join("@" + d for d in reglas.dominios_permitidos()) + ".",
        )
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    with bd() as con:
        con.execute(
            """INSERT INTO codigos_acceso (correo, codigo_hash, expira_en, intentos)
               VALUES (%s, %s, LOCALTIMESTAMP + make_interval(mins => %s), 0)
               ON CONFLICT (correo) DO UPDATE
               SET codigo_hash = EXCLUDED.codigo_hash, expira_en = EXCLUDED.expira_en, intentos = 0""",
            (correo, huella(codigo), reglas.MINUTOS_CODIGO),
        )
    try:
        enviar_correo(
            correo, f"Tu código de acceso PQRS: {codigo}",
            f"Tu código de acceso al sistema de PQRS es {codigo}.\n"
            f"Vence en {reglas.MINUTOS_CODIGO} minutos. Si no lo pediste, ignora este mensaje.",
        )
    except Exception as e:  # el correo no salio: se informa, no se oculta
        print(f"ERROR enviando correo a {correo}: {e}", flush=True)
        return pagina(
            request, "ingreso.html", dominios=reglas.dominios_permitidos(), correo=correo,
            error="No se pudo enviar el código. Revisa que el servicio de correo esté encendido.",
        )
    request.session["correo_pendiente"] = correo
    return ir("/codigo")


@app.get("/codigo")
def codigo_form(request: Request):
    correo = request.session.get("correo_pendiente")
    if not correo:
        return ir("/ingreso")
    return pagina(request, "codigo.html", correo=correo, minutos=reglas.MINUTOS_CODIGO)


@app.post("/codigo")
def validar_codigo(request: Request, codigo: str = Form(...)):
    correo = request.session.get("correo_pendiente")
    if not correo:
        return ir("/ingreso")
    codigo = re.sub(r"\D", "", codigo)
    with bd() as con:
        fila = con.execute(
            """UPDATE codigos_acceso SET intentos = intentos + 1 WHERE correo = %s
               RETURNING codigo_hash, intentos, expira_en < LOCALTIMESTAMP AS vencido""",
            (correo,),
        ).fetchone()
        error = None
        if not fila or fila["vencido"]:
            error = "El código venció. Pide uno nuevo."
        elif fila["intentos"] > reglas.INTENTOS_CODIGO:
            error = "Demasiados intentos. Pide un código nuevo."
        elif not secrets.compare_digest(fila["codigo_hash"], huella(codigo)):
            error = "Código incorrecto."
        if error:
            return pagina(request, "codigo.html", correo=correo, minutos=reglas.MINUTOS_CODIGO, error=error)
        con.execute("DELETE FROM codigos_acceso WHERE correo = %s", (correo,))
        rol = "admin" if correo in reglas.correos_admin() else "usuario"
        u = con.execute(
            """INSERT INTO usuarios (correo, rol) VALUES (%s, %s)
               ON CONFLICT (correo) DO UPDATE
               SET rol = CASE WHEN EXCLUDED.rol = 'admin' THEN 'admin' ELSE usuarios.rol END
               RETURNING id, correo, rol""",
            (correo, rol),
        ).fetchone()
    request.session.clear()
    request.session["usuario"] = {"id": u["id"], "correo": u["correo"], "rol": u["rol"]}
    return ir("/panel" if u["rol"] in ("admin", "funcionario") else "/nueva")


@app.post("/salir")
def salir(request: Request):
    request.session.clear()
    return ir("/ingreso")


# --------------------------------------------------------------- radicacion
@app.get("/nueva")
def nueva(request: Request):
    if not usuario_actual(request):
        return ir("/ingreso")
    return pagina(request, "nueva.html", limites=reglas.LIMITES)


@app.post("/nueva")
async def radicar(
    request: Request,
    texto: str = Form(""),
    acepta: str = Form(""),
    audio: UploadFile | None = File(None),
    foto: UploadFile | None = File(None),
):
    """Una PQRS puede traer texto, un audio y una foto, juntos o por separado.

    Se guarda como paquete en el data lake (pqrs-raw/radicaciones/<radicado>/) y el
    manifiesto se escribe de ultimo: es la senal de que el paquete esta completo.
    """
    u = usuario_actual(request)
    if not u:
        return ir("/ingreso")

    def rechazo(mensaje):
        return pagina(request, "nueva.html", limites=reglas.LIMITES, texto=texto, error=mensaje)

    if acepta != "si":  # RN-04
        return rechazo("Debes aceptar el tratamiento de datos personales para radicar.")

    # RN-07: validar cada parte
    partes = []  # (tipo, nombre_en_paquete, contenido)
    for tipo, archivo in (("audio", audio), ("foto", foto)):
        if archivo and archivo.filename:
            datos = await archivo.read(reglas.LIMITES[tipo]["max_bytes"] + 1)
            contenido, extension, error = reglas.validar_archivo(tipo, archivo.filename, datos)
            if error:
                return rechazo(("Audio: " if tipo == "audio" else "Foto: ") + error)
            partes.append((tipo, f"{tipo}.{extension}", contenido))
    if texto.strip():
        contenido, _, error = reglas.validar_texto(texto, con_adjuntos=bool(partes))
        if error:
            return rechazo(error)
        partes.insert(0, ("texto", "texto.txt", contenido))
    if not partes:
        return rechazo("Escribe tu PQRS, graba un audio o adjunta una foto.")

    canal = partes[0][0] if len(partes) == 1 else "mixto"
    sha = hashlib.sha256(b"".join(hashlib.sha256(c).digest() for _, _, c in partes)).hexdigest()
    with bd() as con:
        hoy = con.execute(  # RN-08
            "SELECT COUNT(*) AS n FROM radicaciones WHERE usuario_id = %s AND recibido_en::date = CURRENT_DATE",
            (u["id"],),
        ).fetchone()["n"]
        if hoy >= reglas.max_radicaciones_dia():
            return rechazo(f"Ya radicaste {hoy} PQRS hoy. El máximo es {reglas.max_radicaciones_dia()} por día.")
        repetida = con.execute(
            "SELECT radicado FROM radicaciones WHERE usuario_id = %s AND sha256 = %s", (u["id"], sha)
        ).fetchone()
        if repetida:
            return rechazo(f"Ya radicaste este mismo contenido con el número {repetida['radicado']}.")

        numero = con.execute("SELECT nextval('radicado_seq') AS n").fetchone()["n"]
        radicado = reglas.formato_radicado(datetime.now().year, numero)  # RN-05
        carpeta = f"{reglas.CARPETA_PAQUETES}/{radicado}"
        # "fecha" va en el manifiesto porque el harness la copia a fecha_recepcion y el
        # reporte mensual agrupa por ese campo (hora de Colombia, UTC-5).
        hoy_co = datetime.now(timezone(timedelta(hours=-5))).date().isoformat()
        lista = [{"tipo": t, "archivo": n} for t, n, _ in partes]

        # RN-06: primero los originales al data lake, despues el manifiesto y el registro
        cliente = s3()
        for _, nombre, contenido in partes:
            cliente.put_object(Bucket=BUCKET, Key=f"{carpeta}/{nombre}", Body=contenido)
        manifiesto = {"radicado": radicado, "fecha": hoy_co, "partes": lista}
        cliente.put_object(Bucket=BUCKET, Key=f"{carpeta}/{reglas.MANIFIESTO}",
                           Body=json.dumps(manifiesto, ensure_ascii=False).encode("utf-8"),
                           ContentType="application/json", Metadata={"fecha": hoy_co})
        con.execute(
            """INSERT INTO radicaciones (radicado, usuario_id, canal, archivo_origen, sha256, acepta_datos, partes)
               VALUES (%s, %s, %s, %s, %s, TRUE, %s)""",
            (radicado, u["id"], canal, f"{carpeta}/{reglas.MANIFIESTO}", sha, json.dumps(lista)),
        )
        con.execute(
            "INSERT INTO historial (radicado, usuario_id, accion, detalle) VALUES (%s, %s, 'Radicada', %s)",
            (radicado, u["id"], " + ".join(t for t, _, _ in partes)),
        )
    return ir(f"/caso/{radicado}")


# -------------------------------------------------------------- seguimiento
def caso_propio(radicado: str, u):
    c = caso(radicado)
    if not c or (c["usuario_id"] != u["id"] and u["rol"] != "admin"):  # cada quien ve lo suyo
        return None
    return c


@app.get("/caso/{radicado}")
def ver_caso(request: Request, radicado: str):
    u = usuario_actual(request)
    if not u:
        return ir("/ingreso")
    c = caso_propio(radicado, u)
    if not c:
        return pagina(request, "mensaje.html", titulo="Caso no encontrado",
                      texto="Ese radicado no existe o no te pertenece.")
    return pagina(request, "caso.html", caso=c, partes=partes_de(c))


@app.get("/api/caso/{radicado}")
def estado_caso(request: Request, radicado: str):
    u = usuario_actual(request)
    if not u:
        return JSONResponse({"error": "sin sesion"}, status_code=401)
    c = caso_propio(radicado, u)
    if not c:
        return JSONResponse({"error": "no encontrado"}, status_code=404)
    return {"estado": c["estado"], "segundos_desde": c["segundos_desde"]}


@app.get("/mis-casos")
def mis_casos(request: Request):
    u = usuario_actual(request)
    if not u:
        return ir("/ingreso")
    return pagina(request, "mis_casos.html", casos=casos("WHERE r.usuario_id = %s", (u["id"],)))


# ------------------------------------------------------------ acceso (QR)
def url_publica():
    """Enlace publico: el fijado en PUBLIC_URL o el que reporta el tunel."""
    if os.environ.get("PUBLIC_URL"):
        return os.environ["PUBLIC_URL"]
    base = os.environ.get("TUNNEL_METRICS")
    if not base:
        return None
    try:
        with urllib.request.urlopen(base + "/quicktunnel", timeout=2) as r:
            host = json.load(r).get("hostname")
        return f"https://{host}" if host else None
    except Exception:
        return None


@app.get("/acceso")
def acceso(request: Request):
    url = url_publica()
    qr = segno.make(url, error="m").svg_inline(scale=7, border=2) if url else None
    return pagina(request, "acceso.html", url=url, qr=qr)


@app.get("/api/enlace")
def enlace():
    """Enlace publico actual del tunel; lo usa scripts/publicar_enlace.py para la pagina de GitHub Pages."""
    return {"url": url_publica()}


@app.get("/salud")
def salud():
    with bd() as con:
        con.execute("SELECT 1")
    return {"ok": True}
