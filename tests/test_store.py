"""Teste da série temporal de market share (SQL, DuckDB em memória — sem rede)."""

import duckdb

from legacy_rag.structured.store import SCHEMA, market_share_serie


def _con_com_dados():
    con = duckdb.connect(":memory:")
    con.execute(SCHEMA)
    con.executemany(
        "INSERT INTO carteira_pf VALUES (?, ?, ?, ?)",
        [
            # consignado: A vai de 30% (202403) para 50% (202406)
            ("A", 202403, "consignado", 30.0), ("B", 202403, "consignado", 70.0),
            ("A", 202406, "consignado", 50.0), ("B", 202406, "consignado", 50.0),
            # outra modalidade não deve contaminar o cálculo de consignado
            ("A", 202403, "cartao", 999.0),
        ],
    )
    return con


def test_market_share_serie_evolui_no_tempo():
    con = _con_com_dados()
    assert market_share_serie(con, "A", "consignado") == [(202403, 0.3), (202406, 0.5)]


def test_serie_isola_a_modalidade():
    # o saldo gigante de A em 'cartao' não pode afetar o share de 'consignado'
    con = _con_com_dados()
    serie_b = market_share_serie(con, "B", "consignado")
    assert serie_b == [(202403, 0.7), (202406, 0.5)]


def test_banco_ausente_retorna_serie_vazia():
    con = _con_com_dados()
    assert market_share_serie(con, "INEXISTENTE", "consignado") == []
