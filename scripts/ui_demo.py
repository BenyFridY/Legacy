"""UI de DEMO (apresentação) — telinha local para perguntar ao sistema VIVO.

NÃO vale ponto na rubrica (o case diz explicitamente que não liga para UI). Existe só como
APARATO DE DEMONSTRAÇÃO ao vivo: mostra na tela a ROTA que o roteador escolheu, a resposta CITADA
e a RECUSA honesta — tornando a arquitetura dual-path visível numa apresentação.

Por que servidor `http.server` e não Streamlit: neste ambiente (conda+Windows) o torch precisa ser
importado ANTES do numpy (ver torch_env). O Streamlit importa numpy no startup, ANTES do nosso código,
o que quebraria o carregamento dos modelos. Um servidor da biblioteca padrão nos deixa controlar a
ordem (preparar_torch primeiro) e carregar os modelos UMA vez — e não adiciona dependência nenhuma.

Uso:
  set KMP_DUPLICATE_LIB_OK=TRUE & set PYTHONPATH=. & set PYTHONIOENCODING=utf-8 & python scripts/ui_demo.py
  -> abre em http://localhost:8000
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from legacy_rag.runtime import construir_deps   # preparar_torch() roda no import (torch antes de numpy)
from legacy_rag.config import ROOT
from legacy_rag.pipeline import responder
from legacy_rag.router.router import rotear

PORTA = 8000
LOGO = ROOT / "assets" / "legacy-logo.png"      # logo da Legacy, servido em /logo.png
DEPS = None  # carregado UMA vez em main()

# Exemplos ROBUSTOS de propósito (cobrem as 4 rotas + 2 tipos de recusa). Evita-se a frase
# "lucro liquido recorrente": ela é borderline (o doc usa "Resultado Recorrente Gerencial") e o
# LLM, mesmo a temp 0, oscila entre responder e recusar — péssimo para uma demo ao vivo.
EXEMPLOS = [
    "Qual foi o Resultado Recorrente Gerencial do Itau no 4T25?",         # doc_unico (texto) - robusto
    "Qual foi o indice de Basileia do Itau no 4T25?",                      # doc_unico - fora do eval (generaliza)
    "Como evoluiu o market share do Banco do Brasil em consignado nos ultimos trimestres?",  # computada (SQL)
    "O market share de consignado do Bradesco no balanco bate com o que computamos do Bacen IF.data?",  # multi_fonte
    "Qual a receita de um bolo de cenoura?",                               # recusa por evidencia (fora de escopo)
    "Qual sera o custo de credito do Bradesco no 2o trimestre de 2027?",   # recusa por escopo (R1, roteador)
]

PAGINA = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legacy Capital - Retrieval Demo</title>
<style>
 :root{--verde:#1a4d36;--verde2:#246b4f;--bg:#f4f7f5;--card:#fff;--linha:#e2e8e4;--texto:#1c2b24}
 *{box-sizing:border-box} body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--texto)}
 header{background:#fff;border-bottom:3px solid var(--verde);padding:14px 24px;display:flex;align-items:center;gap:16px}
 header img{height:46px;width:auto}
 header .ht h1{margin:0;font-size:16px;font-weight:700;color:var(--verde);letter-spacing:.2px}
 header .ht p{margin:3px 0 0;color:#5b6b62;font-size:12.5px}
 main{max-width:880px;margin:24px auto;padding:0 16px}
 .card{background:var(--card);border:1px solid var(--linha);border-radius:12px;padding:18px;margin-bottom:16px;box-shadow:0 1px 2px rgba(0,0,0,.04)}
 textarea{width:100%;border:1px solid var(--linha);border-radius:8px;padding:12px;font-size:15px;resize:vertical;min-height:64px;font-family:inherit}
 button{background:var(--verde);color:#fff;border:0;border-radius:8px;padding:10px 18px;font-size:14px;font-weight:600;cursor:pointer}
 button:hover{background:var(--verde2)}
 .chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
 .chip{background:#eef3f0;border:1px solid var(--linha);border-radius:999px;padding:6px 12px;font-size:12.5px;cursor:pointer;color:var(--verde)}
 .chip:hover{background:#e0eae5}
 .badge{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:700;color:#fff}
 .doc_unico{background:#2563eb}.computada{background:#0d9488}.multi_fonte{background:#7c3aed}.nao_respondivel{background:#d97706}
 .meta{font-size:12.5px;color:#5b6b62;margin:10px 0}
 .resp{white-space:pre-wrap;font-size:15px;line-height:1.5;margin-top:6px}
 .recusa{background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:12px;color:#9a3412}
 .fontes{margin-top:14px;border-top:1px dashed var(--linha);padding-top:10px}
 .fontes h4{margin:0 0 6px;font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:#5b6b62}
 .fontes li{font-size:13px;color:var(--verde)} .spin{color:#5b6b62;font-size:14px}
</style></head><body>
<header><img src="/logo.png" alt="Legacy Capital">
<div class="ht"><h1>Retrieval para Research de Equities</h1>
<p>Demo ao vivo - roteador deterministico - citacao por construcao - recusa honesta</p></div></header>
<main>
 <div class="card">
  <textarea id="q" placeholder="Pergunte algo sobre os bancos (ex.: lucro do Itau no 4T25, market share de consignado do BB)..."></textarea>
  <div style="margin-top:10px"><button onclick="perguntar()">Perguntar</button></div>
  <div class="chips" id="chips"></div>
 </div>
 <div id="saida"></div>
</main>
<script>
const EXEMPLOS = __EXEMPLOS__;
const chips=document.getElementById('chips');
EXEMPLOS.forEach(function(e){const c=document.createElement('span');c.className='chip';c.textContent=e;
 c.onclick=function(){document.getElementById('q').value=e;perguntar();};chips.appendChild(c);});
function esc(s){const d=document.createElement('div');d.textContent=(s==null?'':s);return d.innerHTML;}
async function perguntar(){
 const q=document.getElementById('q').value.trim(); if(!q) return;
 const saida=document.getElementById('saida');
 saida.innerHTML='<div class="card spin">Consultando o sistema...</div>';
 try{
  const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pergunta:q})});
  const d=await r.json();
  const meta='banco(s): '+(d.bancos.length?d.bancos.join(', '):'-')+' | ano(s): '+(d.anos.length?d.anos.join(', '):'-')+' | metrica: '+d.metrica;
  let corpo;
  if(d.recusou){corpo='<div class="recusa"><b>Recusa honesta - nao disponivel na base.</b><br>'+esc(d.motivo||'')+'</div>';}
  else{corpo='<div class="resp">'+esc(d.texto)+'</div>';}
  let fontes='';
  if(d.citacoes&&d.citacoes.length){fontes='<div class="fontes"><h4>Fontes (anexadas por codigo)</h4><ul>'+d.citacoes.map(function(c){return '<li>'+esc(c)+'</li>';}).join('')+'</ul></div>';}
  saida.innerHTML='<div class="card"><span class="badge '+d.categoria+'">'+d.categoria+'</span><div class="meta">'+esc(meta)+'</div>'+corpo+fontes+'</div>';
 }catch(err){saida.innerHTML='<div class="card recusa">Erro: '+esc(String(err))+'</div>';}
}
</script></body></html>
"""


