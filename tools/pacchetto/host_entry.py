"""Punto d'ingresso dell'host Native Messaging dell'estensione (RendicontoSW-host.exe, da firmare come l'app)."""
import sys

from estensione.host import main

if __name__ == "__main__":
    sys.exit(main())
