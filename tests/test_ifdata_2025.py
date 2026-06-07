"""Adaptação da IF.data para 2025 (quebra IFRS9/Res. 4.966) — sem rede.

Cobre: o nível da carteira mudou (Tipo 2->1); em 2025 o cod_inst JÁ É o prudencial (share via
fallback); paginação + dedup das respostas grandes; e a ingestão NÃO apaga dados numa queda da fonte.
"""
import pytest

from legacy_rag.structured import bacen, store
from legacy_rag.structured.bacen import _tipo_instituicao, carteira_pf_modalidades
from legacy_rag.structured.store import (
    carregar_cadastro,
    carregar_periodo,
    conectar,
    market_share_conglomerado_serie,
)


# ---- a carteira por modalidade mudou de NÍVEL em 2025 (Tipo 2 -> Tipo 1)
def test_tipo_instituicao_muda_em_2025():
    assert _tipo_instituicao(202412) == 2      # ≤ 2024: conglomerado financeiro
    assert _tipo_instituicao(202503) == 1       # ≥ 2025: conglomerado prudencial
    assert _tipo_instituicao(202512) == 1


# ---- em 2025 o cod_inst JÁ É o prudencial (sem cadastro) -> share via COALESCE(cod_inst)
def test_share_2025_sem_cadastro_via_fallback():
    con = conectar(":memory:")
    con.executemany("INSERT INTO carteira_pf VALUES (?,?,?,?)", [
        ("C0080075", 202512, "consignado", 140.0),   # Bradesco prudencial DIRETO
        ("C0080329", 202512, "consignado", 200.0),
        ("C9999999", 202512, "consignado", 660.0),   # total 1000
    ])  # NÃO inserimos cadastro de propósito (em 2025 o cod já é prudencial)
    assert market_share_conglomerado_serie(con, "C0080075", "consignado") == [(202512, pytest.approx(0.14))]


# ---- série cruza as duas eras: 2024 (financeiro+cadastro) e 2025 (prudencial direto)
def test_share_cross_era():
    con = conectar(":memory:")
    con.executemany("INSERT INTO carteira_pf VALUES (?,?,?,?)", [
        ("C0010045", 202412, "consignado", 140.0), ("XXXX", 202412, "consignado", 860.0),  # 2024
        ("C0080075", 202512, "consignado", 138.0), ("YYYY", 202512, "consignado", 862.0),  # 2025
    ])
    con.execute("INSERT INTO cadastro VALUES ('C0010045', 202412, 'Bradesco', 'C0080075')")  # só 2024
    serie = market_share_conglomerado_serie(con, "C0080075", "consignado")
    assert serie == [(202412, pytest.approx(0.14)), (202512, pytest.approx(0.138))]


# ---- DELETE-safety: fonte vazia/instável NÃO apaga o que já existe
def test_carregar_periodo_vazio_preserva(monkeypatch):
    con = conectar(":memory:")
    con.execute("INSERT INTO carteira_pf VALUES ('A', 202412, 'consignado', 10.0)")
    monkeypatch.setattr(store, "carteira_pf_modalidades", lambda am: [])     # fonte caiu
    assert carregar_periodo(con, 202412) == 0
    assert con.execute("SELECT COUNT(*) FROM carteira_pf WHERE ano_mes=202412").fetchone()[0] == 1


def test_carregar_cadastro_vazio_preserva(monkeypatch):
    con = conectar(":memory:")
    con.execute("INSERT INTO cadastro VALUES ('A', 202412, 'Banco', 'CONG')")
    monkeypatch.setattr(store, "cadastro_conglomerado", lambda am: {})
    assert carregar_cadastro(con, 202412) == 0
    assert con.execute("SELECT COUNT(*) FROM cadastro WHERE ano_mes=202412").fetchone()[0] == 1


# ---- paginação + dedup: 2 páginas, com a linha "Total" ECOADA (duplicada) -> completo e sem dobrar
def test_carteira_pagina_e_deduplica(monkeypatch):
    monkeypatch.setattr(bacen, "PAGINA_ODATA", 3)   # página pequena p/ forçar a 2ª busca

    def fake_get(url):
        if "$skip=0" in url:                         # 3 cópias da MESMA linha (eco da API) == página cheia
            l = {"CodInst": "C1", "AnoMes": "202512", "Grupo": "consignado",
                 "NomeColuna": "Total", "Saldo": 10.0}
            return {"value": [dict(l), dict(l), dict(l)]}
        if "$skip=3" in url:                         # 2ª página: outra instituição
            return {"value": [{"CodInst": "C2", "AnoMes": "202512", "Grupo": "consignado",
                               "NomeColuna": "Total", "Saldo": 20.0}]}
        return {"value": []}

    monkeypatch.setattr(bacen, "_get_json", fake_get)
    por = {r["cod_inst"]: r["saldo"] for r in carteira_pf_modalidades(202512)}
    assert por == {"C1": 10.0, "C2": 20.0}           # paginou (achou C2) e deduplicou (C1 uma vez só)


def test_carteira_para_se_api_ignora_skip(monkeypatch):
    # API patológica: ignora $skip e devolve SEMPRE a mesma página cheia -> não pode girar pra sempre.
    monkeypatch.setattr(bacen, "PAGINA_ODATA", 2)
    linha = {"CodInst": "C1", "AnoMes": "202512", "Grupo": "consignado", "NomeColuna": "Total", "Saldo": 10.0}
    monkeypatch.setattr(bacen, "_get_json", lambda url: {"value": [dict(linha), dict(linha)]})
    linhas = carteira_pf_modalidades(202512)         # termina pela guarda de "nenhuma chave nova"
    assert [r["cod_inst"] for r in linhas] == ["C1"]
