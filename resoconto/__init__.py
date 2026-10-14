"""Resoconto PDF (M7): impaginazione del JSON giornaliero sigillato secondo l'impaginazione approvata e verifica
del PDF (sigilli del JSON allegato + confronto del testo con una nuova impaginazione)."""
VERSIONE_APP = "5.0.0"   # Snapshot tecnico autorizzato; renderer precedenti in resoconto/storico
# Versione del programma (Setup, Informazioni). Distinta da VERSIONE_APP, che va nei metadati del PDF e decide il
# confronto grafico del Verificatore: la 5.0.1 non cambia l'impaginatore, quindi i PDF 5.0.0 restano VALIDO.
VERSIONE_PROGRAMMA = "5.0.1"
