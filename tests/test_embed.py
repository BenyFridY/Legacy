"""Testes do embedding (sem torch, sem rede): fichas -> matriz de vetores.

O BGE-M3 real é pesado (~2 GB), então testamos o WIRING com um encoder FALSO e determinístico
injetado — exatamente o motivo de o modelo estar atrás da interface Encoder. Provamos a forma
da saída, o uso do .indexavel (com metadados) e o respeito ao tamanho do lote.
"""

import numpy as np

from legacy_rag.index.chunking import chunkar_documento
from legacy_rag.index.embed import embedar_chunks


class FakeEncoder:
    """Encoder leve e determinístico para teste (dim=4). Registra o que viu e quantas chamadas."""

    dim = 4

    def __init__(self):
        self.vistos: list[str] = []
        self.chamadas = 0

    def encode(self, textos):
        self.chamadas += 1
        textos = list(textos)
        self.vistos.extend(textos)
        return np.array([[len(t), sum(map(ord, t)) % 100, t.count(" "), 1.0] for t in textos],
                        dtype=np.float32)


def _duas_fichas():
    return chunkar_documento(["Primeira pagina aqui.", "Segunda pagina aqui."],
                             banco="BB", periodo="3T24", tipo_doc="release")  # 1 ficha por página


def test_embeda_todas_as_fichas_com_a_forma_certa():
    chunks = _duas_fichas()
    vec = embedar_chunks(chunks, FakeEncoder())
    assert vec.shape == (2, 4)


def test_embeda_o_indexavel_com_metadados_nao_o_texto_cru():
    enc = FakeEncoder()
    embedar_chunks(_duas_fichas(), enc)
    assert enc.vistos and all("[banco=" in t for t in enc.vistos)  # foi o .indexavel


def test_lista_vazia_retorna_matriz_vazia():
    vec = embedar_chunks([], FakeEncoder())
    assert vec.shape == (0, 4)


def test_respeita_o_tamanho_do_lote():
    enc = FakeEncoder()
    embedar_chunks(_duas_fichas(), enc, batch=1)
    assert enc.chamadas == 2   # 2 fichas, lote 1 -> 2 chamadas ao encoder
