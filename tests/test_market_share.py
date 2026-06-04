"""Testes da função de market share (pura, com dados conhecidos)."""

from legacy_rag.structured.market_share import market_share, ranking


def test_market_share_basico():
    saldos = {"A": 30.0, "B": 50.0, "C": 20.0}  # total = 100
    assert market_share(saldos, "B") == 0.5
    assert market_share(saldos, "A") == 0.3


def test_market_share_e_uma_razao_unidade_cancela():
    # multiplicar todos os saldos por 1000 (mudar de unidade) NÃO muda o share
    saldos = {"A": 30.0, "B": 50.0, "C": 20.0}
    saldos_mil = {k: v * 1000 for k, v in saldos.items()}
    assert market_share(saldos, "B") == market_share(saldos_mil, "B")


def test_market_share_ausente_ou_zero_recusa():
    assert market_share({"A": 10.0}, "X") is None          # banco ausente da base
    assert market_share({"A": 0.0, "B": 0.0}, "A") is None  # total zero


def test_ranking_ordena_por_saldo():
    saldos = {"A": 30.0, "B": 50.0, "C": 20.0}
    r = ranking(saldos, top=2)
    assert r[0][0] == "B" and abs(r[0][2] - 0.5) < 1e-9
    assert r[1][0] == "A"
    assert len(r) == 2
