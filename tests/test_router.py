"""Testes do roteador determinístico (sem rede, sem modelo).

Dois blocos:
  (1) AS 12 PERGUNTAS DO EVAL — cada uma deve cair na categoria certa e no comportamento
      (answer/refuse) que o eval/questions.yaml espera.
  (2) CASOS-FRONTEIRA levantados pelos críticos adversariais — provam que as armadilhas
      (over-refusal do Nubank/Santander; verbatim x paráfrase; futuro sutil) estão tratadas.
"""

import pytest

from legacy_rag.router.router import rotear


# (1) ---------------------------------------------------------------- as 12 do eval
# (id, pergunta, categoria_esperada, deve_recusar)
DOZE = [
    ("bradesco-tom-macro-3t25",
     "Qual o tom do Bradesco sobre a economia brasileira e o crédito na teleconferência de "
     "resultados do 3T25?", "doc_unico", False),
    ("bb-custo-credito-realizado-2025",
     "Qual foi o custo do crédito realizado pelo Banco do Brasil em 2025?", "doc_unico", False),
    ("itau-guidance-custo-credito-2026",
     "Qual a faixa de guidance de custo de crédito do Itaú para 2026?", "doc_unico", False),
    ("bradesco-share-consignado-declarado",
     "Qual market share de consignado o CEO do Bradesco declarou na teleconferência de resultados?",
     "doc_unico", False),
    ("bb-guidance-vs-realizado-2025",
     "O guidance de custo de crédito do BB para 2025 se confirmou no realizado do ano?",
     "multi_fonte", False),
    ("bradesco-share-declarado-vs-computado",
     "O market share de consignado do Bradesco computado a partir do IF.data confirma o ~14,2% "
     "que o CEO declarou?", "multi_fonte", False),
    ("itau-estrategia-clt-vs-share-real",
     "O Itaú declarou crescer em consignado privado (CLT). O market share dele em consignado subiu "
     "nos trimestres seguintes, segundo o IF.data?", "multi_fonte", False),
    ("bb-share-consignado-trajetoria",
     "Como evoluiu o market share do Banco do Brasil em consignado nos últimos quatro trimestres?",
     "computada", False),
    ("nubank-vs-itau-guidance-pdd",
     "Compare o guidance de custo de crédito do Nubank com o do Itaú.", "nao_respondivel", True),
    ("bradesco-custo-credito-futuro",
     "Qual será o custo de crédito do Bradesco no 2º trimestre de 2027?", "nao_respondivel", True),
    ("itau-citacao-verbatim-inexistente",
     "Cite a frase literal do CEO do Itaú na teleconferência do 4T25 sobre consignado.",
     "nao_respondivel", True),
    ("nubank-share-cartao-respondivel",
     "Qual o market share do Nubank em cartão de crédito, segundo o IF.data?", "computada", False),
]


@pytest.mark.parametrize("qid,pergunta,categoria,recusa", DOZE, ids=[q[0] for q in DOZE])
def test_roteamento_das_12(qid, pergunta, categoria, recusa):
    r = rotear(pergunta)
    assert r.categoria == categoria, f"{qid}: esperava {categoria}, veio {r.categoria} ({r.motivo_recusa})"
    assert r.deve_recusar == recusa, f"{qid}: deve_recusar esperado {recusa}, veio {r.deve_recusar}"


def test_motivo_de_recusa_e_explicavel():
    """Toda recusa por escopo carrega o motivo (R1/R2/R3) — auditável, não 'não sei'."""
    assert rotear("Qual será o custo de crédito do Bradesco em 2027?").motivo_recusa.startswith("R1")
    assert rotear("Compare o guidance de custo de crédito do Nubank com o do Itaú.").motivo_recusa.startswith("R2")
    assert rotear("Cite a frase literal do CEO do Itaú no 4T25.").motivo_recusa.startswith("R3")


def test_trimestre_com_ano_de_4_digitos_equivale_ao_de_2():
    """'4T2025' (forma comum nos releases de RI) = '4T25': detecta o ANO e o PERÍODO filtrável.
    Antes, '4t2025' escapava das duas regexes (3ª auditoria) e perdia ano + filtro de metadados."""
    r = rotear("Qual o lucro do Itau no 4T2025?")
    assert r.anos == [2025] and r.periodos == ["4T25"]


