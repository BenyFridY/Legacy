"""Teste de ponta a ponta do orquestrador (pipeline.responder) — sem torch, sem rede, sem chave.

Monta uma base DuckDB em memória (chunks de texto + carteira_pf de números) e exercita os
4 caminhos: recusa por escopo, doc_unico (texto), computada (números), multi_fonte (fusão).
Encoder/reranker/LLM são FALSOS e determinísticos: provam o FLUXO e as RECUSAS.
"""

import numpy as np
import pytest

from legacy_rag.index.chunking import Chunk
from legacy_rag.index.embed import embedar_chunks
from legacy_rag.index.store_texto import garantir_schema, persistir_chunks
from legacy_rag.pipeline import Dependencias, responder
from legacy_rag.structured.store import conectar


# ---------------------------------------------------------------- fakes

class FakeEncoder:
    dim = 8

    def encode(self, textos):
        # Vetor constante: com poucos chunks, todos viram candidatos; o reranker é quem ordena.
        return np.ones((len(textos), self.dim), dtype=np.float32)


class FakeReranker:
    """Nota = fração das palavras da pergunta presentes no trecho (0–1, determinístico)."""

    def pontuar(self, query, textos):
        qs = set(query.lower().split())
        return [len(qs & set(t.lower().split())) / max(1, len(qs)) for t in textos]


class FakeLLM:
    def __init__(self, resposta="Resposta redigida a partir do contexto fornecido."):
        self.resposta = resposta
        self.ultimo_prompt = None

    def completar(self, prompt):
        self.ultimo_prompt = prompt
        return self.resposta


# ---------------------------------------------------------------- base de teste

@pytest.fixture
def deps():
    con = conectar(":memory:")          # cria carteira_pf
    garantir_schema(con)                # cria chunks

    enc = FakeEncoder()
    chunks = [
        Chunk("BB", "4T25", "release", 12, 0,
              "O custo do crédito realizado pelo Banco do Brasil em 2025 foi R$ 62,0 bilhões."),
        Chunk("Bradesco", "recente", "transcricao", 3, 0,
              "O CEO do Bradesco declarou market share de consignado de cerca de 14,2%."),
    ]
    persistir_chunks(con, chunks, embedar_chunks(chunks, enc))

    # carteira_pf (consignado): BB e Bradesco + um "outro" pra fechar o denominador do sistema.
    linhas = [
        ("C0000001", 202403, "consignado", 200.0),  # BB  -> share 0.20
        ("C0000002", 202403, "consignado", 140.0),  # Bradesco -> 0.14
        ("C9999999", 202403, "consignado", 660.0),  # resto -> total 1000
        ("C0000001", 202412, "consignado", 250.0),  # BB  -> 0.25
        ("C0000002", 202412, "consignado", 142.0),  # Bradesco -> 0.142
        ("C9999999", 202412, "consignado", 608.0),  # resto -> total 1000
    ]
    con.executemany("INSERT INTO carteira_pf VALUES (?, ?, ?, ?)", linhas)

    return Dependencias(
        con=con, encoder=enc, reranker=FakeReranker(), llm=FakeLLM(),
        mapa_cod_inst={"BB": "C0000001", "Bradesco": "C0000002"}, limiar=0.3,
    )


# ---------------------------------------------------------------- os 4 caminhos

def test_recusa_por_escopo(deps):
    r = responder("Qual será o custo de crédito do Bradesco no 2º trimestre de 2027?", deps)
    assert r.recusou and r.motivo.startswith("R1")


def test_doc_unico_responde_citado(deps):
    r = responder("Qual foi o custo do crédito realizado pelo Banco do Brasil em 2025?", deps)
    assert not r.recusou
    assert "BB, 4T25, release, pág. 12" in r.citacoes      # citação estrutural, do chunk
    assert "Fontes:" in r.formatado


def test_doc_unico_sem_evidencia_recusa(deps):
    # Pergunta sobre o Itaú: não há chunk do Itaú na base -> retrieval vazio -> gate recusa.
    r = responder("Qual a faixa de guidance de custo de crédito do Itaú para 2026?", deps)
    assert r.recusou


def test_computada_responde_serie_citada(deps):
    r = responder("Como evoluiu o market share do Banco do Brasil em consignado nos últimos quatro trimestres?", deps)
    assert not r.recusou
    assert "20.0%" in r.texto and "25.0%" in r.texto and "alta" in r.texto
    assert "IF.data" in r.citacoes[0]


def test_computada_sem_cod_inst_recusa_honesta(deps):
    deps.mapa_cod_inst = {}            # simula o cadastro Bacen indisponível (HTTP 500)
    r = responder("Como evoluiu o market share do Banco do Brasil em consignado?", deps)
    assert r.recusou and "cod_inst" in r.motivo


def test_multi_fonte_cruza_declarado_e_computado(deps):
    r = responder(
        "O market share de consignado do Bradesco computado a partir do IF.data confirma o "
        "~14,2% que o CEO declarou?", deps)
    assert not r.recusou
    assert any("IF.data" in c for c in r.citacoes)          # lado computado
    assert any("Bradesco" in c and "transcricao" in c for c in r.citacoes)  # lado declarado
    assert len(r.citacoes) == 2


def test_multi_fonte_sem_llm_devolve_evidencias(deps):
    deps.llm = None
    r = responder(
        "O market share de consignado do Bradesco computado a partir do IF.data confirma o "
        "~14,2% que o CEO declarou?", deps)
    assert not r.recusou and "declarado x computado" in r.texto
