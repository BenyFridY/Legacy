"""Testes do eval runner (recusa-por-escopo, Estágio 1) — sem rede, sem modelo.

Usa as perguntas REAIS do eval/questions.yaml (não um fixture), porque o objetivo é
justamente medir o sistema contra o gabarito de verdade.
"""

from legacy_rag.eval.runner import (
    CAMINHO_ESTENDIDO,
    avaliar_recusa_por_escopo,
    carregar_perguntas,
    formatar_relatorio,
    prever_comportamento,
)


def test_carrega_as_12_perguntas():
    perguntas = carregar_perguntas()
    assert len(perguntas) == 12
    assert all({"id", "question", "expected_behavior"} <= set(q) for q in perguntas)


def test_matriz_de_recusa_perfeita_no_conjunto():
    """O roteador acerta o comportamento (answer/refuse) das 12: 9 answer + 3 refuse."""
    r = avaliar_recusa_por_escopo(carregar_perguntas())
    c = r.contagem
    assert c.correct_refusals == 3      # os 3 non_answerable
    assert c.false_answers == 0         # nenhuma alucinação
    assert c.correct_answers == 9       # os 9 respondíveis (8 + a nova B2 de tom)
    assert c.false_refusals == 0        # nenhuma over-recusa
    assert c.correct_refusal_rate == 1.0
    assert c.over_refusal_rate == 0.0
    assert r.acertos == 12 and r.total == 12


def test_nenhuma_over_recusa_no_distrator_nubank_cartao():
    """A armadilha anti-over-recusa (Nubank+cartão+IF.data) deve ser RESPONDIDA, não recusada."""
    previsto, rota = prever_comportamento(
        "Qual o market share do Nubank em cartão de crédito, segundo o IF.data?")
    assert previsto == "answer" and not rota.deve_recusar


def test_relatorio_tem_as_secoes_chave():
    r = avaliar_recusa_por_escopo(carregar_perguntas())
    texto = formatar_relatorio(r)
    assert "Matriz de confusao de recusa" in texto
    assert "Taxa de recusa correta" in texto
    assert "n=12" in texto                 # honestidade estatística explícita (dinâmico = nº real)


def test_bateria_estendida_36_de_36():
    """A bateria estendida (fraseios pós-congelamento das regras) acerta comportamento E rota.
    36 = 3x o harness oficial: sinônimos de ranking, janelas, tickers, sub-produtos, cross-base."""
    perguntas = carregar_perguntas(CAMINHO_ESTENDIDO)
    assert len(perguntas) == 36
    r = avaliar_recusa_por_escopo(perguntas)
    assert r.acertos == 36 and r.total == 36                       # answer/refuse certo em todas
    assert all(l.rota_ok for l in r.linhas)                        # e a ROTA certa em todas
    assert r.contagem.false_answers == 0 and r.contagem.false_refusals == 0


def test_bateria_estendida_cobre_todas_as_rotas_e_recusas():
    """A bateria não é monocultura: exercita as 4 rotas + recusa, e as 5 famílias R1/R2/R3/R7/R8."""
    r = avaliar_recusa_por_escopo(carregar_perguntas(CAMINHO_ESTENDIDO))
    assert set(r.distribuicao_rotas) == {"computada", "comparativo", "doc_unico",
                                         "multi_fonte", "nao_respondivel"}
    motivos = {l.motivo[:2] for l in r.linhas if l.motivo}
    assert {"R1", "R2", "R3", "R7", "R8"} <= motivos
