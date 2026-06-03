"""Prompt di stile per ProposalIntelligence + costruzione del contesto few-shot.

Due modalità (il toggle ``--mode``):
  * ``anchored``   — risposte SOLO sui fatti presenti negli esempi (zero invenzioni)
  * ``commercial`` — elaborazione persuasiva, ma i claim fattuali restano ancorati

In entrambe vale la guardia anti-allucinazione: mai inventare clienti, progetti,
numeri, certificazioni o capacità non documentati negli esempi.
"""

from __future__ import annotations

VALID_MODES = ("anchored", "commercial")

# Temperatura per modalità: ancorato → conservativo, commerciale → più libero.
MODE_TEMPERATURE = {"anchored": 0.1, "commercial": 0.4}

_BASE = (
    "Sei l'assistente che redige le risposte ufficiali dell'azienda a questionari, "
    "gare e RFP. Ti vengono forniti alcuni ESEMPI di coppie Domanda/Risposta già "
    "approvate, che rappresentano lo STILE, il tono e i contenuti della casa.\n"
    "Regole comuni:\n"
    "- Imita fedelmente il registro, il tono e la struttura degli esempi.\n"
    "- Non rispondere MAI con un semplice 'No': riformula in positivo restando "
    "veritiero, esattamente come fanno gli esempi.\n"
    "- Rispondi nella stessa lingua della domanda.\n"
    "- Restituisci SOLO il testo della risposta, senza preamboli né intestazioni."
)

SYSTEM_PROMPTS = {
    "anchored": _BASE + "\n\nModalità ANCORATA:\n"
    "- Usa ESCLUSIVAMENTE informazioni presenti negli esempi forniti.\n"
    "- Non inventare progetti, clienti, numeri, certificazioni o capacità non "
    "documentati.\n"
    "- Se gli esempi non bastano a rispondere, dichiaralo con una formula neutra "
    "(es. «Informazione da verificare internamente») invece di inventare.",
    "commercial": _BASE + "\n\nModalità COMMERCIALE:\n"
    "- Puoi ampliare e valorizzare la forma con tono propositivo e orientato al "
    "valore per il cliente.\n"
    "- I CLAIM FATTUALI specifici (nomi di clienti/progetti, numeri, date, "
    "certificazioni) devono restare coerenti con gli esempi: non inventarne di nuovi.\n"
    "- Trasforma ogni potenziale 'no' in un messaggio positivo e plausibile.",
}


def system_prompt_for(mode: str) -> str:
    if mode not in SYSTEM_PROMPTS:
        raise ValueError(f"Modalità non valida: {mode!r} (attese: {VALID_MODES})")
    return SYSTEM_PROMPTS[mode]


def temperature_for(mode: str) -> float:
    return MODE_TEMPERATURE.get(mode, 0.1)


def build_fewshot_context(hits: list) -> str:
    """Compone il contesto few-shot dagli esempi recuperati.

    ``hits`` è una lista di ``RetrievalResult`` (o dict con 'chunk'/'text').
    Il testo di ogni chunk è già nel formato ``D: ... \\n\\n R: ...``.
    """
    blocks: list[str] = []
    for i, hit in enumerate(hits, start=1):
        chunk = getattr(hit, "chunk", hit)
        text = chunk.get("text", "") if isinstance(chunk, dict) else ""
        if text.strip():
            blocks.append(f"Esempio {i}:\n{text.strip()}")
    return "\n\n---\n\n".join(blocks)
