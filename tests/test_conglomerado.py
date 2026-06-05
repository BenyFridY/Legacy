"""Market share por CONGLOMERADO (sem rede): prova que soma os vários CNPJs de um banco."""

import pytest

from legacy_rag.structured.store import (
    conectar,
    market_share_conglomerado_serie,
    market_share_serie,
    ranking_conglomerado,
)


@pytest.fixture
def con():
    c = conectar(":memory:")          # cria carteira_pf + cadastro
    # CONG_A = um banco com DOIS CNPJs (111 principal + 112 financeira); CONG_B = um CNPJ (222).
    carteira = [
        ("111", 202403, "consignado", 200.0), ("112", 202403, "consignado", 50.0),
        ("222", 202403, "consignado", 750.0),                                   # total 1000
        ("111", 202412, "consignado", 300.0), ("112", 202412, "consignado", 50.0),
        ("222", 202412, "consignado", 650.0),                                   # total 1000
    ]
    c.executemany("INSERT INTO carteira_pf VALUES (?, ?, ?, ?)", carteira)
    cad = [
        ("111", 202403, "Banco A Principal", "CONG_A"), ("112", 202403, "Banco A Financeira", "CONG_A"),
        ("222", 202403, "Banco B", "CONG_B"),
        ("111", 202412, "Banco A Principal", "CONG_A"), ("112", 202412, "Banco A Financeira", "CONG_A"),
        ("222", 202412, "Banco B", "CONG_B"),
    ]
    c.executemany("INSERT INTO cadastro VALUES (?, ?, ?, ?)", cad)
    return c


def test_conglomerado_soma_os_cnpjs_do_banco(con):
    # CONG_A = 111+112: 250/1000=0.25 em 202403; 350/1000=0.35 em 202412.
    serie = market_share_conglomerado_serie(con, "CONG_A", "consignado")
    assert serie == [(202403, pytest.approx(0.25)), (202412, pytest.approx(0.35))]


def test_por_cnpj_cru_subestima(con):
    # O CNPJ principal sozinho (111) dá 200/1000=0.20 < 0.25 do conglomerado -> justifica a agregação.
    serie = market_share_serie(con, "111", "consignado")
    assert serie[0] == (202403, pytest.approx(0.20))


def test_ranking_nomeia_pelo_maior_membro(con):
    rk = ranking_conglomerado(con, 202412, "consignado", top=2)
    assert rk[0][0] == "CONG_B" and rk[0][2] == pytest.approx(0.65)        # B lidera com 0.65
    assert rk[1][0] == "CONG_A" and rk[1][2] == pytest.approx(0.35)
    assert rk[1][1] == "Banco A Principal"                                  # nome = maior membro (300 > 50)
