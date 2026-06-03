"""Grafo delle dipendenze del codice (NetworkX) + GraphRAG.

Costruisce un DiGraph dai chunk JSONL (metadati calls/imports/bases),
lo persiste su disco e lo rende interrogabile (impatto, dipendenze,
nodi critici) ed espandibile nel retriever.
"""
