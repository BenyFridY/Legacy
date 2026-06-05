"""Testes da busca lexical BM25 (DuckDB em memória, sem rede)."""

import duckdb
import numpy as np

from legacy_rag.index.chunking import chunkar_documento
from legacy_rag.index.store_texto import garantir_schema, persistir_chunks
from legacy_rag.retrieval.lexical import buscar_bm25, tokenizar


def _base():
    con = duckdb.connect(":memory:")
    chunks = chunkar_documento(
        ["O custo de credito foi 4,5 por cento.",
         "A carteira de consignado cresceu.",
         "O guidance trata da inadimplencia."],
        banco="Itau", periodo="4T24", tipo_doc="release")
    persistir_chunks(con, chunks, np.zeros((len(chunks), 2), dtype="float32"))  # vetor irrelevante p/ BM25
    return con


def test_tokenizar_normaliza_acento_e_pontuacao():
    assert tokenizar("Inadimplência 4,5%") == ["inadimplencia", "4", "5"]


def test_acha_a_ficha_pelo_termo_exato():
    con = _base()
    assert "consignado" in buscar_bm25(con, "consignado", k=1)[0].texto


def test_mais_termos_casados_pontuam_mais():
    con = _base()
    top = buscar_bm25(con, "custo credito", k=3)
    assert "custo de credito" in top[0].texto      # 2 termos casam -> vence


def test_filtro_por_metadados():
    con = _base()
    c2 = chunkar_documento(["consignado no BB tambem."], banco="BB", periodo="3T24", tipo_doc="release")
    persistir_chunks(con, c2, np.zeros((1, 2), dtype="float32"))
    res = buscar_bm25(con, "consignado", k=5, banco="BB")
    assert res and all(r.banco == "BB" for r in res)


def test_base_vazia_retorna_vazio():
    con = duckdb.connect(":memory:")
    garantir_schema(con)
    assert buscar_bm25(con, "consignado") == []


def test_resultado_carrega_citacao():
    con = _base()
    r = buscar_bm25(con, "consignado", k=1)[0]
    assert "Itau" in r.citacao and "4T24" in r.citacao
