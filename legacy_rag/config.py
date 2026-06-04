"""Configuração central do projeto (Caso B / consignado). Ver ADR-0002 e ADR-0003."""

from pathlib import Path

# --- Caminhos ---
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"                     # gitignored (dados auto-alimentados)
DUCKDB_PATH = DATA_DIR / "legacy.duckdb"     # store único: números + vetores + BM25/FTS

# --- Bacen / API Olinda (IF.data) ---
OLINDA_IFDATA_BASE = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata"
# Nível de consolidação correto para market share (ADR-0002): conglomerado prudencial.
TIPO_INSTITUICAO_CONGLOMERADO_PRUDENCIAL = 1

# --- Modelos open/free (ADR-0003) ---
EMBED_MODEL = "BAAI/bge-m3"               # embeddings multilíngues (ótimo p/ PT), 1024 dims
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"  # reranker multilíngue

# --- Escopo: bancos do núcleo (ADR-0002) ---
# cnpj_raiz/identificadores verificados; cod_inst do IF.data A CONFIRMAR na ingestão.
BANKS = {
    "BB":       {"nome": "Banco do Brasil", "ticker": "BBAS3", "id_bacen": "COMPE 001 / ISPB 00000000", "cod_inst": None},
    "Bradesco": {"nome": "Bradesco",        "ticker": "BBDC4", "id_bacen": "CNPJ raiz 60746948",        "cod_inst": None},
    "Itau":     {"nome": "Itaú Unibanco",   "ticker": "ITUB4", "id_bacen": "CNPJ raiz 60872504",        "cod_inst": None},
}

# Banco usado como NÃO-RESPONDÍVEL orgânico (USD/IFRS via 20-F — incomparável; ADR-0002).
NON_ANSWERABLE_BANK = {"nome": "Nu Holdings (Nubank)", "motivo": "USD/IFRS via Form 20-F — base contábil/moeda incomparável"}

# Modalidade de crédito no foco do case.
MODALIDADE_FOCO = "consignado"
