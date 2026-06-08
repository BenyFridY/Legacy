"""Ingestão de releases — baixa o PDF da fonte pública e extrai o texto (ADR-0001/0004).

Por que baixar do CDN e não da página de RI?
    As páginas de Relações com Investidores dos bancos respondem **HTTP 403** a um cliente
    programático (anti-robô). Mas o ARQUIVO em si mora num CDN público da plataforma mziq
    (filemanager-cdn.mziq.com / api.mziq.com). Pegamos os bytes direto de lá.

Duas responsabilidades, separadas de propósito:
    baixar(url)            -> bytes do PDF        (toca a REDE; pode falhar/variar no tempo)
    extrair_paginas(bytes) -> [texto por página]  (função PURA; mesmos bytes => mesmo texto)

Guardamos o texto PÁGINA A PÁGINA porque a citação — um não-negociável do case — precisa
apontar "banco X, período Y, documento Z, página N". A página é a âncora da citação; por
isso ela é a unidade que preservamos já na extração (o chunking, no próximo passo, herda).
"""
from __future__ import annotations

import io
import time

import requests
from pypdf import PdfReader

# Mesmo User-Agent identificável que usamos no cliente do Bacen: educado e rastreável.
_HEADERS = {"User-Agent": "LegacyCase/0.1 (research; beny.frid@hashdex.com)"}
MAX_TENTATIVAS = 3


def baixar(url: str, timeout: int = 120, tentativas: int = MAX_TENTATIVAS) -> bytes:
    """Baixa os bytes crus de um PDF público, com retry/backoff em falha TRANSITÓRIA.

    Mesma política do cliente do Bacen (bacen._get_json): um PDF de ~6MB do CDN às vezes corta no
    meio (ChunkedEncodingError) ou bate num 5xx momentâneo -> tenta de novo com backoff. Já um erro
    4xx (403/404) é PERMANENTE -> propaga na hora, sem retry inútil. Um 200 cujo corpo NÃO começa com
    "%PDF" (página HTML/captcha em vez do arquivo) também é permanente -> levanta ValueError na hora.
    A separação baixar (impuro) x extrair (puro) segue: a responsabilidade aqui é só "trazer o arquivo".
    """
    erro: Exception | None = None
    for i in range(max(1, tentativas)):    # sempre ≥1 tentativa (evita 'raise None' se tentativas<=0)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=timeout)
            resp.raise_for_status()        # levanta HTTPError em 4xx e 5xx
            if not resp.content.startswith(b"%PDF"):   # 200, mas NÃO é PDF -> permanente, não adianta repetir
                raise ValueError(
                    f"resposta não é PDF (status {resp.status_code}, {len(resp.content)} bytes, "
                    f"início {resp.content[:16]!r}): provável página HTML/captcha em vez do arquivo.")
            return resp.content
        except requests.exceptions.HTTPError as e:
            sc = getattr(e.response, "status_code", None)
            if sc is not None and 400 <= sc < 500:
                raise                       # 4xx = permanente (URL errada / bloqueio) -> não insiste
            erro = e                        # 5xx = transitório -> vale tentar de novo
            time.sleep(2.0 * (i + 1))
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            erro = e                        # falha de rede -> backoff e retry
            time.sleep(2.0 * (i + 1))
    raise erro                              # esgotou as tentativas -> propaga o último erro


def extrair_paginas(pdf_bytes: bytes) -> list[str]:
    """Texto de cada página do PDF (lista: índice 0 = página 1; índice n-1 = página n).

    Pressuposto: o PDF tem CAMADA DE TEXTO (os releases dos bancos têm — são gerados a partir
    de texto, não escaneados). Um PDF que fosse imagem pura exigiria OCR, o que está fora do
    escopo; se algum dia aparecer, ele se denuncia aqui devolvendo páginas vazias.
    """
    leitor = PdfReader(io.BytesIO(pdf_bytes))
    return [(pagina.extract_text() or "") for pagina in leitor.pages]


def extrair_texto(pdf_bytes: bytes) -> str:
    """Texto do documento inteiro (páginas unidas por quebra dupla — conveniência sobre extrair_paginas)."""
    return "\n\n".join(extrair_paginas(pdf_bytes))
