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


def carteira_por_modalidade(ano_mes: int, grupo: str = GRUPO_CONSIGNADO) -> dict[str, float]:
    """Saldo da carteira PF de uma modalidade, por instituição, num período (AAAAMM).

    Retorna {cod_inst: saldo} usando a coluna 'Total' do grupo (modalidade). Usa o nível
    conglomerado financeiro (Tipo 2), onde o Bacen abre a carteira por modalidade.
    """
    url = (f"{OLINDA_IFDATA_BASE}/IfDataValores"
           "(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)"
           f"?@AnoMes={ano_mes}&@TipoInstituicao={TIPO_PF_MODALIDADE}"
           f"&@Relatorio='{RELATORIO_PF_MODALIDADE}'&$top=100000&$format=json")
    saldos: dict[str, float] = {}
    for row in _get_json(url).get("value", []):
        if (row.get("Grupo") == grupo
                and row.get("NomeColuna") == COLUNA_TOTAL
                and row.get("Saldo") is not None):
            saldos[row["CodInst"]] = float(row["Saldo"])
    return saldos


def cadastro_instituicoes(ano_mes: int) -> dict[str, str]:
    """Mapa {cod_inst: nome da instituição} no período. Assinatura confirmada via $metadata:
    IfDataCadastro(AnoMes: Edm.Int32). Os campos incluem NomeInstituicao, CnpjInstituicaoLider
    e CodConglomeradoPrudencial.

    NOTA (verificado em 2026-06-04): este endpoint está retornando HTTP 500 no servidor do
    Bacen — testado com alias e inline, JSON e XML, e múltiplos períodos, sempre 500, enquanto
    IfDataValores e ListaDeRelatorio respondem normalmente. É uma falha upstream. A implementação
    está correta e volta a funcionar quando o endpoint for restabelecido; até lá, degrada para {}
    (o market share opera por CodInst, que não depende do nome).
    """
    url = (f"{OLINDA_IFDATA_BASE}/IfDataCadastro(AnoMes=@AnoMes)"
           f"?@AnoMes={ano_mes}&$format=json")
    try:
        linhas = _get_json(url).get("value", [])
    except urllib.error.URLError as e:
        code = getattr(e, "code", "?")
        print(f"[bacen] IfDataCadastro indisponível (HTTP {code}); seguindo por CodInst.")
        return {}
    return {row["CodInst"]: (row.get("NomeInstituicao") or "").strip() for row in linhas}
