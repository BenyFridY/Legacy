"""Ingere o Relatório de Análise Econômica e Financeira (RAEF) 4T25 do BRADESCO na base de texto.

Desbloqueia o Caso B3 ao vivo (declarado × computado): a p.41 do RAEF traz a tabela de market
share, com o **crédito consignado declarado pelo próprio Bradesco** (14,1% 4T25 / 14,2% 3T25 /
14,3% 4T24). O lado COMPUTADO, independente, vem do Bacen IF.data (~14,0% no 4T24) — e os dois
batem. URL do CDN mziq confirmada (HTTP 200, ~5,8 MB, 222 pp, %PDF).

Idempotente por (banco, período, tipo_doc): rodar de novo não duplica.
Rodar:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/ingerir_bradesco.py
"""
from legacy_rag.torch_env import preparar_torch  # torch ANTES de numpy/duckdb (Windows/conda)

preparar_torch()

import sys

sys.stdout.reconfigure(encoding="utf-8")

from legacy_rag.config import DUCKDB_PATH
from legacy_rag.index.embed import BGEM3Encoder
from legacy_rag.ingestion.ingerir import ingerir_release
from legacy_rag.structured.store import conectar

URL_BRADESCO_RAEF_4T25 = (
    "https://filemanager-cdn.mziq.com/published/80f2e993-0a30-421a-9470-a4d5c8ad5e9f/"
    "b21ae9be-8683-4e11-94c9-478a1eea4f9f_relatorio_de_analise_economica_e_financeira_4t25.pdf"
)


def main():
    con = conectar(str(DUCKDB_PATH))
    encoder = BGEM3Encoder()
    print(">>> Ingerindo Bradesco RAEF 4T25 (baixa ~5,8MB, embeda ~3min CPU)...")
    n = ingerir_release(con, URL_BRADESCO_RAEF_4T25, banco="Bradesco", periodo="4T25",
                        tipo_doc="release", encoder=encoder)
    print(f">>> {n} fichas gravadas para Bradesco 4T25.")
    por_banco = con.execute(
        "SELECT banco, COUNT(*) FROM chunks GROUP BY banco ORDER BY banco").fetchall()
    print("Chunks por banco:", {b: c for b, c in por_banco})


if __name__ == "__main__":
    main()
