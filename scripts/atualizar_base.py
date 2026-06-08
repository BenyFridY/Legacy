"""atualizar_base.py — UM comando que "liga" a base (criterio nº1 do case), rodando LOCAL.

Voce executa quando quiser (nao precisa de servidor 24/7) e ele puxa da FONTE tudo que falta,
SEM upload manual e de forma IDEMPOTENTE: pula o que ja esta na base, baixa/embeda so o novo.
  1) NUMEROS  -> scripts/ingerir_numeros.py  (Bacen IF.data, por periodo)
  2) TEXTO    -> scripts/ingerir_corpus.py   (manifesto: baixa->chunk->embed->grava)
  3) VALIDA   -> cada doc de texto: o ANO dominante do conteudo bate com o PERIODO do rotulo?
                (pega "URL errada" como a que servia o RAEF 4T19 fingindo ser 3T25)

Uso:  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 &
      python scripts/atualizar_base.py
"""
import os
import subprocess
import sys

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSOS = [
    ("Numeros (Bacen IF.data)", "scripts/ingerir_numeros.py"),
    ("Texto (manifesto)", "scripts/ingerir_corpus.py"),
]


def _ano_esperado(periodo: str):
    if "T" in periodo:           # "3T25" -> 2025
        return 2000 + int(periodo.split("T")[1])
    if "-" in periodo:           # "2026-01" -> 2026
        return int(periodo.split("-")[0])
    return None


def validar_periodos() -> int:
    """Alerta se o ano dominante do TEXTO de um doc nao bate com o periodo do rotulo (URL errada)."""
    import duckdb
    from legacy_rag.config import DUCKDB_PATH
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    docs = con.execute("SELECT DISTINCT banco, periodo, tipo_doc FROM chunks ORDER BY 1, 2, 3").fetchall()
    alertas = 0
    for banco, periodo, tipo in docs:
        textos = con.execute("SELECT texto FROM chunks WHERE banco=? AND periodo=? AND tipo_doc=?",
                             [banco, periodo, tipo]).fetchall()
        blob = " ".join(t for (t,) in textos)
        counts = {ano: blob.count(str(ano)) for ano in range(2017, 2028)}
        dominante = max(counts, key=counts.get)
        esperado = _ano_esperado(periodo)
        ok = esperado is None or (abs(dominante - esperado) <= 1 and counts.get(esperado, 0) > 0)
        if not ok:
            alertas += 1
            print(f"  !! ALERTA: {banco} {periodo} [{tipo}] -> ano dominante {dominante} != esperado "
                  f"{esperado}. URL errada / doc do periodo errado?")
    print("  OK: todos os docs batem com seu periodo." if alertas == 0
          else f"  {alertas} doc(s) suspeito(s) acima — revise a URL no manifesto.")
    return alertas


def main() -> None:
    print("=" * 68)
    print("ATUALIZAR BASE — fetch idempotente de TODAS as fontes (sem upload manual)")
    print("=" * 68)
    for nome, script in PASSOS:
        print(f"\n>>> {nome}: {script}")
        env = {**os.environ, "PYTHONPATH": "."}
        r = subprocess.run([sys.executable, script], cwd=ROOT, env=env)
        if r.returncode != 0:
            print(f"  ! {nome} retornou codigo {r.returncode} — sigo para o proximo passo (nao aborta).")
    print("\n>>> Validacao de consistencia de periodo:")
    validar_periodos()
    print("\n>>> Base atualizada.")


if __name__ == "__main__":
    main()
