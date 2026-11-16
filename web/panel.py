"""Panel administrativo: bandeja por area, correccion de la clasificacion,
respuesta al usuario, tablero, reportes y gestion de roles.

  - Funcionario de area: ve y gestiona los casos de su area.
  - Administrador: ve todo, asigna roles y descarga los reportes.
"""
import mimetypes
from collections import Counter
from datetime import datetime

from fastapi import APIRouter, Form, Request
from fastapi.responses import Response, StreamingResponse

import reglas
from comun import (BUCKET, BUCKET_REPORTES, bd, caso, casos, clave_parte, enviar_correo, ir, pagina,
                   partes_de, puede_ver, s3, usuario_bd)

router = APIRouter(prefix="/panel")

TIPOS_ARCHIVO = {"m4a": "audio/mp4", "opus": "audio/ogg", "webm": "audio/webm", "txt": "text/plain; charset=utf-8"}
ORDEN_SEMAFORO = {"rojo": 0, "amarillo": 1, "verde": 2, None: 3}
ORDEN_ESTADO = {"revision_manual": 0, "clasificada": 1, "en_gestion": 1, "en_proceso": 2,
                "respondida": 3, "cerrada": 4}


def personal(request: Request, solo_admin: bool = False):
    u = usuario_bd(request)
    if not u:
        return None
    permitidos = ("admin",) if solo_admin else ("admin", "funcionario")
    return u if u["rol"] in permitidos else None


def sin_permiso(request: Request):
    if not usuario_bd(request):
        return ir("/ingreso")
    return pagina(request, "mensaje.html", titulo="Sin permiso",
                  texto="Esta sección es solo para funcionarios y administradores.")


def casos_visibles(u):
    """El administrador ve todos; el funcionario, solo los de su area."""
    todos = casos()
    if u["rol"] == "admin":
        return todos
    return [c for c in todos if u.get("area") and c["area_destino"] == u["area"]]


def anotar(con, radicado, usuario_id, accion, detalle=None):
    con.execute("INSERT INTO historial (radicado, usuario_id, accion, detalle) VALUES (%s, %s, %s, %s)",
                (radicado, usuario_id, accion, detalle))


# -------------------------------------------------------------------- bandeja
@router.get("")
def bandeja(request: Request, estado: str = "", urgencia: str = "", area: str = "", q: str = ""):
    u = personal(request)
    if not u:
        return sin_permiso(request)
    lista = casos_visibles(u)
    if u["rol"] == "admin" and area:
        lista = [c for c in lista if c["area_destino"] == area]
    if estado == "abiertos":
        lista = [c for c in lista if c["estado"] not in ("respondida", "cerrada")]
    elif estado:
        lista = [c for c in lista if c["estado"] == estado]
    if urgencia:
        lista = [c for c in lista if c["urgencia"] == urgencia]
    if q.strip():
        lista = [c for c in lista if q.strip().upper() in c["radicado"]]
    lista.sort(key=lambda c: (ORDEN_ESTADO[c["estado"]], ORDEN_SEMAFORO[c["semaforo"]],
                              c.get("fecha_limite") or datetime.max))
    return pagina(request, "panel_bandeja.html", usuario=u, casos=lista, seccion="bandeja",
                  filtro={"estado": estado, "urgencia": urgencia, "area": area, "q": q})


# -------------------------------------------------------------- detalle
def ver(request: Request, radicado: str, u, **extra):
    c = caso(radicado)
    if not c or not puede_ver(u, c):
        return pagina(request, "mensaje.html", usuario=u, titulo="Caso no encontrado",
                      texto="Ese radicado no existe o no pertenece a tu área.")
    with bd() as con:
        historial = con.execute(
            """SELECT h.accion, h.detalle, u.correo,
                      (h.creado_en AT TIME ZONE current_setting('TimeZone')) AT TIME ZONE 'America/Bogota' AS cuando
               FROM historial h LEFT JOIN usuarios u ON u.id = h.usuario_id
               WHERE h.radicado = %s ORDER BY h.creado_en DESC, h.id DESC""",
            (radicado,),
        ).fetchall()
    return pagina(request, "panel_caso.html", usuario=u, caso=c, historial=historial,
                  partes=partes_de(c), seccion="bandeja", **extra)


@router.get("/caso/{radicado}")
def detalle(request: Request, radicado: str):
    u = personal(request)
    if not u:
        return sin_permiso(request)
    return ver(request, radicado, u)


