"""Gate de evidência (Estágio 2 da recusa) — "eu achei trecho bom o suficiente?".

Lembrete dos DOIS estágios de recusa:
  Estágio 1 (escopo)    -> roteador determinístico (R1/R2/R3), decide ANTES de buscar.
  Estágio 2 (evidência) -> ESTE: depois de buscar+reranquear, se o melhor trecho não passa
                           de um limiar de relevância, recusa em vez de redigir no escuro.

Por que isso importa: o roteador deixa passar perguntas "plausíveis" que a base simplesmente
não cobre (ex.: ROE do BB, métrica não-ingerida). Sem este gate, o sistema acharia o trecho
"menos ruim" e o LLM redigiria uma resposta com cara de confiante — alucinação. O gate corta
isso na raiz: pouca evidência -> "não disponível na base".

HONESTIDADE (crítico de arquitetura): o limiar é um PONTO DE PARTIDA, não um número sagrado.
Sem dados rotulados, calibrar de verdade exige um mini-gold (varrer o limiar e achar o "joelho"
entre over-recusa e alucinação) — ver ADR-0005. Por isso o limiar é um parâmetro explícito.
"""
from __future__ import annotations

from dataclasses import dataclass

from legacy_rag.config import LIMIAR_EVIDENCIA_PADRAO
from legacy_rag.retrieval.vetorial import Resultado


@dataclass
class DecisaoEvidencia:
    responder: bool
    melhor_nota: float
    motivo: str | None = None   # preenchido quando responder == False


def gate_evidencia(resultados: list[Resultado],
                   limiar: float = LIMIAR_EVIDENCIA_PADRAO) -> DecisaoEvidencia:
    """Decide se há evidência suficiente para responder, a partir da MELHOR nota do reranker."""
    if not resultados:
        return DecisaoEvidencia(False, 0.0, "Nenhum trecho recuperado para a pergunta.")
    melhor = max(r.score for r in resultados)
    if melhor < limiar:
        # A recusa ENSINA a reformular (bateria simples: "inadimplência do Itaú" ficou a 0,02 do
        # limiar; "PDD do Itaú" falha porque o release do Itaú chama de "custo do crédito" — o
        # retrieval acha o termo que está ESCRITO no documento, não o sinônimo da cabeça do usuário).
        return DecisaoEvidencia(
            False, melhor,
            f"Evidência fraca: melhor nota {melhor:.2f} < limiar {limiar:.2f} -> recusar. "
            "Dica: nomeie o trimestre (ex.: 4T25) e use o termo do documento — ex.: 'custo do "
            "crédito' (Itaú) em vez de 'PDD'; 'inadimplência acima de 90 dias'.")
    return DecisaoEvidencia(True, melhor, None)
