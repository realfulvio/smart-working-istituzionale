"""Rendiconto SW v4 — Redattore AI (M5 AI-Light: Qwen3-1.7B; M6 AI-Standard: Qwen3-4B, stessi fatti e stesso controllo).

Dal JSON giornaliero rivisto estrae in modo deterministico un elenco numerato di fatti; un modello linguistico locale
(Qwen3-1.7B Q4_K_M su llama.cpp, CPU) li riformula in 3–6 frasi con i riferimenti ai fatti; un controllo automatico
rifiuta orari, numeri, termini e valutazioni non presenti nei fatti citati. Un secondo tentativo, poi testo standard
deterministico. Il modello si carica solo a «Genera resoconto» e viene scaricato subito dopo.
"""
__version__ = "4.0.0a5"
VERSIONE_REDATTORE = "m7-2"
