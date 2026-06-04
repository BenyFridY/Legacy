"""Armazenamento do TEXTO no DuckDB — a tabela `chunks` (fichas + vetores).

Mesmo arquivo .duckdb dos números (store único, ADR-0003), porém tabela separada. Aqui mora
a unidade de BUSCA e CITAÇÃO. O embedding é guardado como FLOAT[] (lista) de propósito: não
amarra a dimensão (testes usam um encoder pequeno; a produção usa BGE-M3 de 1024). A busca
exata carrega esses vetores numa matriz e calcula a similaridade (brute-force; ver ADR de escala).

Idempotência por DOCUMENTO: regravar (banco, período, tipo) apaga as fichas antigas daquele
documento e reinsere — o mesmo padrão upsert-por-partição já provado em
structured/store.py:carregar_periodo. (A dedup por hash de conteúdo vem no passo de escala.)
"""
from __future__ import annotations

import duckdb
import numpy as np

from legacy_rag.index.chunking import Chunk

SCHEMA_CHUNKS = """
CREATE SEQUENCE IF NOT EXISTS seq_chunk;
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   BIGINT PRIMARY KEY DEFAULT nextval('seq_chunk'),
    banco      VARCHAR,
    periodo    VARCHAR,
    tipo_doc   VARCHAR,
    pagina     INTEGER,
    ordinal    INTEGER,
    texto      VARCHAR,
    embedding  FLOAT[]
);
"""


def garantir_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Cria a sequência e a tabela `chunks` se ainda não existirem (idempotente)."""
    con.execute(SCHEMA_CHUNKS)


def persistir_chunks(con: duckdb.DuckDBPyConnection, chunks: list[Chunk], vetores: np.ndarray) -> int:
    """Grava as fichas de UM documento + seus vetores. Idempotente por (banco, período, tipo)."""
    if len(chunks) != len(vetores):
        raise ValueError(f"chunks ({len(chunks)}) e vetores ({len(vetores)}) com tamanhos diferentes")
    garantir_schema(con)
    if not chunks:
        return 0
    for banco, periodo, tipo in {(c.banco, c.periodo, c.tipo_doc) for c in chunks}:
        con.execute("DELETE FROM chunks WHERE banco=? AND periodo=? AND tipo_doc=?", [banco, periodo, tipo])
    con.executemany(
        "INSERT INTO chunks (banco, periodo, tipo_doc, pagina, ordinal, texto, embedding) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(c.banco, c.periodo, c.tipo_doc, c.pagina, c.ordinal, c.texto, v.tolist())
         for c, v in zip(chunks, vetores)],
    )
    return len(chunks)


def contar_chunks(con: duckdb.DuckDBPyConnection) -> int:
    return con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