def test_futuro_em_trimestre_de_4_digitos_recusa_r1():
    """Anti-conservador fechado (3ª auditoria): '2T2027'/'4T2027' não casavam ano nenhum -> a pergunta
    de FUTURO ia para o texto em vez de R1 (era a pergunta-recusa do roteiro da demo, como escrita)."""
    r = rotear("Custo de crédito do Bradesco no 2T2027?")
    assert r.deve_recusar and r.motivo_recusa.startswith("R1")
    r2 = rotear("Qual será o market share de consignado do BB no 4T2027, segundo o IF.data?")
    assert r2.deve_recusar and r2.motivo_recusa.startswith("R1")


def test_extrai_periodo_de_trimestre_para_filtro():
    """O TRIMESTRE vira período filtrável ('4t25' -> '4T25') p/ fixar o doc num corpus multi-período;
    um ano-ASSUNTO solto (ex.: guidance 'para 2026') NÃO vira filtro de período."""
    assert rotear("Qual o lucro do Itau no 4T25?").periodos == ["4T25"]
    assert rotear("Qual a faixa de guidance do Itau para 2026?").periodos == []   # 2026 = assunto, não doc
    assert rotear("Compare o 3T25 com o 4T25 do Bradesco").periodos == ["3T25", "4T25"]


# (2) ---------------------------------------------------- casos-fronteira dos críticos

def test_nubank_consignado_cosif_e_respondivel():
    """Over-refusal: share do Nubank em Cosif (IF.data) NÃO recusa pelo nome (mesma lógica da Q11)."""
    r = rotear("Qual o market share do Nubank em consignado, segundo o IF.data?")
    assert r.categoria == "computada" and not r.deve_recusar


def test_santander_fora_do_nucleo_mas_ingerido_responde():
    """R5: Santander está fora do núcleo de prova mas é ingerido; share em Cosif é respondível."""
    r = rotear("Qual o market share do Santander em consignado, segundo o IF.data?")
    assert r.categoria == "computada" and not r.deve_recusar


def test_parafrase_do_itau_e_respondivel_nao_e_verbatim():
    """R3 só recusa 'frase literal/verbatim'; 'o que declarou' (paráfrase do MD&A) é respondível."""
    r = rotear("O que o Itaú declarou sobre consignado CLT no release do 4T25?")
    assert not r.deve_recusar and r.categoria == "doc_unico"


def test_verbatim_do_bb_tambem_recusa():
    """R3 generalizada: BB também não tem transcrição verbatim oficial -> recusar a citação literal."""
    r = rotear("Cite a frase literal do CEO do BB sobre consignado na teleconferência.")
    assert r.deve_recusar and r.motivo_recusa.startswith("R3")


def test_guidance_2027_e_futuro():
    """R1 no limite: guidance publicado vai até 2026; 2027 está além -> recusar."""
    r = rotear("Qual o guidance de custo de crédito do Itaú para 2027?")
    assert r.deve_recusar and r.motivo_recusa.startswith("R1")


def test_bradesco_verbatim_nao_recusa():
    """Contraprova de R3: Bradesco TEM verbatim oficial -> pedir a frase literal dele NÃO recusa."""
    r = rotear("Cite a frase literal do CEO do Bradesco sobre consignado na teleconferência.")
    assert not r.deve_recusar


def test_r2_nao_dispara_em_comparacao_intra_ifrs():
    """Over-refusal fechado (#95): comparar o guidance do Nubank (IFRS) entre anos NÃO é cross-base —
    não há banco Cosif na pergunta -> R2 não pode disparar (e a mensagem 'IFRS x Cosif' seria falsa)."""
    r = rotear("Compare o guidance de custo de crédito do Nubank em 2025 com 2026")
    assert not r.deve_recusar


def test_r2_so_dispara_com_os_dois_lados_de_base():
    """R2 legítimo: Nubank (IFRS) x Itaú (Cosif) -> recusa cross-base (os dois lados reais presentes)."""
    r = rotear("Compare o guidance de custo de crédito do Nubank com o do Itaú.")
    assert r.deve_recusar and r.motivo_recusa.startswith("R2")


def test_share_declarado_de_dois_bancos_nao_vira_comparativo():
    """#248: market share que os CEOs DECLARARAM é fato de TEXTO -> doc_unico, não o comparativo SQL.
    Assert FORTE (3ª auditoria): '!= comparativo' aceitava over-recusa ou rota computada como sucesso."""
    r = rotear("Qual market share de consignado o CEO do Bradesco e o do Itaú declararam na teleconferência?")
    assert r.categoria == "doc_unico" and not r.deve_recusar


def test_share_computado_de_dois_bancos_vira_comparativo():
    """Contraprova: share COMPUTADO de 2 bancos (sem 'declarou') -> comparativo (cross-bank SQL)."""
    r = rotear("Compare o market share de consignado do BB com o do Itaú, segundo o IF.data.")
    assert r.categoria == "comparativo"


