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

import os
from typing import Protocol


class LLMClient(Protocol):
    """Contrato mínimo: dado um prompt, devolve o texto gerado."""

    def completar(self, prompt: str) -> str: ...


# Endpoint COMPATÍVEL com a API da OpenAI — por isso basta `requests`, sem SDK próprio.
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELO_PADRAO = "llama-3.3-70b-versatile"   # forte o suficiente: o LLM só REDIGE o recuperado


class GroqClient:
    """Redator de produção via Groq (free tier). Implementa o contrato LLMClient.

    temperature=0 -> saída determinística (reprodutibilidade do eval). A chave vem do ambiente
    (.env, gitignored); sem chave, falha com mensagem clara em vez de vazar erro de rede.
    """

    def __init__(self, modelo: str = GROQ_MODELO_PADRAO, api_key: str | None = None,
                 timeout: int = 60):
        self._modelo = modelo
        self._api_key = api_key or os.getenv("GROQ_API_KEY")
        self._timeout = timeout

    def completar(self, prompt: str) -> str:
        if not self._api_key:
            raise RuntimeError("GROQ_API_KEY ausente: cole a chave no .env (ver .env.example).")
        import requests  # import local: o módulo carrega sem rede p/ os testes

        resp = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={"model": self._modelo, "temperature": 0.0,
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def criar_llm(provider: str | None = None) -> LLMClient | None:
    """Fábrica do redator a partir de LLM_PROVIDER (.env). Devolve None se não há LLM externo.

    `groq_free` -> GroqClient. `claude_code`/ausente -> None (o pipeline cai no fallback
    determinístico, que mostra as evidências citadas lado a lado — sem inventar texto).
    """
    provider = (provider or os.getenv("LLM_PROVIDER") or "claude_code").strip()
    if provider == "groq_free":
        return GroqClient()
    return None
