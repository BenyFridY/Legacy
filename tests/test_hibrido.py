"""Testes da fusão RRF e da busca híbrida (DuckDB em memória, vetores determinísticos)."""

import duckdb
import numpy as np

from legacy_rag.index.chunking import chunkar_documento
from legacy_rag.index.store_texto import persistir_chunks
from legacy_rag.retrieval.hibrido import buscar_hibrido, fundir_rrf
from legacy_rag.retrieval.vetorial import Resultado


def _R(cid):
    return Resultado(cid, "BB", "3T24", "release", 1, 0, f"t{cid}", score=0.0)


def test_rrf_dedup_e_prioriza_quem_aparece_nas_duas_listas():
    A = [_R(1), _R(2), _R(3)]
    B = [_R(2), _R(1), _R(4)]
    fund = fundir_rrf([A, B])
    assert len(fund) == 4                                # dedup por chunk_id
    assert {r.chunk_id for r in fund[:2]} == {1, 2}      # os que estão nas DUAS listas vencem
    by_id = {r.chunk_id: r.score for r in fund}
    assert by_id[1] > by_id[3] and by_id[2] > by_id[4]


def test_rrf_listas_vazias():
    assert fundir_rrf([[], []]) == []


def _base_hibrida():
    con = duckdb.connect(":memory:")
    chunks = chunkar_documento(["consignado aqui.", "consignado ali.", "outra coisa."],
                               banco="Itau", periodo="4T24", tipo_doc="release")
    vet = np.array([[1, 0, 0, 0], [0, 1, 0, 0], [0.8, 0.2, 0, 0]], dtype="float32")
    persistir_chunks(con, chunks, vet)
    return con


def test_hibrido_premia_ficha_forte_nos_dois_ramos():
    con = _base_hibrida()
    # 'consignado aqui.' casa o termo (BM25) E o vetor da pergunta (e0) -> vence
    top = buscar_hibrido(con, "consignado", np.array([1, 0, 0, 0], dtype="float32"), k=3)
    assert top[0].texto == "consignado aqui."


def test_hibrido_respeita_filtro_de_metadados():
    con = _base_hibrida()
    c2 = chunkar_documento(["consignado no BB."], banco="BB", periodo="3T24", tipo_doc="release")
    persistir_chunks(con, c2, np.array([[1, 0, 0, 0]], dtype="float32"))
    res = buscar_hibrido(con, "consignado", np.array([1, 0, 0, 0], dtype="float32"), k=5, banco="BB")
    assert res and all(r.banco == "BB" for r in res)
