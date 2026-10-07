"""Estensione del browser (M8): host Native Messaging, lettore per la chiusura e generatore dei pacchetti.

Disattivata per impostazione predefinita (impostazione «estensione_browser»: false): è un monitoraggio continuo e
richiede gli stessi presupposti del collector (accordo sindacale o autorizzazione INL, DPIA, informativa).

Decisione del 05/10/2026 (PoC chiuso): nessun permesso «tabs»; host_permissions = soli siti del CED; le pagine fuori
elenco risultano «url_non_visibile» e **non** producono «web_generico». L'assenza di una fascia web non è inattività
(l'aggregatore già non tratta le fonti mancanti come inattività). Vedi README.md e PRIVACY.md.
"""
NOME_HOST = "org.smartworking.istituzionale"
FASCIA_S = 900
GENERICO = "web_generico"  # ancora accettato dal lettore (storico / consuntivo); l'estensione non lo scrive più
