"""Ráfaga de peticiones desde una sola máquina: ¿el servidor la frena?

Lanza N peticiones con C hilos a la vez contra una URL y resume los códigos
de respuesta (cuántos 200, 429, 503, errores…), los tiempos y el ritmo
conseguido. Sirve para comprobar si hay **limitación de peticiones** (la de
``app/anti_ddos.py`` en local, o la que ponga el hosting en producción).

    python tests/ddos/rafaga.py http://127.0.0.1:8765/api/salud -n 400 -c 20
    python tests/ddos/rafaga.py https://pps-appweb-26-27-sju7.onrender.com/api/salud -n 300 -c 20

Úsalo con cabeza contra producción: es tu propio servicio, pero son cientos
de peticiones en pocos segundos.
"""
from __future__ import annotations

import argparse
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def una_peticion(url: str, metodo: str, cuerpo: bytes | None) -> tuple[str, float]:
    inicio = time.perf_counter()
    req = urllib.request.Request(url, data=cuerpo, method=metodo,
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "ludoteca-rafaga"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
            codigo = str(r.status)
    except urllib.error.HTTPError as e:
        codigo = str(e.code)
    except Exception as e:  # noqa: BLE001 - se cuenta como error de red
        codigo = type(e).__name__
    return codigo, (time.perf_counter() - inicio) * 1000


def rafaga(url: str, n: int, concurrencia: int, metodo="GET", cuerpo=None) -> dict:
    inicio = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrencia) as hilos:
        resultados = list(hilos.map(lambda _: una_peticion(url, metodo, cuerpo), range(n)))
    duracion = time.perf_counter() - inicio
    tiempos = sorted(t for _, t in resultados)
    return {
        "codigos": Counter(c for c, _ in resultados),
        "duracion_s": duracion,
        "req_s": n / duracion,
        "mediana_ms": statistics.median(tiempos),
        "p95_ms": tiempos[int(len(tiempos) * 0.95) - 1],
        "max_ms": tiempos[-1],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("url")
    p.add_argument("-n", "--peticiones", type=int, default=300)
    p.add_argument("-c", "--concurrencia", type=int, default=20)
    p.add_argument("--post-json", default=None, help="cuerpo JSON para hacer POST")
    a = p.parse_args()
    cuerpo = a.post_json.encode() if a.post_json else None
    r = rafaga(a.url, a.peticiones, a.concurrencia, "POST" if cuerpo else "GET", cuerpo)
    print(f"{a.peticiones} peticiones, {a.concurrencia} a la vez -> {a.url}")
    print(f"  duración {r['duracion_s']:.1f} s · {r['req_s']:.1f} req/s · "
          f"mediana {r['mediana_ms']:.0f} ms · p95 {r['p95_ms']:.0f} ms · máx {r['max_ms']:.0f} ms")
    for codigo, veces in sorted(r["codigos"].items()):
        print(f"  {codigo}: {veces}")


if __name__ == "__main__":
    main()
