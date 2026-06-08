"""Testes da lógica PURA de calibração do gate (sem modelo): varredura de limiar + joelho."""

from legacy_rag.eval.calibracao_gate import Amostra, escolher_joelho, varrer_limiar


def test_conta_over_recusa_e_vazamento():
    # respondível com nota 0.40 e fora-da-base com 0.40; no limiar 0.50:
    #   respondível 0.40 < 0.50 -> RECUSADA (over-recusa=1); fora 0.40 < 0.50 -> não passou (vazamento=0)
    p = varrer_limiar([Amostra("r", 0.40, True), Amostra("f", 0.40, False)], [0.50])[0]
    assert p.over_recusa == 1 and p.vazamento == 0
    assert p.taxa_over_recusa == 1.0 and p.taxa_vazamento == 0.0 and p.custo == 1.0


def test_joelho_minimiza_custo_e_desempata_no_menor_limiar():
    amostras = [Amostra("r1", 0.70, True), Amostra("r2", 0.65, True),
                Amostra("f1", 0.20, False), Amostra("f2", 0.25, False)]
    pontos = varrer_limiar(amostras, [0.10, 0.30, 0.50, 0.90])
    # 0.30 e 0.50 zeram o custo (separam perfeitamente); o joelho desempata no MENOR limiar (0.30).
    j = escolher_joelho(pontos)
    assert j.limiar == 0.30 and j.custo == 0.0


def test_limiar_alto_demais_vira_tudo_recusa():
    amostras = [Amostra("r1", 0.70, True), Amostra("f1", 0.20, False)]
    p = varrer_limiar(amostras, [0.90])[0]
    assert p.over_recusa == 1 and p.vazamento == 0          # respondível recusada; nada vaza
