"""Identità upstream congelata per verificare i PDF storici neutri.

Un PDF /3 non firma l'identità dell'Ente: non usare la nuova configurazione dell’edizione
per rigenerare il documento precedente. Personalizzazioni storiche sconosciute
richiedono il loro impaginatore/configurazione d'archivio.
"""


def carica():
    return {"nome": "Ente", "sottotitolo": "", "assistenza": "", "logo": "",
            "colori": {"primario": "#1f4e79", "primario_scuro": "#173a5a", "scuro": "#12263a",
                       "tenue": "#e8eef4", "accento": "#9a6b00"}}
