"""Rendiconto SW v4 — Collector Windows minimo (Milestone 3).

Processo della sessione utente (non un servizio), attivo solo tra «Avvia giornata» e «Pausa» / «Chiudi giornata».
Registra soltanto, nel formato raw.jsonl dell'aggregatore (M1):

- eventi di sessione (blocco/sblocco, connessione/disconnessione, accesso/uscita) dalle notifiche WTS, sospensione e
  ripresa dalle notifiche di alimentazione, cambi dell'ora di sistema;
- per ogni fascia di 15 minuti, se c'è stato input sulla postazione (GetLastInputInfo: solo «sì/no», mai tasti,
  coordinate o contenuti);
- il nome dell'eseguibile in primo piano quando c'è input (mai titoli di finestra, nomi di file o percorsi);
- il numero di operazioni SMB per fascia sulle sole unità di rete della sessione dell'utente (collector/smb.py),
  «dato non disponibile» se il PC ha più sessioni utente;

Nessuna lettura della posta (bonifica B2: Outlook è solo la categoria «Posta elettronica» dell'eseguibile in primo
piano). Nessuna cronologia del browser: i siti arriveranno solo dall'estensione (fonte «browser» = non_installato).
Nessun invio di dati: tutto resta in %LOCALAPPDATA%\\RendicontoSW.
"""
__version__ = "4.0.0a1"
