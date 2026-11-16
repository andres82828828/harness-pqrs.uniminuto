"""
Harness: lee las PQRS del data lake, extrae el texto de cada una
(texto directo, transcripcion de audio u OCR de foto), las clasifica
y guarda el resultado en PostgreSQL.

Los archivos originales del data lake NUNCA se modifican (solo se leen).

Uso (dentro de Docker):
    docker compose run --rm harness                  # procesa todo lo pendiente
    docker compose run --rm harness python main.py --limite 3   # prueba rapida
"""
import argparse
import io
import json
import os
import tempfile
import time
from collections import Counter

import boto3
import psycopg2
import pytesseract
from botocore.config import Config
from PIL import Image

from clasificador import clasificar

BUCKET_RAW = "pqrs-raw"
PREFIJOS = {"textos/": "texto", "audios/": "audio", "fotos/": "foto"}
PREFIJO_PAQUETES = "radicaciones/"  # PQRS de la web: texto, audio y/o foto juntos
MANIFIESTO = "manifiesto.json"

_whisper = None


# ------------------------------------------------------------- conexiones
def conectar_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("MINIO_ROOT_USER", "admin"),
        aws_secret_access_key=os.getenv("MINIO_ROOT_PASSWORD", ""),
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def conectar_db(intentos=20):
    for i in range(intentos):
        try:
            return psycopg2.connect(
                host=os.getenv("POSTGRES_HOST", "localhost"),
                dbname=os.getenv("POSTGRES_DB", "pqrs"),
                user=os.getenv("POSTGRES_USER", "pqrs"),
                password=os.getenv("POSTGRES_PASSWORD", ""),
            )
        except psycopg2.OperationalError:
            print(f"Esperando a PostgreSQL ({i + 1}/{intentos}) ...")
            time.sleep(3)
    raise SystemExit("No se pudo conectar a PostgreSQL. Revisa 'docker compose ps' y el .env")


