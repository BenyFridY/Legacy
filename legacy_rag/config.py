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

# Modalidade-FOCO do caso (default quando a pergunta NÃO nomeia o produto): consignado.
# A STRING é a que o Bacen usa e fica gravada em carteira_pf.modalidade -> é a CHAVE DE CONSULTA
# (tem que casar com o DB). "consignado" é só o apelido de EXIBIÇÃO (ROTULOS_MODALIDADE).
MODALIDADE_FOCO = "Empréstimo com Consignação em Folha"

# Detecção de MODALIDADE pela pergunta -> nome canônico do Bacen. O motor de cálculo (SQL) é
# GENÉRICO: computa a fatia de QUALQUER banco em QUALQUER modalidade; o roteador só escolhe a
# modalidade pela palavra na pergunta. Ordem IMPORTA ("sem consignação" antes de "consignação").
# Sem match -> MODALIDADE_FOCO. As palavras já chegam SEM acento (o roteador normaliza).
MODALIDADES = [
    ("Cartão de Crédito",                    ["cartao", "cartoes"]),
    ("Empréstimo sem Consignação em Folha",  ["sem consignacao", "credito pessoal", "emprestimo pessoal"]),
    ("Empréstimo com Consignação em Folha",  ["consignado", "consignacao"]),
    ("Habitação",                            ["habitacao", "imobiliario", "habitacional",
                                              "casa propria", "moradia", "minha casa minha vida"]),
    ("Veículos",                             ["veiculo", "veiculos", "automovel", "automoveis",
                                              "carro", "carros", "automotivo", "automotiva"]),
    ("Rural e Agroindustrial",               ["rural", "agroindustrial", "agronegocio", "agro",
                                              "agricultura", "agricola", "agropecuaria"]),
    ("Outros Créditos",                      ["outros creditos"]),
]

# Sub-recortes que aparecem nos RELEASES dos bancos mas NÃO existem na granularidade do IF.data
# (carteira PF, que só separa nos 7 baldes acima). Pedir o NÚMERO/share de um destes é fora de
# cobertura -> recusa honesta (R7), apontando a modalidade-pai (SQL) ou o release (texto). As palavras
# chegam SEM acento (o roteador normaliza). NÃO recusa quando a pergunta é DECLARADA (texto): o release
# pode citar o sub-produto — ver _gate_escopo/R7. Curado conservador (alta precisão, baixo falso-positivo).
SUBPRODUTOS_FORA_IFDATA = [
    "inss", "siape", "consignado privado", "consignado publico",   # consignado por tipo de empregador
    "cheque especial", "rotativo",                                  # sub-linhas de cartão/cheque
    "capital de giro", "desconto de duplicata", "antecipacao de recebiveis",  # crédito PJ (nem é PF)
    "fies", "estudantil", "consorcio", "leasing", "home equity", "crediario",
]

# Texto legível dos 7 baldes do IF.data, para a mensagem de recusa R7.
MODALIDADES_IFDATA_TXT = "cartão, consignado, crédito pessoal, habitação, veículos, rural e outros"

ROTULOS_MODALIDADE = {        # nome técnico do Bacen -> apelido legível p/ exibição
    "Empréstimo com Consignação em Folha": "consignado",
    "Empréstimo sem Consignação em Folha": "crédito pessoal (sem consignação)",
    "Cartão de Crédito":                   "cartão de crédito",
    "Habitação":                           "habitação / imobiliário",
    "Veículos":                            "veículos",
    "Rural e Agroindustrial":              "rural e agroindustrial",
    "Outros Créditos":                     "outros créditos",
}

# --- Conhecimento que o ROTEADOR precisa sobre cada entidade (ADR-0005) ---
# base_contabil: "cosif" (Bacen/BRL, comparável entre si) | "ifrs" (USD/20-F, incomparável p/ guidance/PDD)
# tem_verbatim:  existe transcrição VERBATIM oficial citável na base? (só Bradesco no núcleo)
# aliases:       formas como a entidade aparece nas perguntas (tudo minúsculo, sem depender de acento)
# Inclui Nubank e Santander porque o estruturado os INGERE (ADR-0004) — o roteador não recusa pelo nome:
# share em Cosif (IF.data) é respondível para todos; só o CRUZAMENTO de base contábil recusa.
# cod_prudencial = código do Conglomerado Prudencial no IF.data (agrega os vários CNPJs do banco).
# Verificado ao vivo contra o IfDataCadastro (AnoMes=202412); usado p/ market share por banco.
# Nubank também tem cod_prudencial (C0084693, verificado ao vivo): o caminho de NÚMEROS responde
# share dele em qualquer modalidade (ex.: cartão); só o cruzamento de base contábil (R2) é que recusa.
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
                  "cod_prudencial": "C0084693", "aliases": ["nubank", "nu holdings", "nu pagamentos", "roxinho"]},
}

# Cobertura temporal da base (ADR-0004): realizado até 4T25; guidance publicado vai até 2026.
# Pergunta sobre ANO > este valor é período futuro/inexistente -> recusa (regra R1 do roteador).
ANO_COBERTURA_MAX = 2026

# Limiar do GATE DE EVIDÊNCIA (Estágio 2): nota do reranker (0–1, normalizada) abaixo disto ->
# recusa "não disponível na base". CALIBRADO (não mais placeholder): a varredura contra o mini-gold
# (eval/gate_gold.yaml; rode scripts/calibrar_gate.py) mostrou respondíveis ~0,72 e fora-da-base
# ~0,50, com o "joelho" (0% over-recusa, 0% vazamento) em ~0,60. O 0,30 antigo deixava 100% das
# fora-da-base passarem. Banda segura medida ~[0,60; 0,71]; escolhido 0,60. Ver ADR-0005.
LIMIAR_EVIDENCIA_PADRAO = 0.60

# Limiar de DISCRIMINAÇÃO DO RERANKER: se o desvio-padrão das notas do cross-encoder fica ABAIXO
# disto, ele "não está decidindo" (notas achatadas = ruído) -> caímos de volta para a ORDEM DO RRF
# em vez de reordenar por ruído. CALIBRADO (scripts/calibrar_discrimina_rerank.py): as notas se
# separam em DOIS grupos com um vão no meio — "achatado" (pstdev <= 0,048) e "discrimina"
# (pstdev >= 0,072); o 0,05 cai no vão. NÃO é detector de dificuldade (uma sondagem FÁCIL também
# pode achatar — e aí manter o RRF é inócuo, ele já estava no topo); é uma REDE DE SEGURANÇA contra
# reordenar por ruído. Ver retrieval/rerank.py e ADR-0005.
LIMIAR_DISCRIMINA_RERANK = 0.05
