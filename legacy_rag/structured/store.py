"""Store estruturado em DuckDB — a "base ligada" do caminho dos números (ADR-0001/0003).

Tabela `carteira_pf(cod_inst, ano_mes, modalidade, saldo)`: a ingestão do Bacen popula;
as consultas (market share, séries no tempo) leem. Persistente em DUCKDB_PATH (gitignored).
O market share é calculado em SQL — determinístico e auditável por re-execução.
"""
from __future__ import annotations

import re
from pathlib import Path

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
        path = str(DUCKDB_PATH)
    if path != ":memory:":
        # cria a pasta-pai (data/ é gitignored) p/ QUALQUER chamador — os scripts reais passam o path
        # explícito e caíam em IOException num clone fresco (3ª auditoria: o mkdir era código morto).
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(path)
    con.execute(SCHEMA)
    return con


def carregar_periodo(con: duckdb.DuckDBPyConnection, ano_mes: int) -> int:
    """Ingere todas as modalidades PF de um período no DuckDB (idempotente: regrava o período)."""
    linhas = carteira_pf_modalidades(ano_mes)
    if not linhas:        # fonte vazia/instável -> PRESERVA o que já existe (não deleta antes de ter o novo)
        return 0
    con.execute("DELETE FROM carteira_pf WHERE ano_mes = ?", [ano_mes])  # idempotente só quando há dado
    con.executemany(
        "INSERT INTO carteira_pf VALUES (?, ?, ?, ?)",
        [(r["cod_inst"], r["ano_mes"], r["modalidade"], r["saldo"]) for r in linhas],
    )
    return len(linhas)


def carregar_periodos(con: duckdb.DuckDBPyConnection, anos_meses: list[int]) -> dict[int, int]:
    """Ingere vários períodos. Retorna {ano_mes: nº de linhas}."""
    return {am: carregar_periodo(con, am) for am in anos_meses}


_RE_TRIMESTRE = re.compile(r"^\s*(\d{4})[Tt]([1-4])\s*$")


def _parse_trimestre(s: str) -> tuple[int, int]:
    """'2024T1' -> (2024, 1). Levanta ValueError em formato inválido."""
    m = _RE_TRIMESTRE.match(s)
    if not m:
        raise ValueError(f"trimestre invalido: {s!r} (use AAAATn, ex.: 2024T1)")
    return int(m.group(1)), int(m.group(2))


def trimestres_intervalo(de: str, ate: str) -> list[int]:
    """Expande um intervalo de trimestres em períodos YYYYMM (mês de FECHAMENTO do trimestre).

    Ex.: trimestres_intervalo("2024T1", "2025T4") ->
         [202403, 202406, 202409, 202412, 202503, 202506, 202509, 202512].
    Mapeamento T->mês: T1=03, T2=06, T3=09, T4=12 (o IF.data do Bacen é trimestral).
    Levanta ValueError se o formato for inválido ou se 'de' vier depois de 'ate'.
    """
    a0, q0 = _parse_trimestre(de)
    a1, q1 = _parse_trimestre(ate)
    ini, fim = a0 * 4 + (q0 - 1), a1 * 4 + (q1 - 1)   # índice linear de trimestres
    if ini > fim:
        raise ValueError(f"intervalo invertido: {de!r} vem depois de {ate!r}")
    periodos = []
    for n in range(ini, fim + 1):
        ano, q = divmod(n, 4)
        periodos.append(ano * 100 + (q + 1) * 3)      # q=0->mês 3 (T1) ... q=3->mês 12 (T4)
    return periodos


def _janela_sql(col: str, am_ini: int | None, am_fim: int | None) -> tuple[str, list[int]]:
    """Fragmento SQL + parâmetros do recorte de janela sobre a coluna `col` (YYYYMM).

    Suporta janela UNILATERAL: só am_ini (janela aberta, "desde X...") ou só am_fim ("...até X").
    Antes, am_fim=None descartava a janela INTEIRA — "desde 2024" devolvia a série desde o começo
    da base, e a variação saía com baseline errado (achado da auditoria final).
    """
    if am_ini is not None and am_fim is not None:
        return f"AND {col} BETWEEN ? AND ?", [am_ini, am_fim]
    if am_ini is not None:
        return f"AND {col} >= ?", [am_ini]
    if am_fim is not None:
        return f"AND {col} <= ?", [am_fim]
    return "", []


def market_share_serie(con: duckdb.DuckDBPyConnection, cod_inst: str, modalidade: str,
                       am_ini: int | None = None, am_fim: int | None = None) -> list[tuple[int, float]]:
    """Série [(ano_mes, share)] de UM CodInst (CNPJ) numa modalidade. share = saldo ÷ sistema, em SQL.

    `am_ini`/`am_fim` (YYYYMM) recortam a JANELA: o filtro entra no numerador E no denominador
    (sistema), para o share seguir = saldo/sistema do MESMO período. Janela unilateral suportada
    (só início = janela aberta; só fim). Sem janela -> série inteira.
    Atenção: por CNPJ cru, pode subestimar um banco que reporta em vários CNPJs — use
    market_share_conglomerado_serie para o share por banco (conglomerado).
    """
    j_sis, p_sis = _janela_sql("ano_mes", am_ini, am_fim)
    j_c, p_c = _janela_sql("c.ano_mes", am_ini, am_fim)
    q = f"""
        WITH sistema AS (
            SELECT ano_mes, SUM(saldo) AS total
            FROM carteira_pf WHERE modalidade = ? {j_sis} GROUP BY ano_mes
        )
        SELECT c.ano_mes, c.saldo / s.total AS share
        FROM carteira_pf c JOIN sistema s USING (ano_mes)
        WHERE c.modalidade = ? AND c.cod_inst = ? {j_c}
        ORDER BY c.ano_mes;
    """
    params = [modalidade, *p_sis, modalidade, cod_inst, *p_c]
    rows = con.execute(q, params).fetchall()
    return [(int(am), float(sh)) for am, sh in rows]


