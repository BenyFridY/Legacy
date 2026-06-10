"""Auditoria da base estruturada: tabelas, calculo do share e alinhamento de periodos.

Uso:  python scripts/auditar_base.py     (PYTHONPATH=. ; le a base real em read-only)

10 checagens, cada uma imprime [OK]/[ALERTA] + evidencia: periodos completos, modalidades,
continuidade do denominador na virada de fonte 2024->2025, share recomputado por SQL INDEPENDENTE
(formulacao diferente da do sistema), confronto com as series registradas nos docs, orfaos de
cadastro, unidade do saldo (IF.data x release), qualidade (NULL/negativo), continuidade por banco
e top-10 do sistema (quem fica fora da cobertura). Resultados de 10/06/2026: resultados-eval.md §6.
"""
import duckdb

from legacy_rag.config import DUCKDB_PATH, ENTIDADES, MODALIDADES
from legacy_rag.structured.store import market_share_conglomerado_serie

con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
MOD_CONSIG = next(nome for nome, aliases in MODALIDADES if "consignado" in aliases)
print("modalidade-chave consignado ->", MOD_CONSIG)

print("\n=== 1) Periodos: linhas, instituicoes, saldo total ===")
rows = con.execute("""
    SELECT ano_mes, COUNT(*) n, COUNT(DISTINCT cod_inst) inst, SUM(saldo) total
    FROM carteira_pf GROUP BY ano_mes ORDER BY ano_mes
""").fetchall()
for am, n, inst, tot in rows:
    print(f"  {am}: {n:>5} linhas  {inst:>4} inst  saldo total {tot:>22,.0f}")
esperados = [202309, 202312, 202403, 202406, 202409, 202412, 202503, 202506, 202509, 202512]
tem = [r[0] for r in rows]
print("  [OK] 10 trimestres 2023T3..2025T4" if tem == esperados else f"  [ALERTA] periodos: {tem}")

print("\n=== 2) Modalidades na base x config ===")
mods_base = {m for (m,) in con.execute("SELECT DISTINCT modalidade FROM carteira_pf").fetchall()}
for m in sorted(mods_base):
    print("  ", m)
print("  [OK] modalidades do config presentes" if all(nome in mods_base for nome, _ in MODALIDADES)
      else "  [ALERTA] modalidade do config ausente da base")

print("\n=== 3) Denominador (sistema) em consignado: continuidade QoQ ===")
sis = con.execute("""
    SELECT ano_mes, SUM(saldo) FROM carteira_pf WHERE modalidade = ?
    GROUP BY ano_mes ORDER BY ano_mes
""", [MOD_CONSIG]).fetchall()
ant = None
salto = False
for am, tot in sis:
    var = "" if ant is None else f"{(tot/ant-1)*100:+6.1f}% QoQ"
    if ant is not None and abs(tot / ant - 1) > 0.15:
        var += "  <-- SALTO >15% (suspeita de dupla contagem/fonte trocada)"
        salto = True
    print(f"  {am}: {tot:>22,.0f}  {var}")
    ant = tot
print("  [ALERTA] ha salto no denominador" if salto else "  [OK] denominador continuo (sem salto >15%), inclusive na virada 2024->2025")

print("\n=== 4) Share recomputado por SQL independente x funcao do sistema ===")
max_diff = 0.0
for banco, info in ENTIDADES.items():
    prud = info.get("cod_prudencial")
    if not prud:
        continue
    oficial = dict(market_share_conglomerado_serie(con, prud, MOD_CONSIG))
    # formulacao independente: subqueries escalares por periodo, sem CTE/join
    for am in [a for a, _ in sis]:
        manual = con.execute("""
            SELECT (SELECT COALESCE(SUM(c.saldo),0) FROM carteira_pf c
                     LEFT JOIN cadastro k ON c.cod_inst=k.cod_inst AND c.ano_mes=k.ano_mes
                     WHERE c.modalidade=? AND c.ano_mes=? AND COALESCE(k.cod_prudencial,c.cod_inst)=?)
                 / (SELECT SUM(saldo) FROM carteira_pf WHERE modalidade=? AND ano_mes=?)
        """, [MOD_CONSIG, am, prud, MOD_CONSIG, am]).fetchone()[0]
        if am in oficial:
            max_diff = max(max_diff, abs(manual - oficial[am]))
        elif manual and manual > 0:
            print(f"  [ALERTA] {banco} {am}: funcao nao devolve ponto, mas manual da {manual:.4f}")
print(f"  max |manual - funcao| = {max_diff:.2e}", "[OK]" if max_diff < 1e-12 else "[ALERTA]")

print("\n=== 5) Confronto com os numeros REGISTRADOS nos docs ===")
doc_bb = {202309: 19.9, 202312: 20.2, 202403: 20.3, 202406: 20.3, 202409: 20.5,
          202412: 20.1, 202503: 19.8, 202506: 19.8, 202509: 19.5, 202512: 19.2}
