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

import http.client
import json
import time
import urllib.error
import urllib.request

from legacy_rag.config import OLINDA_IFDATA_BASE

# Coordenadas da carteira PF por modalidade (descobertas ao vivo).
# A QUEBRA de 2025 (Res. 4.966/IFRS9): até 2024 a carteira por modalidade vem no conglomerado
# FINANCEIRO (Tipo=2); de 2025 ela migrou para o conglomerado PRUDENCIAL (Tipo=1) — e ali o
# CodInst JÁ É o conglomerado prudencial (ex.: C0080329=BB), então nem precisa agregar via cadastro.
TIPO_PF_MODALIDADE = 2            # ≤ 2024
TIPO_PF_MODALIDADE_2025 = 1       # ≥ 2025 (verificado ao vivo: 202503+ só tem dado no Tipo=1)
ANO_MES_NOVO_LAYOUT = 202503      # primeiro período trimestral com o novo layout
RELATORIO_PF_MODALIDADE = 11
COLUNA_TOTAL = "Total"
PAGINA_ODATA = 100000            # tamanho de página do $top/$skip (respostas de 2025 passam disso)


def _tipo_instituicao(ano_mes: int) -> int:
    """Nível onde a carteira PF por modalidade é publicada (mudou em 2025, ver acima)."""
    return TIPO_PF_MODALIDADE_2025 if ano_mes >= ANO_MES_NOVO_LAYOUT else TIPO_PF_MODALIDADE

_HEADERS = {"User-Agent": "LegacyCase/0.1 (research; beny.frid@hashdex.com)"}


def _get_json(url: str, tentativas: int = 3) -> dict:
    """GET + JSON com retry. As respostas de 2025 (Tipo=1) são grandes (~26MB) e a conexão às
    vezes corta no meio (IncompleteRead) -> tenta de novo com backoff antes de desistir."""
    erro: Exception | None = None
    for i in range(max(1, tentativas)):   # sempre ≥1 tentativa (evita 'raise None' se tentativas<=0)
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=120) as resp:
                return json.load(resp)
        except (urllib.error.URLError, http.client.IncompleteRead, ConnectionError, TimeoutError) as e:
            erro = e
            time.sleep(2.0 * (i + 1))
    raise erro  # esgotou as tentativas -> propaga (cadastro_conglomerado degrada em URLError)


def carteira_pf_modalidades(ano_mes: int) -> list[dict]:
    """TODAS as modalidades de crédito PF (coluna 'Total'), por instituição, num período (AAAAMM).

    Retorna [{cod_inst, ano_mes, modalidade, saldo}]. "Ingestão larga" (ADR-0004): traz todas as
    modalidades (consignado, cartão, habitação, veículos, ...); o filtro por consignado é feito
    depois, no cálculo. Usa o nível conglomerado financeiro (Tipo 2), onde o Bacen abre por modalidade.
    """
    base = (f"{OLINDA_IFDATA_BASE}/IfDataValores"
            "(AnoMes=@AnoMes,TipoInstituicao=@TipoInstituicao,Relatorio=@Relatorio)"
            f"?@AnoMes={ano_mes}&@TipoInstituicao={_tipo_instituicao(ano_mes)}"
            f"&@Relatorio='{RELATORIO_PF_MODALIDADE}'&$format=json")
    # PAGINAÇÃO: algumas respostas de 2025 passam de 100k linhas (a API ECOA linhas duplicadas)
    # -> pagina com $skip até a página vir incompleta. dedup por (cod_inst, modalidade) colapsa as
    # cópias da linha "Total" (saldo idêntico; somar dobraria). Em ≤2024 cabe em 1 página -> sem efeito.
    por_chave: dict[tuple[str, str], dict] = {}
    skip = 0
    while True:
        rows = _get_json(f"{base}&$top={PAGINA_ODATA}&$skip={skip}").get("value", [])
        antes = len(por_chave)
        for row in rows:
            if (row.get("Grupo")
                    and row.get("NomeColuna") == COLUNA_TOTAL
                    and row.get("Saldo") is not None):
                por_chave[(row["CodInst"], row["Grupo"])] = {
                    "cod_inst": row["CodInst"],
                    "ano_mes": int(row["AnoMes"]),
                    "modalidade": row["Grupo"],
                    "saldo": float(row["Saldo"]),
                }
        # para na página incompleta OU se a página não trouxe NENHUMA chave nova (guarda contra
        # uma API que ignore $skip e devolva sempre a mesma página cheia -> não gira pra sempre).
        if len(rows) < PAGINA_ODATA or len(por_chave) == antes:
            break
        skip += PAGINA_ODATA
    return list(por_chave.values())


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
    except (urllib.error.URLError, http.client.IncompleteRead, ConnectionError, TimeoutError) as e:
        # mesmos tipos que _get_json pode propagar -> degrada para {} (cálculo por CodInst cru segue)
        print(f"[bacen] IfDataCadastro indisponível ({getattr(e, 'code', type(e).__name__)}); sem nomes/agregação.")
        return {}
    return {row["CodInst"]: {"nome": (row.get("NomeInstituicao") or "").strip(),
                             "prudencial": row.get("CodConglomeradoPrudencial") or row["CodInst"]}
            for row in linhas}
