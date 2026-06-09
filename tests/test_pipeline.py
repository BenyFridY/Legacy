"""Teste de ponta a ponta do orquestrador (pipeline.responder) — sem torch, sem rede, sem chave.

Monta uma base DuckDB em memória (chunks de texto + carteira_pf de números) e exercita os
4 caminhos: recusa por escopo, doc_unico (texto), computada (números), multi_fonte (fusão).
Encoder/reranker/LLM são FALSOS e determinísticos: provam o FLUXO e as RECUSAS.
"""

import numpy as np
import pytest

from legacy_rag.index.chunking import Chunk
from legacy_rag.index.embed import embedar_chunks
from legacy_rag.index.store_texto import garantir_schema, persistir_chunks
from legacy_rag.pipeline import Dependencias, responder
from legacy_rag.structured.store import conectar


# ---------------------------------------------------------------- fakes

class FakeEncoder:
    dim = 8

    def encode(self, textos):
        # Vetor constante: com poucos chunks, todos viram candidatos; o reranker é quem ordena.
        return np.ones((len(textos), self.dim), dtype=np.float32)


class FakeReranker:
    """Nota = fração das palavras da pergunta presentes no trecho (0–1, determinístico)."""

    def pontuar(self, query, textos):
        qs = set(query.lower().split())
        return [len(qs & set(t.lower().split())) / max(1, len(qs)) for t in textos]


class FakeLLM:
    def __init__(self, resposta="Resposta redigida a partir do contexto fornecido."):
        self.resposta = resposta
        self.ultimo_prompt = None

    def completar(self, prompt):
        self.ultimo_prompt = prompt
        return self.resposta


# ---------------------------------------------------------------- base de teste

@pytest.fixture
def deps():
    con = conectar(":memory:")          # cria carteira_pf
    garantir_schema(con)                # cria chunks

    enc = FakeEncoder()
    chunks = [
        Chunk("BB", "4T25", "release", 12, 0,
              "O custo do crédito realizado pelo Banco do Brasil em 2025 foi R$ 62,0 bilhões."),
        Chunk("Bradesco", "recente", "transcricao", 3, 0,
              "O CEO do Bradesco declarou market share de consignado de cerca de 14,2%."),
    ]
    persistir_chunks(con, chunks, embedar_chunks(chunks, enc))

    # carteira_pf: modalidade em nome CANÔNICO do Bacen (o que o roteador detecta e a tabela guarda).
    CONS = "Empréstimo com Consignação em Folha"     # = consignado
    CART = "Cartão de Crédito"
    linhas = [
        ("C0000001", 202403, CONS, 200.0),  # BB  -> share 0.20
        ("C0000002", 202403, CONS, 140.0),  # Bradesco -> 0.14
        ("C9999999", 202403, CONS, 660.0),  # resto -> total 1000
        ("C0000001", 202412, CONS, 250.0),  # BB  -> 0.25
        ("C0000002", 202412, CONS, 142.0),  # Bradesco -> 0.142
        ("C9999999", 202412, CONS, 608.0),  # resto -> total 1000
        ("C0000003", 202412, CART, 110.0),  # Nubank em CARTÃO -> share 0.55 (outra modalidade!)
        ("C9999999", 202412, CART,  90.0),  # resto cartão -> total 200
    ]
    con.executemany("INSERT INTO carteira_pf VALUES (?, ?, ?, ?)", linhas)
    # cadastro: cada CNPJ -> conglomerado prudencial (aqui 1 CNPJ por banco, mas a via é a mesma).
    cad = [
        ("C0000001", 202403, "Banco do Brasil", "PRUD_BB"), ("C0000002", 202403, "Bradesco", "PRUD_BRAD"),
        ("C9999999", 202403, "Outro", "PRUD_OUTRO"),
        ("C0000001", 202412, "Banco do Brasil", "PRUD_BB"), ("C0000002", 202412, "Bradesco", "PRUD_BRAD"),
        ("C9999999", 202412, "Outro", "PRUD_OUTRO"), ("C0000003", 202412, "Nu Pagamentos", "PRUD_NU"),
    ]
    con.executemany("INSERT INTO cadastro VALUES (?, ?, ?, ?)", cad)

    return Dependencias(
        con=con, encoder=enc, reranker=FakeReranker(), llm=FakeLLM(),
        mapa_prudencial={"BB": "PRUD_BB", "Bradesco": "PRUD_BRAD", "Nubank": "PRUD_NU"},
        limiar=0.3,   # casa com as linhas inseridas acima (modalidade vem da pergunta, via roteador)
    )


# ---------------------------------------------------------------- os 4 caminhos

def test_recusa_por_escopo(deps):
    r = responder("Qual será o custo de crédito do Bradesco no 2º trimestre de 2027?", deps)
    assert r.recusou and r.motivo.startswith("R1")


