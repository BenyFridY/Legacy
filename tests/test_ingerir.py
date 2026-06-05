"""Teste da ingestão de ponta a ponta (ingerir_paginas) — sem rede, com encoder FALSO."""

import numpy as np

from legacy_rag.index.store_texto import contar_chunks
from legacy_rag.ingestion.ingerir import ingerir_paginas
from legacy_rag.structured.store import conectar


class FakeEncoder:
    dim = 8

    def encode(self, textos):
        return np.ones((len(textos), self.dim), dtype=np.float32)


def test_ingerir_paginas_chunka_embeda_e_grava():
    con = conectar(":memory:")
    paginas = [
        "O custo do crédito do Banco do Brasil em 2025 foi R$ 62 bilhões. " * 30,  # pág. 1
        "A carteira de consignado cresceu no período, segundo o release. " * 30,   # pág. 2
    ]
    n = ingerir_paginas(con, paginas, "BB", "4T25", "release", FakeEncoder())
    assert n > 0
    assert contar_chunks(con) == n


def test_ingerir_paginas_idempotente_por_documento():
    con = conectar(":memory:")
    paginas = ["Texto da página um. " * 50]
    n1 = ingerir_paginas(con, paginas, "BB", "4T25", "release", FakeEncoder())
    n2 = ingerir_paginas(con, paginas, "BB", "4T25", "release", FakeEncoder())  # regrava o mesmo doc
    assert n1 == n2
    assert contar_chunks(con) == n1            # não duplicou
