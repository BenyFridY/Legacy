"""Eval focado: a "v2 do gate de futuro" (ADR-0005) — responder DATA futura documentada sem alucinar.

10 sondagens de DATA exercitando, ponta a ponta (router + aterramento + gate), a separação:
  - VALOR de métrica em ano futuro            -> RECUSA cedo (R1 refinado)
  - DATA/evento futuro DOCUMENTADO num trecho -> RESPONDE (trava de aterramento deixa passar)
  - VALOR futuro NÃO documentado              -> RECUSA (aterramento barra: nenhum trecho tem o ano)
  - ano presente/sem ano                       -> RESPONDE (não regrediu)

Fakes determinísticos (sem torch/rede/chave), no estilo de tests/test_pipeline.py.
"""

import numpy as np
import pytest

from legacy_rag.index.chunking import Chunk
from legacy_rag.index.embed import embedar_chunks
from legacy_rag.index.store_texto import garantir_schema, persistir_chunks
from legacy_rag.pipeline import Dependencias, responder
from legacy_rag.structured.store import conectar


class FakeEncoder:
    dim = 8

    def encode(self, textos):
        return np.ones((len(textos), self.dim), dtype=np.float32)


class FakeReranker:
    """Nota = fração das palavras da pergunta presentes no trecho (0–1, determinístico)."""

    def pontuar(self, query, textos):
        qs = set(query.lower().split())
        return [len(qs & set(t.lower().split())) / max(1, len(qs)) for t in textos]


class FakeLLM:
    def completar(self, prompt):
        return "Resposta redigida a partir do contexto fornecido."


@pytest.fixture
def deps():
    con = conectar(":memory:")
    garantir_schema(con)
    enc = FakeEncoder()
    # Anos presentes nos trechos: 2025 (vários), 2027 (vigência de norma), 2028 (vencimento).
    chunks = [
        Chunk("BB", "4T25", "release", 12, 0,
              "O custo do crédito realizado pelo Banco do Brasil em 2025 foi R$ 62,0 bilhões."),
        Chunk("BB", "4T25", "release", 30, 0,
              "O lucro líquido do banco em 2025 foi R$ 30 bilhões."),
        Chunk("BB", "4T25", "release", 14, 0,
              "A inadimplência acima de 90 dias do banco em 2025 foi de 3,0%."),
        Chunk("BB", "4T25", "release", 90, 0,
              "Os vencimentos de dívida do banco totalizam R$ 7 bilhões em 2028."),
        Chunk("BB", "4T25", "release", 100, 0,
              "As novas regras da Resolução 4.966 entram em vigor em 2027."),
        # ARMADILHA ADVERSARIAL: "2027" aparece como VALOR (R$ 2027 milhões), não como ano.
        Chunk("BB", "4T25", "release", 31, 0,
              "O lucro líquido do banco em 2025 foi de R$ 2027 milhões."),
    ]
    persistir_chunks(con, chunks, embedar_chunks(chunks, enc))

    CONS = "Empréstimo com Consignação em Folha"
    con.executemany("INSERT INTO carteira_pf VALUES (?, ?, ?, ?)", [
        ("C0000001", 202403, CONS, 200.0), ("C9999999", 202403, CONS, 800.0),
        ("C0000001", 202412, CONS, 250.0), ("C9999999", 202412, CONS, 750.0),
    ])
    con.executemany("INSERT INTO cadastro VALUES (?, ?, ?, ?)", [
        ("C0000001", 202403, "Banco do Brasil", "PRUD_BB"), ("C9999999", 202403, "Outro", "PRUD_OUTRO"),
        ("C0000001", 202412, "Banco do Brasil", "PRUD_BB"), ("C9999999", 202412, "Outro", "PRUD_OUTRO"),
    ])
    return Dependencias(con=con, encoder=enc, reranker=FakeReranker(), llm=FakeLLM(),
                        mapa_prudencial={"BB": "PRUD_BB"}, limiar=0.3)


# (id, pergunta, espera_recusa)
CASOS = [
    # --- VALOR de métrica em ano futuro -> RECUSA cedo (R1 refinado) ---
    ("r1-custo-credito-2027",      "Qual será o custo de crédito do Bradesco em 2027?", True),
    ("r1-market-share-2028",       "Qual o market share do Banco do Brasil em consignado em 2028?", True),
    ("r1-guidance-2027",           "Qual o guidance de custo de crédito do Itaú para 2027?", True),
    # --- DATA/evento futuro DOCUMENTADO -> RESPONDE (aterramento deixa passar) ---
    ("ancora-vencimentos-2028",    "Quais os vencimentos de dívida do banco em 2028?", False),
    ("ancora-vigencia-sem-ano",    "Em que ano entram em vigor as novas regras da Resolução 4.966?", False),
    ("ancora-muda-2027",           "O que muda com as regras que entram em vigor em 2027?", False),
    # --- VALOR futuro NÃO documentado -> RECUSA (aterramento barra: nenhum trecho tem o ano) ---
    ("aterra-lucro-2031",          "Qual será o lucro líquido do banco em 2031?", True),
    ("aterra-inadimplencia-2030",  "Qual a inadimplência do banco em 2030?", True),
    # ADVERSARIAL: "2027" no trecho é VALOR (R$ 2027 milhões), não ano -> aterramento NÃO pode cair nessa.
    ("hard-ano-como-valor",        "Qual o lucro líquido do banco em 2027?", True),
    # --- sanidade: não regrediu o que já respondia ---
    ("sanidade-custo-2025",        "Qual foi o custo do crédito realizado pelo Banco do Brasil em 2025?", False),
    ("sanidade-serie-share",       "Como evoluiu o market share do Banco do Brasil em consignado nos últimos trimestres?", False),
]


@pytest.mark.parametrize("desc,pergunta,espera_recusa", CASOS, ids=[c[0] for c in CASOS])
def test_gate_futuro(deps, desc, pergunta, espera_recusa):
    r = responder(pergunta, deps)
    assert r.recusou == espera_recusa, (
        f"[{desc}] esperava recusa={espera_recusa}, obteve recusa={r.recusou} "
        f"(motivo={r.motivo!r}; texto={r.texto[:80]!r})")