def _payload(pergunta: str) -> dict:
    """Roteia + responde e empacota tudo que a tela mostra (rota, resposta, citações, recusa)."""
    rota = rotear(pergunta)
    resp = responder(pergunta, DEPS)
    return {
        "categoria": rota.categoria, "bancos": rota.bancos, "anos": rota.anos, "metrica": rota.metrica,
        "texto": resp.texto, "citacoes": resp.citacoes, "recusou": resp.recusou, "motivo": resp.motivo,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, codigo: int, corpo: bytes, ctype: str) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        if self.path == "/logo.png":
            try:
                return self._send(200, LOGO.read_bytes(), "image/png")
            except Exception:
                return self._send(404, b"sem logo", "text/plain; charset=utf-8")
        if self.path != "/":
            return self._send(404, b"nao encontrado", "text/plain; charset=utf-8")
        html = PAGINA.replace("__EXEMPLOS__", json.dumps(EXEMPLOS, ensure_ascii=False))
        self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")

    def do_POST(self):
        if self.path != "/ask":
            return self._send(404, b"nao encontrado", "text/plain; charset=utf-8")
        tam = int(self.headers.get("Content-Length", 0))
        try:
            pergunta = json.loads(self.rfile.read(tam) or b"{}").get("pergunta", "")
            corpo = json.dumps(_payload(pergunta), ensure_ascii=False).encode("utf-8")
            self._send(200, corpo, "application/json; charset=utf-8")
        except Exception as e:  # demo: erro vira JSON legível em vez de derrubar o servidor
            self._send(500, json.dumps({"erro": str(e)}).encode("utf-8"), "application/json; charset=utf-8")

    def log_message(self, *args):  # silencia o log ruidoso por requisição
        pass


def main() -> None:
    global DEPS
    print(">>> Carregando modelos (uma vez)...")
    DEPS = construir_deps()
    redator = type(DEPS.llm).__name__ if DEPS.llm else "NENHUM (sem chave -> mostra evidencia citada)"
    print(f">>> Redator: {redator}")
    print(f">>> UI de demo no ar: http://localhost:{PORTA}  (Ctrl+C para parar)")
    HTTPServer(("127.0.0.1", PORTA), Handler).serve_forever()


if __name__ == "__main__":
    main()
