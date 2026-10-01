"""End-to-end smoke tests for the panel server embedded in install-panel.sh.

The server Python is extracted from its heredoc at runtime, imported with
Linux-only modules stubbed, and the request handlers are exercised through
fake requests (login, 2FA, observer role, external API, settings pages).
Run from the repository root:  python tests/test_server.py
"""
import io, json, os, re, sys, types, importlib.util, tempfile, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

_lines = open("install-panel.sh", encoding="utf-8").read().split("\n")
_start = _lines.index("cat > \"$APP_FILE\" <<'PY'")
_end = _lines.index("PY", _start + 1)
_code = "\n".join(_lines[_start + 1:_end])
for _m in ('grp', 'pwd'): sys.modules.setdefault(_m, types.ModuleType(_m))
_tmp = tempfile.mkdtemp()
_extract_path = os.path.join(_tmp, "onyx_server_extract.py")
open(_extract_path, "w", encoding="utf-8").write(_code)
_spec = importlib.util.spec_from_file_location("onyx_server_extract", _extract_path)
srv = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(srv)

import onyx_webapi, onyx_access, onyx_totp
import onyx_telegram as tg

store={"admin":{"user":"admin","hash":srv.hash_password("secret1")},
       "expires":{},"logins":[],"seen_devices":[],"api_keys":[],"telegram":{},"totp":{}}
srv.load=lambda: json.loads(json.dumps(store))
def _save(d): store.clear(); store.update(json.loads(json.dumps(d)))
srv.save=_save
profiles=[{"id":"aabbccddeeff0011","name":"Клиент Тест","protocol":"vless","enabled":True,"secret":"SECR","backend_port":443}]
srv.users=lambda: json.loads(json.dumps(profiles))
srv.traffic=lambda: {"aabbccddeeff0011":{"up":100,"down":200,"last_change":1,"service_active":True}}
srv.xray_path=lambda: "/vless-abcdefabcdefabcdefabcdef"
ctl_calls=[]
srv.ctl=lambda *a: ctl_calls.append(a) or ({"id":"newid0001","name":"x"} if a[0]=="add" else {"ok":True})
srv.ctl_manager_json=lambda cmd,req: {"id":"mtid0001","name":req.get("name")}

class FakeHandler(srv.Handler):
    def __init__(self, method, path, headers=None, body=b""):
        self.command=method; self.path=path; self.request_version="HTTP/1.1"; self.requestline=method+" "+path
        self.client_address=("203.0.113.9",5555)
        import email.message
        self.headers=email.message.Message()
        for k,v in (headers or {}).items(): self.headers[k]=v
        self.rfile=io.BytesIO(body); self.wfile=io.BytesIO()
    def output(self): return self.wfile.getvalue().decode("utf-8","replace")
    def status(self): return self.output().split("\r\n")[0]
    def resp_cookie(self):
        m=re.search(r"Set-Cookie: (sid=[^;\r\n]+)", self.output())
        return ("Cookie", m.group(1)) if m else None
    def resp_json(self):
        return json.loads(self.output().split("\r\n\r\n",1)[1])
    def form_post(self, cookie, fields):
        body=urllib.parse.urlencode(fields).encode()
        h=FakeHandler("POST", self.path if isinstance(self.path,str) else path, dict([cookie]) if cookie else {})
        h.headers["Content-Type"]="application/x-www-form-urlencoded"; h.headers["Content-Length"]=str(len(body))
        h.rfile=io.BytesIO(body); h.wfile=io.BytesIO()
        h.do_POST(); return h

def login_post(user="admin",pw="secret1",code=None):
    form=f"user={user}&password={pw}"+(f"&code={code}" if code is not None else "")
    body=form.encode()
    h=FakeHandler("POST", srv.PANEL_PATH+"/login", {"Content-Type":"application/x-www-form-urlencoded","Content-Length":str(len(body)),"User-Agent":"TestUA/1.0"}, body)
    h.do_POST(); return h

h=login_post(); assert "303" in h.status() and store["logins"][0]["new_device"] is True
print("1) admin login OK")
login_post(); assert store["logins"][-1]["new_device"] is False
print("2) device dedup OK")

