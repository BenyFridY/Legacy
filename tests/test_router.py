"""Testes do roteador determinístico (sem rede, sem modelo).

Dois blocos:
  (1) AS 11 PERGUNTAS DO EVAL — cada uma deve cair na categoria certa e no comportamento
      (answer/refuse) que o eval/questions.yaml espera.
  (2) CASOS-FRONTEIRA levantados pelos críticos adversariais — provam que as armadilhas
      (over-refusal do Nubank/Santander; verbatim x paráfrase; futuro sutil) estão tratadas.
"""

import pytest

from legacy_rag.router.router import rotear


# (1) ---------------------------------------------------------------- as 11 do eval
# (id, pergunta, categoria_esperada, deve_recusar)
ONZE = [
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


@pytest.mark.parametrize("qid,pergunta,categoria,recusa", ONZE, ids=[q[0] for q in ONZE])
def test_roteamento_das_11(qid, pergunta, categoria, recusa):
    r = rotear(pergunta)
    assert r.categoria == categoria, f"{qid}: esperava {categoria}, veio {r.categoria} ({r.motivo_recusa})"
    assert r.deve_recusar == recusa, f"{qid}: deve_recusar esperado {recusa}, veio {r.deve_recusar}"


def test_motivo_de_recusa_e_explicavel():
    """Toda recusa por escopo carrega o motivo (R1/R2/R3) — auditável, não 'não sei'."""
    assert rotear("Qual será o custo de crédito do Bradesco em 2027?").motivo_recusa.startswith("R1")
    assert rotear("Compare o guidance de custo de crédito do Nubank com o do Itaú.").motivo_recusa.startswith("R2")
    assert rotear("Cite a frase literal do CEO do Itaú no 4T25.").motivo_recusa.startswith("R3")


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
