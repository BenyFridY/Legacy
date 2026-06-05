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

# --- Conhecimento que o ROTEADOR precisa sobre cada entidade (ADR-0005) ---
# base_contabil: "cosif" (Bacen/BRL, comparável entre si) | "ifrs" (USD/20-F, incomparável p/ guidance/PDD)
# tem_verbatim:  existe transcrição VERBATIM oficial citável na base? (só Bradesco no núcleo)
# aliases:       formas como a entidade aparece nas perguntas (tudo minúsculo, sem depender de acento)
# Inclui Nubank e Santander porque o estruturado os INGERE (ADR-0004) — o roteador não recusa pelo nome:
# share em Cosif (IF.data) é respondível para todos; só o CRUZAMENTO de base contábil recusa.
ENTIDADES = {
    "BB":        {"nome": "Banco do Brasil",       "base_contabil": "cosif", "tem_verbatim": False,
                  "aliases": ["banco do brasil", "bb", "bbas3"]},
    "Bradesco":  {"nome": "Bradesco",              "base_contabil": "cosif", "tem_verbatim": True,
                  "aliases": ["bradesco", "bbdc4"]},
    "Itau":      {"nome": "Itaú Unibanco",         "base_contabil": "cosif", "tem_verbatim": False,
                  "aliases": ["itau", "itaú", "itub4", "unibanco"]},
    "Nubank":    {"nome": "Nu Holdings (Nubank)",  "base_contabil": "ifrs",  "tem_verbatim": False,
                  "aliases": ["nubank", "nu holdings", "nu pagamentos", "roxinho"]},
    "Santander": {"nome": "Santander Brasil",      "base_contabil": "cosif", "tem_verbatim": False,
                  "aliases": ["santander"]},
}

# Cobertura temporal da base (ADR-0004): realizado até 4T25; guidance publicado vai até 2026.
# Pergunta sobre ANO > este valor é período futuro/inexistente -> recusa (regra R1 do roteador).
ANO_COBERTURA_MAX = 2026
