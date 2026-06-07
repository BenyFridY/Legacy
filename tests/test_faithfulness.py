"""Testes do eval de fidelidade — sem rede, sem chave, sem torch (juiz e LLM falsos)."""

from legacy_rag.eval.faithfulness import (
    CasoFidelidade,
    LLMJuizFidelidade,
    ResultadoFidelidade,
    Veredito,
    _parse_veredito,
    avaliar_fidelidade,
    formatar_relatorio,
)


# ----------------------------------------------------------------- fakes

class FakeJuiz:
    """Julga 'fiel' se o número da resposta aparece no contexto (regra determinística)."""

    def julgar(self, caso: CasoFidelidade) -> Veredito:
        fiel = caso.resposta in caso.contexto
        return Veredito(fundamentada=fiel,
                        alegacoes_sem_suporte=[] if fiel else [caso.resposta],
                        justificativa="ok" if fiel else "numero ausente no contexto")


class FakeLLM:
    def __init__(self, saida):
        self.saida = saida
        self.ultimo_prompt = None

    def completar(self, prompt):
        self.ultimo_prompt = prompt
        return self.saida


# ----------------------------------------------------------------- _parse_veredito

def test_parse_json_fiel():
    v = _parse_veredito('{"fundamentada": true, "alegacoes_sem_suporte": [], "justificativa": "tudo bate"}')
    assert v.fundamentada and v.alegacoes_sem_suporte == [] and v.justificativa == "tudo bate"


def test_parse_json_infiel_lista_alegacoes():
    v = _parse_veredito('Claro!\n{"fundamentada": false, "alegacoes_sem_suporte": ["R$ 99 bi"], "justificativa": "x"}')
    assert not v.fundamentada and v.alegacoes_sem_suporte == ["R$ 99 bi"]


def test_parse_sem_json_e_conservador():
    # Juiz ilegível NÃO pode absolver: faithfulness trata 'não confirmei' como não-fundamentada.
    v = _parse_veredito("desculpe, não consegui avaliar")
    assert not v.fundamentada and "ilegível" in v.justificativa


def test_parse_json_quebrado_e_conservador():
    v = _parse_veredito('{"fundamentada": true, ')
    assert not v.fundamentada


def test_parse_bool_como_string_e_conservador():
    # O LLM às vezes serializa o booleano como STRING. bool("false")==True seria um BUG (absolveria).
    assert _parse_veredito('{"fundamentada": "false", "alegacoes_sem_suporte": ["x"]}').fundamentada is False
    assert _parse_veredito('{"fundamentada": "true", "alegacoes_sem_suporte": []}').fundamentada is True


# ----------------------------------------------------------------- LLMJuizFidelidade

def test_llm_juiz_monta_prompt_e_parseia():
    llm = FakeLLM('{"fundamentada": true, "alegacoes_sem_suporte": [], "justificativa": "ok"}')
    juiz = LLMJuizFidelidade(llm)
    caso = CasoFidelidade("c1", "Qual o lucro?", "R$ 12,3 bi", "Lucro de R$ 12,3 bi no 4T25.")
    v = juiz.julgar(caso)
    assert v.fundamentada
    assert "R$ 12,3 bi" in llm.ultimo_prompt and "Qual o lucro?" in llm.ultimo_prompt  # prompt usa os campos


# ----------------------------------------------------------------- avaliar_fidelidade

def test_avaliar_agrega_taxa():
    casos = [
        CasoFidelidade("ok", "Saldo consignado?", "R$ 75,3 bi", "Carteira consignado de R$ 75,3 bi."),  # fiel
        CasoFidelidade("ruim", "Saldo consignado?", "R$ 99,9 bi", "Carteira consignado de R$ 75,3 bi."),  # infiel
    ]
    res = avaliar_fidelidade(casos, FakeJuiz())
    assert res.total == 2 and res.fundamentadas == 1 and res.taxa == 0.5


def test_taxa_none_sem_casos():
    assert ResultadoFidelidade().taxa is None


def test_relatorio_mostra_taxa_e_falhas():
    casos = [CasoFidelidade("ruim", "Pergunta?", "R$ 99 bi", "contexto sem esse numero")]
    txt = formatar_relatorio(avaliar_fidelidade(casos, FakeJuiz()))
    assert "Taxa de fidelidade" in txt and "0%" in txt and "ruim" in txt
