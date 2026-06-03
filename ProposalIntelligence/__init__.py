"""ProposalIntelligence — auto-risposta a questionari / gare in stile aziendale.

Carica un corpus di coppie Domanda/Risposta già scritte nello stile della casa,
poi — dato un nuovo questionario con sole domande — genera le risposte imitando
quello stile, fondandole sugli esempi recuperati.

Pipeline (come gli altri moduli della suite):
    Q&A docs → qa_parser → chunk (1 coppia) → embed(domanda) → ChromaDB "proposal_intelligence"
    nuovo questionario → estrai domande → retrieve esempi simili → LLM (prompt di stile) → Markdown
"""

COLLECTION_NAME = "proposal_intelligence"

__all__ = ["COLLECTION_NAME"]