store["observer"]={"user":"helper","hash":srv.hash_password("view123")}
h=login_post("helper","view123"); assert "303" in h.status()
ck=h.resp_cookie()
h2=FakeHandler("GET", srv.PANEL_PATH+"/settings", dict([ck])); h2.do_GET()
assert "303" in h2.status() and "dashboard" in h2.output()
h3=FakeHandler("GET", srv.PANEL_PATH+"/users", dict([ck])); h3.do_GET()
assert "200" in h3.status() and 'data-role="observer"' in h3.output()
print("3) observer gating OK")
h4=FakeHandler("POST", srv.PANEL_PATH+"/add-user", {"Cookie":ck[1],"Content-Type":"application/x-form","Content-Length":"6","X-Onyx-Async":"1"}, b"csrf=x")
h4.do_POST(); assert "403" in h4.status()
print("4) observer POST blocked")

key,token=onyx_webapi.new_key("bot"); store["api_keys"]=[key]
h5=FakeHandler("GET", srv.PANEL_PATH+"/api/v1/clients", {"Authorization":"Bearer "+token}); h5.web_api("clients","GET")
data=h5.resp_json()
assert "200" in h5.status() and data["ok"] and data["clients"][0]["name"]=="Клиент Тест" and data["clients"][0]["link"]
h5b=FakeHandler("GET", srv.PANEL_PATH+"/api/v1/clients", {"Authorization":"Bearer onx_wrong"}); h5b.web_api("clients","GET")
assert "401" in h5b.status()
print("5) API list + 401 OK")

body=json.dumps({"name":"Новый клиент","protocol":"vless","devices":2}).encode()
h6=FakeHandler("POST", srv.PANEL_PATH+"/api/v1/clients", {"Authorization":"Bearer "+token,"Content-Length":str(len(body))}, body)
h6.web_api("clients","POST")
print("   create ->", h6.status(), "| ctl:", ctl_calls[-1] if ctl_calls else None)
assert "201" in h6.status() and ctl_calls[-1][0]=="add", (h6.status(), h6.output()[:300], ctl_calls)
profiles.append({"id":"newid0001","name":"Новый клиент","protocol":"vless","enabled":True,"secret":"NEWSECRET","backend_port":443})
h6b=FakeHandler("POST", srv.PANEL_PATH+"/api/v1/clients/newid0001/renew", {"Authorization":"Bearer "+token,"Content-Length":"12"}, b'{"days":30}')
h6b.web_api("clients/newid0001/renew","POST"); assert "200" in h6b.status() and store["expires"].get("newid0001"), (h6b.status(), h6b.output()[:200])
h6c=FakeHandler("POST", srv.PANEL_PATH+"/api/v1/clients/newid0001/toggle", {"Authorization":"Bearer "+token,"Content-Length":"20"}, b'{"enabled":false}')
h6c.web_api("clients/newid0001/toggle","POST"); assert ctl_calls[-1][:3]==("set-user","newid0001","0")
h6d=FakeHandler("POST", srv.PANEL_PATH+"/api/v1/clients/newid0001/delete", {"Authorization":"Bearer "+token,"Content-Length":"2"}, b'{}')
h6d.web_api("clients/newid0001/delete","POST"); assert ctl_calls[-1][:2]==("delete","newid0001")
print("6) API create/renew/toggle/delete OK")
assert store["api_keys"][0]["last_used"]>0
print("7) key last_used OK")

store["totp"]={"secret":onyx_totp.generate_secret(),"enabled":True}
h8=login_post(); assert "401" in h8.status()
h8=login_post(code=onyx_totp.totp_at(store["totp"]["secret"])); assert "303" in h8.status()
print("8) 2FA gate OK")

store["totp"]={}
ha=login_post(); cka=ha.resp_cookie()
h9=FakeHandler("GET", srv.PANEL_PATH+"/settings", dict([cka])); h9.do_GET()
out=h9.output()
for marker in ("Уведомления Telegram","tgForm","Автобэкап","totpSetupBtn","observerForm","apiKeyForm","login-log","Журнал входов"):
    assert marker in out, "missing: "+marker
assert 'data-role="admin"' in out
print("9) settings page new cards OK")

h10=FakeHandler("GET", srv.PANEL_PATH+"/cascade", dict([cka])); h10.do_GET()
assert "data-failover-switch" in h10.output() and "Автопереключение" in h10.output()
print("10) cascade failover toggle rendered OK")

