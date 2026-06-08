"""Ingere o CORPUS de texto a partir do MANIFESTO (a "base ligada", reproduzivel).

Le corpus/manifesto.yaml e abastece o DuckDB SOZINHO — sem upload manual. Idempotente por
(banco, periodo, tipo_doc): rodar de novo PULA o que ja esta na base (so baixa/embeda o novo).
Por-documento try/except: uma fonte que cair (404/403/timeout) NAO aborta as outras.

Documentos heterogeneos de proposito (release longo, transcricao, sumario curto, nota; varios
bancos e periodos) -> provam o criterio de heterogeneidade (10%) e o caminho de escala.

Uso:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/ingerir_corpus.py
"""
import sys

from legacy_rag.torch_env import preparar_torch
preparar_torch()                       # torch ANTES de numpy/duckdb (conflito OpenMP/DLL no Windows)

import yaml

from legacy_rag.config import DUCKDB_PATH, ROOT
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.index.store_texto import garantir_schema
from legacy_rag.ingestion.ingerir import ingerir_release
from legacy_rag.structured.store import conectar

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MANIFESTO = ROOT / "corpus" / "manifesto.yaml"


def _ja_ingerido(con, banco: str, periodo: str, tipo: str) -> int:
    return con.execute("SELECT COUNT(*) FROM chunks WHERE banco=? AND periodo=? AND tipo_doc=?",
                       [banco, periodo, tipo]).fetchone()[0]


def main() -> None:
    docs = yaml.safe_load(MANIFESTO.read_text(encoding="utf-8"))["documentos"]
    con = conectar(str(DUCKDB_PATH))
    garantir_schema(con)
    encoder = BGEM3Encoder()
    print(f">>> Manifesto: {len(docs)} documento(s).")

    novos = pulados = falhas = 0
    for d in docs:
        chave = f"{d['banco']} {d['periodo']} [{d['tipo_doc']}]"
        try:
            ja = _ja_ingerido(con, d["banco"], d["periodo"], d["tipo_doc"])
            if ja:
                print(f"  = PULA {chave}: ja na base ({ja} fichas).")
                pulados += 1
                continue
            print(f"  + INGERE {chave}: {d.get('fonte', '')}")
            n = ingerir_release(con, d["url"], d["banco"], d["periodo"], d["tipo_doc"], encoder)
            if n == 0:                  # baixou (200) mas SEM texto extraível (PDF-imagem) -> não é sucesso
                print("    ! 0 fichas: documento sem texto extraível (fonte degradada/imagem?) -> FALHA.")
                falhas += 1
                continue                # não conta como 'novo'; idempotência não fica presa em doc vazio
            print(f"    -> {n} fichas gravadas.")
            novos += 1
        except Exception as e:                              # uma fonte ruim nao derruba o resto
            print(f"  ! FALHA {chave}: {type(e).__name__}: {e}")
            falhas += 1

    print(f"\n>>> Resumo: {novos} ingerido(s), {pulados} pulado(s), {falhas} falha(s).")
    por = con.execute("SELECT banco, tipo_doc, COUNT(*) FROM chunks GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
    print("Fichas por (banco, tipo):")
    for b, t, c in por:
        print(f"  {b:12} {t:16} {c}")


if __name__ == "__main__":
    main()
