"""Eval runner — fecha o laço entre as perguntas (eval/questions.yaml) e o sistema.

ESCOPO DESTE RUNNER (honesto, ver crítico nº4 do painel de validação): ele mede a
RECUSA-POR-ESCOPO (Estágio 1 do gate) ponta-a-ponta, SEM precisar de modelo nenhum.
Por quê dá pra medir já: a decisão "isto está fora da base, recuse" é tomada pelo
ROTEADOR DETERMINÍSTICO (regras R1/R2/R3) — não depende de embedding nem reranker.

O que este runner AINDA NÃO mede (espera os modelos reais + gold de chunk_id):
  - recusa-por-EVIDÊNCIA (Estágio 2: nota do reranker < limiar);
  - qualidade de retrieval (hit@k, P@k, R@k, MRR) — precisa dos embeddings reais e do
    gold de quais chunks são relevantes, fixado na ingestão.

Ou seja: este é o primeiro NÚMERO REAL do eval — a regra inegociável "recuse quando
não está na base", na parte que o roteador resolve sozinho. O n é pequeno (uma dúzia de
perguntas): o número é uma sanidade forte, não uma estatística de população (reportamos o n junto).

CIRCULARIDADE (honesto): estas perguntas e as regras R1/R2/R3 co-evoluíram (mesmo autor) -> o placar
mede CONSISTÊNCIA INTERNA do gate de escopo, não generalização para perguntas não vistas.
"""
from __future__ import annotations

from dataclasses import dataclass

import yaml

from legacy_rag.config import ROOT
from legacy_rag.eval.metrics import RefusalCounts, score_refusals
from legacy_rag.router.router import Rota, rotear

CAMINHO_PADRAO = ROOT / "eval" / "questions.yaml"
CAMINHO_ESTENDIDO = ROOT / "eval" / "questions_estendido.yaml"   # 36 fraseios extra (rota + recusa)


# --------------------------------------------------------------------------
# Carregar o conjunto de perguntas.
# --------------------------------------------------------------------------

def carregar_perguntas(caminho=CAMINHO_PADRAO) -> list[dict]:
    """Lê o eval/questions.yaml e devolve a lista de perguntas (dicts)."""
    with open(caminho, encoding="utf-8") as f:
        dados = yaml.safe_load(f)
    return dados["questions"]


# --------------------------------------------------------------------------
# Prever o comportamento (answer/refuse) que o sistema teria — só com o roteador.
# --------------------------------------------------------------------------

def prever_comportamento(pergunta: str) -> tuple[str, Rota]:
    """Roteia a pergunta; recusa-por-escopo -> 'refuse', caso contrário -> 'answer'.

    (No sistema completo, um 'answer' aqui ainda pode virar 'refuse' depois, no
    Estágio 2, se o retrieval não trouxer evidência boa. Este runner mede só o Estágio 1.)
    """
    rota = rotear(pergunta)
    return ("refuse" if rota.deve_recusar else "answer"), rota


# --------------------------------------------------------------------------
# Avaliar o conjunto inteiro.
# --------------------------------------------------------------------------

@dataclass
class LinhaResultado:
    id: str
    esperado: str          # answer | refuse (do yaml)
    previsto: str          # answer | refuse (do roteador)
    categoria: str         # rota.categoria
    motivo: str | None     # motivo de recusa, se houver
    ok: bool               # previsto == esperado
    rota_esperada: str | None = None   # expected_route do yaml (bateria estendida); None = não checa
    rota_ok: bool | None = None        # categoria == rota_esperada (None quando não checa)


@dataclass
class ResultadoEscopo:
    linhas: list[LinhaResultado]
    contagem: RefusalCounts
    distribuicao_rotas: dict[str, int]   # quantas perguntas em cada categoria de rota

    @property
    def acertos(self) -> int:
        return sum(1 for l in self.linhas if l.ok)

    @property
    def total(self) -> int:
        return len(self.linhas)


