"""Ingestão de ponta a ponta — a "base ligada" do caminho do texto.

Junta as peças que já existiam em uma operação só: baixar -> extrair páginas -> chunkar ->
EMBEDDAR -> persistir no DuckDB. É o que torna a base "automática": apontar para um release
(URL do CDN) e o documento entra pronto para busca, com idempotência por (banco, período, tipo).

Separado em duas funções para ser TESTÁVEL sem rede:
  - ingerir_paginas: recebe as páginas já extraídas (chunk -> embed -> store) — testa com fake.
  - ingerir_release: baixa o PDF + extrai e chama ingerir_paginas — usada na ingestão real.
"""
from __future__ import annotations

import duckdb

from legacy_rag.index.chunking import ALVO_CHARS, OVERLAP_CHARS, chunkar_documento
from legacy_rag.index.embed import Encoder, embedar_chunks
from legacy_rag.index.store_texto import garantir_schema, persistir_chunks
from legacy_rag.ingestion.releases import baixar, extrair_paginas


def ingerir_paginas(con: duckdb.DuckDBPyConnection, paginas: list[str], banco: str, periodo: str,
                    tipo_doc: str, encoder: Encoder, alvo: int = ALVO_CHARS,
                    overlap: int = OVERLAP_CHARS) -> int:
    """Chunka as páginas, embeda e persiste. Retorna o nº de fichas gravadas."""
    chunks = chunkar_documento(paginas, banco, periodo, tipo_doc, alvo, overlap)
    vetores = embedar_chunks(chunks, encoder)
    garantir_schema(con)
    return persistir_chunks(con, chunks, vetores)


def ingerir_release(con: duckdb.DuckDBPyConnection, url: str, banco: str, periodo: str,
                    tipo_doc: str, encoder: Encoder, **kw) -> int:
    """Baixa o release do CDN, extrai por página e ingere. Retorna o nº de fichas gravadas."""
    paginas = extrair_paginas(baixar(url))
    return ingerir_paginas(con, paginas, banco, periodo, tipo_doc, encoder, **kw)
