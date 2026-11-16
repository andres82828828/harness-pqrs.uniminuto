"""Publica en GitHub Pages el enlace actual del tunel.

La pagina fija (acceso/index.html) vive en la rama gh-pages y redirige al enlace que dice
enlace.json. Como el enlace del tunel cambia cada vez que se reinicia, este script lo lee de la
web local y lo sube a gh-pages. Asi el profesor siempre usa la misma direccion:
    https://<usuario>.github.io/<repositorio>/

Uso (con el sistema levantado):
    python scripts/publicar_enlace.py
    python scripts/publicar_enlace.py --repo https://github.com/<usuario>/<repo>.git

Requisitos: git instalado y permiso de escritura en el repositorio. GitHub Pages debe estar
activado una vez en Settings -> Pages -> "Deploy from a branch" -> rama gh-pages, carpeta /.
"""
import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def enlace_actual(web, espera):
    """Pide el enlace a la web local; el tunel tarda unos segundos en tenerlo."""
    limite = time.time() + espera
    while True:
        try:
            with urllib.request.urlopen(f"{web}/api/enlace", timeout=5) as r:
                url = json.load(r).get("url")
            if url:
                return url
        except OSError:
            pass
        if time.time() > limite:
            sys.exit(f"No hay enlace publico en {web}/api/enlace. Revisa que la web y el tunel esten levantados.")
        time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="URL del repositorio (por defecto, el remoto origin de esta copia)")
    ap.add_argument("--rama", default="gh-pages")
    ap.add_argument("--web", default="http://localhost:8000")
    ap.add_argument("--espera", type=int, default=60, help="segundos maximos esperando el enlace")
    args = ap.parse_args()

    repo = args.repo or git("remote", "get-url", "origin", cwd=RAIZ).stdout.strip()
    url = enlace_actual(args.web, args.espera)
    print(f"Enlace del tunel: {url}")

    with tempfile.TemporaryDirectory() as tmp:
        destino = Path(tmp) / "pages"
        clon = git("clone", "--depth", "1", "--branch", args.rama, repo, str(destino), cwd=tmp, check=False)
        if clon.returncode != 0:  # la rama aun no existe: se crea vacia
            destino.mkdir()
            git("init", cwd=destino)
            git("checkout", "--orphan", args.rama, cwd=destino)
            git("remote", "add", "origin", repo, cwd=destino)

        previo = destino / "enlace.json"
        mismo_enlace = previo.exists() and json.loads(previo.read_text(encoding="utf-8")).get("url") == url
        def normal(ruta):  # git en Windows puede cambiar los finales de linea
            return ruta.read_bytes().replace(b"\r\n", b"\n")
        archivos = [f for f in (RAIZ / "acceso").iterdir() if f.is_file()]  # index.html, logo...
        mismos = all((destino / f.name).exists() and normal(destino / f.name) == normal(f) for f in archivos)
        if mismo_enlace and mismos:
            print("La pagina ya tenia este enlace; no hay nada que publicar.")
            return
        for f in archivos:
            shutil.copy(f, destino / f.name)
        (destino / ".nojekyll").write_text("")
        (destino / "enlace.json").write_text(json.dumps(
            {"url": url, "actualizado": datetime.now().strftime("%d/%m/%Y %H:%M")}, ensure_ascii=False), encoding="utf-8")

        git("add", "-A", cwd=destino)
        if not git("status", "--porcelain", cwd=destino).stdout.strip():
            print("La pagina ya tenia este enlace; no hay nada que publicar.")
            return
        git("commit", "-m", f"Actualiza el enlace de acceso: {url}", cwd=destino)
        empuje = git("push", "origin", f"HEAD:{args.rama}", cwd=destino, check=False)
        if empuje.returncode != 0:
            sys.exit("No se pudo subir a GitHub:\n" + empuje.stderr.strip()
                     + "\nRevisa que tu cuenta tenga permiso de escritura en el repositorio.")
    print(f"Publicado en la rama {args.rama}. En 1 o 2 minutos la pagina de GitHub Pages redirige al nuevo enlace.")


if __name__ == "__main__":
    main()
