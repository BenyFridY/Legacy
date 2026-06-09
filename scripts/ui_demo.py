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
    "Qual banco teve o maior market share em consignado no 4T25?",          # ranking (comparativo de todos)
    "Entre o Banco do Brasil e o Bradesco, quem ganhou mais participacao em consignado de 2023 a 2024?",  # comparativo (cross-bank, janela)
    "O market share de consignado do Bradesco no balanco bate com o que computamos do Bacen IF.data?",  # multi_fonte
    "Qual a receita de um bolo de cenoura?",                               # recusa por evidencia (fora de escopo)
    "Qual sera o custo de credito do Bradesco no 2o trimestre de 2027?",   # recusa por escopo (R1, roteador)
]

PAGINA = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Legacy Capital - Retrieval Demo</title>
<style>
 :root{--verde:#1a4d36;--verde2:#2a6b4d;--verde-claro:#eaf3ee;--bg:#eef2f0;--card:#fff;
       --linha:#e3e9e5;--texto:#16261f;--suave:#5b6b62}
 *{box-sizing:border-box} html,body{height:100%}
 body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
      background:linear-gradient(180deg,#eef2f0,#e4ede8);color:var(--texto);
      display:flex;flex-direction:column;height:100vh}
 header{background:linear-gradient(120deg,var(--verde),var(--verde2));color:#fff;padding:18px 28px;
        display:flex;align-items:center;gap:18px;flex-shrink:0;box-shadow:0 2px 16px rgba(26,77,54,.28)}
 header .logo{height:62px;width:62px;border-radius:15px;background:#fff;padding:9px;display:flex;
              align-items:center;justify-content:center;box-shadow:0 3px 10px rgba(0,0,0,.18)}
 header .logo img{max-height:100%;max-width:100%}
 header h1{margin:0;font-size:19px;font-weight:700;letter-spacing:.3px}
 header p{margin:4px 0 0;color:#cfe3d8;font-size:12.5px}
 main{flex:1;display:flex;flex-direction:column;width:100%;max-width:900px;margin:0 auto;padding:0 18px;overflow:hidden}
 #thread{flex:1;overflow-y:auto;padding:22px 2px}
 .vazio{color:var(--suave);font-size:14.5px;text-align:center;margin-top:48px;line-height:1.7}
 .vazio b{color:var(--verde)}
 .msg-user{display:flex;justify-content:flex-end;margin:14px 0}
 .msg-user .bolha{background:linear-gradient(135deg,var(--verde),var(--verde2));color:#fff;
      border-radius:18px 18px 5px 18px;padding:11px 16px;max-width:78%;font-size:15px;line-height:1.45;
      box-shadow:0 2px 10px rgba(26,77,54,.2)}
 .msg-bot{display:flex;margin:14px 0}
 .card{background:var(--card);border:1px solid var(--linha);border-radius:18px 18px 18px 5px;padding:18px;
       max-width:88%;box-shadow:0 4px 18px rgba(20,38,31,.08)}
 .badge{display:inline-block;padding:4px 12px;border-radius:999px;font-size:11px;font-weight:700;color:#fff;
        letter-spacing:.5px;text-transform:uppercase}
 .doc_unico{background:#2563eb}.computada{background:#0d9488}.comparativo{background:#0e7490}.multi_fonte{background:#7c3aed}.nao_respondivel{background:#d97706}
 .meta{font-size:12px;color:var(--suave);margin:11px 0 4px}
 .resp{white-space:pre-wrap;font-size:15px;line-height:1.55;margin-top:4px}
 .recusa{background:#fff7ed;border:1px solid #fed7aa;border-radius:10px;padding:13px;color:#9a3412;font-size:14.5px}
 .fontes{margin-top:15px;border-top:1px dashed var(--linha);padding-top:11px}
 .fontes h4{margin:0 0 7px;font-size:10.5px;text-transform:uppercase;letter-spacing:.6px;color:var(--suave)}
 .fontes ul{margin:0;padding-left:18px} .fontes li{font-size:13px;color:var(--verde);margin:2px 0}
 .spin{color:var(--suave);font-size:14.5px;display:flex;align-items:center;gap:9px}
 .dot{width:8px;height:8px;border-radius:50%;background:var(--verde);animation:pulse 1s infinite}
 @keyframes pulse{0%,100%{opacity:.25}50%{opacity:1}}
 .composer{flex-shrink:0;padding:14px 0 20px}
 .chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
 .chip{background:#fff;border:1px solid var(--linha);border-radius:999px;padding:7px 14px;font-size:12.5px;
       cursor:pointer;color:var(--verde);box-shadow:0 1px 3px rgba(0,0,0,.04);transition:all .15s}
 .chip:hover{background:var(--verde-claro);border-color:var(--verde2)}
 .row{display:flex;gap:10px;align-items:flex-end;background:#fff;border:1px solid var(--linha);
      border-radius:16px;padding:8px 8px 8px 16px;box-shadow:0 4px 16px rgba(20,38,31,.09)}
 textarea{flex:1;border:0;outline:none;background:transparent;padding:8px 0;font-size:15.5px;resize:none;
          max-height:140px;font-family:inherit;line-height:1.45;color:var(--texto)}
 button{background:linear-gradient(135deg,var(--verde),var(--verde2));color:#fff;border:0;border-radius:12px;
        padding:12px 22px;font-size:14px;font-weight:600;cursor:pointer;transition:filter .15s}
 button:hover{filter:brightness(1.1)}
</style></head><body>
<header>
 <div class="logo"><img src="/logo.png" alt="Legacy Capital"></div>
 <div><h1>Legacy Capital &middot; Research de Equities</h1>
 <p>Retrieval ao vivo &middot; roteador deterministico &middot; citacao por construcao &middot; recusa honesta</p></div>
</header>
<main>
 <div id="thread"><div class="vazio">Pergunte sobre os bancos - lucro, market share, guidance, custo de credito.<br>Toda resposta vem <b>citada</b>; se nao esta na base, o sistema <b>recusa</b>.<br><small>Cada pergunta e independente (sem memoria de conversa) - faca a pergunta completa.</small></div></div>
 <div class="composer">
  <div class="chips" id="chips"></div>
  <div class="row">
   <textarea id="q" rows="1" placeholder="Pergunte algo... (Enter envia, Shift+Enter quebra linha)"></textarea>
   <button onclick="perguntar()">Enviar</button>
  </div>
 </div>
</main>
<script>
const EXEMPLOS = __EXEMPLOS__;
const thread=document.getElementById('thread'), chips=document.getElementById('chips'), q=document.getElementById('q');
EXEMPLOS.forEach(function(e){var c=document.createElement('span');c.className='chip';c.textContent=e;
 c.onclick=function(){q.value=e;perguntar();};chips.appendChild(c);});
function esc(s){var d=document.createElement('div');d.textContent=(s==null?'':s);return d.innerHTML;}
function rolar(){thread.scrollTop=thread.scrollHeight;}
function addUser(t){var v=thread.querySelector('.vazio'); if(v) v.remove();
 var d=document.createElement('div');d.className='msg-user';d.innerHTML='<div class="bolha">'+esc(t)+'</div>';
 thread.appendChild(d);rolar();}
function addBot(html){var d=document.createElement('div');d.className='msg-bot';d.innerHTML=html;thread.appendChild(d);rolar();return d;}
async function perguntar(){
 var texto=q.value.trim(); if(!texto) return;
 addUser(texto); q.value=''; q.style.height='auto';
 var ph=addBot('<div class="card"><div class="spin"><span class="dot"></span>Consultando o sistema...</div></div>');
 try{
  var r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pergunta:texto})});
  var d=await r.json();
  if(d.erro){ph.innerHTML='<div class="card recusa">Erro: '+esc(d.erro)+'</div>';rolar();return;}
  var meta='banco(s): '+(d.bancos.length?d.bancos.join(', '):'-')+' | ano(s): '+(d.anos.length?d.anos.join(', '):'-')+' | metrica: '+d.metrica;
  var corpo;
  if(d.recusou){corpo='<div class="recusa"><b>Recusa honesta - nao disponivel na base.</b><br>'+esc(d.motivo||'')+'</div>';}
  else{corpo='<div class="resp">'+esc(d.texto)+'</div>';}
  var fontes='';
  if(d.citacoes&&d.citacoes.length){fontes='<div class="fontes"><h4>Fontes (anexadas por codigo)</h4><ul>'+d.citacoes.map(function(c){return '<li>'+esc(c)+'</li>';}).join('')+'</ul></div>';}
  ph.innerHTML='<div class="card"><span class="badge '+d.categoria+'">'+d.categoria+'</span><div class="meta">'+esc(meta)+'</div>'+corpo+fontes+'</div>';
  rolar();
 }catch(err){ph.innerHTML='<div class="card recusa">Erro: '+esc(String(err))+'</div>';rolar();}
}
q.addEventListener('input',function(){q.style.height='auto';q.style.height=Math.min(q.scrollHeight,140)+'px';});
q.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();perguntar();}});
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
    print(">>> Carregando modelos (uma vez, ~1-2 min na primeira vez)...")
    DEPS = construir_deps()
    redator = type(DEPS.llm).__name__ if DEPS.llm else "NENHUM (sem chave -> mostra evidencia citada)"
    print(f">>> Redator: {redator}")
    print(f">>> UI de demo no ar: http://localhost:{PORTA}  (Ctrl+C para parar)")
    try:
        HTTPServer(("127.0.0.1", PORTA), Handler).serve_forever()
    except KeyboardInterrupt:    # Ctrl+C e o jeito anunciado de parar: sair limpo, sem traceback na tela
        print("\n>>> Demo encerrada.")


if __name__ == "__main__":
    main()
