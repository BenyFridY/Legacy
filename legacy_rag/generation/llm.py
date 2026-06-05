"""Interface trocável do LLM (ADR-0003) — o "redator" da resposta.

Mesma estratégia do Encoder e do Reranker: o resto do sistema NÃO conhece o provedor
concreto, só o contrato `LLMClient.completar(prompt) -> texto`. Isso deixa o pipeline
testável com um LLM FALSO (determinístico, sem rede, sem chave) e permite trocar
claude_code / gemini_free / groq_free / ollama / anthropic mudando uma linha.

Por que a geração é a ÚLTIMA peça e a "menos crítica" da nota: a qualidade do sistema
mora no RETRIEVAL (achar o trecho certo) e na RECUSA. O LLM só REDIGE o que já foi
recuperado — por isso ele fica atrás de interface e a troca de provedor mexe <0,3% (ver
evidências). O que NÃO terceirizamos ao LLM: a citação (anexada estruturalmente) e a
decisão de recusar (gate de escopo + gate de evidência), justamente pra não depender do
"bom senso" do modelo.
"""
from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    """Contrato mínimo: dado um prompt, devolve o texto gerado."""

    def completar(self, prompt: str) -> str: ...
