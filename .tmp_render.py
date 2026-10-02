"""Render real panel pages with stub data for visual/functional verification."""
import http.server
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import test_server as ts  # runs the smoke tests, exposes srv + FakeHandler + login_post

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.tmp_render')
os.makedirs(OUT, exist_ok=True)

h = ts.login_post()
cookie = h.resp_cookie()
ts.srv.DOMAIN = 'panel.test.local'

# Synthetic VPS metrics so the dashboard traffic chart renders with data.
import math
import time as _time
_now = int(_time.time())
_history = [{'time': _now - (59 - i) * 60,
             'up_rate': int(400000 + 2600000 * abs(math.sin(i / 5.5)) + (i * 37000) % 700000),
             'down_rate': int(2600000 + 7800000 * abs(math.cos(i / 7.5)) + (i * 51000) % 900000)}
            for i in range(60)]
ts.srv.server_metrics.dashboard_data = lambda hours=1: {
    'latest': {'time': _now, 'cpu': 17, 'cores': 4,
               'ram_used': 2100000000, 'ram_total': 4000000000,
               'swap_used': 0, 'swap_total': 2000000000,
               'disk_used': 12000000000, 'disk_total': 40000000000,
               'traffic_fresh': True,
               'services': {'xray': {'state': 'active'}, 'relay': {'state': 'active'}, 'awg': {'state': 'inactive'},
                            'openflux': {'state': 'inactive'}, 'caddy': {'state': 'active'}, 'panel': {'state': 'active'}}},
    'history': [p for p in _history if p['time'] >= _now - hours * 3600],
    'collector_error': {}}

pages = {
    'login': ts.srv.PANEL_PATH + '/login',
    'dashboard': ts.srv.PANEL_PATH + '/dashboard',
    'users': ts.srv.PANEL_PATH + '/users',
    'nodes': ts.srv.PANEL_PATH + '/nodes',
    'cascade': ts.srv.PANEL_PATH + '/cascade',
    'routing': ts.srv.PANEL_PATH + '/routing',
    'updates': ts.srv.PANEL_PATH + '/updates',
    'settings': ts.srv.PANEL_PATH + '/settings',
}
for name, page_path in pages.items():
    try:
        hh = ts.FakeHandler('GET', page_path, dict([cookie]) if cookie else {})
        hh.do_GET()
        body = hh.output().split('\r\n\r\n', 1)[1]
        with open(os.path.join(OUT, name + '.html'), 'w', encoding='utf-8') as f:
            f.write(body)
        print(name, '->', len(body), 'bytes')
    except Exception as exc:
        print(name, 'FAILED:', exc)

REPO = os.path.dirname(os.path.abspath(__file__))


class Render(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, p):
        if p.startswith('/__font/'):
            return os.path.join(REPO, 'fonts', os.path.basename(p))
        if p == '/__logo':
            return os.path.join(REPO, 'onyx-logo.png')
        if p.startswith('/__qr') or p.startswith('/xray/__qr'):
            return os.path.join(REPO, 'onyx-logo.png')
        return super().translate_path(p)

    def log_message(self, *a):
        pass


os.chdir(OUT)
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 8644), Render)
print('render server on http://127.0.0.1:8644/login.html')
srv.serve_forever()
