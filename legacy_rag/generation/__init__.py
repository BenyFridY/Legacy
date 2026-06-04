"""Etapas 5-6 — Geração da resposta (com citação e recusa).

Módulos planejados:
- llm.py    → interface `LLMClient` trocável (ADR-0003): claude_code / gemini_free / groq_free /
              ollama / anthropic. Trocar de provider = uma linha no .env.
- answer.py → orquestra: pergunta → roteador → caminho(s) → monta o prompt com os trechos/números
              recuperados → o LLM redige a resposta CITANDO a fonte, ou RECUSA se não há base.

A recusa é estrutural (caminho vazio / score abaixo do limiar), não "bom senso" do LLM (Aula 1).
"""
