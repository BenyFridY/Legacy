"""Testes da tabela `chunks` (DuckDB em memória, sem rede): persistência de fichas + vetores."""

import duckdb
import numpy as np
import pytest

from legacy_rag.index.chunking import chunkar_documento
from legacy_rag.index.store_texto import contar_chunks, persistir_chunks


def _chunks_e_vetores(banco="Itau", periodo="4T24", tipo="release", paginas=None):
    paginas = paginas or ["Primeira pagina aqui.", "Segunda pagina aqui."]
    chunks = chunkar_documento(paginas, banco=banco, periodo=periodo, tipo_doc=tipo)
    vet = np.arange(len(chunks) * 4, dtype="float32").reshape(len(chunks), 4)
    return chunks, vet


def test_persiste_e_conta():
    con = duckdb.connect(":memory:")
    chunks, vet = _chunks_e_vetores()
    assert persistir_chunks(con, chunks, vet) == len(chunks)
    assert contar_chunks(con) == len(chunks)


def test_embedding_faz_roundtrip():
    con = duckdb.connect(":memory:")
    chunks, vet = _chunks_e_vetores()
    persistir_chunks(con, chunks, vet)
    guardado = con.execute("SELECT embedding FROM chunks ORDER BY chunk_id LIMIT 1").fetchone()[0]
    assert np.allclose(guardado, vet[0])


def test_idempotente_por_documento():
    con = duckdb.connect(":memory:")
    chunks, vet = _chunks_e_vetores()
    persistir_chunks(con, chunks, vet)
    persistir_chunks(con, chunks, vet)            # regrava o MESMO documento
    assert contar_chunks(con) == len(chunks)      # não duplicou


def test_documentos_diferentes_coexistem():
    con = duckdb.connect(":memory:")
    c1, v1 = _chunks_e_vetores(banco="Itau", periodo="4T24")
    c2, v2 = _chunks_e_vetores(banco="BB", periodo="3T24", paginas=["So uma pagina."])
    persistir_chunks(con, c1, v1)
    persistir_chunks(con, c2, v2)
    assert contar_chunks(con) == len(c1) + len(c2)


def test_tamanhos_incompativeis_levantam_erro():
    con = duckdb.connect(":memory:")
    chunks, vet = _chunks_e_vetores()
    with pytest.raises(ValueError):
        persistir_chunks(con, chunks, vet[:-1])   # menos vetores que fichas