@router.post("/caso/{radicado}/clasificar")
def clasificar(request: Request, radicado: str, tipo: str = Form(""), tema: str = Form(""),
               urgencia: str = Form(""), motivo: str = Form("")):
    """RN-13: el funcionario corrige; la respuesta del modelo se conserva en pqrs_casos."""
    u = personal(request)
    if not u:
        return sin_permiso(request)
    c = caso(radicado)
    if not c or not puede_ver(u, c):
        return ver(request, radicado, u)
    error = reglas.validar_clasificacion(tipo, tema, urgencia)
    if not error and c["estado"] == "cerrada":
        error = "El caso ya está cerrado."
    if error:
        return ver(request, radicado, u, error=error)
    antes = f"{c['tipo'] or '-'} / {c['tema'] or '-'} / {c['urgencia'] or '-'}"
    with bd() as con:
        con.execute(
            """INSERT INTO gestion (radicado, tipo, tema, urgencia, actualizado_por)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (radicado) DO UPDATE
               SET tipo = EXCLUDED.tipo, tema = EXCLUDED.tema, urgencia = EXCLUDED.urgencia,
                   actualizado_por = EXCLUDED.actualizado_por, actualizado_en = NOW()""",
            (radicado, tipo, tema, urgencia, u["id"]),
        )
        detalle_txt = f"{antes} → {tipo} / {tema} / {urgencia}"
        if motivo.strip():
            detalle_txt += f". Motivo: {motivo.strip()[:300]}"
        anotar(con, radicado, u["id"], "Clasificación corregida", detalle_txt)
    nuevo = caso(radicado)
    if not puede_ver(u, nuevo):  # cambio de tema hacia otra area: sale de esta bandeja
        return pagina(request, "mensaje.html", usuario=u, titulo="Caso reasignado",
                      texto=f"El caso {radicado} pasó al área {nuevo['area_destino']}.")
    return ir(f"/panel/caso/{radicado}")


@router.post("/caso/{radicado}/estado")
def cambiar_estado(request: Request, radicado: str, estado: str = Form(""), respuesta: str = Form("")):
    u = personal(request)
    if not u:
        return sin_permiso(request)
    c = caso(radicado)
    if not c or not puede_ver(u, c):
        return ver(request, radicado, u)
    respuesta = respuesta.strip()
    error = reglas.validar_cambio_estado(c["estado"], estado, respuesta)
    if error:
        return ver(request, radicado, u, error=error, respuesta_borrador=respuesta)
    with bd() as con:
        con.execute(
            """INSERT INTO gestion (radicado, estado, respuesta, respondida_en, actualizado_por)
               VALUES (%(r)s, %(e)s, %(resp)s, CASE WHEN %(e)s = 'respondida' THEN NOW() END, %(u)s)
               ON CONFLICT (radicado) DO UPDATE
               SET estado = EXCLUDED.estado,
                   respuesta = CASE WHEN %(e)s = 'respondida' THEN EXCLUDED.respuesta ELSE gestion.respuesta END,
                   respondida_en = CASE WHEN %(e)s = 'respondida' THEN NOW() ELSE gestion.respondida_en END,
                   actualizado_por = EXCLUDED.actualizado_por, actualizado_en = NOW()""",
            {"r": radicado, "e": estado, "resp": respuesta if estado == "respondida" else None, "u": u["id"]},
        )
        anotar(con, radicado, u["id"], f"Estado: {reglas.ETIQUETA_ESTADO[estado]}",
               respuesta[:300] if estado == "respondida" else None)
    if estado == "respondida":  # avisar al usuario; si el correo falla, el caso igual queda respondido
        try:
            enviar_correo(c["correo"], f"Respuesta a tu PQRS {radicado}",
                          f"Tu PQRS {radicado} fue respondida:\n\n{respuesta}\n\n"
                          "Puedes consultarla en el sistema de PQRS, en Mis casos.")
        except Exception as e:
            print(f"ERROR avisando a {c['correo']}: {e}", flush=True)
    return ir(f"/panel/caso/{radicado}")


@router.get("/archivo/{radicado}/{parte}")
def archivo(request: Request, radicado: str, parte: str):
    """Entrega el original de una parte (texto, audio o foto) guardado en el data lake (solo lectura)."""
    u = personal(request)
    if not u:
        return Response(status_code=403)
    c = caso(radicado)
    if not c or not puede_ver(u, c):
        return Response(status_code=404)
    clave = clave_parte(c, parte)
    if not clave:
        return Response(status_code=404)
    obj = s3().get_object(Bucket=BUCKET, Key=clave)
    extension = clave.rsplit(".", 1)[-1].lower()
    tipo = TIPOS_ARCHIVO.get(extension) or mimetypes.guess_type(clave)[0] or "application/octet-stream"
    return StreamingResponse(obj["Body"].iter_chunks(), media_type=tipo,
                             headers={"Content-Disposition": f'inline; filename="{radicado}-{clave.split("/")[-1]}"'})


# -------------------------------------------------------------- tablero
def conteo(lista, campo, orden=None):
    total = Counter(c[campo] for c in lista if c[campo])
    claves = orden or sorted(total, key=lambda k: -total[k])
    maximo = max(total.values(), default=0)
    return [{"clave": k, "n": total.get(k, 0), "pct": round(100 * total.get(k, 0) / maximo) if maximo else 0}
            for k in claves]