# (3) -------------------------------------- R7: sub-produto fora da granularidade do IF.data
# O IF.data (carteira PF) só separa em 7 modalidades. Pedir o NÚMERO de um sub-recorte que só existe
# no release (consignado INSS, cheque especial, SFH...) deve RECUSAR com motivo — não computar a
# modalidade-pai disfarçada. Mas o sub-produto DECLARADO (texto) segue respondível.

def test_r7_recusa_subproduto_no_caminho_de_numero():
    """R7: número de 'consignado INSS' (sub-recorte do consignado) não é computável no IF.data."""
    r = rotear("Qual o market share de consignado INSS do BB, segundo o IF.data?")
    assert r.deve_recusar and r.motivo_recusa.startswith("R7")


def test_r7_recusa_cheque_especial():
    """R7: 'cheque especial' não é uma das 7 modalidades do IF.data -> recusa no caminho de número."""
    r = rotear("Qual o market share do Bradesco em cheque especial?")
    assert r.deve_recusar and r.motivo_recusa.startswith("R7")


def test_r7_nao_dispara_em_pergunta_declarada():
    """R7 só barra o NÚMERO: o sub-produto DECLARADO (texto) é respondível — o release pode citá-lo.
    É a Q6 do eval ('consignado privado/CLT que o Itaú declarou') -> segue multi_fonte, não recusa."""
    r = rotear("O Itaú declarou crescer em consignado privado (CLT). O market share dele em consignado "
               "subiu nos trimestres seguintes, segundo o IF.data?")
    assert not r.deve_recusar and r.categoria == "multi_fonte"


def test_r7_nao_dispara_sem_subproduto():
    """Contraprova: consignado puro É uma das 7 modalidades -> não é sub-produto, não recusa por R7."""
    r = rotear("Qual o market share do BB em consignado, segundo o IF.data?")
    assert not r.deve_recusar and r.categoria == "computada"


# (4) -------------------------------------- modalidade explícita x presumida (transparência)
# Sem produto na pergunta, assumimos consignado (foco do caso), mas marcamos explicita=False para o
# pipeline AVISAR que presumiu — mata o "default silencioso".

def test_modalidade_explicita_quando_nomeada():
    assert rotear("market share do BB em cartao, segundo o IF.data").modalidade_explicita is True


def test_modalidade_presumida_quando_ausente():
    r = rotear("Qual o market share do BB, segundo o IF.data?")
    assert r.modalidade_explicita is False and r.categoria == "computada"


def test_sinonimo_de_modalidade_amplia_recall():
    """Sinônimo coloquial ('carro') resolve p/ Veículos em vez de cair no default consignado."""
    r = rotear("Qual o market share do BB em financiamento de carro, segundo o IF.data?")
    assert r.modalidade_explicita is True and "Veículos" in r.modalidade and not r.deve_recusar


def test_carro_chefe_e_idiomatismo_nao_veiculos():
    """3ª auditoria: 'produto carro-chefe' casava 'carro' -> Veículos como EXPLÍCITA (número errado
    com cara de certeza, sem aviso). O idiomatismo é removido antes da detecção -> presume + avisa."""
    r = rotear("Qual o market share do produto carro-chefe do BB, segundo o IF.data?")
    assert r.modalidade_explicita is False and "Consigna" in r.modalidade


# (5) -------------------------------------- aliases com fronteira de palavra (tickers)

def test_ticker_nao_detecta_banco_por_substring():
    """3ª auditoria: 'BBDC4' contém 'bb' -> detectava BB+Bradesco e virava comparação não pedida."""
    r = rotear("Qual o market share do BBDC4 em consignado, segundo o IF.data?")
    assert r.bancos == ["Bradesco"] and r.categoria == "computada"


def test_tickers_continuam_casando_isolados():
    assert rotear("Qual o market share do BBAS3 em consignado, segundo o IF.data?").bancos == ["BB"]
    assert rotear("Qual o market share do ITUB4 em consignado, segundo o IF.data?").bancos == ["Itau"]
    assert "BB" in rotear("Qual o market share do BB em consignado, segundo o IF.data?").bancos


def test_itau_bba_nao_vira_banco_do_brasil():
    """'Itaú BBA' (braço de atacado) não pode acionar o alias 'bb' do Banco do Brasil."""
    r = rotear("O que o Itau BBA declarou sobre consignado no release do 4T25?")
    assert r.bancos == ["Itau"]


# (6) -------------------------------------- fronteira do R7 (por desenho, não por acidente)

