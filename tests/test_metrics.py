"""Testes das métricas do eval (funções puras, casos conhecidos)."""

from legacy_rag.eval.metrics import (
    hit_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    mrr,
    score_refusals,
)


def test_hit_at_k():
    retrieved = ["a", "b", "c", "d"]
    assert hit_at_k(retrieved, {"c"}, k=3) is True
    assert hit_at_k(retrieved, {"c"}, k=2) is False
    assert hit_at_k(retrieved, {"z"}, k=4) is False


def test_precision_at_k():
    retrieved = ["a", "b", "c", "d"]
    gold = {"a", "c"}
    assert precision_at_k(retrieved, gold, k=4) == 0.5  # 2 de 4
    assert precision_at_k(retrieved, gold, k=1) == 1.0  # 'a' é relevante
    assert precision_at_k(retrieved, gold, k=0) == 0.0


def test_recall_at_k():
    retrieved = ["a", "b", "c", "d"]
    gold = {"a", "c", "z"}  # 'z' nunca recuperado
    assert recall_at_k(retrieved, gold, k=4) == 2 / 3
    assert recall_at_k(retrieved, gold, k=1) == 1 / 3
    assert recall_at_k(retrieved, set(), k=4) == 0.0


def test_reciprocal_rank():
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == 0.5      # 2ª posição
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0      # 1ª posição
    assert reciprocal_rank(["a", "b", "c"], {"z"}) == 0.0      # ausente


def test_mrr():
    retrieved_lists = [["a", "b"], ["x", "y", "z"]]
    gold_lists = [{"b"}, {"x"}]                                # rr = 0.5 e 1.0
    assert mrr(retrieved_lists, gold_lists) == 0.75
    assert mrr([], []) == 0.0


def test_score_refusals():
    pairs = [
        ("refuse", "refuse"),   # ✓ recusa correta
        ("refuse", "answer"),   # ✗ alucinou
        ("answer", "answer"),   # ✓ respondeu
        ("answer", "answer"),   # ✓ respondeu
        ("answer", "refuse"),   # ✗ recusou demais
    ]
    c = score_refusals(pairs)
    assert c.correct_refusals == 1
    assert c.false_answers == 1
    assert c.correct_answers == 2
    assert c.false_refusals == 1
    assert c.correct_refusal_rate == 0.5          # 1 de 2 não-respondíveis
    assert c.over_refusal_rate == 1 / 3           # 1 de 3 respondíveis recusado


def test_refusal_rates_none_when_empty():
    only_answerable = score_refusals([("answer", "answer")])
    assert only_answerable.correct_refusal_rate is None   # não há não-respondíveis
    only_refusals = score_refusals([("refuse", "refuse")])
    assert only_refusals.over_refusal_rate is None        # não há respondíveis
