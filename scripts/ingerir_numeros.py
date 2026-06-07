"""Camada de ingestao dos NUMEROS (Bacen IF.data) — a "base ligada" do caminho estruturado.

Abastece o DuckDB SOZINHO a partir da fonte publica (API Olinda do Bacen), de forma
REPRODUZIVEL e idempotente (regrava por periodo, nunca duplica):
  - carteira_pf : carteira de credito PF por instituicao e modalidade (todas as modalidades).
  - cadastro    : CodInst -> nome + conglomerado prudencial (para nomear e AGREGAR os CNPJs).

Com as duas, o market share por banco sai em SQL (carteira do conglomerado / sistema).
A carteira so e rebaixada para periodos AUSENTES (economiza rede); o cadastro e (re)carregado
sempre (e barato e estava vazio). Rode quando quiser atualizar a base:
  set PYTHONPATH=. & python scripts/ingerir_numeros.py
"""
from legacy_rag.config import DUCKDB_PATH, MODALIDADE_FOCO
from legacy_rag.structured.store import (
    carregar_cadastro,
    carregar_periodo,
    conectar,
)

# Janela trimestral coberta (IF.data e trimestral). Ajuste aqui para ampliar o historico.
# A partir de 2025 (Res. 4.966/IFRS9) a carteira por modalidade migrou de Tipo=2 p/ Tipo=1 no
# IF.data -> tratado em bacen._tipo_instituicao; por isso 2025 ja entra normalmente aqui.
PERIODOS = [202309, 202312, 202403, 202406, 202409, 202412, 202503, 202506, 202509, 202512]


def main():
    con = conectar(str(DUCKDB_PATH))
    presentes = {r[0] for r in con.execute(
        "SELECT DISTINCT ano_mes FROM carteira_pf").fetchall()}

    for am in PERIODOS:
        try:  # uma queda transitoria do Bacen num periodo nao aborta o resto (base preservada)
            if am in presentes:
                print(f"  carteira {am}: ja presente, pulando")
            else:
                print(f"  carteira {am}: {carregar_periodo(con, am)} linhas")
            print(f"  cadastro {am}: {carregar_cadastro(con, am)} instituicoes")
        except Exception as e:  # noqa: BLE001
            print(f"  [falha em {am}: {type(e).__name__}: {e} -> pulando este periodo]")

    total_cad = con.execute("SELECT COUNT(*) FROM cadastro").fetchone()[0]
    print(f">>> Pronto. cadastro: {total_cad} linhas; modalidade foco: {MODALIDADE_FOCO}")


if __name__ == "__main__":
    main()