def avaliar_recusa_por_escopo(perguntas: list[dict]) -> ResultadoEscopo:
    """Roteia todas as perguntas e monta a matriz de confusão de recusa (Estágio 1)."""
    linhas: list[LinhaResultado] = []
    distribuicao: dict[str, int] = {}
    for q in perguntas:
        esperado = q["expected_behavior"]
        rota_esp = q.get("expected_route")          # opcional (bateria estendida): checa a ROTA também
        previsto, rota = prever_comportamento(q["question"])
        distribuicao[rota.categoria] = distribuicao.get(rota.categoria, 0) + 1
        linhas.append(LinhaResultado(
            id=q["id"], esperado=esperado, previsto=previsto,
            categoria=rota.categoria, motivo=rota.motivo_recusa, ok=(previsto == esperado),
            rota_esperada=rota_esp,
            rota_ok=(rota.categoria == rota_esp) if rota_esp else None,
        ))
    contagem = score_refusals((l.esperado, l.previsto) for l in linhas)
    return ResultadoEscopo(linhas=linhas, contagem=contagem, distribuicao_rotas=distribuicao)


# --------------------------------------------------------------------------
# Relatório legível (para o terminal e para a apresentação).
# --------------------------------------------------------------------------

def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def formatar_relatorio(r: ResultadoEscopo,
                       titulo: str = "EVAL - Recusa por ESCOPO (Estagio 1, roteador deterministico, sem modelo)",
                       rodape: list[str] | None = None) -> str:
    L = []
    L.append("=" * 72)
    L.append(titulo)
    L.append("=" * 72)
    L.append(f"{'id':<38} {'esperado':<9} {'previsto':<9} {'ok':<3} rota")
    L.append("-" * 72)
    for l in r.linhas:
        marca = "ok" if (l.ok and l.rota_ok is not False) else "X"
        L.append(f"{l.id:<38} {l.esperado:<9} {l.previsto:<9} {marca:<3} {l.categoria}")
    L.append("-" * 72)

    c = r.contagem
    L.append("Matriz de confusao de recusa:")
    L.append(f"  recusas corretas (recusou certo) ............. {c.correct_refusals}")
    L.append(f"  alucinacoes (respondeu o que devia recusar) .. {c.false_answers}")
    L.append(f"  respostas corretas (respondeu certo) ......... {c.correct_answers}")
    L.append(f"  recusas indevidas (recusou demais) ........... {c.false_refusals}")
    L.append("")
    L.append(f"  Taxa de recusa correta ... {_pct(c.correct_refusal_rate)}   (dos que DEVIAM recusar)")
    L.append(f"  Taxa de over-recusa ...... {_pct(c.over_refusal_rate)}   (dos respondiveis, recusou por engano)")
    L.append(f"  Acuracia de comportamento  {r.acertos}/{r.total}")
    com_rota = [l for l in r.linhas if l.rota_ok is not None]
    if com_rota:
        L.append(f"  Rota correta ............. {sum(1 for l in com_rota if l.rota_ok)}/{len(com_rota)}"
                 "   (categoria prevista == esperada)")
    L.append("")
    L.append(f"Distribuicao de rotas: {r.distribuicao_rotas}")
    for linha in (rodape if rodape is not None else [
        f"(n={r.total}: sanidade forte, nao estatistica de populacao. Estagio 2 e retrieval",
        " esperam os modelos reais + gold de chunk_id fixado na ingestao.)",
        "CIRCULARIDADE: estas perguntas e as regras R1/R2/R3 co-evoluiram (mesmo autor) -> mede",
        " consistencia INTERNA do gate de escopo, NAO generalizacao p/ perguntas nao vistas.",
    ]):
        L.append(linha)
    L.append("=" * 72)
    return "\n".join(L)


def main() -> None:
    perguntas = carregar_perguntas()
    resultado = avaliar_recusa_por_escopo(perguntas)
    print(formatar_relatorio(resultado))
    if CAMINHO_ESTENDIDO.exists():
        ext = avaliar_recusa_por_escopo(carregar_perguntas(CAMINHO_ESTENDIDO))
        print()
        print(formatar_relatorio(
            ext,
            titulo="EVAL ESTENDIDO - 36 fraseios extra (rota + recusa, Estagio 1, sem modelo)",
            rodape=[
                f"(n={ext.total}; tambem checa a ROTA, nao so recusar/responder.)",
                "Fraseios escritos APOS o congelamento das regras (10/06) — reduz, nao elimina,",
                " a circularidade do conjunto oficial (mesmo autor, fraseios nao vistos).",
            ]))


if __name__ == "__main__":
    main()