def preparar_esquema(conn):
    """Pone al dia una base creada con una version anterior del esquema."""
    with conn.cursor() as cur:
        cur.execute("ALTER TABLE pqrs_casos ADD COLUMN IF NOT EXISTS fecha_recepcion DATE")
        # PQRS de varias partes (texto + audio + foto) usan el canal 'mixto'
        cur.execute("ALTER TABLE pqrs_casos DROP CONSTRAINT IF EXISTS pqrs_casos_canal_check")
        cur.execute("""ALTER TABLE pqrs_casos ADD CONSTRAINT pqrs_casos_canal_check
                       CHECK (canal IN ('texto', 'audio', 'foto', 'mixto'))""")
        cur.execute("ALTER TABLE pqrs_casos ADD COLUMN IF NOT EXISTS segundos_clasificacion REAL")
        cur.execute("""CREATE TABLE IF NOT EXISTS pqrs_partes (
                           id              SERIAL PRIMARY KEY,
                           archivo_origen  TEXT NOT NULL REFERENCES pqrs_casos (archivo_origen) ON DELETE CASCADE,
                           tipo            TEXT NOT NULL CHECK (tipo IN ('texto', 'audio', 'foto')),
                           archivo         TEXT NOT NULL,
                           texto_extraido  TEXT,
                           segundos        REAL,
                           error           TEXT
                       )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_partes_caso ON pqrs_partes (archivo_origen)")
    conn.commit()


# ------------------------------------------------------ extraccion de texto
def leer_texto(datos):
    return datos.decode("utf-8", errors="replace")


def transcribir_audio(datos):
    global _whisper
    from faster_whisper import WhisperModel

    if _whisper is None:
        modelo = os.getenv("WHISPER_MODEL", "small")
        print(f"  Cargando modelo Whisper '{modelo}' (la primera vez descarga el modelo) ...")
        _whisper = WhisperModel(modelo, device="cpu", compute_type="int8")
    if datos is None:
        return ""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(datos)
        ruta = f.name
    try:
        segmentos, _ = _whisper.transcribe(ruta, language="es")
        return " ".join(s.text.strip() for s in segmentos)
    finally:
        os.remove(ruta)


def leer_foto(datos):
    imagen = Image.open(io.BytesIO(datos))
    return pytesseract.image_to_string(imagen, lang="spa").strip()


EXTRACTORES = {"texto": leer_texto, "audio": transcribir_audio, "foto": leer_foto}


# ------------------------------------------------------------------ main
def listar_objetos(s3):
    for prefijo, canal in PREFIJOS.items():
        paginas = s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET_RAW, Prefix=prefijo)
        for pagina in paginas:
            for obj in pagina.get("Contents", []):
                if not obj["Key"].endswith("/"):
                    yield obj["Key"], canal
    # Paquetes: una carpeta por radicacion con varias partes. Solo cuentan cuando ya
    # existe el manifiesto, que la web escribe de ultimo (paquete completo).
    paginas = s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET_RAW, Prefix=PREFIJO_PAQUETES)
    for pagina in paginas:
        for obj in pagina.get("Contents", []):
            if obj["Key"].endswith("/" + MANIFIESTO):
                yield obj["Key"], "paquete"


# ---------------------------------------------------------------- paquetes
ORDEN_PARTES = ["texto", "audio", "foto"]  # primero lo que escribio la persona
ETIQUETA_PARTE = {"texto": "Texto escrito", "audio": "Transcripción del audio", "foto": "Texto de la foto"}


def procesar_paquete(s3, clave_manifiesto):
    """Extrae el texto de cada parte, lo une con etiquetas y clasifica una sola vez.

    Devuelve (fila_caso, partes). Si una parte falla se anota y se sigue con las demas;
    si ninguna deja texto, el caso queda sin clasificar (revision manual en la web).
    """
    manifiesto = json.loads(s3.get_object(Bucket=BUCKET_RAW, Key=clave_manifiesto)["Body"].read())
    carpeta = clave_manifiesto.rsplit("/", 1)[0]
    declaradas = sorted(manifiesto.get("partes", []), key=lambda p: ORDEN_PARTES.index(p["tipo"]))

    partes = []
    for parte in declaradas:
        clave = f"{carpeta}/{parte['archivo']}"
        inicio = time.perf_counter()
        try:
            datos = s3.get_object(Bucket=BUCKET_RAW, Key=clave)["Body"].read()
            texto = EXTRACTORES[parte["tipo"]](datos).strip()
            error = None if texto else "no se pudo extraer texto"
        except Exception as e:
            texto, error = "", str(e)[:300]
        segundos = round(time.perf_counter() - inicio, 2)
        partes.append({"tipo": parte["tipo"], "archivo": f"{BUCKET_RAW}/{clave}", "texto": texto,
                       "segundos": segundos, "error": error})
        estado = f"ERROR: {error}" if error else f"{len(texto)} caracteres"
        print(f"    {parte['tipo']:<6} {segundos:>6.1f} s  {estado}", flush=True)

    utiles = [p for p in partes if p["texto"]]
    if len(utiles) == 1:
        texto_total = utiles[0]["texto"]  # una sola parte: el mismo texto que se evaluo
    else:
        texto_total = "\n\n".join(f"[{ETIQUETA_PARTE[p['tipo']]}] {p['texto']}" for p in utiles)

    tipos = {p["tipo"] for p in partes}
    caso = {"canal": tipos.pop() if len(tipos) == 1 else "mixto", "texto": texto_total,
            "fecha": manifiesto.get("fecha"), "resultado": None, "segundos_clasificacion": None}
    if utiles:
        inicio = time.perf_counter()
        caso["resultado"] = clasificar(texto_total)
        caso["segundos_clasificacion"] = round(time.perf_counter() - inicio, 2)
    return caso, partes


def guardar_paquete(conn, clave_manifiesto, caso, partes):
    origen = f"{BUCKET_RAW}/{clave_manifiesto}"
    r = caso["resultado"] or {}
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO pqrs_casos
               (archivo_origen, canal, texto_extraido, tipo, tema, urgencia, area_destino,
                clasificador, fecha_recepcion, segundos_clasificacion)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (archivo_origen) DO NOTHING""",
            (origen, caso["canal"], caso["texto"] or None, r.get("tipo"), r.get("tema"), r.get("urgencia"),
             r.get("area"), r.get("clasificador", "sin texto"), caso["fecha"], caso["segundos_clasificacion"]),
        )
        if cur.rowcount:
            for p in partes:
                cur.execute(
                    """INSERT INTO pqrs_partes (archivo_origen, tipo, archivo, texto_extraido, segundos, error)
                       VALUES (%s,%s,%s,%s,%s,%s)""",
                    (origen, p["tipo"], p["archivo"], p["texto"] or None, p["segundos"], p["error"]),
                )
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=0, help="procesar solo N archivos (prueba)")
    ap.add_argument("--ciclo", type=float, default=0,
                    help="modo worker: revisar el data lake cada N segundos y no terminar")
    args = ap.parse_args()

    s3 = conectar_s3()
    conn = conectar_db()
    preparar_esquema(conn)

    if not args.ciclo:
        procesar(s3, conn, args.limite)
        conn.close()
        return

    # Modo worker: la web radica y este ciclo clasifica cada PQRS nueva sin intervencion.
    print(f"Worker activo: revisando el data lake cada {args.ciclo:g} s", flush=True)
    if os.getenv("PRECARGAR_WHISPER") == "1":
        transcribir_audio(None)  # solo carga el modelo
    while True:
        try:
            procesar(s3, conn, args.limite, silencioso=True)
        except Exception as e:  # p. ej. la base se reinicio: reconectar y seguir
            print(f"ERROR en el ciclo: {e}", flush=True)
            try:
                conn.close()
            except Exception:
                pass
            conn = conectar_db()
        time.sleep(args.ciclo)


