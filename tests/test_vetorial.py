"""Testes da busca vetorial (DuckDB em memória, vetores determinísticos — sem modelo/rede)."""

import duckdb
import numpy as np

from legacy_rag.index.chunking import chunkar_documento
from legacy_rag.index.store_texto import persistir_chunks
from legacy_rag.retrieval.vetorial import buscar_vetorial


def _base():
    """3 fichas (uma por página) com vetores 'identidade': alpha=e0, beta=e1, gamma=e2."""
    con = duckdb.connect(":memory:")
    chunks = chunkar_documento(["alpha aqui.", "beta aqui.", "gamma aqui."],
                               banco="Itau", periodo="4T24", tipo_doc="release")
    persistir_chunks(con, chunks, np.eye(3, 4, dtype="float32"))
    return con


def test_acha_a_ficha_mais_proxima():
    con = _base()
    top = buscar_vetorial(con, np.array([1, 0, 0, 0], dtype="float32"), k=2)
    assert top[0].texto == "alpha aqui." and top[0].pagina == 1
    assert top[0].score > top[1].score                  # ordenado por similaridade


def test_k_limita_resultados():
    con = _base()
    assert len(buscar_vetorial(con, np.array([0, 1, 0, 0], dtype="float32"), k=1)) == 1


def test_filtro_por_metadados():
    con = _base()
    c2 = chunkar_documento(["delta aqui."], banco="BB", periodo="3T24", tipo_doc="release")
    persistir_chunks(con, c2, np.array([[1, 0, 0, 0]], dtype="float32"))
    res = buscar_vetorial(con, np.array([1, 0, 0, 0], dtype="float32"), k=5, banco="BB")
    assert res and all(r.banco == "BB" for r in res)    # pré-filtro isolou o banco


def test_base_vazia_retorna_vazio():
    con = duckdb.connect(":memory:")
    from legacy_rag.index.store_texto import garantir_schema
    garantir_schema(con)
    assert buscar_vetorial(con, np.array([1, 0, 0, 0], dtype="float32")) == []


def test_resultado_carrega_citacao():
    con = _base()
    r = buscar_vetorial(con, np.array([0, 0, 1, 0], dtype="float32"), k=1)[0]
    assert "Itau" in r.citacao and "4T24" in r.citacao and "pág." in r.citacao