hb=FakeHandler("POST", srv.PANEL_PATH+"/backups-save", dict([cka]))
bodyb=urllib.parse.urlencode({"csrf":hb.csrf(),"mode":"telegram","hour":"9","keep":"10"}).encode()
hb.headers["Content-Type"]="application/x-www-form-urlencoded"; hb.headers["Content-Length"]=str(len(bodyb))
hb.rfile=io.BytesIO(bodyb); hb.wfile=io.BytesIO()
hb.do_POST()
jb=hb.resp_json()
assert "200" in hb.status() and "Расписание" in jb["message"], (hb.status(), hb.output()[:200])
assert store["backups"]["mode"]=="telegram" and store["backups"]["hour"]==9
print("11) backups-save OK")

import onyx_telegram as tg
def boom(t): raise RuntimeError("Unauthorized")
srv.telegram_api.get_me=boom
ht=FakeHandler("POST", srv.PANEL_PATH+"/telegram-save", dict([cka]))
bodyt=urllib.parse.urlencode({"csrf":ht.csrf(),"token":"123:bad","chat":"1","action":"save","event_expiry":"1"}).encode()
ht.headers["Content-Type"]="application/x-www-form-urlencoded"; ht.headers["Content-Length"]=str(len(bodyt))
ht.rfile=io.BytesIO(bodyt); ht.wfile=io.BytesIO()
ht.do_POST()
assert "400" in ht.status() and "Telegram" in ht.output(), (ht.status(), ht.output()[:200])
print("12) telegram-save invalid token -> 400 OK")

captured={}
class FakeResp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self,*a): return False
import urllib.request as _ur
def fake_urlopen(req, timeout=None):
    captured["body"]=req.data; captured["headers"]=req.headers
    return FakeResp(b'{"ok":true}')
_urlopen_orig=_ur.urlopen; _ur.urlopen=fake_urlopen
tg.send_document("123:tok","42","backup.tar.gz",b"PAYLOAD")
_ur.urlopen=_urlopen_orig
body=captured["body"]; ctype=captured["headers"]["Content-type"]
assert "multipart/form-data" in ctype and b"PAYLOAD" in body and b'filename="backup.tar.gz"' in body
print("13) send_document multipart OK")

cascades=[{"id":"a"*16,"name":"Primary","enabled":True,"mode":"all","uuid":"0"*32,"address":"up.example","port":443,"network":"tcp","security":"none","stream":{}},
          {"id":"b"*16,"name":"Reserve","enabled":False,"mode":"all","uuid":"1"*32,"address":"up2.example","port":443,"network":"tcp","security":"none","stream":{}}]
seen={}
srv.cascade_api.load_cascades=lambda p: json.loads(json.dumps(cascades))
def fake_save(p,cs): seen["saved"]=json.loads(json.dumps(cs))
srv.cascade_api.save_cascades=fake_save
srv.cascade_api.ping=lambda r: {"ok":False,"ms":0,"message":"down","checked_at":1}
FA=srv.FAILOVER_FAILURES; FA.clear()
FA=srv.onyx_failover.note_result(FA,"a"*16,False)
FA=srv.onyx_failover.note_result(FA,"a"*16,False)
action=srv.onyx_failover.decide(srv.cascade_api.load_cascades(None),FA)
assert action=={"disable":"a"*16,"enable":"b"*16}, action
for c in cascades:
    if c.get("id")==action["disable"]: c["enabled"]=False
    if c.get("id")==action["enable"]: c["enabled"]=True
assert cascades[0]["enabled"] is False and cascades[1]["enabled"] is True
print("14) failover decision + swap OK")

# 15) dashboard renders palette + top consumers card
h15=FakeHandler("GET", srv.PANEL_PATH+"/dashboard", dict([cka])); h15.do_GET()
out=h15.output()
assert "paletteDialog" in out and "Топ потребителей трафика" in out and 'data-role="admin"' in out
print("15) dashboard palette + top consumers OK")

# 16) login page shows 2FA code field only when enabled
store["totp"]={"secret":onyx_totp.generate_secret(),"enabled":True}
h16=FakeHandler("GET", srv.PANEL_PATH+"/login"); h16.do_GET()
assert "loginCode" in h16.output()
store["totp"]={}
h16b=FakeHandler("GET", srv.PANEL_PATH+"/login"); h16b.do_GET()
assert "loginCode" not in h16b.output()
print("16) login 2FA field conditional OK")

# 17) settings page carries live preview pane and preset thumbs
out=h17=None
h17=FakeHandler("GET", srv.PANEL_PATH+"/settings", dict([cka])); h17.do_GET()
out=h17.output()
assert "customPresetLive" in out and "data-preset-card" in out
print("17) editor live preview pane OK")
print("ALL SERVER SMOKE TESTS PASSED")
