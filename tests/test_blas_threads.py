"""OpenBLAS auf einen Thread, bevor numpy geladen wird (jampilot/__init__.py).

Auf dem Proberaum-PC drehten sonst zwoelf BLAS-Threads mit je 57 % CPU im
Leerlauf - und der Hop wurde damit langsamer, nicht schneller.
"""

import os
import subprocess
import sys


def _in_frischem_prozess(env_extra: dict) -> str:
    env = {k: v for k, v in os.environ.items() if k != "OPENBLAS_NUM_THREADS"}
    env.update(env_extra)
    return subprocess.check_output(
        [sys.executable, "-c",
         "import jampilot, os; print(os.environ.get('OPENBLAS_NUM_THREADS'))"],
        env=env, text=True).strip()


def test_das_paket_setzt_einen_blas_thread():
    assert _in_frischem_prozess({}) == "1"


def test_eine_eigene_vorgabe_bleibt_bestehen():
    assert _in_frischem_prozess({"OPENBLAS_NUM_THREADS": "4"}) == "4"
