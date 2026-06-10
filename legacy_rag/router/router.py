"""Roteador determinístico — o "cérebro" que decide o caminho de cada pergunta.

Duas decisões, NESTA ordem:

  1) GATE DE ESCOPO — a pergunta é respondível pela base? Se não, vira `nao_respondivel`
     e o sistema RECUSA antes mesmo de buscar (a regra inegociável do case). Três regras:
       R1  VALOR de métrica em período futuro (ano além da cobertura). Pergunta de DATA/evento com
           ano futuro NÃO cai aqui — vai p/ o texto + trava de aterramento (só responde se um trecho
           documentar o ano). Ver pipeline._aterrar_ano_futuro e ADR-0005.
       R2  comparação entre BASES CONTÁBEIS incompatíveis (IFRS x Cosif) numa métrica de
           release/Cosif (guidance / custo de crédito / PDD). É uma CONJUNÇÃO: só dispara com
           (comparação) E (entidade só-IFRS) E (métrica de release) — NUNCA pelo nome "Nubank".
       R3  pedido de citação VERBATIM ("frase literal") de entidade sem transcrição oficial na
           base. Ancorado no flag `tem_verbatim` por-entidade (não na palavra "Itaú"); e só
           dispara em "frase literal/verbatim", não em "o que declarou" (paráfrase é respondível).
       R7  pedido do NÚMERO/share de um SUB-RECORTE fora da granularidade do IF.data (consignado
           INSS, cheque especial, SFH...). O Bacen (carteira PF) só separa em 7 modalidades; computar
           a modalidade-pai disfarçada de sub-produto responderia a pergunta ERRADA -> recusa honesta
           (aponta a pai via SQL ou o release via texto). NÃO dispara em pergunta DECLARADA (texto).
       R8  pedido de RECOMENDAÇÃO de investimento ("vale a pena comprar?") -> recusa: a base documenta
           fatos (cotação histórica, consenso de analistas no release); aconselhar compra/venda não.

  2) CAMINHO (se estiver no escopo):
       doc_unico   um fato em um único documento (release/MD&A).
       computada   número/série calculado do IF.data via SQL (market share etc.).
       comparativo compara o market share de 2+ bancos (cross-bank), tudo em SQL.
       multi_fonte cruza o DECLARADO (texto) com o COMPUTADO (número) — o coração do Caso B.

Por que DETERMINÍSTICO (regras), e não um LLM decidindo solto? REPRODUTIBILIDADE. O eval vale
metade da nota e mede o sistema repetidamente; um roteador-LLM daria caminhos diferentes para a
MESMA pergunta e o número de eval tremeria. Regras: mesma entrada -> mesmo caminho -> eval confiável
e auditável. O preço é fragilidade (uma frase com palavras estranhas pode cair no caminho errado);
por isso a acurácia do roteamento é MEDIDA no eval, não escondida.

LIMITAÇÕES CONHECIDAS (1º corte; ver ADR-0005). Cobre R1/R2/R3 + as 12 perguntas do eval. Lacunas
documentadas para a ingestão larga (ADR-0004), deixadas honestas em vez de fingidas:
  R4  distinguir REALIZADO de GUIDANCE dentro de 2026 (pedir realizado de período ainda não
      publicado deveria recusar) — hoje cai no gate de evidência (Estágio 2).
  R5  entidade ingerida fora do núcleo de prova (Santander, Nubank em Cosif) -> responder, não
      recusar pelo nome (já tratado: ENTIDADES inclui os dois com base_contabil="cosif").
  R6  métrica não-ingerida (ROE, NPL) -> cai no gate de evidência (Estágio 2). (Basileia NÃO é exemplo:
      está verbatim no release do Itaú e o gate responde — gold `itau-basileia`, calibrar_gate.)
A recusa-por-evidência (Estágio 2) depende do reranker real e é avaliada só com os modelos plugados.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from legacy_rag.config import (
    ANO_COBERTURA_MAX, ENTIDADES, MODALIDADE_FOCO, MODALIDADES,
    MODALIDADES_IFDATA_TXT, SUBPRODUTOS_FORA_IFDATA,
)

CATEGORIAS = ("doc_unico", "computada", "comparativo", "multi_fonte", "nao_respondivel", "direta")


# --------------------------------------------------------------------------
# Normalização: tudo minúsculo e sem acento, para casar regras sem depender de
# o usuário ter digitado "Itaú" ou "itau".
# --------------------------------------------------------------------------

def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


# --------------------------------------------------------------------------
# Slots: os "fatos" que extraímos da pergunta antes de decidir qualquer coisa.
# Separar EXTRAÇÃO de DECISÃO deixa cada regra curta e testável.
# --------------------------------------------------------------------------

@dataclass
class Slots:
    bancos: list[str] = field(default_factory=list)   # chaves de ENTIDADES mencionadas
    anos: list[int] = field(default_factory=list)      # anos citados (de "2027" e de "4T25")
    periodos: list[str] = field(default_factory=list)  # trimestres citados ("4t25" -> "4T25"), p/ filtro de metadados
    metrica: str = "outra"                              # rótulo grosso p/ transparência/log
    modalidade: str = MODALIDADE_FOCO                   # produto do Bacen citado (cartão, veículos...); default consignado
    modalidade_explicita: bool = False                  # a pergunta NOMEOU o produto? (senão, assumimos consignado -> transparência)
    subproduto_fora: str | None = None                  # sub-recorte fora da granularidade do IF.data (R7), se citado
    cita_ifdata: bool = False                           # "segundo o IF.data", "Bacen"
    declarado: bool = False                             # "declarou", "CEO", "guidance", "estratégia"
    confronto: bool = False                             # "confirmou", "subiu", "vs" — promete-vs-entrega
    serie: bool = False                                 # "evoluiu", "últimos N trimestres", "trajetória"
    comparacao: bool = False                            # "compare ... com", "versus"
    pede_verbatim: bool = False                         # "frase literal", "transcrição verbatim"
    superlativo: bool = False                           # "qual banco...", "maior", "lidera" — pedido de ranking
    janela_aberta: bool = False                         # "trimestres seguintes", "desde" — janela SEM fim fixo
    janela_ate: bool = False                            # "até 2024" — o período citado é o TETO, não a moldura
    pede_recomendacao: bool = False                     # "vale a pena comprar?" — conselho de investimento (R8)


def _detectar_bancos(t: str) -> list[str]:
    """Alias casa com FRONTEIRA DE PALAVRA, não substring: 'bb' dentro de 'BBDC4'/'Itaú BBA' detectava
    Banco do Brasil espúrio — a pergunta virava comparação de 2 bancos que ninguém pediu, e R3 recusava
    o verbatim do Bradesco citando o BB (3ª auditoria; ticker é o jeito natural de perguntar em equities)."""
    achados = []
    for chave, info in ENTIDADES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", t) for a in info["aliases"]):
            achados.append(chave)
    return achados


# Token de trimestre nas formas usuais de RI: "4T25"/"4T2025" E o anglo fundido "4Q25"/"4Q2025"
# (corrente em sell-side). A forma de 4 dígitos escapava das duas regexes ("2T2027" não casava nem como
# trimestre nem como ano solto, pois '\b(20\d{2})\b' não tem fronteira entre o 't' e o '2') -> pergunta
# de FUTURO passava sem R1 (3ª auditoria); "4Q27" repetia a MESMA brecha pela letra (4ª bateria) -> [tq].
_TRIMESTRE_RE = r"\b([1-4])[tq](20\d{2}|\d{2})\b"


def _detectar_anos(t: str) -> list[int]:
    anos = [int(a) for a in re.findall(r"\b(20\d{2})\b", t)]            # "2025", "2027"
    for q, yy in re.findall(_TRIMESTRE_RE, t):                          # "4t25"/"4t2025" -> 2025
        anos.append(int(yy) if len(yy) == 4 else 2000 + int(yy))
    return sorted(set(anos))


def _detectar_periodos(t: str) -> list[str]:
    """Trimestres citados, no formato do DB ("4t25" E "4t2025" -> "4T25"). Usado como FILTRO DE
    METADADOS p/ fixar o documento certo num corpus multi-período. Só TOKEN DE TRIMESTRE vira filtro —
    um ano "solto" (ex.: 'guidance para 2026') é ASSUNTO, não o período do documento, e não filtra."""
    vistos = dict.fromkeys(f"{q}T{yy[-2:]}" for q, yy in re.findall(_TRIMESTRE_RE, t))
    return list(vistos)


def _casa_palavra(p: str, t: str) -> bool:
    """Keyword casa com FRONTEIRA DE PALAVRA (+ plural opcional), não substring — mesma regra dos
    aliases de banco. Sem isto, 'magro' continha 'agro' (Rural EXPLÍCITA errada, e o aviso de presunção
    era SUPRIMIDO — a falha que motivou o caso 'carro-chefe') e 'fiesta' continha 'fies' (R7 falso)."""
    return re.search(rf"\b{re.escape(p)}s?\b", t) is not None


def _detectar_modalidade(t: str) -> tuple[str, bool]:
    """Produto do Bacen citado na pergunta (cartão, veículos, ...) e SE foi nomeado explicitamente.
    Sem match -> (MODALIDADE_FOCO, False): assumimos consignado (foco do caso), mas o `False` deixa o
    pipeline AVISAR que assumiu (mata o 'default silencioso'). O motor de cálculo é genérico."""
    t = re.sub(r"carro[\s-]chefe", "", t)   # idiomatismo ("produto carro-chefe") não é pedido de Veículos;
    for canonico, palavras in MODALIDADES:  # sem isto, 'carro' casava e SUPRIMIA o aviso de presunção
        if any(_casa_palavra(p, t) for p in palavras):
            return canonico, True
    return MODALIDADE_FOCO, False


def _subproduto_fora_cobertura(t: str) -> str | None:
    """Sub-recorte que o release detalha mas o IF.data NÃO separa (consignado INSS, cheque especial,
    SFH...). Devolve o termo citado, ou None. Usado pelo gate (R7) p/ recusar o NÚMERO com honestidade
    em vez de computar a modalidade-pai disfarçada de sub-produto."""
    for termo in SUBPRODUTOS_FORA_IFDATA:
        if _casa_palavra(termo, t):
            return termo
    return None


def extrair_slots(pergunta: str) -> Slots:
    """Lê a pergunta e preenche os slots por regras léxicas (determinístico, sem modelo)."""
    t = _sem_acento(pergunta)

    if re.search(r"market share|participacao|\bshare\b", t):
        metrica = "market_share"
    elif re.search(r"custo (do|de) credito|\bpdd\b|provis", t):
        metrica = "custo_credito"
    elif re.search(r"guidance|projec", t):
        metrica = "guidance"
    elif re.search(r"\bcarteira\b|\bsaldo\b", t):
        metrica = "carteira"          # saldo ABSOLUTO em R$ (vs share, que é a fatia relativa)
    else:
        metrica = "outra"

    modalidade, modalidade_explicita = _detectar_modalidade(t)

    return Slots(
        bancos=_detectar_bancos(t),
        anos=_detectar_anos(t),
        periodos=_detectar_periodos(t),
        metrica=metrica,
        modalidade=modalidade,
        modalidade_explicita=modalidade_explicita,
        subproduto_fora=_subproduto_fora_cobertura(t),
        cita_ifdata=bool(re.search(r"if[\s.]?data|bacen|banco central", t)),
        declarado=bool(re.search(
            r"declar|disse|falou|citou|afirm|coment|\bceo\b|telecon|\bcall\b|guidance|estrateg|prometeu", t)),
        confronto=bool(re.search(
            r"confirm|bate com|\bvs\b|versus|subiu|caiu|aumentou|diminuiu|se confirmou|entreg|cumpriu", t)),
        serie=bool(re.search(r"evolu|trajet|ao longo|ultimos|trimestres seguintes|\bserie\b", t)),
        comparacao=bool(re.search(r"\bcompar|\bvs\b|versus|em relacao a", t)),
        pede_verbatim=bool(re.search(r"frase literal|verbatim|cite a frase|transcricao (literal|verbatim)", t)),
        # sinônimos de ranking com \b; "primeiro" SOZINHO fica fora ("primeiro trimestre") e
        # "na frente" também ("frente de consignado" é linha de negócio nos releases, não ranking).
        superlativo=bool(re.search(
            r"qual (o )?banco|que banco|\bquem\b|\bmaior\b|\bmenor\b|\blidera?\b|\blideranca\b"
            r"|\branking\b|\bdominam?\b|\brei\b|\bcampe(a|ao|as|oes)\b|\btop\b"
            r"|numero (um|1)\b|primeiro lugar", t)),
        janela_aberta=bool(re.search(r"seguintes|\bdesde\b|a partir de", t)),
        # "até que ponto..." é retórico ("em que medida"), não teto de janela; "bate(u)" não casa (\b).
        janela_ate=bool(re.search(r"\bate\b(?!\s+que\b)", t)),
        pede_recomendacao=bool(re.search(
            r"vale a pena (comprar|vender|investir)|dev(o|emos) (comprar|vender|investir)"
            r"|compro ou vendo|hora de (comprar|vender)|me recomenda (comprar|vender)", t)),
    )


# --------------------------------------------------------------------------
# Estágio 1 — gate de escopo (R1/R2/R3/R7). Devolve o MOTIVO da recusa, ou None.
# --------------------------------------------------------------------------

_METRICAS_RELEASE_COSIF = {"guidance", "custo_credito"}  # só existem no release/Cosif


def _gate_escopo(s: Slots) -> str | None:
    # R1 — VALOR de métrica em período futuro/inexistente. Refinado (ADR-0005): só recusa CEDO quando a
    # pergunta pede o VALOR de uma métrica (market share / custo de crédito / guidance) num ano além da
    # cobertura — é o caso em que inventar é o risco. Pergunta de DATA/EVENTO com ano futuro (vigência de
    # norma, vencimento de dívida) NÃO é barrada aqui: segue p/ o texto, onde a "trava de aterramento"
    # (pipeline._aterrar_ano_futuro) só responde se um trecho recuperado documentar literalmente o ano.
    if s.anos and max(s.anos) > ANO_COBERTURA_MAX and s.metrica != "outra":
        return (f"R1: valor de '{s.metrica}' em {max(s.anos)} está além da cobertura da base "
                f"(realizado até 4T25, guidance até {ANO_COBERTURA_MAX}).")

    # R2 — comparação entre bases contábeis incompatíveis (CONJUNÇÃO, nunca só o nome). Exige os DOIS
    # lados reais: >=1 banco IFRS E >=1 banco Cosif. Sem o lado Cosif, "Nubank 2025 vs 2026" é uma
    # comparação INTRA-IFRS (temporal) respondível — recusá-la seria over-refusal e a mensagem
    # "IFRS x Cosif" seria falsa (não há Cosif na pergunta). Ver ADR-0005.
    ifrs = [b for b in s.bancos if ENTIDADES[b]["base_contabil"] == "ifrs"]
    cosif = [b for b in s.bancos if ENTIDADES[b]["base_contabil"] == "cosif"]
    if s.comparacao and ifrs and cosif and s.metrica in _METRICAS_RELEASE_COSIF:
        return (f"R2: comparação entre bases contábeis incompatíveis (IFRS {ifrs} x Cosif {cosif}) numa "
                f"métrica de release/Cosif ('{s.metrica}'). Sem base comum -> incomparável.")

    # R3 — citação verbatim de entidade sem transcrição oficial na base.
    if s.pede_verbatim:
        sem_verbatim = [b for b in s.bancos if not ENTIDADES[b]["tem_verbatim"]]
        if sem_verbatim:
            return (f"R3: pedido de citação verbatim de entidade sem transcrição oficial na base "
                    f"({sem_verbatim}). Citar literalmente o que não está na base = inventar.")

    # R8 — pedido de RECOMENDAÇÃO de investimento ("vale a pena comprar?"). A base documenta fatos
    # (cotação histórica, consenso de analistas publicado no release); recomendar compra/venda é opinião
    # fora do contrato do sistema — e numa gestora, a recusa explícita é a resposta certa. Regex estreito
    # (busca o conselho, não o fato): "quantos analistas recomendam comprar?" segue p/ o texto.
    if s.pede_recomendacao:
        return ("R8: pedido de recomendação de investimento. O sistema reporta o que está na base "
                "(cotação histórica e consenso de analistas constam nos releases) — não recomenda "
                "compra ou venda.")

    # R7 — sub-recorte de produto fora da granularidade do IF.data, num pedido de NÚMERO/share. O Bacen
    # (carteira PF) só separa em 7 modalidades; "consignado INSS", "cheque especial", "SFH" etc. não são
    # uma delas. Computar a modalidade-pai disfarçada de sub-produto seria responder a pergunta ERRADA;
    # recusar com motivo é o honesto (aponta a modalidade-pai via SQL, ou o release via texto). NÃO
    # dispara em pergunta DECLARADA (texto): o release pode citar o sub-produto. FRONTEIRA por desenho:
    # número de sub-produto SEM citar IF.data/share ("saldo de cheque especial do Itaú?") segue para o
    # TEXTO — o release traz o saldo e o gate decide; R7 só protege o caminho COMPUTADO. Ver ADR-0005.
    # Para CARTEIRA (saldo), o sinal de SQL é ranking/série/2+ bancos — saldo SPOT de sub-produto
    # ("saldo de cheque especial do Itaú?") continua indo pro TEXTO, como documentado acima.
    if s.subproduto_fora and not s.declarado and (
            s.cita_ifdata or s.metrica == "market_share"
            or (s.metrica == "carteira" and (s.superlativo or s.serie or len(s.bancos) >= 2))):
        return (f"R7: '{s.subproduto_fora}' é um sub-recorte fora da granularidade do IF.data "
                f"(carteira PF separa em: {MODALIDADES_IFDATA_TXT}). O número por sub-produto não é "
                f"computável; posso dar a modalidade-pai (SQL) ou o que o release declara (texto).")

    return None


# --------------------------------------------------------------------------
# Estágio 1 (continuação) — classificação do caminho (só se estiver no escopo).
# Precedência: comparação cross-bank -> confronto declarado-vs-computado -> número puro -> fato único.
# --------------------------------------------------------------------------

def _classificar_caminho(s: Slots) -> str:
    # comparativo: market share COMPUTADO de 2+ bancos -> compara as séries (cross-bank), tudo em SQL.
    # `not declarado` é o mesmo desempate da Q3 (computada): share que o CEO DECLAROU é fato de TEXTO,
    # não cálculo SQL — então share declarado por 2 bancos cai no texto (doc_unico), não no comparativo.
    # "Pede NÚMERO do IF.data": a palavra share/participação, OU a fonte citada com a MODALIDADE
    # nomeada ("quem lidera em cartão segundo o IF.data?"), OU ranking de uma modalidade explícita
    # ("qual banco lidera o consignado?" — o fraseio que a PRÓPRIA recusa computada sugere; auditoria
    # final). `cita_ifdata` sozinho NÃO basta — "o que o Bacen mudou na 4.966?" é pergunta de TEXTO
    # sobre as notas; a palavra 'Bacen' não sequestra a rota. Guardas do ranking: `declarado` segura
    # "maior desafio citado pelo CEO" no texto; sem modalidade do Bacen ("maior lucro"), texto também.
    # CARTEIRA (saldo em R$) segue o princípio "absoluto = release; dinâmica/comparação = IF.data":
    # o saldo SPOT ("qual o saldo no 4T25?") fica no TEXTO — o release é a autoridade e a auditoria
    # de 10/06 mostrou que as fontes se confirmam (R$ 75,3 bi nos dois). Série ("como evoluiu a
    # carteira...") e comparação de 2+ bancos vêm pro SQL, que é quem tem a série e o cross-bank.
    pede_carteira_sql = (s.metrica == "carteira" and s.modalidade_explicita
                         and (s.serie or len(s.bancos) >= 2))
    pede_numero = (s.metrica == "market_share" or (s.cita_ifdata and s.modalidade_explicita)
                   or (s.superlativo and s.modalidade_explicita) or pede_carteira_sql)
    # RANKING ("qual banco lidera/tem o maior share?") é comparativo sem banco nomeado OU com UM SÓ
    # ("o Itaú é o maior?"): comparar só a série do nomeado respondia OUTRA pergunta ("qual o share
    # dele?") com cara de completa. rotear() preenche com TODOS os cobertos — o corpo lista cada
    # banco e o veredito de duas pontas mostra onde o nomeado ficou.
    if pede_numero and not s.declarado and (len(s.bancos) >= 2 or s.superlativo):
        return "comparativo"
    # multi_fonte: cruza o DECLARADO (texto) com o COMPUTADO/realizado (número).
    if s.confronto and (s.declarado or s.cita_ifdata):
        return "multi_fonte"
    # computada: número do IF.data — share PONTUAL ou série. Market share não vive confiável em texto;
    # a 4ª bateria provou que exigir "segundo o IF.data"/"evoluiu" mandava a pergunta MAIS NATURAL do
    # caso ("qual o share do BB no agro em 2024?") pro texto -> recusa de algo computável. O `not
    # declarado` desempata o caso Q3: share que o CEO DECLAROU é fato de TEXTO -> doc_unico.
    if pede_numero and not s.declarado:
        return "computada"
    return "doc_unico"


# --------------------------------------------------------------------------
# A rota: o que o roteador devolve para o resto do sistema.
# --------------------------------------------------------------------------

@dataclass
class Rota:
    categoria: str                 # uma de CATEGORIAS
    bancos: list[str]              # entidades detectadas (chaves de ENTIDADES)
    anos: list[int]                # anos detectados
    metrica: str                   # rótulo grosso da métrica
    periodos: list[str] = field(default_factory=list)  # trimestres ("4T25") p/ filtro de metadados
    modalidade: str = MODALIDADE_FOCO  # produto do Bacen p/ o caminho de números (default consignado)
    modalidade_explicita: bool = False  # a pergunta nomeou o produto? (senão, o pipeline avisa que assumiu)
    janela_aberta: bool = False        # "trimestres seguintes"/"desde" -> a janela de números NÃO fecha no
                                       # ano citado (a pergunta do PDF: "disse em 2023... subiu DEPOIS?")
    janela_ate: bool = False           # "até 2024" -> o período citado é o TETO; a série começa do início
                                       # da base (espelho da janela aberta, pelo outro lado)
    motivo_recusa: str | None = None   # preenchido quando categoria == "nao_respondivel"
    resposta_pronta: str | None = None  # preenchido quando categoria == "direta" (saudação/meta)

    @property
    def deve_recusar(self) -> bool:
        return self.categoria == "nao_respondivel"


# Saudação e meta-pergunta sobre o SISTEMA não são perguntas de conhecimento: a resposta não está
# em PDF nenhum (está no config) — buscar seria errado nos dois sentidos. "Bom dia" ecoava a
# transcrição do Bradesco (que tem 'bom dia' literal, nota > 0,60) com 5 fontes; "quais bancos
# estão na base?" recusava algo que o sistema SABE. Camada de UX, não um 5º caminho de retrieval.
_SAUDACAO_RE = re.compile(   # casa a MENSAGEM INTEIRA: "bom dia, qual o lucro..." NÃO entra aqui
    r"^(bom dia|boa tarde|boa noite|oi+|ola|opa|e ai|eai|hey|hello|hi"
    r"|obrigad[oa]s?|valeu|tudo bem|td bem|tudo bom|teste|ping)[\s!?.,]*$")
_RESPOSTA_SAUDACAO = (
    "Olá! Pergunte sobre os bancos cobertos — Itaú, Bradesco, Banco do Brasil, Santander e Nubank: "
    "lucro, market share por modalidade (cartão, consignado, veículos...), guidance, custo de crédito. "
    "Toda resposta sai citada; o que não está na base é recusado com o motivo.")
_RESPOSTA_COBERTURA = (   # janelas: as mesmas que o R1 e a recusa do caminho computado já declaram
    "Cobertura atual — bancos: Itaú, Bradesco, Banco do Brasil, Santander e Nubank. "
    "Texto (releases, transcrições e notas do Bacen, ingeridos por manifesto): 3T25 a 1T26. "
    "Números (Bacen IF.data, carteira PF por modalidade, share computado em SQL): 3T23 a 4T25. "
    "Fora disso, o sistema recusa com o motivo.")


def _resposta_direta(t: str) -> str | None:
    """Resposta de sistema (sem retrieval) p/ saudação e meta-pergunta de cobertura; None = segue o fluxo."""
    if _SAUDACAO_RE.match(t.strip()):
        return _RESPOSTA_SAUDACAO
    if (re.search(r"\b(quais?|que) (bancos|fontes|documentos|empresas)\b", t)
            and re.search(r"base|cobert|disponiv|voce (tem|cobre|atende)", t)) \
            or re.search(r"qual (e |eh )?a cobertura( da base)?|o que (tem|ha|existe) na base", t):
        return _RESPOSTA_COBERTURA
    return None


def rotear(pergunta: str) -> Rota:
    """Decide o caminho da pergunta: escopo primeiro (recusa cedo), depois o caminho."""
    direta = _resposta_direta(_sem_acento(pergunta))
    if direta is not None:
        return Rota("direta", [], [], "outra", resposta_pronta=direta)
    s = extrair_slots(pergunta)
    motivo = _gate_escopo(s)
    if motivo is not None:
        return Rota("nao_respondivel", s.bancos, s.anos, s.metrica,
                    periodos=s.periodos, modalidade=s.modalidade,
                    modalidade_explicita=s.modalidade_explicita, motivo_recusa=motivo)
    categoria = _classificar_caminho(s)
    bancos = s.bancos
    if categoria == "comparativo" and len(bancos) < 2:
        bancos = list(ENTIDADES)   # ranking sem banco nomeado (ou com UM: "o Itaú é o maior?"):
                                   # compara TODOS os cobertos e o veredito elege o líder real
    return Rota(categoria, bancos, s.anos, s.metrica,
                periodos=s.periodos, modalidade=s.modalidade,
                modalidade_explicita=s.modalidade_explicita, janela_aberta=s.janela_aberta,
                janela_ate=s.janela_ate)