serie_bb = dict(market_share_conglomerado_serie(con, ENTIDADES["BB"]["cod_prudencial"], MOD_CONSIG))
err = [(am, round(serie_bb[am]*100, 1), doc_bb[am]) for am in doc_bb if round(serie_bb[am]*100, 1) != doc_bb[am]]
print("  BB consignado (10 pts) ==", "doc [OK]" if not err else f"DIVERGE: {err}")
MOD_CARTAO = next(nome for nome, aliases in MODALIDADES if "cartao" in aliases)
doc_nu = {202309: 11.1, 202312: 12.0, 202403: 12.9, 202406: 13.1, 202409: 13.2,
          202412: 12.6, 202503: 13.4, 202506: 14.2, 202509: 14.8, 202512: 14.9}
serie_nu = dict(market_share_conglomerado_serie(con, ENTIDADES["Nubank"]["cod_prudencial"], MOD_CARTAO))
err2 = [(am, round(serie_nu[am]*100, 1), doc_nu[am]) for am in doc_nu if round(serie_nu[am]*100, 1) != doc_nu[am]]
print("  Nubank cartao (10 pts) ==", "doc [OK]" if not err2 else f"DIVERGE: {err2}")

print("\n=== 6) Orfaos de cadastro (pre-2025, onde o mapeamento depende do cadastro) ===")
for am in [a for a in tem if a < 202501]:
    orf, saldo_orf, tot = con.execute("""
        SELECT COUNT(*), COALESCE(SUM(CASE WHEN k.cod_inst IS NULL THEN c.saldo END),0), SUM(c.saldo)
        FROM carteira_pf c LEFT JOIN cadastro k ON c.cod_inst=k.cod_inst AND c.ano_mes=k.ano_mes
        WHERE c.ano_mes=?
    """, [am]).fetchone()
    n_orf = con.execute("""
        SELECT COUNT(DISTINCT c.cod_inst) FROM carteira_pf c
        LEFT JOIN cadastro k ON c.cod_inst=k.cod_inst AND c.ano_mes=k.ano_mes
        WHERE c.ano_mes=? AND k.cod_inst IS NULL
    """, [am]).fetchone()[0]
    pct = saldo_orf / tot * 100 if tot else 0
    flag = "[OK]" if pct < 1 else "[ALERTA]"
    print(f"  {am}: {n_orf} inst sem cadastro, {pct:.2f}% do saldo  {flag}")

print("\n=== 7) Unidade do saldo (IF.data x release) ===")
itau = ENTIDADES["Itau"]["cod_prudencial"]
saldo_itau = con.execute("""
    SELECT SUM(c.saldo) FROM carteira_pf c
    LEFT JOIN cadastro k ON c.cod_inst=k.cod_inst AND c.ano_mes=k.ano_mes
    WHERE c.modalidade=? AND c.ano_mes=202512 AND COALESCE(k.cod_prudencial,c.cod_inst)=?
""", [MOD_CONSIG, itau]).fetchone()[0]
print(f"  Itau consignado 2025-12 (IF.data): {saldo_itau:,.0f} (release gerencial: R$ 75,3 bi)")
print(f"  se unidade = R$: {saldo_itau/1e9:,.1f} bi | se R$ mil: {saldo_itau/1e6:,.1f} bi")

print("\n=== 8) Qualidade: nulos / negativos / zeros ===")
nn, neg, zer = con.execute("""
    SELECT SUM(CASE WHEN saldo IS NULL THEN 1 ELSE 0 END),
           SUM(CASE WHEN saldo < 0 THEN 1 ELSE 0 END),
           SUM(CASE WHEN saldo = 0 THEN 1 ELSE 0 END) FROM carteira_pf
""").fetchone()
print(f"  NULL={nn} negativos={neg} zeros={zer}", "[OK]" if not nn and not neg else "[ALERTA]")

print("\n=== 9) Continuidade dos 5 bancos (consignado: 10 pontos cada?) ===")
for banco, info in ENTIDADES.items():
    prud = info.get("cod_prudencial")
    if not prud:
        continue
    s = market_share_conglomerado_serie(con, prud, MOD_CONSIG)
    print(f"  {banco:<10} {len(s):>2} pontos consignado", "[OK]" if len(s) == 10 else "(ver: pode nao operar a modalidade)")

print("\n=== 10) Top-10 do sistema em consignado 2025-12 (quem fica FORA dos 5 cobertos?) ===")
from legacy_rag.structured.store import ranking_conglomerado
for cod, nome, sh in ranking_conglomerado(con, 202512, MOD_CONSIG, top=10):
    print(f"  {sh*100:5.1f}%  {nome[:60]}")
