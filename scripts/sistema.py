"""Enciende o apaga todo el sistema PQRS con un solo comando (Windows).

Uso, desde la carpeta del proyecto:
    python scripts/sistema.py encender
    python scripts/sistema.py apagar
    python scripts/sistema.py apagar --simular      # muestra qué haría, sin hacer nada

encender: Docker Desktop -> servicios -> enlace en GitHub Pages -> calienta el modelo -> abre la app.
apagar:   detiene los servicios -> cierra Docker Desktop de forma segura -> cierra pgAdmin, el .env
          abierto en el Bloc de notas y la ventana de VS Code del proyecto.

Las ventanas se cierran "con amabilidad" (como al presionar la X): si hay algo sin guardar, el
programa pregunta antes de cerrarse. Nada se cierra a la fuerza y no se borran datos.
El navegador no se cierra, para no perder tus otras pestañas: cierra a mano las del sistema.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
COMPOSE = ["docker", "compose", "-f", "docker-compose.yml", "-f", "docker-compose.web.yml"]
REPO_PAGES = "https://github.com/andres82828828/harness-pqrs.uniminuto.git"
SIMULAR = False


def paso(texto):
    print(f"\n== {texto}", flush=True)


def correr(cmd, comprobar=True, silencioso=False):
    """Ejecuta un comando en la carpeta del proyecto (o solo lo muestra en modo simulación)."""
    print("   $ " + " ".join(cmd), flush=True)
    if SIMULAR:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    r = subprocess.run(cmd, cwd=RAIZ, text=True, capture_output=silencioso)
    if comprobar and r.returncode != 0:
        sys.exit(f"   El comando falló (código {r.returncode}). Revisa el mensaje de arriba.")
    return r


def powershell(script):
    """Ejecuta una instrucción corta de PowerShell y devuelve lo que imprime."""
    if SIMULAR:
        return ""
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], text=True, capture_output=True)
    return r.stdout.strip()


def docker_listo():
    r = subprocess.run(["docker", "desktop", "status", "--format", "json"], text=True, capture_output=True)
    try:
        return json.loads(r.stdout).get("Status") == "running"
    except (json.JSONDecodeError, AttributeError):
        return "running" in r.stdout.lower()


# ------------------------------------------------------------------ encender
def encender(calentar=True):
    paso("1/5  Encender Docker Desktop")
    if SIMULAR:
        correr(["docker", "desktop", "start"])
    elif docker_listo():
        print("   Docker ya estaba encendido.")
    else:
        correr(["docker", "desktop", "start"], comprobar=False)
        print("   Esperando a que Docker esté listo", end="", flush=True)
        for _ in range(60):  # hasta 5 minutos
            if docker_listo():
                print(" listo.")
                break
            print(".", end="", flush=True)
            time.sleep(5)
        else:
            sys.exit("\n   Docker no arrancó. Si aparece 'An unexpected error occurred ... rename ... .sock',"
                     "\n   sigue los pasos de docs/comandos_powershell.md (sección 'Si Docker no arranca').")

    paso("2/5  Levantar los servicios")
    correr(COMPOSE + ["up", "-d"])
    correr(COMPOSE + ["ps", "--format", "table {{.Name}}\t{{.Status}}"])

    paso("3/5  Actualizar la página fija de GitHub Pages con el enlace del túnel")
    r = correr([sys.executable, "scripts/publicar_enlace.py", "--repo", REPO_PAGES], comprobar=False)
    if r.returncode != 0:
        print("   No se pudo publicar (¿sin internet?). La app funciona igual en http://localhost:8000")

    paso("4/5  Calentar el modelo de IA (la primera respuesta tarda 1 a 2 minutos)")
    if calentar:
        correr(["docker", "exec", "pqrs-ollama", "ollama", "run", "llama3.2:3b", "Responde solo: listo"],
               comprobar=False)
    else:
        print("   Omitido (--sin-calentar).")

    paso("5/5  Abrir la app")
    print("   http://localhost:8000  (y el buzón de prueba en http://localhost:8025)")
    if not SIMULAR:
        webbrowser.open("http://localhost:8000")
    print("\nSistema encendido.")


# -------------------------------------------------------------------- apagar
def cerrar_ventanas(nombre, proceso, filtro_titulo=None):
    """Pide a las ventanas que se cierren, como al presionar la X (no fuerza nada)."""
    filtro = f" | Where-Object {{ $_.MainWindowTitle -like '*{filtro_titulo}*' }}" if filtro_titulo else ""
    script = (f"$v = Get-Process -Name '{proceso}' -ErrorAction SilentlyContinue | "
              f"Where-Object {{ $_.MainWindowHandle -ne 0 }}{filtro}; "
              f"$n = @($v).Count; foreach ($p in $v) {{ [void]$p.CloseMainWindow() }}; $n")
    print(f"   {nombre}: ", end="")
    if SIMULAR:
        print(f"cerraría las ventanas de '{proceso}'" + (f" con '{filtro_titulo}' en el título" if filtro_titulo else ""))
        return
    n = powershell(script) or "0"
    print("no estaba abierto." if n == "0" else f"se pidió cerrar {n} ventana(s). Si pregunta por guardar, decide tú.")


def apagar():
    paso("1/3  Detener los servicios (no borra datos)")
    correr(COMPOSE + ["stop"], comprobar=False)

    paso("2/3  Cerrar Docker Desktop de forma segura")
    correr(["docker", "desktop", "stop"], comprobar=False)

    paso("3/3  Cerrar programas abiertos del proyecto")
    cerrar_ventanas("pgAdmin", "pgAdmin4")
    cerrar_ventanas("Bloc de notas con el .env", "notepad", ".env")
    cerrar_ventanas("VS Code (ventana del proyecto)", "Code", "pqrs-inteligente")
    print("   Navegador: no se cierra para no perder tus otras pestañas; cierra a mano las de"
          "\n   localhost:8000, localhost:8025 y localhost:9001.")
    print("\nSistema apagado. Tus datos siguen guardados.")


def main():
    global SIMULAR
    ap = argparse.ArgumentParser(description="Enciende o apaga el sistema PQRS.")
    ap.add_argument("accion", choices=["encender", "apagar"])
    ap.add_argument("--simular", action="store_true", help="mostrar los pasos sin ejecutarlos")
    ap.add_argument("--sin-calentar", action="store_true", help="no calentar el modelo al encender")
    args = ap.parse_args()
    SIMULAR = args.simular
    if SIMULAR:
        print("(modo simulación: no se ejecuta nada)")
    if args.accion == "encender":
        encender(calentar=not args.sin_calentar)
    else:
        apagar()


if __name__ == "__main__":
    main()