def test_doc_unico_responde_citado(deps):
    r = responder("Qual foi o custo do crédito realizado pelo Banco do Brasil em 2025?", deps)
    assert not r.recusou
    assert "BB, 4T25, release, pág. 12" in r.citacoes      # citação estrutural, do chunk
    assert "Fontes:" in r.formatado


def test_doc_unico_sem_evidencia_recusa(deps):
    # Pergunta sobre o Itaú: não há chunk do Itaú na base -> retrieval vazio -> gate recusa.
    r = responder("Qual a faixa de guidance de custo de crédito do Itaú para 2026?", deps)
    assert r.recusou


def test_computada_responde_serie_citada(deps):
    r = responder("Como evoluiu o market share do Banco do Brasil em consignado nos últimos quatro trimestres?", deps)
    assert not r.recusou
    assert "20.0%" in r.texto and "25.0%" in r.texto and "alta" in r.texto
    assert "IF.data" in r.citacoes[0]


def test_computada_sem_conglomerado_recusa_honesta(deps):
    deps.mapa_prudencial = {}          # banco sem conglomerado mapeado -> recusa, não inventa
    r = responder("Como evoluiu o market share do Banco do Brasil em consignado?", deps)
    assert r.recusou and "conglomerado" in r.motivo


def test_computada_detecta_modalidade_da_pergunta_cartao(deps):
    """A modalidade NÃO é fixa em consignado: 'cartão' na pergunta -> calcula CARTÃO (Nubank, 55%).
    Prova que o caminho de números é genérico (qualquer banco x qualquer modalidade)."""
    r = responder("Qual o market share do Nubank em cartão de crédito, segundo o IF.data?", deps)
    assert not r.recusou
    assert "55.0%" in r.texto
    assert "Cartão de Crédito" in r.citacoes[0]


def test_computada_avisa_quando_modalidade_presumida(deps):
    """Transparência: pergunta SEM produto -> assume consignado, mas AVISA (mata o default silencioso)."""
    r = responder("Qual o market share do Banco do Brasil, segundo o IF.data?", deps)
    assert not r.recusou
    assert "assumi consignado" in r.texto and "20.0%" in r.texto


def test_computada_nao_avisa_quando_modalidade_explicita(deps):
    """Contraprova: 'consignado' nomeado na pergunta -> sem aviso de presunção."""
    r = responder("Como evoluiu o market share do BB em consignado?", deps)
    assert not r.recusou and "assumi" not in r.texto


def test_r7_recusa_subproduto_no_pipeline(deps):
    """R7 ponta a ponta: número de um sub-recorte fora do IF.data (consignado INSS) recusa, não computa."""
    r = responder("Qual o market share de consignado INSS do Banco do Brasil, segundo o IF.data?", deps)
    assert r.recusou and r.motivo.startswith("R7")


def test_comparativo_cross_bank_quem_ganhou_mais(deps):
    """Cross-bank: compara a série de 2 bancos (SQL) e diz quem ganhou mais share.
    BB 20->25% (+5 p.p.) vs Bradesco 14->14,2% (+0,2 p.p.) -> BB ganhou mais."""
    r = responder("Entre o Banco do Brasil e o Bradesco, qual ganhou mais participação em consignado?", deps)
    assert not r.recusou
    assert "25.0%" in r.texto and "14.2%" in r.texto            # finais de cada banco
    assert "ganhou mais" in r.texto and "BB" in r.texto.split("ganhou mais")[-1]   # líder = BB
    assert "IF.data" in r.citacoes[0]


def test_comparativo_recusa_se_menos_de_dois_computaveis(deps):
    """Santander não está no mapa_prudencial do fixture -> só BB computa -> recusa honesta (exige >= 2)."""
    r = responder("Compare o market share de consignado do Banco do Brasil e do Santander.", deps)
    assert r.recusou and "ao menos 2" in r.motivo


def test_multi_fonte_cruza_declarado_e_computado(deps):
    r = responder(
        "O market share de consignado do Bradesco computado a partir do IF.data confirma o "
        "~14,2% que o CEO declarou?", deps)
    assert not r.recusou
    assert any("IF.data" in c for c in r.citacoes)          # lado computado
    assert any("Bradesco" in c and "transcricao" in c for c in r.citacoes)  # lado declarado
    assert len(r.citacoes) == 2


class LLMQuebrado:
    """Redator que falha como na vida real (rede caiu, 429 esgotado, chave inválida)."""

    def completar(self, prompt):
        raise ConnectionError("rede caiu no meio da demo")