def carregar_cadastro(con: duckdb.DuckDBPyConnection, ano_mes: int) -> int:
    """Ingere o cadastro (CodInst -> nome + conglomerado prudencial) de um período. Idempotente."""
    mapa = cadastro_conglomerado(ano_mes)
    if not mapa:          # cadastro indisponível/vazio -> PRESERVA o existente (não apaga numa queda do Bacen)
        return 0
    con.execute("DELETE FROM cadastro WHERE ano_mes = ?", [ano_mes])  # idempotente só quando há dado
    con.executemany(
        "INSERT INTO cadastro VALUES (?, ?, ?, ?)",
        [(cod, ano_mes, info["nome"], info["prudencial"]) for cod, info in mapa.items()],
    )
    return len(mapa)


def market_share_conglomerado_serie(con: duckdb.DuckDBPyConnection, cod_prudencial: str,
                                    modalidade: str, am_ini: int | None = None,
                                    am_fim: int | None = None) -> list[tuple[int, float]]:
    """Série [(ano_mes, share)] de um BANCO (conglomerado prudencial) numa modalidade.

    Soma o saldo de TODOS os CNPJs do conglomerado (join carteira_pf x cadastro) e divide pelo
    sistema, por período. É o share "por banco" correto (não subestima quem usa vários CNPJs).
    `am_ini`/`am_fim` (YYYYMM) recortam a JANELA — aplicada ao numerador (conglomerado) E ao
    denominador (sistema), para o share seguir = saldo/sistema do MESMO período. Janela unilateral
    suportada (só início = janela aberta; só fim). Sem janela -> tudo.
    """
    j_sis, p_sis = _janela_sql("ano_mes", am_ini, am_fim)
    j_cong, p_cong = _janela_sql("c.ano_mes", am_ini, am_fim)
    q = f"""
        WITH sistema AS (
            SELECT ano_mes, SUM(saldo) AS total
            FROM carteira_pf WHERE modalidade = ? {j_sis} GROUP BY ano_mes
        ),
        cong AS (
            -- LEFT JOIN + COALESCE: até 2024 o cod_inst (financeiro) mapeia para o prudencial via
            -- cadastro; de 2025 o próprio cod_inst JÁ É o prudencial (sem cadastro) -> cai no fallback.
            SELECT c.ano_mes, SUM(c.saldo) AS saldo
            FROM carteira_pf c
            LEFT JOIN cadastro cad ON c.cod_inst = cad.cod_inst AND c.ano_mes = cad.ano_mes
            WHERE c.modalidade = ? AND COALESCE(cad.cod_prudencial, c.cod_inst) = ? {j_cong}
            GROUP BY c.ano_mes
        )
        SELECT cong.ano_mes, cong.saldo / s.total AS share
        FROM cong JOIN sistema s USING (ano_mes)
        ORDER BY cong.ano_mes;
    """
    params = [modalidade, *p_sis, modalidade, cod_prudencial, *p_cong]
    rows = con.execute(q, params).fetchall()
    return [(int(am), float(sh)) for am, sh in rows]


def ranking_conglomerado(con: duckdb.DuckDBPyConnection, ano_mes: int, modalidade: str,
                         top: int = 10) -> list[tuple[str, str, float]]:
    """Top conglomerados por share numa modalidade/período: [(cod_prudencial, nome, share)].

    Nome = o do MAIOR membro do conglomerado (arg_max em SQL). Para inspeção e apresentação.
    """
    q = """
        SELECT COALESCE(cad.cod_prudencial, c.cod_inst) AS prudencial,
               arg_max(COALESCE(NULLIF(cad.nome, ''), c.cod_inst), c.saldo) AS nome,
               SUM(c.saldo) / (SELECT SUM(saldo) FROM carteira_pf WHERE modalidade = ? AND ano_mes = ?) AS share
        FROM carteira_pf c
        LEFT JOIN cadastro cad ON c.cod_inst = cad.cod_inst AND c.ano_mes = cad.ano_mes
        WHERE c.modalidade = ? AND c.ano_mes = ?
        GROUP BY COALESCE(cad.cod_prudencial, c.cod_inst)
        ORDER BY share DESC
        LIMIT ?;
    """
    rows = con.execute(q, [modalidade, ano_mes, modalidade, ano_mes, top]).fetchall()
    return [(cod, nome, float(sh)) for cod, nome, sh in rows]
