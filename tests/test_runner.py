"""Testes do eval runner (recusa-por-escopo, Estágio 1) — sem rede, sem modelo.

Usa as perguntas REAIS do eval/questions.yaml (não um fixture), porque o objetivo é
justamente medir o sistema contra o gabarito de verdade.
"""

from legacy_rag.eval.runner import (
    avaliar_recusa_por_escopo,
    carregar_perguntas,
    formatar_relatorio,
    prever_comportamento,
)


def test_carrega_as_11_perguntas():
    perguntas = carregar_perguntas()
    assert len(perguntas) == 11
    assert all({"id", "question", "expected_behavior"} <= set(q) for q in perguntas)


def test_matriz_de_recusa_perfeita_no_conjunto():
    """O roteador acerta o comportamento (answer/refuse) das 11: 8 answer + 3 refuse."""
    r = avaliar_recusa_por_escopo(carregar_perguntas())
    c = r.contagem
    assert c.correct_refusals == 3      # os 3 non_answerable
    assert c.false_answers == 0         # nenhuma alucinação
    assert c.correct_answers == 8       # os 8 respondíveis
    assert c.false_refusals == 0        # nenhuma over-recusa
    assert c.correct_refusal_rate == 1.0
    assert c.over_refusal_rate == 0.0
    assert r.acertos == 11 and r.total == 11


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
    assert "n=11" in texto                 # honestidade estatística explícita