def test_redator_caido_degrada_para_evidencia_citada_no_texto(deps):
    """3ª auditoria: falha do LLM não pode virar 'Erro:' cru — cai na MESMA evidência citada do 'sem chave'."""
    deps.llm = LLMQuebrado()
    r = responder("Qual foi o custo do crédito realizado pelo Banco do Brasil em 2025?", deps)
    assert not r.recusou and "Trechos recuperados" in r.texto and "indisponível" in r.texto
    assert "BB, 4T25, release, pág. 12" in r.citacoes          # a citação estrutural sobrevive à queda


def test_redator_caido_degrada_no_multi_fonte(deps):
    deps.llm = LLMQuebrado()
    r = responder("O market share de consignado do Bradesco computado a partir do IF.data confirma o "
                  "~14,2% que o CEO declarou?", deps)
    assert not r.recusou and "declarado x computado" in r.texto    # evidências lado a lado, citadas


def test_multi_fonte_sem_llm_devolve_evidencias(deps):
    deps.llm = None
    r = responder(
        "O market share de consignado do Bradesco computado a partir do IF.data confirma o "
        "~14,2% que o CEO declarou?", deps)
    assert not r.recusou and "declarado x computado" in r.texto


def test_multi_fonte_llm_nao_reconcilia_mostra_evidencias(deps):
    # LLM devolve o sentinela (ex.: figura declarada numa célula de tabela) -> NÃO recusa:
    # como temos as duas evidências, mostra declarado x computado lado a lado, citados.
    deps.llm = FakeLLM("NAO_ENCONTRADO")
    r = responder(
        "O market share de consignado do Bradesco computado a partir do IF.data confirma o "
        "~14,2% que o CEO declarou?", deps)
    assert not r.recusou and "declarado x computado" in r.texto
    assert len(r.citacoes) == 2


def test_multi_fonte_ano_futuro_sem_ancora_recusa(deps):
    """Brecha fechada (#61/ADR-0005): pergunta multi_fonte com ANO FUTURO e metrica='outra' (R1 não
    dispara) e nenhum trecho documentando o ano -> a trava de aterramento recusa (não infere o futuro)."""
    r = responder("A estratégia que o CEO do Bradesco declarou para 2028 se confirmou no IF.data?", deps)
    assert r.recusou and "2028" in (r.motivo or "")


# ---------------------------------------------------------------- cross-ano / cross-banco (ADR-0005)

@pytest.fixture
def deps_multiano():
    """Base com 3 anos (2023/2024/2025) e 3 bancos em consignado, p/ exercitar recorte por janela e
    comparação cross-bank com líder que MUDA conforme o ano. Total = 1000/período (share = saldo/1000)."""
    con = conectar(":memory:")
    garantir_schema(con)                            # cria 'chunks' (vazia: estes testes são de números)
    CONS = "Empréstimo com Consignação em Folha"
    #            período  BB    Bradesco  Itau   resto   (shares ->)
    # 202312:          .10      .30      .20    .40
    # 202412:          .30      .25      .15    .30
    # 202512:          .20      .40      .25    .15
    linhas = [
        ("PRUD_BB", 202312, CONS, 100.0), ("PRUD_BRAD", 202312, CONS, 300.0),
        ("PRUD_ITAU", 202312, CONS, 200.0), ("PRUD_OUT", 202312, CONS, 400.0),
        ("PRUD_BB", 202412, CONS, 300.0), ("PRUD_BRAD", 202412, CONS, 250.0),
        ("PRUD_ITAU", 202412, CONS, 150.0), ("PRUD_OUT", 202412, CONS, 300.0),
        ("PRUD_BB", 202512, CONS, 200.0), ("PRUD_BRAD", 202512, CONS, 400.0),
        ("PRUD_ITAU", 202512, CONS, 250.0), ("PRUD_OUT", 202512, CONS, 150.0),
    ]
    con.executemany("INSERT INTO carteira_pf VALUES (?, ?, ?, ?)", linhas)  # cod_inst = prudencial (fallback)
    return Dependencias(
        con=con, encoder=FakeEncoder(), reranker=FakeReranker(), llm=FakeLLM(),
        mapa_prudencial={"BB": "PRUD_BB", "Bradesco": "PRUD_BRAD", "Itau": "PRUD_ITAU"})


def test_comparativo_cross_ano_muda_o_lider(deps_multiano):
    """O CORAÇÃO da correção: anos diferentes -> respostas DIFERENTES (antes os anos eram decorativos).
    2023->2024: BB +20 vs Bradesco -5 -> BB. 2024->2025: BB -10 vs Bradesco +15 -> Bradesco (líder MUDA)."""
    d = deps_multiano
    r1 = responder("Entre o Banco do Brasil e o Bradesco, quem ganhou mais participação em consignado de 2023 a 2024?", d)
    r2 = responder("Entre o Banco do Brasil e o Bradesco, quem ganhou mais participação em consignado de 2024 a 2025?", d)
    assert not r1.recusou and not r2.recusou
    assert "2023-12 a 2024-12" in r1.texto and r1.texto.split("participação:")[-1].strip().startswith("BB")
    assert "2024-12 a 2025-12" in r2.texto and r2.texto.split("participação:")[-1].strip().startswith("Bradesco")
    assert r1.texto != r2.texto                                # anos diferentes => respostas diferentes