def test_r7_numero_sem_ifdata_segue_para_o_texto():
    """Fronteira documentada: 'saldo de cheque especial' SEM citar IF.data/share não é pedido de
    cálculo — o release pode trazer o saldo do sub-produto -> caminho de TEXTO + gate decide."""
    r = rotear("Qual o saldo de cheque especial do Itau no 4T25?")
    assert not r.deve_recusar and r.categoria == "doc_unico"


def test_r7_numero_de_subproduto_com_bacen_recusa():
    """Contraprova: o MESMO sub-produto com a fonte Bacen citada -> R7 (não computável no IF.data)."""
    r = rotear("Qual o saldo de cheque especial do Itau no 4T25, segundo o Bacen?")
    assert r.deve_recusar and r.motivo_recusa.startswith("R7")


# (7) -------------------------------------- 4ª bateria adversarial (véspera da entrega)
# A bateria contra o pipeline REAL provou que o roteador subentregava o caminho SQL: share PONTUAL
# ("qual o share do BB no agro em 2024?") ia pro TEXTO e era recusado, "Bacen" sequestrava pergunta
# regulatória pro SQL, e "qual banco lidera?" não tinha caminho. Estes testes fixam os consertos.

def test_share_pontual_vai_para_o_sql_sem_citar_ifdata():
    """A pergunta MAIS NATURAL do caso ('qual o share de X em Y no 4T25?') é pedido de NÚMERO:
    computada, mesmo sem 'segundo o IF.data' — market share não vive confiável em texto."""
    r = rotear("Qual o market share do Nubank em cartão de crédito no 4T25?")
    assert r.categoria == "computada" and r.bancos == ["Nubank"]
    r2 = rotear("Qual o market share do Banco do Brasil no agro em 2024?")
    assert r2.categoria == "computada" and r2.bancos == ["BB"] and "Rural" in r2.modalidade


def test_bacen_sozinho_nao_sequestra_pergunta_de_texto():
    """'O que mudou com a Resolução 4.966 do Bacen?' é pergunta de TEXTO (notas na base): a palavra
    'Bacen' sem modalidade nomeada não pode ligar o SQL — antes recusava algo respondível."""
    r = rotear("O que mudou com a Resolução 4.966 do Bacen?")
    assert r.categoria == "doc_unico" and not r.deve_recusar


def test_bacen_com_modalidade_nomeada_segue_computavel():
    """Contraprova: 'segundo o IF.data' + modalidade nomeada continua no caminho SQL."""
    r = rotear("Qual a carteira de consignado do Itaú segundo o IF.data?")
    assert r.categoria == "computada"


def test_ranking_sem_banco_vira_comparativo_de_todos():
    """'Qual banco lidera?' não nomeia banco — o comparativo cross-bank (que já elege líder com gap
    em p.p.) recebe TODOS os cobertos. Antes: doc_unico -> recusa de algo computável."""
    r = rotear("Qual banco teve o maior market share em consignado no 4T25?")
    assert r.categoria == "comparativo" and len(r.bancos) == 5
    r2 = rotear("Quem lidera em cartão de crédito segundo o IF.data?")
    assert r2.categoria == "comparativo" and len(r2.bancos) == 5


def test_trimestre_anglo_4q_equivale_a_4t():
    """'4Q25' (sell-side) = '4T25': detecta ano e período filtrável; '4Q27' dispara R1 (a MESMA
    brecha anti-conservadora do '2T2027', pela letra)."""
    r = rotear("Qual o lucro do Itau no 4Q25?")
    assert r.anos == [2025] and r.periodos == ["4T25"]
    r2 = rotear("Qual o market share do Itau no 4Q27 segundo o IF.data?")
    assert r2.deve_recusar and r2.motivo_recusa.startswith("R1")


def test_modalidade_exige_fronteira_de_palavra():
    """'magro' continha 'agro' -> Rural EXPLÍCITA errada + aviso de presunção SUPRIMIDO (a falha do
    'carro-chefe', agora pela fronteira). Com \\b: presume consignado e avisa."""
    r = rotear("Como evoluiu o resultado magro do BB segundo o IF.data?")
    assert r.modalidade_explicita is False and "Consigna" in r.modalidade


def test_subproduto_exige_fronteira_de_palavra():
    """'fiesta' continha 'fies' -> R7 falso. Com \\b: segue pro texto (gate decide)."""
    r = rotear("Qual o market share do Itau na linha fiesta?")
    assert not r.deve_recusar


