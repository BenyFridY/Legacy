"""Store estruturado em DuckDB — a "base ligada" do caminho dos números (ADR-0001/0003).

Tabela `carteira_pf(cod_inst, ano_mes, modalidade, saldo)`: a ingestão do Bacen popula;
as consultas (market share, séries no tempo) leem. Persistente em DUCKDB_PATH (gitignored).
O market share é calculado em SQL — determinístico e auditável por re-execução.
"""
from __future__ import annotations

import duckdb

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.structured.bacen import carteira_pf_modalidades, cadastro_conglomerado

SCHEMA = """
CREATE TABLE IF NOT EXISTS carteira_pf (
    cod_inst   VARCHAR,
    ano_mes    INTEGER,
    modalidade VARCHAR,
    saldo      DOUBLE,
    PRIMARY KEY (cod_inst, ano_mes, modalidade)
);
CREATE TABLE IF NOT EXISTS cadastro (
    cod_inst       VARCHAR,
    ano_mes        INTEGER,
    nome           VARCHAR,
    cod_prudencial VARCHAR,           -- conglomerado prudencial (vários CNPJs -> 1 banco)
    PRIMARY KEY (cod_inst, ano_mes)
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
    """Série [(ano_mes, share)] de UM CodInst (CNPJ) numa modalidade. share = saldo ÷ sistema, em SQL.

    Atenção: por CNPJ cru, pode subestimar um banco que reporta em vários CNPJs — use
    market_share_conglomerado_serie para o share por banco (conglomerado).
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


def carregar_cadastro(con: duckdb.DuckDBPyConnection, ano_mes: int) -> int:
    """Ingere o cadastro (CodInst -> nome + conglomerado prudencial) de um período. Idempotente."""
    mapa = cadastro_conglomerado(ano_mes)
    con.execute("DELETE FROM cadastro WHERE ano_mes = ?", [ano_mes])
    con.executemany(
        "INSERT INTO cadastro VALUES (?, ?, ?, ?)",
        [(cod, ano_mes, info["nome"], info["prudencial"]) for cod, info in mapa.items()],
    )
    return len(mapa)


def market_share_conglomerado_serie(con: duckdb.DuckDBPyConnection, cod_prudencial: str,
                                    modalidade: str) -> list[tuple[int, float]]:
    """Série [(ano_mes, share)] de um BANCO (conglomerado prudencial) numa modalidade.

    Soma o saldo de TODOS os CNPJs do conglomerado (join carteira_pf x cadastro) e divide pelo
    sistema, por período. É o share "por banco" correto (não subestima quem usa vários CNPJs).
    """
    q = """
        WITH sistema AS (
            SELECT ano_mes, SUM(saldo) AS total
            FROM carteira_pf WHERE modalidade = ? GROUP BY ano_mes
        ),
        cong AS (
            SELECT c.ano_mes, SUM(c.saldo) AS saldo
            FROM carteira_pf c
            JOIN cadastro cad ON c.cod_inst = cad.cod_inst AND c.ano_mes = cad.ano_mes
            WHERE c.modalidade = ? AND cad.cod_prudencial = ?
            GROUP BY c.ano_mes
        )
        SELECT cong.ano_mes, cong.saldo / s.total AS share
        FROM cong JOIN sistema s USING (ano_mes)
        ORDER BY cong.ano_mes;
    """
    rows = con.execute(q, [modalidade, modalidade, cod_prudencial]).fetchall()
    return [(int(am), float(sh)) for am, sh in rows]


def ranking_conglomerado(con: duckdb.DuckDBPyConnection, ano_mes: int, modalidade: str,
                         top: int = 10) -> list[tuple[str, str, float]]:
    """Top conglomerados por share numa modalidade/período: [(cod_prudencial, nome, share)].

    Nome = o do MAIOR membro do conglomerado (arg_max em SQL). Para inspeção e apresentação.
    """
    q = """
        SELECT cad.cod_prudencial,
               arg_max(cad.nome, c.saldo) AS nome,
               SUM(c.saldo) / (SELECT SUM(saldo) FROM carteira_pf WHERE modalidade = ? AND ano_mes = ?) AS share
        FROM carteira_pf c
        JOIN cadastro cad ON c.cod_inst = cad.cod_inst AND c.ano_mes = cad.ano_mes
        WHERE c.modalidade = ? AND c.ano_mes = ?
        GROUP BY cad.cod_prudencial
        ORDER BY share DESC
        LIMIT ?;
    """
    rows = con.execute(q, [modalidade, ano_mes, modalidade, ano_mes, top]).fetchall()
    return [(cod, nome, float(sh)) for cod, nome, sh in rows]