@router.get("/tablero")
def tablero(request: Request):
    u = personal(request)
    if not u:
        return sin_permiso(request)
    lista = casos_visibles(u)
    clasificados = [c for c in lista if c["estado"] not in ("en_proceso", "revision_manual")]
    respondidos = [c for c in lista if c["estado"] in ("respondida", "cerrada")]
    tiempos = [c["segundos_proceso"] for c in lista if c.get("segundos_proceso") is not None]
    datos = {
        "total": len(lista),
        "abiertos": sum(c["estado"] not in ("respondida", "cerrada") for c in lista),
        "vencidos": sum(c["semaforo"] == "rojo" for c in lista),
        "revision": sum(c["estado"] == "revision_manual" for c in lista),
        "a_tiempo": round(100 * sum(c.get("a_tiempo", False) for c in respondidos) / len(respondidos)) if respondidos else None,
        "corregidos": round(100 * sum(c["corregido"] for c in clasificados) / len(clasificados)) if clasificados else None,
        "tiempo_medio": round(sum(tiempos) / len(tiempos), 1) if tiempos else None,
        "por_estado": conteo(lista, "estado", list(reglas.ETIQUETA_ESTADO)),
        "por_urgencia": conteo(lista, "urgencia", reglas.URGENCIAS),
        "por_tipo": conteo(lista, "tipo", reglas.TIPOS),
        "por_tema": conteo(lista, "tema"),
        "por_area": conteo(lista, "area_destino"),
        "por_canal": conteo(lista, "canal", ["texto", "audio", "foto"]),
    }
    return pagina(request, "panel_tablero.html", usuario=u, d=datos, seccion="tablero")


# ------------------------------------------------------------- reportes
@router.get("/reportes")
def reportes(request: Request):
    u = personal(request, solo_admin=True)
    if not u:
        return sin_permiso(request)
    try:
        objetos = s3().list_objects_v2(Bucket=BUCKET_REPORTES).get("Contents", [])
    except Exception:  # el bucket lo crea el harness la primera vez que genera un reporte
        objetos = []
    objetos.sort(key=lambda o: o["LastModified"], reverse=True)
    return pagina(request, "panel_reportes.html", usuario=u, objetos=objetos, seccion="reportes")


@router.get("/reportes/descargar")
def descargar_reporte(request: Request, clave: str):
    if not personal(request, solo_admin=True):
        return Response(status_code=403)
    try:
        obj = s3().get_object(Bucket=BUCKET_REPORTES, Key=clave)
    except Exception:
        return Response(status_code=404)
    tipo = mimetypes.guess_type(clave)[0] or "application/octet-stream"
    return StreamingResponse(obj["Body"].iter_chunks(), media_type=tipo,
                             headers={"Content-Disposition": f'attachment; filename="{clave.split("/")[-1]}"'})


# ------------------------------------------------------------- usuarios
def lista_usuarios():
    with bd() as con:
        return con.execute(
            """SELECT u.id, u.correo, u.rol, u.area,
                      (SELECT COUNT(*) FROM radicaciones r WHERE r.usuario_id = u.id) AS radicadas
               FROM usuarios u ORDER BY (u.rol = 'usuario'), u.correo"""
        ).fetchall()


@router.get("/usuarios")
def usuarios(request: Request):
    u = personal(request, solo_admin=True)
    if not u:
        return sin_permiso(request)
    return pagina(request, "panel_usuarios.html", usuario=u, usuarios=lista_usuarios(), seccion="usuarios")


@router.post("/usuarios")
def guardar_usuario(request: Request, correo: str = Form(""), rol: str = Form(""), area: str = Form("")):
    u = personal(request, solo_admin=True)
    if not u:
        return sin_permiso(request)
    correo = correo.strip().lower()
    error = None
    if not reglas.correo_permitido(correo):  # RN-01 tambien para el personal
        error = "El correo debe ser institucional."
    elif rol not in reglas.ROLES:
        error = "Rol no válido."
    elif rol == "funcionario" and area not in reglas.AREAS:
        error = "Un funcionario necesita un área."
    elif correo == u["correo"] and rol != "admin":
        error = "No puedes quitarte tu propio rol de administrador."
    if error:
        return pagina(request, "panel_usuarios.html", usuario=u, usuarios=lista_usuarios(),
                      seccion="usuarios", error=error)
    with bd() as con:
        con.execute(
            """INSERT INTO usuarios (correo, rol, area) VALUES (%s, %s, %s)
               ON CONFLICT (correo) DO UPDATE SET rol = EXCLUDED.rol, area = EXCLUDED.area""",
            (correo, rol, area if rol == "funcionario" else None),
        )
    return ir("/panel/usuarios")