def test_modalidade_plural_continua_casando():
    """A fronteira aceita plural ('cartões' -> cartão): \\b com s? opcional não derruba recall."""
    assert rotear("share do Itau em cartoes segundo o IF.data").modalidade == "Cartão de Crédito"


def test_tickers_santander_e_nubank():
    """Simetria com ITUB4/BBDC4/BBAS3 (3ª auditoria): SANB11 e ROXO34 também são o jeito natural
    de perguntar em equities."""
    assert rotear("Qual o market share do SANB11 em veículos no 4T25?").bancos == ["Santander"]
    assert rotear("market share do ROXO34 em cartão no 4T25").bancos == ["Nubank"]


def test_r8_recusa_pedido_de_recomendacao():
    """'Vale a pena comprar?' é conselho de investimento, não fato da base -> R8 (numa gestora,
    a recusa explícita É a resposta certa)."""
    r = rotear("Qual a cotação de BBDC4 hoje? Vale a pena comprar?")
    assert r.deve_recusar and r.motivo_recusa.startswith("R8")


def test_r8_nao_dispara_no_fato_sobre_analistas():
    """Contraprova: 'quantos analistas recomendam comprar?' é FATO publicado no release -> texto."""
    r = rotear("Quantos analistas recomendam comprar BBDC4, segundo o release?")
    assert not r.deve_recusar


def test_parafrase_natural_do_carro_chefe_roteia_multi_fonte():
    """5ª bateria: 'falou'/'citou' não eram DECLARADO, 'entregou' não era CONFRONTO e 'banco central'
    (por extenso) não ligava cita_ifdata — as paráfrases naturais do carro-chefe (promessa×entrega,
    o TÍTULO do Caso B) morriam no texto. Os três léxicos agora cobrem."""
    r = rotear("O que o CEO do Bradesco falou de consignado bate com o Bacen?")
    assert r.categoria == "multi_fonte"
    r2 = rotear("O 14,2% de consignado que o Bradesco citou se confirma nos dados do banco central?")
    assert r2.categoria == "multi_fonte"
    r3 = rotear("O Bradesco entregou o share de consignado que prometeu?")
    assert r3.categoria == "multi_fonte"


def test_saudacao_recebe_resposta_direta_sem_retrieval():
    """'Bom dia' ecoava a transcrição do Bradesco (que tem 'bom dia' literal) com 5 fontes —
    saudação não é pergunta de conhecimento: resposta de SISTEMA, sem retrieval."""
    r = rotear("Bom dia")
    assert r.categoria == "direta" and "bancos cobertos" in r.resposta_pronta
    assert rotear("oi").categoria == "direta"
    assert rotear("Obrigado!").categoria == "direta"


def test_saudacao_com_pergunta_segue_o_fluxo_normal():
    """Contraprova: a saudação só casa a mensagem INTEIRA — 'bom dia, qual o lucro...' roteia normal."""
    r = rotear("Bom dia, qual foi o lucro do Itaú no 4T25?")
    assert r.categoria == "doc_unico" and r.bancos == ["Itau"]


def test_meta_pergunta_de_cobertura_responde_direto():
    """'Quais bancos estão na base?' recusava — mas a resposta o sistema SABE (está no config)."""
    r = rotear("Quais bancos estão na base?")
    assert r.categoria == "direta" and "Nubank" in r.resposta_pronta and "3T23 a 4T25" in r.resposta_pronta
    assert rotear("Qual a cobertura da base?").categoria == "direta"
    assert rotear("que fontes você tem disponíveis?").categoria == "direta"


def test_janela_aberta_em_trimestres_seguintes():
    """B3 do enunciado: 'disse em 2023... subiu nos trimestres SEGUINTES?' — o ano citado é ponto
    de PARTIDA (janela aberta), não moldura; 'de 2023 a 2024' segue fechada."""
    r = rotear("O Santander disse em 2023 que ia ganhar participação em cartões. O market share "
               "dele em cartão de crédito subiu de fato nos trimestres seguintes?")
    assert r.janela_aberta is True and r.categoria == "multi_fonte"
    assert rotear("Como evoluiu o share do BB de 2023 a 2024, segundo o IF.data?").janela_aberta is False


def test_janela_ate_e_teto_nao_moldura():
    """Espelho da janela aberta: 'até 2024' liga o slot (o ano vira TETO no pipeline); 'bateu' não
    casa por fronteira de palavra e 'até que ponto' é retórico, não teto."""
    assert rotear("Como evoluiu o market share do BB em consignado até 2024?").janela_ate is True
    assert rotear("O guidance do BB bateu com o realizado?").janela_ate is False
    assert rotear("Até que ponto o share do BB cresceu em 2024?").janela_ate is False
