"""Testes do gate de evidência + geração (sem rede, sem chave, via LLM FALSO)."""

from legacy_rag.generation.answer import (
    SENTINELA_NAO_ENCONTRADO,
    montar_prompt,
    responder_de_contexto,
)
from legacy_rag.generation.gate import gate_evidencia
from legacy_rag.retrieval.vetorial import Resultado


def _res(cid, texto, score):
    return Resultado(cid, "BB", "4T25", "release", 7, 0, texto, score=score)


class LLMFixo:
    """LLM falso: devolve sempre o mesmo texto (controla o teste sem modelo real)."""

    def __init__(self, resposta):
        self.resposta = resposta
        self.ultimo_prompt = None

    def completar(self, prompt):
        self.ultimo_prompt = prompt
        return self.resposta


# ---------------------------------------------------------------- gate de evidência

def test_gate_evidencia_forte_responde():
    d = gate_evidencia([_res(1, "...", 0.9), _res(2, "...", 0.4)], limiar=0.3)
    assert d.responder and d.melhor_nota == 0.9 and d.motivo is None


def test_gate_evidencia_fraca_recusa():
    d = gate_evidencia([_res(1, "...", 0.1), _res(2, "...", 0.2)], limiar=0.3)
    assert not d.responder and d.melhor_nota == 0.2 and "Evidência fraca" in d.motivo


def test_gate_sem_resultados_recusa():
    d = gate_evidencia([], limiar=0.3)
    assert not d.responder and d.melhor_nota == 0.0


# ---------------------------------------------------------------- geração + citação

def test_responde_com_citacao_estrutural():
    res = [_res(1, "O custo do crédito foi R$ 62,0 bilhões.", 0.8)]
    llm = LLMFixo("O custo do crédito do BB em 2025 foi R$ 62,0 bilhões.")
    r = responder_de_contexto("Qual o custo do crédito do BB em 2025?", res, llm, limiar=0.3)
    assert not r.recusou
    assert r.citacoes == ["BB, 4T25, release, pág. 7"]   # vem do Resultado, não do texto do LLM
    assert "Fontes:" in r.formatado


def test_citacao_independe_do_texto_do_llm():
    """Mesmo se o LLM não mencionar a fonte, a citação é anexada por código."""
    res = [_res(1, "trecho relevante", 0.8)]
    r = responder_de_contexto("pergunta?", res, LLMFixo("resposta sem citar nada"), limiar=0.3)
    assert r.citacoes == ["BB, 4T25, release, pág. 7"]


def test_evidencia_fraca_nao_chama_llm():
    """Gate recusa ANTES de redigir: o LLM nem é chamado (ultimo_prompt fica None)."""
    llm = LLMFixo("não deveria ser usado")
    r = responder_de_contexto("pergunta?", [_res(1, "x", 0.05)], llm, limiar=0.3)
    assert r.recusou and llm.ultimo_prompt is None


def test_llm_diz_nao_encontrado_vira_recusa():
    """Defesa em profundidade: evidência passou no gate, mas o LLM não achou -> recusa."""
    res = [_res(1, "texto sobre outra coisa", 0.9)]
    r = responder_de_contexto("pergunta?", res, LLMFixo(SENTINELA_NAO_ENCONTRADO), limiar=0.3)
    assert r.recusou and "não encontrou" in r.motivo


def test_prompt_tem_instrucao_contexto_e_pergunta():
    res = [_res(1, "trecho XYZ", 0.8)]
    p = montar_prompt("minha pergunta?", res)
    assert "SOMENTE os trechos" in p          # instrução de groundedness
    assert "trecho XYZ" in p                   # o contexto
    assert "(BB, 4T25, release, pág. 7)" in p  # a citação no contexto
    assert "minha pergunta?" in p              # a pergunta
