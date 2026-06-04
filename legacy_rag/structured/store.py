"""Store estruturado em DuckDB — a "base ligada" do caminho dos números (ADR-0001/0003).

Tabela `carteira_pf(cod_inst, ano_mes, modalidade, saldo)`: a ingestão do Bacen popula;
as consultas (market share, séries no tempo) leem. Persistente em DUCKDB_PATH (gitignored).
O market share é calculado em SQL — determinístico e auditável por re-execução.
"""
from __future__ import annotations

import duckdb

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.structured.bacen import carteira_pf_modalidades

SCHEMA = """
CREATE TABLE IF NOT EXISTS carteira_pf (
    cod_inst   VARCHAR,
    ano_mes    INTEGER,
    modalidade VARCHAR,
    saldo      DOUBLE,
    PRIMARY KEY (cod_inst, ano_mes, modalidade)
);
"""


def conectar(path=None) -> duckdb.DuckDBPyConnection:
    """Abre (ou cria) a base DuckDB e garante o schema. path=':memory:' para testes."""
    if path is None:
        DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)  # cria data/ (gitignored)
        path = str(DUCKDB_PATH)
    con = duckdb.connect(path)
    con.execute(SCHEMA)
    return con


def carregar_periodo(con: duckdb.DuckDBPyConnection, ano_mes: int) -> int:
    """Ingere todas as modalidades PF de um período no DuckDB (idempotente: regrava o período)."""
    linhas = carteira_pf_modalidades(ano_mes)
    con.execute("DELETE FROM carteira_pf WHERE ano_mes = ?", [ano_mes])
    con.executemany(
        "INSERT INTO carteira_pf VALUES (?, ?, ?, ?)",
        [(r["cod_inst"], r["ano_mes"], r["modalidade"], r["saldo"]) for r in linhas],
    )
    return len(linhas)


def carregar_periodos(con: duckdb.DuckDBPyConnection, anos_meses: list[int]) -> dict[int, int]:
    """Ingere vários períodos. Retorna {ano_mes: nº de linhas}."""
    return {am: carregar_periodo(con, am) for am in anos_meses}


def market_share_serie(con: duckdb.DuckDBPyConnection, cod_inst: str, modalidade: str) -> list[tuple[int, float]]:
    """Série [(ano_mes, share)] de um banco numa modalidade, ao longo dos períodos na base.

    share = saldo do banco ÷ soma do sistema, por período — calculado em SQL.
    """
    q = """
        WITH sistema AS (
            SELECT ano_mes, SUM(saldo) AS total
            FROM carteira_pf WHERE modalidade = ? GROUP BY ano_mes
        )
        SELECT c.ano_mes, c.saldo / s.total AS share
        FROM carteira_pf c JOIN sistema s USING (ano_mes)
        WHERE c.modalidade = ? AND c.cod_inst = ?
        ORDER BY c.ano_mes;
    """
    rows = con.execute(q, [modalidade, modalidade, cod_inst]).fetchall()
    return [(int(am), float(sh)) for am, sh in rows]
