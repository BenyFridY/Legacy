"""Testa o GroqClient, a fabrica criar_llm e o carregador de .env — SEM tocar a rede.

O GroqClient faz HTTP; mockamos requests.post para provar que (a) monta o payload certo,
(b) parseia a resposta no formato OpenAI, (c) falha com mensagem clara sem chave. A qualidade
do texto gerado nao se testa aqui (depende do modelo real) — isso e a demo da resolucao do case.
"""
import sys
import types

import pytest

from legacy_rag.env import carregar_dotenv
from legacy_rag.generation.llm import GroqClient, criar_llm


class _FakeResp:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")   # simula requests.HTTPError
    def json(self):
        return self._payload


def _mock_requests(monkeypatch, capturado):
    """Injeta um modulo 'requests' falso cujo post() grava o que recebeu e devolve resposta OpenAI."""
    mod = types.ModuleType("requests")
    def post(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, headers=headers, json=json, timeout=timeout)
        return _FakeResp({"choices": [{"message": {"content": "RESPOSTA REDIGIDA"}}]})
    mod.post = post
    monkeypatch.setitem(sys.modules, "requests", mod)


def test_groq_monta_payload_e_parseia(monkeypatch):
    cap = {}
    _mock_requests(monkeypatch, cap)
    cli = GroqClient(api_key="gsk_teste")
    out = cli.completar("Pergunta?")
    assert out == "RESPOSTA REDIGIDA"
    assert cap["json"]["temperature"] == 0.0                       # determinístico
    assert cap["json"]["messages"][0]["content"] == "Pergunta?"
    assert cap["headers"]["Authorization"] == "Bearer gsk_teste"


def test_groq_retry_em_429(monkeypatch):
    """429 na 1ª chamada, 200 na 2ª -> retorna a resposta (provou o retry com backoff)."""
    chamadas = {"n": 0}
    mod = types.ModuleType("requests")
    def post(url, headers=None, json=None, timeout=None):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            return _FakeResp(None, status_code=429, headers={"Retry-After": "0"})
        return _FakeResp({"choices": [{"message": {"content": "OK DEPOIS DO RETRY"}}]})
    mod.post = post
    monkeypatch.setitem(sys.modules, "requests", mod)
    monkeypatch.setattr("legacy_rag.generation.llm.time.sleep", lambda _: None)  # não espera de verdade
    cli = GroqClient(api_key="gsk_x")
    assert cli.completar("x") == "OK DEPOIS DO RETRY"
    assert chamadas["n"] == 2


def test_groq_429_persistente_levanta(monkeypatch):
    """429 em todas as tentativas -> esgota e levanta (erro claro, não silencioso)."""
    mod = types.ModuleType("requests")
    mod.post = lambda url, headers=None, json=None, timeout=None: _FakeResp(None, status_code=429)
    monkeypatch.setitem(sys.modules, "requests", mod)
    monkeypatch.setattr("legacy_rag.generation.llm.time.sleep", lambda _: None)
    cli = GroqClient(api_key="gsk_x", max_tentativas=3)
    with pytest.raises(Exception):
        cli.completar("x")


def test_groq_content_nulo_vira_string_vazia(monkeypatch):
    """content:null (ex.: content_filter) -> "" e não None, senão os consumidores quebram em .strip()."""
    mod = types.ModuleType("requests")
    mod.post = lambda url, headers=None, json=None, timeout=None: _FakeResp(
        {"choices": [{"message": {"content": None}}]})
    monkeypatch.setitem(sys.modules, "requests", mod)
    assert GroqClient(api_key="gsk_x").completar("x") == ""


def test_groq_sem_chave_falha_claro(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cli = GroqClient(api_key=None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        cli.completar("x")


def test_criar_llm_por_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_x")
    assert isinstance(criar_llm("groq_free"), GroqClient)
    assert criar_llm("claude_code") is None                        # cai no fallback determinístico
    assert criar_llm("qualquer_outro") is None


def test_carregar_dotenv_nao_sobrescreve(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('GROQ_API_KEY="gsk_do_arquivo"\n# comentario\nLLM_PROVIDER=groq_free\n',
                   encoding="utf-8")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "ja_definido")              # ambiente tem precedência
    lidos = carregar_dotenv(env)
    assert lidos["GROQ_API_KEY"] == "gsk_do_arquivo"               # aspas removidas
    import os
    assert os.environ["GROQ_API_KEY"] == "gsk_do_arquivo"         # injetado (não existia)
    assert os.environ["LLM_PROVIDER"] == "ja_definido"            # NÃO sobrescreveu


def test_carregar_dotenv_ausente_ok(tmp_path):
    assert carregar_dotenv(tmp_path / "nao_existe.env") == {}
