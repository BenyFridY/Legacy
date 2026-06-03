"""Métricas de avaliação de retrieval e recusa.

Funções puras, sem dependências externas — testáveis isoladamente e ANTES de
existir o sistema de retrieval ("comece pelo eval": medir antes de otimizar).

Convenções:
- `retrieved`: lista ORDENADA de ids de chunk/linha (rank 1 primeiro).
- `gold`: coleção de ids relevantes (a resposta-ouro de retrieval).
- Comportamento de recusa: "answer" (respondeu) ou "refuse" (recusou).
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence, Iterable


# --------------------------------------------------------------------------
# Métricas de retrieval (por pergunta)
# --------------------------------------------------------------------------

def hit_at_k(retrieved: Sequence[str], gold: Iterable[str], k: int) -> bool:
    """True se ao menos um id relevante aparece no top-k."""
    goldset = set(gold)
    return any(r in goldset for r in retrieved[:k])


def precision_at_k(retrieved: Sequence[str], gold: Iterable[str], k: int) -> float:
    """Fração do top-k que é relevante. Denominador = min(k, itens recuperados)."""
    if k <= 0:
        return 0.0
    topk = retrieved[:k]
    if not topk:
        return 0.0
    goldset = set(gold)
    return sum(1 for r in topk if r in goldset) / len(topk)


def recall_at_k(retrieved: Sequence[str], gold: Iterable[str], k: int) -> float:
    """Fração dos relevantes que aparece no top-k."""
    goldset = set(gold)
    if not goldset:
        return 0.0
    topk = set(retrieved[:k])
    return len(topk & goldset) / len(goldset)


def reciprocal_rank(retrieved: Sequence[str], gold: Iterable[str]) -> float:
    """1/posição do primeiro relevante; 0 se nenhum foi recuperado."""
    goldset = set(gold)
    for i, r in enumerate(retrieved, start=1):
        if r in goldset:
            return 1.0 / i
    return 0.0


def mrr(retrieved_lists: Sequence[Sequence[str]], gold_lists: Sequence[Iterable[str]]) -> float:
    """Mean Reciprocal Rank sobre um conjunto de perguntas."""
    if not retrieved_lists:
        return 0.0
    rrs = [reciprocal_rank(r, g) for r, g in zip(retrieved_lists, gold_lists)]
    return sum(rrs) / len(rrs)


# --------------------------------------------------------------------------
# Métricas de recusa (a regra inegociável: recusar quando não está na base)
# --------------------------------------------------------------------------

@dataclass
class RefusalCounts:
    """Matriz de confusão de recusa vs. resposta."""
    correct_refusals: int = 0   # esperado=refuse, previsto=refuse  (✓ recusou certo)
    false_answers: int = 0      # esperado=refuse, previsto=answer  (✗ alucinou)
    correct_answers: int = 0    # esperado=answer, previsto=answer  (✓ respondeu)
    false_refusals: int = 0     # esperado=answer, previsto=refuse  (✗ recusou demais)

    @property
    def correct_refusal_rate(self) -> float | None:
        """Dos que DEVIAM ser recusados, quantos foram. None se não há não-respondíveis."""
        denom = self.correct_refusals + self.false_answers
        return self.correct_refusals / denom if denom else None

    @property
    def over_refusal_rate(self) -> float | None:
        """Dos que eram respondíveis, quantos foram recusados por engano. None se não há respondíveis."""
        denom = self.correct_answers + self.false_refusals
        return self.false_refusals / denom if denom else None


def score_refusals(pairs: Iterable[tuple[str, str]]) -> RefusalCounts:
    """`pairs`: iterável de (expected_behavior, predicted_behavior) ∈ {'answer','refuse'}."""
    c = RefusalCounts()
    for expected, predicted in pairs:
        if expected == "refuse" and predicted == "refuse":
            c.correct_refusals += 1
        elif expected == "refuse" and predicted == "answer":
            c.false_answers += 1
        elif expected == "answer" and predicted == "answer":
            c.correct_answers += 1
        elif expected == "answer" and predicted == "refuse":
            c.false_refusals += 1
        else:
            raise ValueError(f"comportamento inválido: {(expected, predicted)!r}")
    return c
