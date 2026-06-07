"""Configuração central do projeto (Caso B / consignado). Ver ADR-0002 e ADR-0003."""

from pathlib import Path

# --- Caminhos ---
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"                     # gitignored (dados auto-alimentados)
DUCKDB_PATH = DATA_DIR / "legacy.duckdb"     # store único: números + vetores + BM25/FTS

# --- Bacen / API Olinda (IF.data) ---
OLINDA_IFDATA_BASE = "https://olinda.bcb.gov.br/olinda/servico/IFDATA/versao/v1/odata"

# --- Modelos open/free (ADR-0003) ---
EMBED_MODEL = "BAAI/bge-m3"               # embeddings multilíngues (ótimo p/ PT), 1024 dims
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"  # reranker multilíngue

# Modalidade de crédito no foco do case.
# A STRING é a que o Bacen usa e que fica gravada em carteira_pf.modalidade -> é a CHAVE DE
# CONSULTA (tem que casar com o DB). "consignado" é só o apelido de EXIBIÇÃO (ROTULOS_MODALIDADE).
MODALIDADE_FOCO = "Empréstimo com Consignação em Folha"
ROTULOS_MODALIDADE = {MODALIDADE_FOCO: "consignado"}   # nome técnico do Bacen -> apelido legível

# --- Conhecimento que o ROTEADOR precisa sobre cada entidade (ADR-0005) ---
# base_contabil: "cosif" (Bacen/BRL, comparável entre si) | "ifrs" (USD/20-F, incomparável p/ guidance/PDD)
# tem_verbatim:  existe transcrição VERBATIM oficial citável na base? (só Bradesco no núcleo)
# aliases:       formas como a entidade aparece nas perguntas (tudo minúsculo, sem depender de acento)
# Inclui Nubank e Santander porque o estruturado os INGERE (ADR-0004) — o roteador não recusa pelo nome:
# share em Cosif (IF.data) é respondível para todos; só o CRUZAMENTO de base contábil recusa.
# cod_prudencial = código do Conglomerado Prudencial no IF.data (agrega os vários CNPJs do banco).
# Verificado ao vivo contra o IfDataCadastro (AnoMes=202412); usado p/ market share por banco.
# Nubank em consignado não é foco (núcleo é Cosif/consignado); cod_prudencial fica None até precisar.
ENTIDADES = {
    "BB":        {"nome": "Banco do Brasil",       "base_contabil": "cosif", "tem_verbatim": False,
                  "cod_prudencial": "C0080329", "aliases": ["banco do brasil", "bb", "bbas3"]},
    "Bradesco":  {"nome": "Bradesco",              "base_contabil": "cosif", "tem_verbatim": True,
                  "cod_prudencial": "C0080075", "aliases": ["bradesco", "bbdc4"]},
    "Itau":      {"nome": "Itaú Unibanco",         "base_contabil": "cosif", "tem_verbatim": False,
                  "cod_prudencial": "C0080099", "aliases": ["itau", "itaú", "itub4", "unibanco"]},
    "Santander": {"nome": "Santander Brasil",      "base_contabil": "cosif", "tem_verbatim": False,
                  "cod_prudencial": "C0080185", "aliases": ["santander"]},
    "Nubank":    {"nome": "Nu Holdings (Nubank)",  "base_contabil": "ifrs",  "tem_verbatim": False,
                  "cod_prudencial": None,       "aliases": ["nubank", "nu holdings", "nu pagamentos", "roxinho"]},
}

# Cobertura temporal da base (ADR-0004): realizado até 4T25; guidance publicado vai até 2026.
# Pergunta sobre ANO > este valor é período futuro/inexistente -> recusa (regra R1 do roteador).
ANO_COBERTURA_MAX = 2026

# Limiar do GATE DE EVIDÊNCIA (Estágio 2): nota do reranker (0–1, normalizada) abaixo disto ->
# recusa "não disponível na base". PLACEHOLDER a calibrar contra um mini-gold (varrer o "joelho"
# da curva over-recusa x alucinação); ver ADR-0005. Não é um valor sagrado — é um ponto de partida.
LIMIAR_EVIDENCIA_PADRAO = 0.30