def test_comparativo_quantifica_quanto_a_mais(deps_multiano):
    """'quanto um banco ganhou MAIS que outro': o gap em p.p. é explícito (BB +20 vs Bradesco -5 = 25 p.p.)."""
    r = responder("Entre o Banco do Brasil e o Bradesco, quem ganhou mais participação em consignado de 2023 a 2024?", deps_multiano)
    assert "+25.0 p.p. a mais que Bradesco" in r.texto


def test_computada_cross_ano_recorta_a_janela(deps_multiano):
    """O caminho de números (1 banco) também respeita a janela: 2023->2024 sobe (10->30), 2024->2025 cai (30->20)."""
    d = deps_multiano
    r_sobe = responder("Como evoluiu o market share do Banco do Brasil em consignado de 2023 a 2024?", d)
    r_cai = responder("Como evoluiu o market share do Banco do Brasil em consignado de 2024 a 2025?", d)
    assert "10.0%" in r_sobe.texto and "30.0%" in r_sobe.texto and "alta" in r_sobe.texto
    assert "30.0%" in r_cai.texto and "20.0%" in r_cai.texto and "queda" in r_cai.texto
    assert r_sobe.texto != r_cai.texto


def test_comparativo_empate_nao_elege_lider(deps_multiano):
    """Empate (#146): na janela inteira BB +10 e Bradesco +10 -> diz 'equivalente', não inventa líder."""
    r = responder("Entre o Banco do Brasil e o Bradesco, quem ganhou mais participação em consignado?", deps_multiano)
    assert not r.recusou and "equivalente" in r.texto.lower() and "ganhou mais" not in r.texto


def test_comparativo_tres_bancos_rankeia(deps_multiano):
    """3+ bancos (#282): 2024->2025 -> Bradesco +15 > Itau +10 > BB -10, ranqueado e com líder correto."""
    r = responder("Compare o market share de consignado entre Banco do Brasil, Bradesco e Itaú "
                  "de 2024 a 2025, segundo o IF.data.", deps_multiano)
    assert not r.recusou
    for nome in ("BB", "Bradesco", "Itau"):
        assert nome in r.texto
    assert r.texto.index("Bradesco") < r.texto.index("Itau") < r.texto.index("BB")   # ordenado por variação
    assert r.texto.split("participação:")[-1].strip().startswith("Bradesco")


def test_comparativo_recusa_sem_trimestre_comum():
    """Janelas defasadas (#2/#7): BB só em 2024, Bradesco só em 2025 -> sem trimestre comum -> recusa
    honesta (não compara maçã x laranja nem rotula a janela de um para o outro)."""
    con = conectar(":memory:")
    garantir_schema(con)
    CONS = "Empréstimo com Consignação em Folha"
    con.executemany("INSERT INTO carteira_pf VALUES (?, ?, ?, ?)", [
        ("PRUD_BB", 202412, CONS, 300.0), ("PRUD_OUT", 202412, CONS, 700.0),
        ("PRUD_BRAD", 202512, CONS, 400.0), ("PRUD_OUT", 202512, CONS, 600.0),
    ])
    deps = Dependencias(con=con, encoder=FakeEncoder(), reranker=FakeReranker(), llm=FakeLLM(),
                        mapa_prudencial={"BB": "PRUD_BB", "Bradesco": "PRUD_BRAD"})
    r = responder("Entre o Banco do Brasil e o Bradesco, quem ganhou mais participação em consignado?", deps)
    assert r.recusou and "comum" in (r.motivo or "")


def test_multi_fonte_so_computado_nao_ecoa_numero_da_pergunta(deps_multiano):
    """#180: multi_fonte com share mas SEM trecho declarado na base -> ramo 'só computado' devolve a
    série citada SEM LLM, sem ecoar o '99%' que veio na pergunta (não apresenta número não-citado)."""
    r = responder("O market share de consignado do BB confirma os 99% que o CEO declarou?", deps_multiano)
    assert not r.recusou
    assert "99%" not in r.texto                                # não ecoou o número da pergunta
    assert len(r.citacoes) == 1 and "IF.data" in r.citacoes[0]
    assert "computado do IF.data" in r.texto                   # cabeçalho honesto do ramo só-computado
