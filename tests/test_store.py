"""Teste da série temporal de market share (SQL, DuckDB em memória — sem rede)."""

import duckdb
import pytest

from legacy_rag.structured.store import SCHEMA, market_share_serie, trimestres_intervalo


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


# --- selecao de janela por trimestre (--de/--ate na CLI de ingestao) -------------------------

def test_trimestres_intervalo_expande_janela_completa():
    # 2024T1..2025T4 = 8 trimestres, mes de fechamento (T1=03 ... T4=12)
    assert trimestres_intervalo("2024T1", "2025T4") == [
        202403, 202406, 202409, 202412, 202503, 202506, 202509, 202512]


def test_trimestres_intervalo_um_so_trimestre():
    assert trimestres_intervalo("2025T2", "2025T2") == [202506]


def test_trimestres_intervalo_cruza_o_ano():
    assert trimestres_intervalo("2024T3", "2025T1") == [202409, 202412, 202503]


def test_trimestres_intervalo_aceita_t_minusculo_e_espacos():
    assert trimestres_intervalo(" 2024t4 ", "2025t1") == [202412, 202503]


def test_trimestres_intervalo_invertido_e_erro():
    with pytest.raises(ValueError):
        trimestres_intervalo("2025T4", "2024T1")


def test_trimestres_intervalo_formato_invalido_e_erro():
    for ruim in ("2024", "2024T5", "24T1", "2024-T1", "abacaxi"):
        with pytest.raises(ValueError):
            trimestres_intervalo(ruim, "2025T4")