def procesar(s3, conn, limite=0, silencioso=False):
    with conn.cursor() as cur:
        cur.execute("SELECT archivo_origen FROM pqrs_casos")
        ya_procesados = {fila[0] for fila in cur.fetchall()}
    conn.commit()

    pendientes = [(k, c) for k, c in listar_objetos(s3) if f"{BUCKET_RAW}/{k}" not in ya_procesados]
    if limite:
        pendientes = pendientes[:limite]
    if silencioso and not pendientes:
        return
    print(f"Archivos pendientes: {len(pendientes)} (ya procesados: {len(ya_procesados)})", flush=True)

    nuevos, errores = Counter(), 0
    for n, (clave, canal) in enumerate(pendientes, start=1):
        print(f"[{n}/{len(pendientes)}] {clave}")
        if canal == "paquete":
            try:
                caso, partes = procesar_paquete(s3, clave)
                guardar_paquete(conn, clave, caso, partes)
                nuevos[caso["canal"]] += 1
                r = caso["resultado"]
                if r:
                    print(f"    -> {caso['canal']}: {r['tipo']} / {r['tema']} / urgencia {r['urgencia']}"
                          f" / {r['area']}  (clasificó en {caso['segundos_clasificacion']} s)", flush=True)
                    if r.get("nota"):
                        print(f"       ({r['nota']})")
                else:
                    print("    -> ninguna parte dejó texto: queda para revisión manual", flush=True)
            except Exception as e:
                conn.rollback()
                errores += 1
                print(f"    ERROR: {e}", flush=True)
            continue
        try:
            objeto = s3.get_object(Bucket=BUCKET_RAW, Key=clave)
            datos = objeto["Body"].read()
            fecha = objeto.get("Metadata", {}).get("fecha")

            texto = EXTRACTORES[canal](datos)
            if not texto.strip():
                raise ValueError("no se pudo extraer texto del archivo")
            resultado = clasificar(texto)

            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO pqrs_casos
                       (archivo_origen, canal, texto_extraido, tipo, tema, urgencia,
                        area_destino, clasificador, fecha_recepcion)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (archivo_origen) DO NOTHING""",
                    (f"{BUCKET_RAW}/{clave}", canal, texto, resultado["tipo"], resultado["tema"],
                     resultado["urgencia"], resultado["area"], resultado["clasificador"], fecha),
                )
            conn.commit()
            nuevos[canal] += 1
            print(f"    -> {resultado['tipo']} / {resultado['tema']} / urgencia {resultado['urgencia']}"
                  f" / {resultado['area']}")
            if resultado.get("nota"):
                print(f"       ({resultado['nota']})")
        except Exception as e:  # un archivo con error no detiene al resto
            conn.rollback()
            errores += 1
            print(f"    ERROR: {e}")

    print(f"\nListo. Procesados: {sum(nuevos.values())} {dict(nuevos)} | Errores: {errores}", flush=True)


if __name__ == "__main__":
    main()
