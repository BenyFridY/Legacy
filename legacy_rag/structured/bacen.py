"""Cliente da API Olinda (IF.data) do Bacen — caminho dos números (ADR-0001/0004).

Estrutura descoberta explorando a API ao vivo:
- A carteira de crédito por MODALIDADE da Pessoa Física está em:
    TipoInstituicao = 2   (visão conglomerado financeiro; a prudencial=1 só traz 6 agregados)
    Relatório       = 11  ("Carteira de crédito ativa Pessoa Física - modalidade e prazo")
    Grupo           = a modalidade (ex.: "Empréstimo com Consignação em Folha" = consignado)
    NomeColuna      = "Total" (saldo total da modalidade; as outras colunas são faixas de prazo)
- Consignado = "Empréstimo com Consignação em Folha" (NÃO é "sem Consignação em Folha").
- O Saldo entra numa razão (market share), então a unidade cancela.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from legacy_rag.config import OLINDA_IFDATA_BASE

# Coordenadas da carteira PF por modalidade (descobertas ao vivo).
TIPO_PF_MODALIDADE = 2
RELATORIO_PF_MODALIDADE = 11
COLUNA_TOTAL = "Total"
GRUPO_CONSIGNADO = "Empréstimo com Consignação em Folha"

_HEADERS = {"User-Agent": "LegacyCase/0.1 (research; beny.frid@hashdex.com)"}


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def carteira_pf_modalidades(ano_mes: int) -> list[dict]:
    """TODAS as modalidades de crédito PF (coluna 'Total'), por instituição, num período (AAAAMM).

    Retorna [{cod_inst, ano_mes, modalidade, saldo}]. "Ingestão larga" (ADR-0004): traz todas as
    modalidades (consignado, cartão, habitação, veículos, ...); o filtro por consignado é feito
    depois, no cálculo. Usa o nível conglomerado financeiro (Tipo 2), onde o Bacen abre por modalidade.
    """
    url = (f"{OLINDA_IFDATA_BASE}/IfDataValores"
           "(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)"
           f"?@AnoMes={ano_mes}&@TipoInstituicao={TIPO_PF_MODALIDADE}"
           f"&@Relatorio='{RELATORIO_PF_MODALIDADE}'&$top=100000&$format=json")
    out: list[dict] = []
    for row in _get_json(url).get("value", []):
        if (row.get("Grupo")
                and row.get("NomeColuna") == COLUNA_TOTAL
                and row.get("Saldo") is not None):
            out.append({
                "cod_inst": row["CodInst"],
                "ano_mes": int(row["AnoMes"]),
                "modalidade": row["Grupo"],
                "saldo": float(row["Saldo"]),
            })
    return out


def carteira_por_modalidade(ano_mes: int, grupo: str = GRUPO_CONSIGNADO) -> dict[str, float]:
    """Saldo {cod_inst: saldo} de UMA modalidade num período (filtra carteira_pf_modalidades)."""
    return {r["cod_inst"]: r["saldo"]
            for r in carteira_pf_modalidades(ano_mes) if r["modalidade"] == grupo}


def cadastro_conglomerado(ano_mes: int) -> dict[str, dict]:
    """Mapa {cod_inst: {'nome', 'prudencial'}} no período, do IfDataCadastro.

    DESCOBERTA (2026-06-05): o endpoint voltou (HTTP 200) e — crucial — traz linhas com CodInst
    NUMÉRICO (= raiz de CNPJ, ex. '60746948' = Banco Bradesco S.A.), os MESMOS códigos da carteira
    (TipoInstituicao=2). Validado: 785/785 instituições da carteira casam aqui por CodInst. Cada
    linha dá NomeInstituicao + CodConglomeradoPrudencial, o que permite SOMAR o consignado por
    CONGLOMERADO (um banco grande = vários CNPJs) e nomear — ver store.market_share_conglomerado_serie.

    `prudencial` cai no próprio CodInst quando vazio (instituição independente). Degrada para {}
    se o endpoint voltar a falhar (o cálculo por CodInst cru ainda funciona, só sem agregação/nome).
    """
    url = f"{OLINDA_IFDATA_BASE}/IfDataCadastro(AnoMes=@AnoMes)?@AnoMes={ano_mes}&$format=json"
    try:
        linhas = _get_json(url).get("value", [])
    except urllib.error.URLError as e:
        print(f"[bacen] IfDataCadastro indisponível (HTTP {getattr(e, 'code', '?')}); sem nomes/agregação.")
        return {}
    return {row["CodInst"]: {"nome": (row.get("NomeInstituicao") or "").strip(),
                             "prudencial": row.get("CodConglomeradoPrudencial") or row["CodInst"]}
            for row in linhas}


def cadastro_instituicoes(ano_mes: int) -> dict[str, str]:
    """Mapa simples {cod_inst: nome} (atalho sobre cadastro_conglomerado)."""
    return {cod: info["nome"] for cod, info in cadastro_conglomerado(ano_mes).items()}
