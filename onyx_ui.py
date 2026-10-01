"""Dependency-free admin UI: theme tokens, unified accounts and real metrics."""
import html
import json
import math
import os
import re
import time
from urllib.parse import urlencode, urlsplit, parse_qs

VERSION = '1.5.1'


def esc(value): return html.escape(str(value), quote=True)


def size(value):
    if value is None: return '—'
    value = max(0, float(value))
    for unit in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if value < 1024 or unit == 'ТБ': return ('%.0f' if unit == 'Б' else '%.1f') % value + ' ' + unit
        value /= 1024


def duration(value):
    if value is None: return '—'
    value = max(0, int(value))
    return f'{value//86400} д. {value%86400//3600} ч.' if value >= 86400 else f'{value//3600} ч. {value%3600//60} мин.'


def icon(name):
    paths = {'grid': '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
             'users': '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M17 4a3 3 0 0 1 0 6m1 4a5 5 0 0 1 3 4v3"/>',
             'settings': '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="8" cy="18" r="2"/>',
             'nodes': '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01M11 6.5h6M11 17.5h6"/>',
             'cascade': '<path d="m12 2-10 5 10 5 10-5-10-5Z"/><path d="m2 12.5 10 5 10-5"/><path d="m2 17.5 10 5 10-5"/>',
             'power': '<path d="M12 3v8"/><path d="M17.4 6.6a8 8 0 1 1-10.8 0"/>',
             'route': '<circle cx="5" cy="19" r="2"/><circle cx="19" cy="5" r="2"/><path d="M7 19h6a4 4 0 0 0 4-4V9"/><path d="m17 6 3-3 2 4-5-1Z"/>',
             'logout': '<path d="M10 4H4v16h6m4-12 4 4-4 4m-6-4h10"/>',
             'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
             'refresh': '<path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6"/>',
             'chart': '<path d="M3 3v18h18M6 15l4-5 4 3 6-8"/>',
             'link': '<path d="m10 13 4-4m-6 5-2 2a3 3 0 0 0 4 4l3-3m-2-10 3-3a3 3 0 0 1 4 4l-2 2"/>',
             'copy':'<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V4H4v12h4"/>',
             'edit':'<path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14z"/>',
             'qr':'<path d="M3 3h6v6H3zM15 3h6v6h-6zM3 15h6v6H3zM15 15h2v2h-2zM21 15v6h-6"/>',
             'trash':'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
             'search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
             'github': '<path d="M9 21v-3c-4 1-4-2-6-2m12 5v-4c0-1-.4-1.7-1-2 3-.4 5-1.5 5-5a4 4 0 0 0-1-3c.3-1 0-3 0-3-2 0-3 1-3 1a11 11 0 0 0-6 0S8 4 6 4c0 0-.3 2 0 3a4 4 0 0 0-1 3c0 3.5 2 4.6 5 5-.6.3-1 1-1 2"/>',
             'gitlab': '<path d="m3 10 3-7 3 7h6l3-7 3 7-3 9-6 3-6-3z"/>',
             'youtube': '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3z"/>',
             'menu': '<path d="M4 7h16M4 12h16M4 17h16"/>',
             'plus': '<path d="M12 5v14M5 12h14"/>'}
    return '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+paths.get(name, paths['grid'])+'</svg>'


CSS = '''
:root{color-scheme:dark;--bg:#071116;--surface:#0f2028;--raised:#152b35;--input:#0a1920;--line:#24404b;--text:#e9f4f6;--muted:#91aeb8;--accent:#56decb;--on-accent:#052820;--tint:#56decb12;--green:#8bdbaa;--red:#ff9993;--amber:#f5c989;--shadow:0 18px 60px #0003}
:root[data-theme=light]{color-scheme:light;--bg:#eaf0ed;--surface:#fbfdfb;--raised:#eff5f1;--input:#f5f8f5;--line:#cfddd5;--text:#142f2b;--muted:#5d7870;--accent:#087c6d;--on-accent:#fff;--tint:#087c6d0c;--green:#27754b;--red:#b94042;--amber:#886124;--shadow:0 18px 50px #153b2310}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}body{margin:0;min-width:320px;-webkit-text-size-adjust:100%;background:var(--bg);color:var(--text);font:14px/1.55 "Segoe UI",system-ui,sans-serif}button,input,select,textarea{font:inherit}button,input,select,textarea,a,summary{outline-offset:4px}a{color:var(--accent)}button{cursor:pointer;touch-action:manipulation}button:disabled{opacity:.45;cursor:not-allowed}h1,h2,h3,p{overflow-wrap:anywhere}h1{font-size:34px;line-height:1.15;letter-spacing:-.055em;margin:0;font-weight:650}h2{font-size:17px;margin:0;font-weight:600;letter-spacing:-.02em}h3{font-size:15px;margin:0}p{margin:8px 0 16px}.muted,small,.sub{color:var(--muted)}.ico{width:18px;height:18px;flex:0 0 auto}.eyebrow{display:block;font:10px/1.5 ui-monospace,monospace;letter-spacing:.18em;color:var(--accent);text-transform:uppercase;margin-bottom:9px}
.app{height:100dvh;padding:14px;display:grid;grid-template-columns:218px minmax(0,1fr);gap:14px}.sidebar{display:flex;flex-direction:column;min-height:0;overflow:auto;background:var(--surface);border:1px solid var(--line);border-radius:22px;padding:22px 14px}.brand{display:flex;gap:11px;align-items:center;padding:0 6px 20px}.brand img{width:42px;height:42px;border-radius:13px}.brand b{font-size:12px;letter-spacing:.035em}.brand small{display:block;font:10px/1.7 ui-monospace,monospace;margin-top:3px}.brand-tools{padding:0 6px 25px;display:flex;gap:8px}.brand-tools button{width:100%;justify-content:flex-start;font-size:11px;background:transparent}.nav{display:grid;gap:8px}.nav a,.logout{display:flex;align-items:center;gap:12px;padding:13px 14px;border:1px solid transparent;border-radius:12px;color:var(--muted);text-decoration:none;font-size:13px;font-weight:550}.nav a.active{background:var(--accent);color:var(--on-accent)}.nav a:hover:not(.active),.logout:hover{background:var(--raised);color:var(--text)}.side-footer{margin-top:auto;padding-top:32px}.logout{color:var(--muted)}.social{display:flex;justify-content:center;gap:16px;padding-top:21px;border-top:1px solid var(--line);margin-top:14px}.social a{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:10px;text-decoration:none}.social .ico{width:14px;height:14px}.workspace{min-width:0;overflow:auto;scrollbar-width:thin;scrollbar-color:var(--line) transparent}main{max-width:1560px;margin:0 auto;padding:24px 24px 44px}.page-head{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:26px}.page-head p{font-size:13px;color:var(--muted);margin:8px 0 0}.card,.account{min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:18px}.card{padding:23px;margin-bottom:18px}.card-title{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:20px}.card-title h2{display:flex;align-items:center;gap:8px}.btn,button{display:inline-flex;align-items:center;justify-content:center;gap:8px;padding:10px 14px;border:1px solid var(--line);background:var(--raised);color:var(--text);border-radius:10px;text-decoration:none;font-size:12px;font-weight:550;line-height:1.4}.btn:hover,button:hover{border-color:var(--accent)}.btn.primary,button.primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}button.danger,.btn.danger{background:transparent;color:var(--red)}button.quiet,.btn.quiet{background:transparent}.actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.actions form{margin:0}.note{margin:15px 0;padding:12px 15px;border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:9px;background:var(--tint);font-size:12px;color:var(--muted);overflow-wrap:anywhere}.note.warning{border-left-color:var(--amber);color:var(--amber)}.note code{font-size:11px;overflow-wrap:anywhere}input,textarea,select{width:100%;min-width:0;border:1px solid var(--line);background:var(--input);color:var(--text);padding:11px 13px;border-radius:10px}input:focus,textarea:focus,select:focus{border-color:var(--accent)}input[type=checkbox]{width:16px;height:16px;accent-color:var(--accent);cursor:pointer}label{display:block;font-size:12px;font-weight:550;color:var(--muted);margin:13px 0 7px}.checks{display:flex;gap:18px;flex-wrap:wrap;margin:18px 0}.check{display:flex;align-items:center;gap:8px;margin:0;color:var(--text)}.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.badge{display:inline-flex;align-items:center;gap:6px;font-size:11px;white-space:nowrap;color:var(--muted)}.badge:before{content:"";width:5px;height:5px;border-radius:50%;background:var(--muted)}.badge.on{color:var(--green)}.badge.on:before{background:var(--green)}.pill{display:inline-flex;align-items:center;padding:3px 7px;border-radius:6px;border:1px solid var(--line);font-size:10px;line-height:1.5;color:var(--muted)}.pills{display:flex;flex-wrap:wrap;gap:5px}.proto-vless{color:var(--accent);background:var(--tint)}.proto-hysteria{color:var(--amber)}.proto-web{color:var(--green)}
.overview-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:22px}.overview-stat{padding:17px 19px;border-left:2px solid var(--line)}.overview-stat:first-child{border-color:var(--accent)}.overview-stat span{display:block;font-size:11px;color:var(--muted)}.overview-stat b{display:block;font:500 29px/1.3 ui-monospace,monospace;letter-spacing:-.07em;margin-top:5px}.dashboard-grid{display:grid;grid-template-columns:minmax(0,1.8fr) minmax(280px,1fr);gap:18px}.graph-card{background:linear-gradient(145deg,var(--surface),var(--input));border-top:2px solid var(--accent)}.graph-speeds{display:flex;gap:38px;margin:26px 0 0}.graph-speeds span{font-size:11px;color:var(--muted);display:block}.graph-speeds b{font:500 25px/1.8 ui-monospace,monospace;letter-spacing:-.05em}.graph-speeds small{font-size:11px;color:var(--muted)}.chart-wrap{height:250px;margin:6px 0 15px}.chart-wrap svg{display:block;width:100%;height:100%;overflow:visible}.chart-wrap text{fill:var(--muted);font:10px ui-monospace,monospace}.chart-empty{height:100%;display:flex;flex-direction:column;gap:12px;align-items:center;justify-content:center;text-align:center;color:var(--muted);font-size:12px}.chart-empty .ico{width:34px;height:34px;opacity:.6}.range{display:flex;gap:3px;padding:3px;border:1px solid var(--line);border-radius:9px}.range button{border:0;background:transparent;font-size:11px;padding:5px 9px}.range button.selected{background:var(--tint);color:var(--accent)}.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:10px;color:var(--muted)}.legend i{display:inline-block;width:7px;height:7px;border-radius:3px;background:var(--accent);margin-right:6px}.legend .down i{background:var(--amber)}.service-list{display:grid}.service-line{display:flex;justify-content:space-between;align-items:center;gap:8px;border-bottom:1px solid var(--line);padding:15px 0;font-size:12px}.service-line:last-child{border-bottom:0}.node-domain{font-size:15px;font-weight:550;overflow-wrap:anywhere;margin-bottom:8px}.node-label{display:flex;align-items:center;gap:8px}.node-label i{display:block;width:8px;height:8px;border:2px solid var(--accent);border-radius:50%}.update-box{border-top:1px dashed var(--line);padding-top:20px;margin-top:20px}.update-box p{font-size:11px;color:var(--muted);margin:10px 0 0}.resource-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px}.resource{padding:19px;background:var(--surface);border:1px solid var(--line);border-radius:15px}.resource-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.resource strong{font-size:12px;font-weight:550}.resource-head b{font:500 20px ui-monospace,monospace;color:var(--accent)}.meter{height:4px;background:var(--line);border-radius:4px;overflow:hidden;margin-bottom:12px}.meter i{display:block;width:var(--value,0%);height:100%;background:var(--accent);border-radius:4px}.resource small{display:block;font-size:10px}.two-col.equal{display:grid;grid-template-columns:1fr 1fr;gap:18px}.detail-list{display:grid;gap:14px}.detail-line{display:flex;justify-content:space-between;gap:18px;font-size:12px}.detail-line span{color:var(--muted)}.detail-line strong{font-weight:550;text-align:right}.dashboard-clients{display:grid;gap:1px}.client-glance{display:grid;grid-template-columns:minmax(140px,1fr) minmax(100px,1fr) 120px auto;gap:16px;align-items:center;padding:15px 0;border-top:1px solid var(--line);font-size:12px}.client-glance:first-child{border-top:0}.client-glance strong{font-size:13px;overflow-wrap:anywhere}.client-glance small{display:block;margin-top:3px}.client-glance .btn{padding:6px 10px;font-size:11px}.client-glance .traffic-value{text-align:right}
.clients-summary{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));border:1px solid var(--line);background:var(--surface);border-radius:18px;margin-bottom:20px;padding:20px 5px}.client-stat{padding:2px 18px;border-right:1px solid var(--line)}.client-stat:last-child{border:0}.client-stat span{display:block;font-size:10px;color:var(--muted);white-space:nowrap}.client-stat b{display:block;margin-top:6px;font:500 23px ui-monospace,monospace}.client-stat:first-child b{color:var(--accent)}.client-stat:nth-child(3) b{color:var(--green)}.clients-panel{border:1px solid var(--line);background:var(--surface);border-radius:18px;overflow:hidden}.clients-toolbar{display:flex;align-items:center;gap:10px;padding:16px;border-bottom:1px solid var(--line);flex-wrap:wrap}.search-field{flex:1;min-width:180px;display:flex;align-items:center;gap:8px;padding-left:12px;border:1px solid var(--line);border-radius:10px;background:var(--input);color:var(--muted)}.search-field input{border:0;background:transparent;padding-left:0;font-size:12px}.clients-toolbar select{font-size:12px;width:auto;max-width:175px;padding:10px 30px 10px 11px}.table-scroll{overflow-x:auto;scrollbar-width:thin;scrollbar-color:var(--line) transparent}.clients-table{width:100%;min-width:930px;border-collapse:collapse;text-align:left;table-layout:auto}.clients-table th{font-size:10px;font-weight:500;letter-spacing:.03em;color:var(--muted);background:var(--raised);padding:12px 11px;white-space:nowrap}.clients-table td{padding:18px 11px;border-bottom:1px solid var(--line);font-size:12px;vertical-align:middle}.clients-table tr:last-child td{border-bottom:0}.clients-table tbody tr:hover{background:var(--tint)}.clients-table .select-col{width:40px;text-align:center;padding-right:4px}.clients-table .client-name{min-width:155px;max-width:240px}.client-name strong{display:block;font-size:13px;overflow-wrap:anywhere}.client-name small{display:block;color:var(--muted);font:10px/1.8 ui-monospace,monospace}.clients-table .protocol-col{max-width:160px;min-width:105px}.traffic-cell{min-width:120px}.traffic-cell b{font:500 12px ui-monospace,monospace}.traffic-cell small{display:block;font-size:9px;white-space:nowrap;margin-top:4px}.traffic-split{height:3px;margin-top:9px;background:var(--line);border-radius:4px;overflow:hidden;display:flex}.traffic-split i{height:100%;display:block}.traffic-split .up{background:var(--accent)}.traffic-split .down{background:var(--amber)}.hwid-cell{font:12px ui-monospace,monospace}.hwid-cell small{font:9px "Segoe UI",sans-serif;display:block}.row-actions{display:flex;gap:3px;align-items:center}.icon-btn{height:30px;width:30px;padding:6px;background:transparent;border-color:transparent;border-radius:8px;color:var(--muted)}.icon-btn .ico{width:16px;height:16px}.icon-btn:hover{color:var(--accent)}.icon-btn.danger:hover{color:var(--red);border-color:var(--red)}.access-switch{padding:0;width:33px;height:19px;background:var(--line);border:0;border-radius:20px;display:block;position:relative}.access-switch:after{content:"";position:absolute;top:3px;left:3px;width:13px;height:13px;background:var(--muted);border-radius:50%;transition:left .15s}.access-switch[aria-checked=true]{background:var(--accent)}.access-switch[aria-checked=true]:after{left:17px;background:var(--on-accent)}.access-switch:disabled{opacity:.6}.bulk-bar{padding:11px 16px;background:var(--tint);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:9px;flex-wrap:wrap}.bulk-bar strong{font-size:11px;margin-right:auto}.bulk-bar button{font-size:11px;padding:7px 11px}.list-footer{padding:13px 17px;border-top:1px solid var(--line);display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;font-size:10px;color:var(--muted)}.empty{padding:30px;text-align:center;color:var(--muted);font-size:13px}.table-loading{opacity:.6;pointer-events:none}
dialog{padding:25px;width:min(570px,calc(100vw - 32px));max-height:90vh;max-height:min(90dvh,calc(100dvh - 12px));overflow:auto;overscroll-behavior:contain;background:var(--surface);border:1px solid var(--line);color:var(--text);border-radius:20px;box-shadow:var(--shadow)}dialog::backdrop{background:#020d14aa;backdrop-filter:blur(7px)}.dialog-head{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px}.dialog-head h2{font-size:21px}.dialog-head button{padding:4px 10px;font-size:21px}
@media(max-width:760px){.dialog-head button{min-width:40px;min-height:40px}}.client-detail .account{padding:0;border:0;background:transparent}.account{padding:20px;margin:0}.account-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.account-head .identity{display:flex;align-items:center;gap:12px;min-width:0}.avatar{display:grid;place-items:center;width:40px;height:40px;flex-shrink:0;background:var(--tint);color:var(--accent);border-radius:12px}.account h3{font-size:16px}.account .pills{margin-top:5px}.account-metrics{display:flex;gap:22px;margin:20px 0;font-size:13px}.account-metrics span{display:block;font-size:10px;color:var(--muted);margin-bottom:4px}.account details{border-top:1px solid var(--line);padding-top:12px;margin-top:18px}.account summary{cursor:pointer;color:var(--muted);font-size:12px;padding:4px 0}.sub-url{font:11px/1.5 ui-monospace,monospace;margin-bottom:12px}.device{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 0;border-top:1px solid var(--line);font-size:12px}.device small{display:block;font-size:10px}.qr-image{display:block;width:100%;max-width:260px;padding:12px;background:#fff;border-radius:10px;margin:18px auto}.client-detail .account>details>summary{display:none}
.update-dialog{width:min(470px,calc(100vw - 28px));padding:0;overflow:auto}.update-dialog .dialog-head{padding:22px 24px 17px;margin:0;border-bottom:1px solid var(--line)}.update-dialog-body{padding:23px 24px}.update-release{display:flex;align-items:center;gap:14px;padding:16px;border:1px solid var(--line);border-radius:13px;background:var(--input)}.update-release-mark{display:grid;place-items:center;width:43px;height:43px;flex:0 0 auto;border-radius:12px;background:var(--tint);color:var(--accent)}.update-release-mark .ico{width:22px;height:22px}.update-release span{display:block;font-size:10px;color:var(--muted);margin-bottom:4px}.update-release strong{font:600 17px/1.3 ui-monospace,monospace}.update-dialog-body>p{margin:17px 0 0;color:var(--muted);font-size:12px;line-height:1.65}.update-dialog-actions{display:flex;justify-content:flex-end;gap:9px;padding:15px 24px 21px;border-top:1px solid var(--line)}
.release-banner{max-width:1512px;margin:14px auto 0;padding:13px 16px;display:flex;align-items:center;gap:13px;border:1px solid color-mix(in srgb,var(--accent) 55%,var(--line));border-radius:13px;background:linear-gradient(100deg,var(--tint),var(--surface) 58%);box-shadow:0 12px 34px #0002}.release-banner[hidden]{display:none}.release-banner-mark{display:grid;place-items:center;width:38px;height:38px;flex:0 0 auto;border-radius:11px;background:var(--accent);color:var(--on-accent)}.release-banner-mark .ico{width:19px;height:19px}.release-banner-copy{min-width:0;flex:1}.release-banner-copy b{display:block;font-size:12px}.release-banner-copy small{display:block;margin-top:2px;font-size:10px}.release-banner-version{font:600 11px ui-monospace,monospace;color:var(--accent);white-space:nowrap}.release-banner-actions{display:flex;align-items:center;gap:7px}.release-banner-actions .btn{padding:8px 12px}.release-banner-close{width:34px;height:34px;padding:6px;background:transparent;font-size:18px;color:var(--muted)}
@media(max-width:700px){.release-banner{margin:10px 8px 0;align-items:flex-start;flex-wrap:wrap}.release-banner-copy{width:calc(100% - 54px)}.release-banner-version{margin-left:51px}.release-banner-actions{margin-left:auto}.release-banner-actions .btn{font-size:11px}}
.version-manager{margin-top:18px}.version-manager h3{font-size:13px;margin:0 0 5px}.version-manager>p{margin:0 0 14px;color:var(--muted);font-size:10px}.version-row{display:grid;grid-template-columns:110px minmax(120px,1fr) auto;gap:8px;align-items:center;margin-top:9px}.version-row label{margin:0;font-size:11px}.version-row select{min-width:0;padding:9px}.version-row button{white-space:nowrap}.version-state{display:block;grid-column:2/-1;color:var(--muted);font-size:9px}
.updates-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;background:linear-gradient(135deg,var(--surface),var(--raised));border-top:2px solid var(--accent)}.updates-hero-copy{display:flex;align-items:center;gap:16px}.updates-hero-icon{display:grid;place-items:center;width:52px;height:52px;flex:0 0 auto;border-radius:15px;background:var(--tint);color:var(--accent)}.updates-hero-icon .ico{width:25px;height:25px}.updates-hero p{margin:6px 0 0;color:var(--muted);font-size:12px}.updates-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.updates-card{display:flex;flex-direction:column;margin:0}.updates-card .card-title{align-items:flex-start}.updates-card .card-title p{margin:6px 0 0;color:var(--muted);font-size:11px}.update-installed{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:14px 15px;margin-bottom:15px;border:1px solid var(--line);border-radius:11px;background:var(--input)}.update-installed span{font-size:11px;color:var(--muted)}.update-installed strong{font:600 13px ui-monospace,monospace}.update-control{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:end}.update-control label{grid-column:1/-1;margin-top:0}.update-control button{min-width:126px}.update-control button.comp-icon{min-width:44px;width:44px;height:44px;padding:0;justify-self:end}.update-control button.comp-icon .ico{width:18px;height:18px}.component-stack{display:grid;gap:12px}.component-item{padding:15px;border:1px solid var(--line);border-radius:12px;background:var(--input)}.component-item-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:12px}.component-item-head strong{font-size:13px}.component-item-head small{font:10px ui-monospace,monospace}.update-status{min-height:46px;margin:16px 0 0}.update-safety{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.update-safety div{padding:15px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.update-safety b{display:block;font-size:11px;margin-bottom:4px}.update-safety small{font-size:10px;line-height:1.55}
@media(max-width:900px){.updates-grid{grid-template-columns:1fr}.updates-hero{align-items:flex-start}.update-safety{grid-template-columns:1fr}}
@media(max-width:600px){.version-row{grid-template-columns:1fr}.version-state{grid-column:auto}.version-row button{width:100%}.updates-hero{display:block}.updates-hero>.actions{margin-top:16px}.update-control{grid-template-columns:1fr}.update-control button{width:100%}.updates-hero-copy{align-items:flex-start}}
.preset-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.preset{position:relative;display:flex;flex-direction:column;align-items:flex-start;min-width:0;padding:18px;background:var(--raised);border:1px solid var(--line);border-radius:14px}.preset .preset-art{display:grid;place-items:center;height:54px;width:100%;font-size:28px;border-bottom:1px dashed var(--line);padding-bottom:12px;margin-bottom:15px}.preset b{font-size:12px}.preset p{font-size:11px;color:var(--muted);margin:7px 0 18px}.preset button{width:100%;margin-top:auto;font-size:11px}.editor-bar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:13px 16px;font:11px ui-monospace,monospace;color:var(--muted);border:1px solid var(--line);border-bottom:0;border-radius:12px 12px 0 0;background:var(--raised)}.editor-bar i{font-style:normal;color:var(--accent)}.code-editor{display:block;min-height:340px;max-height:700px;padding:19px;border-radius:0 0 12px 12px;font:12px/1.9 ui-monospace,Consolas,monospace;resize:vertical;tab-size:2}.editor-actions{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:17px}.preview-dialog{width:min(1240px,calc(100vw - 32px));padding:0;overflow:auto}.preview-top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:15px 18px;border-bottom:1px solid var(--line)}.preview-top strong{font-size:13px}.preview-stage{display:flex;justify-content:center;padding:20px;background:var(--bg);height:min(72dvh,780px);min-height:240px}.preview-stage iframe{display:block;width:100%;max-width:100%;height:100%;border:1px solid var(--line);border-radius:10px;background:transparent}.preview-stage.phone iframe{width:390px;border-radius:24px}.preview-caption{margin:0;padding:10px 18px;border-top:1px solid var(--line);font-size:11px;color:var(--muted)}
.login-page{min-height:100dvh;display:grid;place-items:center;padding:28px;background:radial-gradient(ellipse at 15% 20%,var(--tint),transparent 65%),var(--bg)}.login-shell{width:min(910px,100%);display:grid;grid-template-columns:1.1fr 1fr;border:1px solid var(--line);border-radius:26px;overflow:hidden;background:var(--surface);box-shadow:var(--shadow)}.login-story{padding:48px;background:var(--input);display:flex;flex-direction:column;justify-content:space-between;min-height:440px;position:relative;overflow:hidden}.login-story:after{content:"";position:absolute;width:330px;height:330px;right:-180px;bottom:-180px;border:50px solid var(--tint);border-radius:50%;pointer-events:none}.login-brand{display:flex;gap:12px;align-items:center;font-size:12px;letter-spacing:.06em}.login-brand img{width:48px;height:48px;border-radius:15px}.login-story h2{font-size:40px;line-height:1.12;font-weight:500;letter-spacing:-.05em;max-width:290px}.login-story p{color:var(--muted);font-size:13px;max-width:270px;margin-top:18px}.login-story small{font:10px ui-monospace,monospace;letter-spacing:.12em;color:var(--accent)}.signin{padding:46px 38px;display:flex;flex-direction:column;justify-content:center}.signin h1{font-size:27px}.signin p{font-size:12px;color:var(--muted);margin-bottom:20px}.signin .primary{width:100%;margin-top:25px}.login-theme{position:fixed;right:24px;top:20px}.mobile-caption{display:none}[hidden]{display:none!important}
@media(min-width:1700px){main{padding-left:36px;padding-right:36px}.app{grid-template-columns:230px minmax(0,1fr)}}
@media(max-width:1150px){.app{grid-template-columns:192px minmax(0,1fr);padding:10px;gap:8px}main{padding:24px 18px}.brand{gap:8px}.brand b{font-size:11px}.brand img{width:36px;height:36px}.dashboard-grid{grid-template-columns:minmax(0,1.5fr) minmax(245px,1fr)}.clients-summary{grid-template-columns:repeat(3,minmax(0,1fr));row-gap:18px}.client-stat:nth-child(3){border-right:0}.resource-grid{grid-template-columns:1fr 1fr}.graph-speeds{gap:20px}.graph-speeds b{font-size:22px}.preset-grid{grid-template-columns:1fr 1fr}.client-glance{grid-template-columns:1fr 1fr auto}.client-glance .badge{display:none}}
@media(max-width:900px){.dashboard-grid,.two-col.equal{grid-template-columns:1fr}.overview-stats{grid-template-columns:1fr 1fr}.graph-card{margin-bottom:0}.graph-speeds b{font-size:27px}.clients-toolbar select{max-width:100%}.login-story{padding:30px}.login-story h2{font-size:34px}.signin{padding:35px 28px}}
@media(max-width:700px){.app{display:block;height:auto;padding:8px}.sidebar{padding:14px;border-radius:16px;overflow:visible}.brand{padding:0 50px 13px 2px}.brand b{font-size:12px}.brand img{width:37px;height:37px}.brand-tools{position:absolute;right:25px;top:24px;padding:0;gap:5px}.brand-tools button{width:34px;height:34px;padding:7px}.brand-tools button span{display:none}.brand-tools .mobile-caption{display:none}.nav{grid-template-columns:repeat(3,minmax(0,1fr));gap:6px}.nav a{padding:9px 4px;font-size:11px;gap:6px;justify-content:center}.nav .ico{width:15px}.side-footer{display:flex;justify-content:space-between;align-items:center;padding-top:10px}.side-footer .logout{font-size:10px;padding:4px 6px;gap:5px}.social{margin:0;padding:0;border:0;gap:14px}.social a{font-size:9px}.social .ico{width:12px}.workspace{overflow:visible}main{padding:23px 5px 35px}.page-head{align-items:flex-start;gap:12px;margin-bottom:21px}.page-head h1{font-size:30px}.page-head p{font-size:12px}.page-head>button{font-size:11px;padding:10px;max-width:145px}.eyebrow{font-size:9px}.card{padding:18px}.graph-speeds{gap:20px}.graph-speeds b{font-size:23px}.chart-wrap{height:210px}.resource{padding:15px}.resource-head b{font-size:17px}.resource-head strong{font-size:11px}.overview-stat{padding:10px 14px}.overview-stat b{font-size:24px}.client-glance{grid-template-columns:minmax(0,1fr) auto;gap:9px}.client-glance .pills{display:none}.client-glance .btn{grid-column:1/-1;justify-self:start}.clients-summary{padding:16px 0;row-gap:16px;border-radius:15px}.client-stat{padding:0 11px}.client-stat b{font-size:20px}.client-stat span{font-size:9px}.clients-toolbar{padding:12px;gap:8px}.search-field{flex-basis:100%}.clients-toolbar select{flex:1 1 100%;font-size:12px;min-width:0;width:100%;padding-right:28px}.clients-table{display:block;min-width:0}.clients-table thead{display:none}.clients-table tbody{display:grid;gap:12px;padding:12px}.clients-table tr{position:relative;display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:13px;padding:12px;gap:10px;background:var(--input)}.clients-table td{display:block;padding:0;border:0;min-width:0}.clients-table td:before{content:attr(data-label);display:block;color:var(--muted);font-size:9px;margin-bottom:4px}.clients-table .select-col{position:absolute;right:12px;top:14px;width:20px}.clients-table .client-name{grid-column:1/-1;max-width:none;padding-right:28px}.client-name strong{font-size:15px}.clients-table .state-col{position:static;grid-area:2/2;justify-self:end;align-self:center}.clients-table .state-col:before{display:none}.clients-table .activity-col{grid-area:2/1;min-height:26px;align-self:center}.clients-table .activity-col:before{display:none}.clients-table .protocol-col{max-width:none}.traffic-cell{min-width:0}.clients-table .actions-col{grid-column:1/-1;border-top:1px solid var(--line);padding-top:9px}.clients-table .actions-col:before{display:none}.row-actions{justify-content:flex-end;gap:9px}.row-actions .icon-btn{width:35px;height:33px;border:1px solid var(--line)}.clients-table tr:last-child td{border:0}.bulk-bar{padding:12px}.form-grid{grid-template-columns:1fr}.account-head{flex-wrap:wrap}.account-metrics{gap:15px}.device{flex-wrap:wrap}.preview-top{padding:12px}.preview-stage{padding:10px;height:65dvh}.preview-dialog{width:calc(100vw - 16px)}.editor-actions{align-items:stretch;flex-direction:column}.preset-grid{gap:8px}.preset{padding:13px}.preset button{padding:9px}.login-page{padding:80px 18px 30px}.login-shell{grid-template-columns:1fr;max-width:420px}.login-story{padding:25px;min-height:0;gap:20px}.login-story h2{font-size:27px}.login-story p,.login-story>small{display:none}.login-story .eyebrow{display:none}.signin{padding:28px}.login-theme{top:18px;right:18px}}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
'''

THEME_INIT = """<script>try{const saved=localStorage.getItem('onyx-theme');document.documentElement.dataset.theme=saved==='light'?'light':'dark'}catch(e){document.documentElement.dataset.theme='dark'}</script>"""
COMMON_JS = """<script>
document.querySelectorAll('[data-theme-toggle]').forEach(b=>{function label(){const light=document.documentElement.dataset.theme==='light';const s=b.querySelector('span');if(s)s.textContent=light?'Тёмная тема':'Светлая тема';b.setAttribute('aria-label',light?'Включить тёмную тему':'Включить светлую тему')}label();b.addEventListener('click',()=>{const t=document.documentElement.dataset.theme==='light'?'dark':'light';document.documentElement.dataset.theme=t;try{localStorage.setItem('onyx-theme',t)}catch(e){}document.querySelectorAll('[data-theme-toggle]').forEach(x=>{const s=x.querySelector('span');if(s)s.textContent=t==='light'?'Тёмная тема':'Светлая тема'});label()})});
/* Small animated toast: one shared stack at the top of the screen. */
function onyxToast(message,type){type=type==='err'?'err':'ok';
  let box=document.getElementById('onyxToasts');
  if(!box){box=document.createElement('div');box.id='onyxToasts';box.className='onyx-toasts';box.setAttribute('role','status');document.body.append(box)}
  const t=document.createElement('div');t.className='onyx-toast '+type;
  t.innerHTML='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(type==='ok'?'<path d="m4 12.5 5 5L20 6.5"/>':'<path d="M12 9v5"/><path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 17h.01"/>')+'</svg><span></span>';
  t.querySelector('span').textContent=String(message||'Готово');
  box.append(t);
  requestAnimationFrame(()=>t.classList.add('show'));
  setTimeout(()=>{t.classList.remove('show');setTimeout(()=>t.remove(),300)},4200);
  while(box.children.length>3)box.firstElementChild.remove();
}
/* Animated service-restart overlay with a spinning ring. */
function onyxOps(title,text){
  let ov=document.getElementById('onyxOps');
  if(!ov){ov=document.createElement('div');ov.id='onyxOps';ov.className='onyx-ops';
    ov.innerHTML='<div class="onyx-ops-card"><svg class="onyx-ops-ring" viewBox="0 0 56 56" aria-hidden="true"><circle class="bg" cx="28" cy="28" r="24"/><circle class="fg" cx="28" cy="28" r="24"/></svg><h3></h3><p></p></div>';
    document.body.append(ov)}
  ov.querySelector('h3').textContent=title;ov.querySelector('p').textContent=text||'';
  requestAnimationFrame(()=>ov.classList.add('show'));return ov}
function onyxOpsClose(){const ov=document.getElementById('onyxOps');if(ov){ov.classList.remove('show');setTimeout(()=>ov.remove(),250)}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-service-restart]');if(!b)return;
  const target=b.dataset.serviceRestart;
  const ok=await onyxConfirm(target==='panel'?'Перезапустить панель? Интерфейс будет недоступен несколько секунд, затем страница обновится сама.':'Перезапустить модули — Xray, релей и MTProxy? Клиентские подключения кратко оборвутся.',{ok:'Перезапустить'});
  if(!ok)return;
  const modal=onyxOps(target==='panel'?'Перезапуск панели':'Перезапуск модулей','Выполняем…');
  const p=modal.querySelector('p');
  try{
    const r=await fetch(b.dataset.url,{method:'POST',headers:{'X-Onyx-Async':'1'},body:new URLSearchParams({csrf:b.dataset.csrf,target})});
    let res;try{res=await r.json()}catch(e2){throw new Error('Панель вернула некорректный ответ.')}
    if(!r.ok||!res.ok)throw new Error(res.message||'Не удалось запустить перезапуск.');
    if(target==='panel'){
      p.textContent='Служба перезапускается — ждём возврата…';
      const t0=Date.now();
      while(Date.now()-t0<90000){
        await new Promise(s=>setTimeout(s,1200));
        try{const h=await fetch(b.dataset.url.replace(/service-restart$/,'__health'),{cache:'no-store'});
          if(h.ok&&!h.redirected)break}catch(e3){}}
      onyxOpsClose();onyxToast('Панель перезапущена.');setTimeout(()=>location.reload(),500);
    }else{
      p.textContent='Перезапускаем службы…';
      const st=b.dataset.url.replace(/service-restart$/,'restart-status');
      const t0=Date.now();let finished=false;
      while(Date.now()-t0<120000){
        await new Promise(s=>setTimeout(s,1500));
        try{const s2=await fetch(st,{cache:'no-store'});if(!s2.ok||s2.redirected)continue;
          const d=await s2.json();
          if(d.message)p.textContent=d.message;
          if(d.phase==='done'){onyxOpsClose();onyxToast(d.message||'Модули перезапущены.');finished=true;setTimeout(()=>location.reload(),500);break}
          if(d.phase==='failed'){onyxOpsClose();onyxToast(d.message||'Ошибка перезапуска.','err');finished=true;break}}catch(e3){}}
      if(!finished){onyxOpsClose();onyxToast('Перезапуск не подтвердился. Проверьте службы.','err')}
    }
  }catch(e){onyxOpsClose();onyxToast(e.message,'err')}
});
async function onyxCopy(text,container=document.body){try{await navigator.clipboard.writeText(text);return}catch(e){}const prior=document.activeElement,x=document.createElement('textarea');x.value=text;x.setAttribute('aria-label','Копирование ссылки');x.style.position='fixed';x.style.opacity='0';container.appendChild(x);try{x.focus();x.select();if(!document.execCommand('copy'))throw new Error('Clipboard unavailable')}finally{x.remove();if(prior?.isConnected)prior.focus()}}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-copy]');if(b&&!b.disabled){const old=b.innerHTML;b.disabled=true;try{await onyxCopy(b.dataset.copy,b.closest('dialog')||document.body);b.textContent=b.classList.contains('icon-btn')?'✓':'✓ Скопировано'}catch(err){b.textContent=b.classList.contains('icon-btn')?'!':'Не удалось скопировать'}finally{setTimeout(()=>{b.innerHTML=old;b.disabled=false},1600)}}const close=e.target.closest('[data-close-dialog]');if(close){const d=close.closest('dialog');d.close();const frame=d.querySelector('iframe');if(frame){frame.removeAttribute('srcdoc')}}});
/* Themed confirm dialog replacing window.confirm across the panel */
(function(){
  if(document.getElementById('onyxConfirmDlg'))return;
  const d=document.createElement('dialog');d.id='onyxConfirmDlg';
  d.innerHTML='<div class="dialog-head"><h2 id="onyxConfirmTitle"></h2></div><p id="onyxConfirmMsg"></p><form method="dialog"><div class="actions onyx-confirm-actions"><button value="cancel">Отмена</button><button class="primary" id="onyxConfirmOk" value="ok">Подтвердить</button></div></form>';
  document.body.append(d);
})();
function onyxConfirm(message,opts){opts=opts||{};return new Promise(resolve=>{
  const d=document.getElementById('onyxConfirmDlg');
  document.getElementById('onyxConfirmTitle').textContent=opts.title||'Подтвердите действие';
  document.getElementById('onyxConfirmMsg').textContent=message||'Вы уверены?';
  const ok=document.getElementById('onyxConfirmOk');ok.textContent=opts.ok||'Подтвердить';
  ok.classList.toggle('danger',Boolean(opts.danger));
  d.returnValue='';d.addEventListener('close',()=>resolve(d.returnValue==='ok'),{once:true});
  d.showModal();
})}
document.addEventListener('submit',async e=>{const f=e.target.closest('form[data-confirm]');if(!f||f.matches('[data-client-action]'))return;const act=new URL(f.action,location.href).pathname;if(['delete-user','subscription-action','openflux-profile'].some(s=>act.endsWith('/'+s)))return;e.preventDefault();if(!(await onyxConfirm(f.dataset.confirm,{danger:true})))return;f.submit()});
(()=>{const burger=document.getElementById('navBurger'),nav=document.getElementById('topnav');if(!burger||!nav)return;function setNav(open){nav.classList.toggle('open',open);document.body.classList.toggle('nav-open',open);burger.setAttribute('aria-expanded',String(open));burger.setAttribute('aria-label',open?'Закрыть меню':'Открыть меню')}burger.addEventListener('click',()=>setNav(!nav.classList.contains('open')));document.addEventListener('click',e=>{if(nav.classList.contains('open')&&!e.target.closest('#topnav,#navBurger'))setNav(false)});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&nav.classList.contains('open')){setNav(false);burger.focus()}});nav.addEventListener('click',e=>{if(e.target.closest('a'))setNav(false)});const wide=matchMedia('(min-width:701px)');(wide.addEventListener?wide.addEventListener('change',m=>{if(m.matches)setNav(false)}):wide.addListener(m=>{if(m.matches)setNav(false)}));
/* Themed dropdowns over native selects */
(function(){
const CHEV='<svg class="ico selx-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
function build(sel){
  if(sel.dataset.selxDone)return;sel.dataset.selxDone="1";
  const wrap=document.createElement("div");wrap.className="selx";if(sel.id)wrap.dataset.for=sel.id;
  sel.parentNode.insertBefore(wrap,sel);wrap.appendChild(sel);
  sel.classList.add("selx-native");sel.setAttribute("tabindex","-1");sel.setAttribute("aria-hidden","true");
  const btn=document.createElement("button");btn.type="button";btn.className="selx-trigger";
  btn.setAttribute("aria-haspopup","listbox");btn.setAttribute("aria-expanded","false");
  if(sel.getAttribute("aria-label"))btn.setAttribute("aria-label",sel.getAttribute("aria-label"));
  const label=document.createElement("span");label.className="selx-label";
  btn.append(label);btn.insertAdjacentHTML("beforeend",CHEV);wrap.append(btn);
  const pop=document.createElement("div");pop.className="selx-pop";pop.setAttribute("role","listbox");wrap.append(pop);
  let act=-1,openFlag=false;
  function render(){
    const cur=sel.value,curOpt=sel.selectedOptions[0];
    label.textContent=curOpt?curOpt.textContent:"";
    pop.innerHTML="";
    [...sel.options].forEach(o=>{
      const el=document.createElement("div");
      el.className="selx-opt"+(o.value===cur?" sel":"")+(o.disabled?" dis":"");
      el.setAttribute("role","option");el.setAttribute("aria-selected",o.value===cur?"true":"false");
      el.textContent=o.textContent;
      if(!o.disabled)el.addEventListener("click",()=>{if(sel.value!==o.value){sel.value=o.value;sel.dispatchEvent(new Event("change",{bubbles:true}))}closePop()});
      pop.append(el);
    });
  }
  function rectBelowViewport(){const r=btn.getBoundingClientRect();return r.bottom+300>window.innerHeight&&r.top>340}
  function openPop(){
    document.querySelectorAll(".selx.open").forEach(x=>{if(x!==wrap)x.classList.remove("open")});
    render();wrap.classList.add("open");openFlag=true;btn.setAttribute("aria-expanded","true");
    const selOpt=pop.querySelector(".selx-opt.sel");act=selOpt?[...pop.children].indexOf(selOpt):0;
    if(selOpt)selOpt.scrollIntoView({block:"nearest"});
    if(rectBelowViewport())wrap.classList.add("up");else wrap.classList.remove("up");
  }
  function closePop(refocus){
    wrap.classList.remove("open");openFlag=false;btn.setAttribute("aria-expanded","false");
    if(refocus)btn.focus({preventScroll:true});
  }
  btn.addEventListener("click",()=>{openFlag?closePop():openPop()});
  wrap.addEventListener("keydown",e=>{
    if(e.key==="Escape"){if(wrap.classList.contains("open")){e.preventDefault();closePop(true)}return}
    const items=[...pop.querySelectorAll(".selx-opt:not(.dis)")];
    if(!wrap.classList.contains("open")){
      if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();openPop()}
      return
    }
    if(e.key==="ArrowDown"||e.key==="ArrowUp"){e.preventDefault();if(!items.length)return;act=e.key==="ArrowDown"?Math.min(act+1,items.length-1):Math.max(act-1,0);items.forEach((el,i)=>el.classList.toggle("act",i===act));items[act].scrollIntoView({block:"nearest"});return}
    if(e.key==="Home"||e.key==="End"){e.preventDefault();act=e.key==="Home"?0:items.length-1;items.forEach((el,i)=>el.classList.toggle("act",i===act));items[act].scrollIntoView({block:"nearest"});return}
    if(e.key==="Enter"||e.key===" "){e.preventDefault();if(items[act])items[act].click()}
  });
  document.addEventListener("click",e=>{if(openFlag&&!wrap.contains(e.target))closePop()});
  document.addEventListener("keydown",e=>{if(e.key==="Escape"&&wrap.classList.contains("open"))closePop()});
  sel.addEventListener("change",render);
  new MutationObserver(render).observe(sel,{childList:true});
  render();
}
document.querySelectorAll("select").forEach(build);
new MutationObserver(muts=>{muts.forEach(m=>{m.addedNodes.forEach(n=>{if(n.nodeType===1){if(n.matches("select"))build(n);n.querySelectorAll("select").forEach(build)}})})}).observe(document.body,{childList:true,subtree:true});
})();
})();
</script>"""


def qr_attributes(endpoint, name, link, protocols, kind='direct', user_port=None):
    labels={'web':'WEB Proxy','vless':'VLESS XHTTP','hysteria':'Hysteria2','mtproto':'MTProto','awg20':'AWG 2.0','awg31':'AWG 3.1','openflux':'OpenFlux'}
    parsed=urlsplit(link)
    web=protocols==['web']
    openflux=protocols==['openflux']
    telegram=web or protocols==['mtproto']
    host=parsed.hostname or '' if openflux else parse_qs(parsed.query).get('server',[parsed.hostname or ''])[0] if telegram else parsed.hostname or ''
    port=None if web or openflux or kind=='subscription' else int(parse_qs(parsed.query).get('port',['443'])[0]) if protocols==['mtproto'] else parsed.port or 443
    if protocols and protocols[0] in ('awg20','awg31'):
        match=re.search(r'(?m)^Endpoint\s*=\s*([^:\s]+):(\d+)\s*$',link)
        host=match.group(1) if match else ''
        port=int(match.group(2)) if match else (int(user_port) if user_port else None)
    info={'name':name,'link':link,'protocols':' · '.join(labels.get(p,p) for p in protocols),
          'kind':kind,'host':host,'port':port,'web':telegram,'openflux':openflux}
    return 'data-qr="'+esc(endpoint)+'" data-qr-info="'+esc(json.dumps(info,ensure_ascii=False))+'"'


QR_CSS='''
.connection-dialog{width:min(700px,calc(100vw - 32px));padding:0;overflow:auto;background:linear-gradient(145deg,var(--surface),var(--input));border-radius:24px}
.connection-header{display:flex;align-items:center;gap:11px;padding:23px 26px 20px}.connection-mark{display:grid;place-items:center;width:36px;height:36px;border-radius:11px;background:var(--tint);color:var(--accent)}.connection-header h2{font-size:16px;letter-spacing:-.02em}.connection-header small{font-size:10px;letter-spacing:.09em}.connection-close{margin-left:auto;width:33px;height:33px;padding:0;background:transparent;font-size:21px;color:var(--muted)}
.connection-body{display:grid;grid-template-columns:234px minmax(0,1fr);gap:26px;padding:0 26px 25px;align-items:center}.qr-visual{text-align:center;min-width:0}.qr-canvas{width:234px;height:234px;max-width:100%;display:grid;place-items:center;background:#fff;border-radius:15px;padding:12px;box-shadow:0 8px 30px #0001}.qr-canvas img{display:block;width:100%;height:100%;object-fit:contain;image-rendering:pixelated}.qr-canvas p{font-size:12px;line-height:1.5;color:#4d6269;margin:0;padding:16px}.qr-caption{font-size:10px;color:var(--muted);margin-top:12px}.connection-info{min-width:0}.connection-kind{font-size:10px;letter-spacing:.04em;color:var(--accent);margin:0 0 5px}.connection-info h3{font-size:23px;font-weight:600;line-height:1.2;letter-spacing:-.035em}.connection-protocol{display:block;font-size:11px;color:var(--muted);margin:9px 0 17px;overflow-wrap:anywhere}.connection-meta{display:flex;flex-wrap:wrap;gap:12px;font-size:11px;margin-bottom:18px}.connection-meta span{color:var(--muted)}.connection-meta b{color:var(--text);font-weight:500;overflow-wrap:anywhere}.connect-steps{display:grid;gap:11px;margin:0;padding:0;list-style:none;counter-reset:step}.connect-steps li{display:flex;gap:10px;font-size:12px;color:var(--muted);line-height:1.5}.connect-steps li:before{counter-increment:step;content:counter(step);display:grid;place-items:center;flex:0 0 22px;height:22px;border:1px solid var(--line);border-radius:50%;color:var(--accent);font-size:10px}.connection-footer{padding:18px 26px 21px;border-top:1px solid var(--line);background:var(--tint)}.connection-footer>.actions{justify-content:space-between;gap:14px}.connection-footer .primary{min-width:210px}.connection-footer small{font-size:10px;max-width:245px}.connection-status{margin:8px 0 0;font-size:12px;color:var(--accent)}.connection-status:empty{display:none}.connection-link{margin-top:8px;font-size:11px;color:var(--muted)}.connection-link summary{cursor:pointer;width:fit-content}.connection-link input{margin-top:10px;font:11px/1.5 ui-monospace,monospace}.qr-retry{margin:10px 0 0;font-size:11px}
@media(max-width:600px){.connection-dialog{width:calc(100vw - 24px);max-height:92dvh}.connection-header{padding:19px 19px 16px}.connection-body{grid-template-columns:1fr;gap:18px;padding:0 20px 20px}.qr-visual{grid-row:2}.qr-canvas{margin:0 auto;width:216px;height:216px}.connection-info{text-align:center}.connection-info h3{font-size:22px}.connection-meta{justify-content:center;margin-bottom:12px}.connection-protocol{margin:7px 0 10px}.connect-steps{text-align:left;max-width:285px;margin:0 auto;gap:7px}.connection-footer{padding:16px 20px}.connection-footer>.actions{display:grid;justify-content:stretch}.connection-footer .primary{width:100%}.connection-footer small{max-width:none}.connection-status{text-align:center}}
'''
CSS += QR_CSS
CSS += '''.preset>.actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,110px),1fr));width:100%;gap:7px;margin-top:auto}.preset>.actions form{min-width:0}.preset>.actions button{margin:0;padding:9px 7px}'''
CSS += '''.preset-create-dialog{width:min(920px,calc(100vw - 28px))}.preset-create-dialog .code-editor{min-height:300px;max-height:46dvh}.preset-create-dialog .editor-bar{margin-top:0}@media(max-width:700px){.preset-create-dialog .form-grid{grid-template-columns:1fr}.preset-create-dialog .code-editor{min-height:240px}}'''
CSS += '''.preset[data-preset-card]{display:block;padding:0;aspect-ratio:16/10;overflow:hidden;isolation:isolate}
.preset[data-preset-card]:hover{border-color:var(--accent)}
.preset[data-preset-card] .preset-thumb{position:absolute;inset:0;background:var(--surface)}
.preset[data-preset-card] .preset-art{position:absolute;inset:0;height:auto;display:grid;place-items:center;border:0;padding:0;margin:0;font-size:30px;color:var(--muted);opacity:.5}
.preset[data-preset-card] .preset-frame{position:absolute;top:0;left:0;width:1280px;height:800px;border:0;background:#fff;transform-origin:0 0;transform:scale(var(--s,.25));pointer-events:none}
.preset[data-preset-card] .preset-veil{position:absolute;inset:0;z-index:1;display:flex;flex-direction:column;padding:14px;opacity:0;pointer-events:none;transition:opacity .18s ease;background:linear-gradient(180deg,color-mix(in srgb,var(--bg) 38%,transparent),color-mix(in srgb,var(--bg) 88%,transparent));-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px)}
.preset[data-preset-card] .preset-veil b{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.preset[data-preset-card] .preset-veil p{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:11px;color:color-mix(in srgb,var(--text) 74%,transparent);margin:6px 0 14px}
.preset[data-preset-card] .preset-veil .actions{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,112px),1fr));gap:7px;margin-top:auto}
.preset[data-preset-card] .preset-veil .actions form{min-width:0}
.preset[data-preset-card] .preset-veil .actions button{width:100%;margin:0;padding:9px 7px;font-size:11px}
.preset[data-preset-card]:hover .preset-veil,.preset[data-preset-card]:focus-within .preset-veil,.preset[data-preset-card].revealed .preset-veil{opacity:1;pointer-events:auto}
.preset[data-preset-card].has-frame .preset-art{display:none}
@media(max-width:700px){.preset-grid{grid-template-columns:1fr}}'''
CSS += '''
.openflux-card{overflow:hidden;background:radial-gradient(circle at 100% 0,var(--tint),transparent 38%),var(--surface)}.openflux-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.openflux-title{display:flex;align-items:center;gap:13px}.openflux-mark{display:grid;place-items:center;width:43px;height:43px;flex:0 0 auto;border:1px solid color-mix(in srgb,var(--accent) 40%,var(--line));border-radius:12px;background:var(--tint);color:var(--accent);font-weight:750}.openflux-title h2{margin:0}.openflux-title p{margin:4px 0 0;color:var(--muted);font-size:11px}.openflux-status{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid var(--line);border-radius:99px;color:var(--muted);font-size:10px;white-space:nowrap}.openflux-status i{width:7px;height:7px;border-radius:50%;background:var(--muted)}.openflux-status.on{color:var(--green)}.openflux-status.on i{background:var(--green);box-shadow:0 0 0 4px color-mix(in srgb,var(--green) 14%,transparent)}.openflux-form{margin-top:22px}.openflux-input{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px}.openflux-input input{font:11px ui-monospace,monospace}.openflux-input button{min-width:155px}.openflux-hint{display:block;margin-top:9px;font-size:10px}.openflux-client{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:20px;padding-top:20px;border-top:1px solid var(--line)}.openflux-field{min-width:0;padding:13px;border:1px solid var(--line);border-radius:10px;background:var(--input)}.openflux-field.wide{grid-column:1/-1}.openflux-field span{display:block;margin-bottom:7px;color:var(--muted);font-size:9px;letter-spacing:.06em;text-transform:uppercase}.openflux-value{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:6px}.openflux-value input{min-width:0;padding:9px;font:10px ui-monospace,monospace}.openflux-value button{padding:8px 10px}.openflux-field b{font:500 12px ui-monospace,monospace}.openflux-controls{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-top:15px}.openflux-controls>small{max-width:600px;font-size:10px}.openflux-controls .actions{margin-left:auto}.openflux-copy-status{min-height:16px;margin:9px 0 0;color:var(--accent);font-size:10px}@media(max-width:700px){.openflux-head{align-items:stretch;flex-direction:column}.openflux-status{width:max-content}.openflux-input{grid-template-columns:1fr}.openflux-input button{width:100%}.openflux-client{grid-template-columns:1fr}.openflux-field.wide{grid-column:auto}.openflux-controls{align-items:stretch;flex-direction:column}.openflux-controls .actions{display:grid;width:100%;margin:0}.openflux-controls .actions form,.openflux-controls .actions button{width:100%}}
'''

# Graphite-blue theme restored from the selected reference; light mode remains available.
CSS += '''
:root{--bg:#101318;--surface:#1b1e24;--raised:#22262e;--input:#171a20;--line:#303641;--text:#f3f5f8;--muted:#93a0b8;--accent:#3b82f6;--on-accent:#fff;--tint:#3b82f619;--green:#41c78d;--red:#f06f75;--amber:#dcae43;--sidebar:#181b21;--shadow:0 14px 46px #0006}
:root[data-theme=light]{--bg:#f3f5f8;--surface:#fff;--raised:#eef1f5;--input:#f9fafc;--line:#d8dde6;--text:#202630;--muted:#667188;--accent:#2563d9;--on-accent:#fff;--tint:#2563d912;--green:#25865b;--red:#bd464c;--amber:#916918;--sidebar:#fff;--shadow:0 8px 30px #17203614}
body{font-size:14px;line-height:1.5}h1{font-size:32px;font-weight:650;letter-spacing:-.035em}h2{letter-spacing:-.015em}.eyebrow{display:none}
.app{padding:0;gap:0;grid-template-columns:216px minmax(0,1fr)}.sidebar{border:0;border-right:1px solid var(--line);border-radius:0;background:var(--sidebar);padding:36px 18px 22px}.brand{display:block;padding:0 16px 50px}.brand-wordmark{display:block;font-size:40px!important;line-height:1.1;letter-spacing:-.06em!important;color:var(--accent)}.brand-name{display:block;font-size:10px;letter-spacing:.07em;color:var(--muted);margin-top:9px}.brand small{font:10px/1.5 inherit;margin-top:5px}.nav{gap:9px}.nav a,.logout{font-size:13px;font-weight:500;padding:13px 15px;border-radius:9px}.nav a.active{background:var(--tint);color:var(--accent)}.side-footer{padding-top:36px}.brand-tools{padding:16px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-bottom:12px}.brand-tools button{width:100%;font-size:11px;justify-content:flex-start;border:0;padding:10px}.theme-track{margin-left:auto;width:29px;height:17px;border-radius:20px;background:var(--accent);position:relative;flex-shrink:0}.theme-track:after{content:"";position:absolute;top:3px;right:3px;width:11px;height:11px;background:var(--on-accent);border-radius:50%}:root[data-theme=dark] .theme-track:after{right:15px}.social{border:0;justify-content:flex-start;padding:20px 12px 0;gap:18px}.social a{font-size:10px}.social .ico{width:16px;height:16px}.workspace{background:var(--bg)}main{max-width:1720px;padding:38px 36px 44px}.page-head{margin-bottom:32px;align-items:center}.page-head p{font-size:13px;margin-top:6px}.page-head .primary{padding:12px 17px;font-size:13px}.btn,button{border-radius:8px;font-weight:500;background:var(--surface)}.btn.primary,button.primary{box-shadow:0 2px 6px #0003}input,textarea,select{border-radius:8px;background:var(--input)}button:hover,.btn:hover{background:var(--tint)}button.primary:hover,.btn.primary:hover{background:var(--accent);filter:brightness(1.08)}.card,.account{border-radius:14px}.pill,.proto-hysteria,.proto-web,.proto-vless{border:0;background:var(--tint);color:var(--accent);font-size:11px;padding:4px 7px}.badge{font-size:10px}.avatar{border-radius:50%}
.clients-layout{display:grid;grid-template-columns:minmax(0,1fr);gap:24px;align-items:start}.clients-content{min-width:0}.connection-slot:empty{display:none}.clients-summary{grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:18px 5px;margin-bottom:20px;gap:0}.client-stat{padding:0 20px}.client-stat:first-child{padding-left:20px}.client-stat:nth-child(3){border-right:1px solid var(--line)}.client-stat:last-child{border:0}.client-stat span{font-size:11px;white-space:normal}.client-stat b{font:600 25px/1.3 "Segoe UI",system-ui,sans-serif;font-variant-numeric:tabular-nums;color:var(--text);margin-top:8px}.client-stat:first-child b{color:var(--accent)}.clients-panel{border:1px solid var(--line);border-radius:12px;background:var(--surface);overflow:hidden}.clients-toolbar{padding:16px;border-bottom:1px solid var(--line);gap:8px}.search-field{min-width:190px;border-radius:8px;flex:2}.search-field input{font-size:12px}.clients-toolbar select{flex:1;min-width:110px;max-width:180px;font-size:11px;background:var(--input)}.clients-toolbar #clientSort{max-width:140px}.clients-table{min-width:730px}.clients-table th{padding:12px 8px;font-size:11px;letter-spacing:0;background:var(--raised);border-bottom:1px solid var(--line)}.clients-table td{padding:16px 8px;font-size:12px}.clients-table .client-name{min-width:170px;max-width:260px}.client-identity{display:flex;align-items:center;gap:11px;min-width:0}.client-initial{display:grid;place-items:center;width:35px;height:35px;flex-shrink:0;border-radius:50%;background:var(--tint);color:var(--accent);font-size:16px;font-weight:500}.client-identity>div{min-width:0}.client-name strong{font-size:13px;font-weight:550}.client-name small{font:10px/1.7 "Segoe UI",system-ui,sans-serif}.client-name .badge{margin-top:4px}.clients-table .activity-col{display:none}.clients-table .hwid-cell{display:none}.clients-table .protocol-col{max-width:170px}.traffic-cell{min-width:104px}.traffic-cell b{font:500 12px "Segoe UI",system-ui,sans-serif;font-variant-numeric:tabular-nums}.traffic-cell small{font-size:9px}.traffic-split{height:2px;opacity:.5}.row-actions{gap:2px}.row-actions .icon-btn{width:28px;height:30px;border:0}.icon-btn.danger{color:var(--muted)}.icon-btn.danger:hover{color:var(--red)}.clients-table .select-col{width:28px;padding-left:0}.clients-table input[type=checkbox]{width:13px;height:13px}.access-switch{width:36px;height:21px}.access-switch:after{width:15px;height:15px}.access-switch[aria-checked=true]:after{left:18px}.clients-table tr.qr-selected{background:var(--tint);box-shadow:inset 2px 0 var(--accent)}.clients-table tr.qr-selected [data-qr]{color:var(--accent);background:var(--surface)}.list-footer{padding:15px 16px;border-top:1px solid var(--line);font-size:11px}.list-footer span:last-child{font-size:10px}.client-help{border:0;background:none;border-top:1px solid var(--line);border-radius:0;padding:16px 0;margin-top:22px}.client-help summary{cursor:pointer}.bulk-bar{border:1px solid var(--line);border-radius:8px;margin-bottom:10px}
.connection-dialog{width:min(390px,calc(100vw - 32px));padding:0;border-radius:14px;background:var(--surface);max-height:90dvh;box-shadow:var(--shadow)}.connection-header{padding:22px 23px 18px}.connection-header h2{font-size:15px;font-weight:550}.connection-close{border:0;width:30px;height:30px}.connection-body{display:flex;flex-direction:column;gap:19px;padding:0 24px 20px}.connection-info{width:100%;text-align:left}.connection-person{display:flex;align-items:center;gap:12px}.connection-person .client-initial{width:45px;height:45px;font-size:22px}.connection-person>div{min-width:0}.connection-info h3{font-size:21px;letter-spacing:-.025em;overflow-wrap:anywhere}.connection-kind{font-size:11px;letter-spacing:0;color:var(--muted);margin:5px 0 0}.connection-protocol{display:flex;justify-content:center;flex-wrap:wrap;gap:6px;margin:18px 0 10px}.connection-meta{justify-content:center;margin:0;gap:8px;font-size:10px}.qr-canvas{width:220px;height:220px;max-width:100%;margin:0 auto;border:1px solid #e1e6df;border-radius:12px;box-shadow:none;padding:12px}.qr-visual{width:100%}.qr-caption{font-size:11px;max-width:230px;margin:12px auto 0;line-height:1.6}.connection-footer{padding:0 24px 20px;border:0;background:transparent}.connection-footer .primary{width:100%;min-width:0;padding:12px;font-size:12px}.connection-status{font-size:11px;margin-top:10px;text-align:center}.connection-link{margin-top:14px}.connection-link summary{margin:0 auto;color:var(--accent);padding:5px;font-size:12px;list-style:none}.connection-link summary::-webkit-details-marker{display:none}.connection-link input{font-size:10px}.connection-privacy{margin:20px 0 0;padding-top:16px;border-top:1px solid var(--line);font-size:10px;line-height:1.6;color:var(--muted);text-align:center}.connection-dialog.docked{position:static;inset:auto;margin:0;width:100%;max-height:none;box-shadow:0 2px 8px #233c2508}.connection-slot{min-width:0}.connection-slot:has(.docked[open]){position:sticky;top:28px}
.graph-card{background:var(--surface);border-top:1px solid var(--line)}.graph-speeds b,.overview-stat b,.resource-head b{font-family:"Segoe UI",system-ui,sans-serif;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.resource{border-radius:12px}.resource-grid{gap:14px}.preset{background:var(--raised)}.login-page{background:radial-gradient(circle at 18% 20%,var(--tint),transparent 38%),var(--bg)}.login-shell{padding:0;border-radius:18px}.login-story{background:var(--tint)}.login-story:after{display:none}.login-story h2{font-weight:550}.signin h1{font-size:28px}.login-brand .brand-wordmark{font-size:32px!important}.login-brand{align-items:flex-start;flex-direction:column;gap:4px;letter-spacing:.02em}
@media(min-width:1440px){.clients-layout:has(.docked[open]){grid-template-columns:minmax(0,1fr) 304px}.clients-layout:has(.docked[open]) .page-head .primary{font-size:12px;padding:12px}.clients-layout:has(.docked[open]) .page-head{gap:10px}}
@media(max-width:1150px){.app{padding:0;gap:0;grid-template-columns:190px minmax(0,1fr)}main{padding:28px 24px}.sidebar{padding:30px 12px 20px}.brand{padding-left:12px}.client-stat{padding:0 12px}.client-stat b{font-size:23px}.clients-summary{grid-template-columns:repeat(4,minmax(0,1fr))}.clients-toolbar select{max-width:none}}
@media(max-width:700px){.app{display:block;padding:0}.sidebar{padding:18px 16px 10px;border:0;border-bottom:1px solid var(--line);border-radius:0}.brand{padding:0 58px 18px 0}.brand-wordmark{font-size:28px!important}.brand-name{font-size:8px;margin-top:4px}.brand small{display:none}.brand-tools{top:21px;right:16px;border:0;margin:0;padding:0;position:absolute}.brand-tools button{border:1px solid var(--line);width:36px;height:36px;padding:8px}.theme-track{display:none}.nav a{padding:10px 4px;font-size:12px}.side-footer{padding-top:8px}.side-footer .logout{font-size:11px;padding:6px 0}.social{padding:0;gap:15px}.social a{font-size:10px}main{padding:24px 16px 36px}.page-head{align-items:flex-start;margin-bottom:25px;flex-wrap:wrap}.page-head h1{font-size:29px}.page-head .primary{font-size:12px;padding:10px 14px}.page-head .actions{gap:6px}.clients-summary{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:20px;margin-bottom:25px}.client-stat{padding:0 14px}.client-stat:nth-child(odd){padding-left:0}.client-stat:nth-child(even){border-right:0}.client-stat b{font-size:24px;margin-top:5px}.client-stat span{font-size:11px}.clients-toolbar{padding:0 0 18px}.clients-toolbar select{flex:1 1 calc(50% - 8px);width:auto;max-width:none;font-size:12px}.clients-toolbar #clientSort{max-width:none}.clients-table{min-width:0}.clients-table tbody{padding:0;gap:12px}.clients-table tr{padding:15px;background:var(--surface);grid-template-columns:1fr 1fr}.clients-table td{padding:0}.clients-table .client-name{max-width:none;padding-right:25px}.client-name strong{font-size:15px}.client-identity{gap:10px}.client-name .badge{display:none}.clients-table .activity-col,.clients-table .hwid-cell{display:block}.clients-table .protocol-col{max-width:none}.clients-table .state-col{justify-self:end}.client-name small{font-size:10px}.clients-table .select-col{right:14px;top:14px}.clients-table .actions-col{padding-top:10px}.row-actions{gap:12px}.row-actions .icon-btn{height:38px;width:38px;border:1px solid var(--line)}.client-help{font-size:11px}.connection-dialog{width:min(390px,calc(100vw - 24px));max-height:92dvh}.connection-body{padding:0 20px 18px;gap:17px}.connection-header{padding:18px 20px 15px}.connection-footer{padding:0 20px 18px}.connection-info h3{font-size:21px}.connection-info{text-align:left}.qr-canvas{width:210px;height:210px}.connection-slot{position:static!important}.connection-privacy{margin-top:15px}.login-shell{padding:0}.login-brand{flex-direction:row;align-items:center;gap:10px}.login-story{padding:25px}.signin{padding:26px}.login-story h2{font-size:26px}.login-theme{position:absolute}}
'''

# Classic graphite shell: wide workspace, slim top bar and the dashboard geometry
# from the earlier stable interface. Current account and protocol controls remain.
CSS += '''
.app{display:block;height:auto;min-height:100dvh}.sidebar{display:none!important}.workspace{min-height:100dvh;overflow:visible;background:var(--bg)}
.appbar{position:sticky;top:0;z-index:40;min-height:61px;padding:0 28px;display:grid;grid-template-columns:minmax(220px,1fr) auto minmax(220px,1fr);align-items:center;gap:20px;background:color-mix(in srgb,var(--surface) 96%,transparent);border-bottom:1px solid var(--line);backdrop-filter:blur(16px)}
.appbar-left,.appbar-tools,.topnav{display:flex;align-items:center}.appbar-left{gap:14px;min-width:0}.mini-brand{display:block;width:38px;height:38px;overflow:hidden;border:1px solid var(--line);border-radius:10px;background:#061531;text-decoration:none;box-shadow:0 3px 12px #001b4b55}.mini-brand img{display:block;width:100%;height:100%;object-fit:cover}.appbar .host{display:flex;align-items:center;gap:8px;min-width:0;color:var(--muted);font-size:12px;overflow-wrap:anywhere}.appbar .host i{width:6px;height:6px;flex:0 0 auto;border-radius:50%;background:var(--accent);box-shadow:0 0 0 4px var(--tint)}
.topnav{justify-content:center;gap:4px}.topnav a{display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:7px;color:var(--muted);text-decoration:none;font-size:12px;font-weight:550}.topnav a:hover{color:var(--text);background:var(--raised)}.topnav a.active{color:var(--accent);background:var(--tint)}.topnav .ico{width:16px;height:16px}
.appbar-tools{justify-content:flex-end;gap:6px}.appbar-tools button,.appbar-tools .btn{border-color:var(--line);background:var(--raised);padding:8px 11px}.appbar-tools .theme-track{display:none}.appbar-tools .logout{width:37px;height:37px;padding:8px;border:1px solid var(--line);border-radius:8px}.appbar-tools .logout span{display:none}
main{width:100%;max-width:1680px;margin:0 auto;padding:34px clamp(22px,4vw,66px) 50px}.page-head{margin-bottom:26px}.page-head h1{font-size:31px}.classic-footer{max-width:1680px;margin:0 auto;padding:0 clamp(22px,4vw,66px) 26px;display:flex;justify-content:flex-end;gap:16px}.classic-footer a{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:10px;text-decoration:none}.classic-footer .ico{width:14px;height:14px}
.card,.account,.clients-summary,.clients-panel{border-radius:12px}.overview-stats{gap:18px}.overview-stat{padding:18px 20px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.overview-stat:first-child{border-color:var(--line)}.overview-stat b{font-family:"Segoe UI",system-ui,sans-serif;font-size:25px;letter-spacing:-.03em}
.resource-deck{padding:22px 0;margin-bottom:18px}.resource-deck .resource-grid{margin:0;gap:0}.resource-deck .resource{display:flex;align-items:center;gap:17px;padding:0 22px;border:0;border-right:1px solid var(--line);border-radius:0;background:transparent}.resource-deck .resource:last-child{border-right:0}.resource-ring{position:relative;display:grid;place-items:center;width:72px;height:72px;flex:0 0 auto;border-radius:50%;background:conic-gradient(var(--accent) var(--value,0%),var(--line) 0)}.resource-ring:before{content:"";position:absolute;inset:5px;border-radius:50%;background:var(--surface)}.resource-ring b{position:relative;font-size:11px;font-weight:650;font-variant-numeric:tabular-nums}.resource-copy{min-width:0}.resource-copy strong{display:block;font-size:12px}.resource-copy small{display:block;margin-top:5px;font-size:10px}.resource-grid-title{display:none}
.graph-card{border-top:1px solid var(--line);background:var(--surface)}
.login-page{background:radial-gradient(circle at 50% 20%,var(--tint),transparent 34%),var(--bg)}.login-card{width:min(430px,100%);padding:34px;border:1px solid var(--line);border-radius:15px;background:var(--surface);box-shadow:var(--shadow)}.login-card .signin-logo{display:block;width:62px;height:62px;margin:0 auto 22px;border-radius:17px}.login-card h1{text-align:center;font-size:27px}.login-card>p{text-align:center;color:var(--muted);font-size:13px;margin-bottom:23px}.login-card .primary{width:100%;margin-top:23px}.login-card .login-version{display:block;text-align:center;margin-top:22px;font:10px ui-monospace,monospace;color:var(--muted)}
@media(max-width:900px){.appbar{grid-template-columns:1fr auto;padding:10px 18px;gap:10px}.topnav{grid-column:1/-1;grid-row:2;justify-content:stretch}.topnav a{flex:1;justify-content:center}.appbar-tools .theme-label{display:none}.appbar-left{gap:11px}main{padding:28px 20px 42px}.resource-deck .resource-grid{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:22px}.resource-deck .resource:nth-child(2){border-right:0}.resource-deck .resource:nth-child(n+3){border-top:1px solid var(--line);padding-top:22px}.overview-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:560px){.appbar{position:static;padding:12px 14px}.mini-brand{width:34px;height:34px}.appbar .host{font-size:10px}.topnav{gap:2px}.topnav a{min-width:0;padding:9px 2px;font-size:9px;gap:0}.topnav .ico{display:none}.appbar-tools button,.appbar-tools .btn{width:34px;height:34px;padding:7px}.appbar-tools button span{display:none}main{padding:24px 14px 36px}.resource-deck{padding:0}.resource-deck .resource-grid{grid-template-columns:1fr}.resource-deck .resource{padding:16px 18px;border-right:0;border-top:1px solid var(--line)!important}.resource-deck .resource:first-child{border-top:0!important}.resource-ring{width:62px;height:62px}.overview-stats{gap:10px}.overview-stat{padding:15px}.classic-footer{padding:0 14px 22px}.login-card{padding:28px 22px}.login-theme{right:14px;top:14px}}
'''

# Compact connection workspace and quiet social actions in the fixed app bar.
CSS += '''
.classic-footer{display:none}.appbar-tools .social-icon,.appbar-tools .logout{display:grid;place-items:center;width:37px;height:37px;padding:8px;border:1px solid var(--line);border-radius:8px;color:var(--muted);background:var(--raised);text-decoration:none}.appbar-tools .social-icon:hover,.appbar-tools .logout:hover{color:var(--accent);border-color:var(--accent);background:var(--tint)}.appbar-tools .social-icon .ico{width:17px;height:17px}.appbar-tools .logout span{display:none}
.connection-dialog{width:min(404px,calc(100vw - 32px));padding:0;border-radius:16px;background:var(--surface);max-height:92dvh;box-shadow:var(--shadow);overflow:auto}.connection-header{padding:20px 22px 15px;border-bottom:1px solid var(--line)}.connection-heading small{display:block;margin-bottom:3px;color:var(--accent);font:600 9px/1.4 ui-monospace,monospace;letter-spacing:.13em}.connection-header h2{font-size:16px;font-weight:600}.connection-close{border:1px solid var(--line);width:32px;height:32px;background:var(--input);font-size:19px}.connection-body{display:flex;flex-direction:column;gap:14px;padding:18px 22px}.connection-info{width:100%;padding:15px;border:1px solid var(--line);border-radius:12px;background:var(--input);text-align:left}.connection-person{display:flex;align-items:center;gap:12px}.connection-person .client-initial{width:43px;height:43px;font-size:20px}.connection-person>div{min-width:0}.connection-info h3{font-size:19px;letter-spacing:-.02em;overflow-wrap:anywhere}.connection-kind{font-size:10px;letter-spacing:0;color:var(--muted);margin:3px 0 0}.connection-protocol{display:flex;justify-content:flex-start;flex-wrap:wrap;gap:6px;margin:14px 0}.connection-meta{display:grid;grid-template-columns:minmax(0,1fr) auto;margin:0;gap:8px;font-size:10px}.connection-meta span{display:block;min-width:0;padding:9px 10px;border:1px solid var(--line);border-radius:8px;background:var(--surface)}.connection-meta small{display:block;margin-bottom:3px;font-size:8px;letter-spacing:.08em;text-transform:uppercase}.connection-meta b{display:block;max-width:100%;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.qr-visual{width:100%;padding:15px;border:1px solid var(--line);border-radius:12px;background:linear-gradient(145deg,var(--raised),var(--input));text-align:center}.qr-canvas{position:relative;width:214px;height:214px;max-width:100%;margin:0 auto;display:grid;place-items:center;border:1px solid #dfe4eb;border-radius:14px;background:#fff;box-shadow:0 10px 26px #0002;padding:12px;overflow:hidden}.qr-canvas img{width:100%;height:100%;object-fit:contain}.qr-canvas.has-error{height:156px;border-color:color-mix(in srgb,var(--red) 35%,var(--line));background:color-mix(in srgb,var(--red) 7%,var(--surface));box-shadow:none}.qr-canvas.has-error:before{content:"!";display:grid;place-items:center;width:30px;height:30px;margin:0 auto 9px;border-radius:50%;background:color-mix(in srgb,var(--red) 14%,transparent);color:var(--red);font-weight:700}.qr-canvas.has-error p{padding:0 14px;color:var(--muted)}.qr-canvas p{font-size:11px;line-height:1.55;color:#4d6269;margin:0;padding:14px}.qr-caption{font-size:10px;max-width:250px;margin:11px auto 0;line-height:1.55}.qr-retry{margin:10px auto 0;font-size:10px;padding:7px 10px}.connection-footer{padding:0 22px 20px;border:0;background:transparent}.connection-footer .primary{width:100%;min-width:0;padding:12px;font-size:12px}.connection-status{font-size:10px;margin-top:9px;text-align:center}.connection-link{margin-top:11px}.connection-link summary{margin:0 auto;color:var(--accent);padding:5px;font-size:11px;list-style:none}.connection-link input{font-size:10px}.connection-privacy{margin:15px 0 0;padding-top:14px;border-top:1px solid var(--line);font-size:9px;line-height:1.6;color:var(--muted);text-align:center}.connection-dialog.docked{position:static;inset:auto;margin:0;width:100%;max-height:none;box-shadow:0 2px 8px #0002}.connection-slot:has(.docked[open]){position:sticky;top:78px}
@media(max-width:700px){.connection-dialog{width:min(404px,calc(100vw - 20px))}.connection-header{padding:17px 18px 14px}.connection-body{padding:15px 18px}.connection-footer{padding:0 18px 18px}.qr-canvas{width:204px;height:204px}.appbar-tools .social-icon{width:36px;height:36px;padding:8px}}
@media(max-width:420px){.appbar-left .host{display:none}.appbar-tools{gap:4px}.appbar-tools .social-icon,.appbar-tools .logout{width:34px;height:34px;padding:7px}}
'''


def qr_dialog():
    return '''<dialog id="accountQr" class="connection-dialog" aria-labelledby="qrDialogTitle"><header class="connection-header"><div class="connection-heading"><small>ДОСТУП К КЛИЕНТУ</small><h2 id="qrDialogTitle">Подключение</h2></div><button type="button" class="connection-close" data-close-dialog aria-label="Закрыть QR">×</button></header><div class="connection-body"><section class="connection-info"><div class="connection-person"><span id="qrInitial" class="client-initial" aria-hidden="true"></span><div><h3 id="qrClientName"></h3><p id="qrKind" class="connection-kind"></p></div></div><div id="qrProtocol" class="connection-protocol"></div><div class="connection-meta"><span><small>Сервер</small><b id="qrHost"></b></span><span id="qrPortRow" hidden><small>Порт</small><b id="qrPort"></b></span></div></section><div class="qr-visual"><div class="qr-canvas" aria-busy="true"><img id="accountQrImage" alt="QR подключения" hidden><p id="qrImageStatus" role="status">Создаём QR…</p></div><button type="button" id="qrRetry" class="qr-retry quiet" hidden>Повторить загрузку</button><p class="qr-caption"><span id="qrStepOne"></span><br><span id="qrStepTwo"></span></p></div></div><footer class="connection-footer"><button type="button" class="primary" id="qrCopy">'''+icon('copy')+'''<span>Скопировать ссылку</span></button><p id="qrCopyStatus" class="connection-status" role="status"></p><details id="qrLinkDetails" class="connection-link"><summary>Показать ссылку вручную</summary><input id="qrLink" readonly aria-label="Ссылка подключения" spellcheck="false"></details><p class="connection-privacy">QR и ссылка открывают доступ к подключению.<br>Храните их как пароль.</p></footer></dialog>'''+QR_JS


QR_JS='''<script>
(()=>{const dialog=document.getElementById('accountQr'),image=document.getElementById('accountQrImage'),status=document.getElementById('qrImageStatus'),retry=document.getElementById('qrRetry'),canvas=dialog.querySelector('.qr-canvas'),copy=document.getElementById('qrCopy'),copyStatus=document.getElementById('qrCopyStatus'),link=document.getElementById('qrLink');let serial=0,endpoint='';
function clearImage(){image.onload=null;image.onerror=null;image.hidden=true;image.removeAttribute('src')}
function loadQr(){const generation=++serial;clearImage();canvas.classList.remove('has-error');status.hidden=false;status.textContent='Создаём QR…';canvas.setAttribute('aria-busy','true');retry.hidden=true;image.onload=()=>{if(generation!==serial)return;image.hidden=false;status.hidden=true;canvas.setAttribute('aria-busy','false')};image.onerror=()=>{if(generation!==serial)return;clearImage();canvas.classList.add('has-error');status.textContent='Не удалось создать QR. Обновите список и попробуйте ещё раз.';retry.hidden=false;canvas.setAttribute('aria-busy','false')};const separator=endpoint.includes('?')?'&':'?';image.src=endpoint+separator+'_qr='+generation+'-'+Date.now()}
const wide=matchMedia('(min-width:1440px)');let opener=null;
function selectedRow(q){document.querySelectorAll('[data-client]').forEach(row=>{const chosen=row===q?.closest('[data-client]');row.classList.toggle('qr-selected',chosen);const b=row.querySelector('[data-qr]');if(b)b.setAttribute('aria-expanded',String(chosen))})}
function openQr(q){let info;try{info=JSON.parse(q.dataset.qrInfo)}catch(e){return}opener=q;endpoint=q.dataset.qr;document.getElementById('qrClientName').textContent=info.name;document.getElementById('qrInitial').textContent=Array.from(info.name.trim())[0]?.toLocaleUpperCase('ru')||'•';document.getElementById('qrKind').textContent=info.kind==='subscription'?'Ссылка подписки':'Отдельное подключение';const protocols=document.getElementById('qrProtocol');protocols.replaceChildren();info.protocols.split(' · ').forEach(p=>{const badge=document.createElement('span');badge.className='pill';badge.textContent=p;protocols.appendChild(badge)});document.getElementById('qrHost').textContent=info.host;document.getElementById('qrPortRow').hidden=info.port===null;document.getElementById('qrPort').textContent=info.port??'';document.getElementById('qrStepOne').textContent=info.openflux?'Отсканируйте QR в приложении OpenFlux':info.web?'Сканируйте камерой другого устройства.':'Отсканируйте в совместимом приложении';document.getElementById('qrStepTwo').textContent=info.openflux?'Добавится ссылка на публичный документ.':info.web?'Откройте ссылку в Telegram.':'или скопируйте ссылку.';link.value=info.link;copyStatus.textContent='';copy.disabled=false;document.getElementById('qrLinkDetails').open=false;selectedRow(q);const dock=wide.matches&&!q.closest('dialog')&&!document.querySelector('dialog:modal');if(dialog.open&&dialog.classList.contains('docked')!==dock){dialog.close();return}dialog.classList.toggle('docked',dock);if(!dialog.open){if(dock)dialog.show();else dialog.showModal()}loadQr()}
document.addEventListener('click',e=>{const q=e.target.closest('[data-qr]');if(q)openQr(q)});
// Switching layout closes the private card instead of leaving a modal trapped off-screen.
wide.addEventListener('change',()=>{if(dialog.open)dialog.close()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&dialog.open&&dialog.classList.contains('docked')&&!document.querySelector('dialog:modal')){e.preventDefault();dialog.close()}});
document.addEventListener('onyx-filtered',()=>{if(dialog.open&&opener?.closest('[data-client]')?.hidden)dialog.close()});
document.querySelectorAll('[data-open-client],#newAccount').forEach(b=>b.addEventListener('click',()=>{if(dialog.open)dialog.close()}));
retry.addEventListener('click',loadQr);copy.addEventListener('click',async()=>{const generation=serial;copy.disabled=true;try{await onyxCopy(link.value,dialog);if(generation===serial)copyStatus.textContent='Ссылка скопирована — можно вставлять в приложение.'}catch(e){if(generation===serial){document.getElementById('qrLinkDetails').open=true;link.focus();link.select();copyStatus.textContent='Не удалось скопировать автоматически. Скопируйте выделенную ссылку.'}}finally{if(generation===serial)copy.disabled=false}});
dialog.addEventListener('close',()=>{++serial;clearImage();canvas.classList.remove('has-error');link.value='';endpoint='';copyStatus.textContent='';selectedRow(null);dialog.classList.remove('docked');if(opener?.isConnected&&!opener.closest('[hidden]')&&!document.querySelector('dialog:modal'))opener.focus({preventScroll:true})});
})();
</script>'''

CSS += '''
.create-dialog{width:min(760px,calc(100vw - 28px));padding:0;overflow:hidden}.create-dialog .dialog-head{padding:24px 26px 18px;margin:0;border-bottom:1px solid var(--line)}.create-dialog form{padding:22px 26px 25px;overflow:auto;max-height:calc(90dvh - 78px)}.create-step{margin-top:22px}.create-step:first-of-type{margin-top:18px}.create-step-title{display:flex;align-items:center;gap:9px;margin-bottom:11px;font-size:12px;color:var(--muted)}.create-step-title i{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:var(--tint);color:var(--accent);font:600 11px/1 ui-monospace,monospace}.create-mode-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.choice-card{position:relative;display:flex;gap:12px;align-items:flex-start;margin:0;padding:15px;border:1px solid var(--line);border-radius:11px;background:var(--input);color:var(--text);cursor:pointer}.choice-card:hover{border-color:var(--accent)}.choice-card input{width:16px;height:16px;flex:0 0 auto;margin-top:3px;accent-color:var(--accent)}.choice-card:has(input:checked){border-color:var(--accent);background:var(--tint);box-shadow:inset 0 0 0 1px var(--accent)}.choice-card strong{display:block;font-size:13px}.choice-card small{display:block;font-size:10px;line-height:1.45;margin-top:4px}.protocol-picker{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.protocol-picker .choice-card{min-height:76px}.protocol-picker em{font:500 9px/1.5 ui-monospace,monospace;color:var(--accent);display:block;margin-top:5px}.device-row{display:grid;grid-template-columns:minmax(0,1fr) 150px;gap:14px;align-items:end}.device-row label{margin-top:0}.create-summary{display:flex;align-items:center;justify-content:space-between;gap:15px;margin-top:22px;padding:14px 15px;border:1px solid var(--line);border-radius:10px;background:var(--raised)}.create-summary span{font-size:11px;color:var(--muted)}.create-summary b{font-size:12px;text-align:right}.create-actions{position:sticky;z-index:2;bottom:-25px;justify-content:flex-end;margin-top:18px;padding:13px 0 0;background:linear-gradient(transparent,var(--surface) 18%)}.create-actions .primary{min-width:150px}.proto-mtproto{color:var(--green)}
.secret-editor{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:8px;margin:8px 0}.secret-editor input{min-width:0;font:11px ui-monospace,monospace}.secret-editor+small{display:block;margin-bottom:12px;line-height:1.5;color:var(--muted)}
.live-indicator{display:inline-flex;align-items:center;gap:7px;margin-left:auto;padding:7px 10px;border:1px solid var(--line);border-radius:8px;font-size:10px;color:var(--muted);white-space:nowrap}.live-indicator i{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px color-mix(in srgb,var(--green) 14%,transparent)}.live-indicator.stale i{background:var(--amber);box-shadow:none}.live-indicator.offline i{background:var(--red);box-shadow:none}.live-block{transition:opacity .18s ease}.live-block.refreshing{opacity:.72}
@media(max-width:620px){.create-dialog .dialog-head{padding:19px}.create-dialog form{padding:18px}.create-mode-grid,.protocol-picker{grid-template-columns:1fr}.device-row{grid-template-columns:1fr}.create-summary{align-items:flex-start;flex-direction:column}.create-actions{display:grid;grid-template-columns:1fr 1fr;bottom:-17px}.create-actions .primary{min-width:0}.secret-editor{grid-template-columns:1fr 1fr}.secret-editor input{grid-column:1/-1}}
'''


def theme_button(): return '<button type="button" class="quiet" data-theme-toggle aria-label="Переключить тему">'+icon('sun')+'</button>'


def restart_buttons(path, csrf):
    if not csrf: return ''
    return (f'<button type="button" class="quiet" data-service-restart="panel" data-url="{esc(path)}/service-restart" data-csrf="{esc(csrf)}" aria-label="Перезапустить панель" title="Перезапустить панель">{icon("power")}</button>'
            f'<button type="button" class="quiet" data-service-restart="modules" data-url="{esc(path)}/service-restart" data-csrf="{esc(csrf)}" aria-label="Перезапустить модули" title="Перезапустить модули — Xray, релей, MTProxy">{icon("refresh")}</button>')


def page_layout(title, body, path, active, domain, csrf=''):
    links = ''.join(f'<a class="{"active" if key==active else ""}" href="{esc(path)}/{key}">{icon(glyph)}{label}</a>' for key, label, glyph in [('dashboard','Дашборд','grid'),('users','Пользователи','users'),('nodes','Ноды','nodes'),('cascade','Каскад','cascade'),('routing','Маршрутизация','route'),('updates','Обновления','refresh'),('settings','Настройки','settings')])
    social = ''
    banner = f'''<aside id="releaseBanner" class="release-banner" role="status" hidden><span class="release-banner-mark">{icon('refresh')}</span><div class="release-banner-copy"><b>Доступна новая версия Onyx Panel</b><small>Обновление можно установить с автоматической резервной копией</small></div><span id="releaseBannerVersion" class="release-banner-version"></span><div class="release-banner-actions"><a class="btn primary" href="{esc(path)}/updates">Посмотреть</a><button type="button" id="releaseBannerClose" class="release-banner-close" aria-label="Скрыть уведомление">×</button></div></aside>'''
    banner_script = f'''<script>(()=>{{const banner=document.getElementById('releaseBanner'),version=document.getElementById('releaseBannerVersion'),close=document.getElementById('releaseBannerClose');if(!banner)return;function dismissed(v){{try{{return localStorage.getItem('onyx-release-banner:'+v)==='1'}}catch(e){{return false}}}}function show(d){{if(!d||!d.available||!d.latest||dismissed(d.latest)){{banner.hidden=true;return}}banner.dataset.version=d.latest;version.textContent=(d.current||'—')+' → '+d.latest;banner.hidden=false}}async function check(){{try{{const r=await fetch('{esc(path)}/update-status',{{cache:'no-store'}});if(r.ok&&!r.redirected)show(await r.json())}}catch(e){{}}}}close.addEventListener('click',()=>{{const v=banner.dataset.version;if(v)try{{localStorage.setItem('onyx-release-banner:'+v,'1')}}catch(e){{}}banner.hidden=true}});window.addEventListener('onyx-update-status',e=>show(e.detail));check();setInterval(check,30000)}})();</script>'''
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#101318"><title>{esc(title)} · Onyx Panel</title><link rel="icon" type="image/png" href="{esc(path)}/__logo">{THEME_INIT}<style>{CSS}</style></head><body><div class="app"><div class="workspace"><header class="appbar"><div class="appbar-left"><a class="mini-brand" href="{esc(path)}/dashboard" aria-label="Onyx Panel"><img src="{esc(path)}/__logo" alt="" width="38" height="38"></a><div class="host"><i></i>{esc(domain)}</div></div><nav class="topnav" id="topnav" aria-label="Разделы панели">{links}</nav><div class="appbar-tools">{theme_button()}{restart_buttons(path, csrf)}{social}<a class="logout" href="{esc(path)}/logout" aria-label="Выйти">{icon('logout')}<span>Выйти</span></a><button type="button" class="burger" id="navBurger" aria-expanded="false" aria-controls="topnav" aria-label="Открыть меню">{icon('menu')}</button></div></header>{banner}<main>{body}</main></div></div>{COMMON_JS}{banner_script}</body></html>'''


def login_ui(path):
    return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#101318"><title>Вход · Onyx Panel</title><link rel="icon" type="image/png" href="{esc(path)}/__logo">{THEME_INIT}<style>{CSS}</style></head><body class="login-page"><div class="login-theme">{theme_button()}</div><main class="login-card"><img class="signin-logo" src="{esc(path)}/__logo" alt="Onyx Panel"><h1>Onyx Panel</h1><p>Панель управления подключениями</p><form method="post" action="{esc(path)}/login"><label for="loginName">Логин</label><input id="loginName" name="user" autocomplete="username" required autofocus><label for="loginPassword">Пароль</label><input id="loginPassword" type="password" name="password" autocomplete="current-password" required><button class="primary">Войти</button></form><small class="login-version">{VERSION}</small></main>{COMMON_JS}</body></html>'''



def hidden(csrf, **values):
    return ''.join(f'<input type="hidden" name="{esc(k)}" value="{esc(v)}">' for k,v in {'csrf':csrf, **values}.items())


def aggregate(ids, traffic, enabled=True):
    rows = [traffic.get(uid, {}) for uid in ids]
    return {'up': sum(max(0,int(r.get('up',0))) for r in rows), 'down': sum(max(0,int(r.get('down',0))) for r in rows),
            'active': enabled and any(r.get('service_active') and 0 <= time.time()-r.get('last_change',0) <= 90 for r in rows)}


def badge(active, enabled=True):
    return '<span class="badge '+('on' if active and enabled else '')+'">'+('Отключена' if not enabled else 'Передаёт трафик' if active else 'Нет трафика')+'</span>'


def protocol_checks(sub):
    choices=[('vless','VLESS XHTTP'),('hysteria','Hysteria2')]
    return '<div class="checks">'+''.join(f'<label class="check"><input type="checkbox" name="{p}" value="1" {"checked" if p in sub.get("protocols",["vless","hysteria"]) else ""}>{title}</label>' for p,title in choices)+'</div>'


def subscription_card(sub, path, domain, csrf, traffic, compact=False):
    sid = sub['id']; enabled = sub.get('enabled', True)
    total = aggregate(sub.get('profile_ids',[]), traffic, enabled)
    total['active'] = aggregate(sub.get('live_profile_ids', []), traffic, enabled)['active']
    url = 'https://'+domain+'/onyx-sub/'+sub['token']
    count = sum(not d.get('revoked') for d in sub['devices'])
    limit = str(count)+' / '+str(sub['max_devices']) if sub['max_devices'] else 'Без лимита'
    names={'vless':'VLESS','hysteria':'Hysteria2'}
    head = f'''<div class="account-head"><div class="identity"><div class="avatar">{icon('link')}</div><div><h3>{esc(sub['name'])}</h3><div class="pills"><span class="pill">Подписка</span>{''.join('<span class="pill">'+names.get(p,p)+'</span>' for p in sub['protocols'])}</div></div></div>{badge(total['active'],enabled)}</div><div class="account-metrics"><div><span>Устройства · HWID</span><b>{limit}</b></div><div><span>Трафик: {size(total['up']+total['down'])}</span><b>↑ {size(total['up'])} · ↓ {size(total['down'])}</b></div></div>'''
    buttons = f'<div class="actions"><button class="btn primary" data-copy="{esc(url)}">Скопировать подписку</button>'
    if compact:
        return f'<article class="account">{head}{buttons}<a class="btn" href="{esc(path)}/users#account-{esc(sid)}">Управление</a></div></article>'
    buttons += '<button '+qr_attributes(path+'/subscription-qr?'+urlencode({'id':sid}),sub['name'],url,sub['protocols'],'subscription')+'>QR</button></div>'
    def action(op, text, device=None, confirm=''):
        fields = {'operation':op,'id':sid}
        if device: fields['device_id']=device
        return f'<form method="post" action="{esc(path)}/subscription-action"'+(f' data-confirm="{esc(confirm)}"' if confirm else '')+'>'+hidden(csrf,**fields)+f'<button class="{"danger" if op in ("delete","rotate","revoke") else "quiet"}">{text}</button></form>'
    devices = []
    for d in sub['devices']:
        seen = time.strftime('%d.%m %H:%M UTC',time.gmtime(d.get('last_seen',0))) if d.get('last_seen') else '—'
        devices.append('<div class="device"><div><b>'+esc(d['name'])+'</b><small>'+('Отозвано' if d.get('revoked') else 'Разрешено')+' · обновление '+seen+'</small></div>'+action('allow' if d.get('revoked') else 'revoke','Разрешить' if d.get('revoked') else 'Отозвать',d['id'])+'</div>')
    details = f'''<details><summary>Настройки и устройства</summary><label>Ссылка подписки</label><input class="sub-url" value="{esc(url)}" readonly aria-label="Ссылка подписки {esc(sub['name'])}"><form method="post" action="{esc(path)}/subscription-action">{hidden(csrf,operation='update',id=sid)}<div class="form-grid"><div><label>Имя пользователя</label><input name="name" value="{esc(sub['name'])}" required maxlength="80"></div><div><label>Лимит HWID · 0 без привязки</label><input type="number" name="max_devices" min="0" max="20" value="{sub['max_devices']}" required></div></div>{protocol_checks(sub)}<button class="primary">Сохранить настройки</button></form><p class="note">Переход между 0 и ненулевым лимитом отзывает прежние ключи. Время обновления подписки не означает присутствие устройства онлайн.</p>{''.join(devices) or '<p class="muted">Устройства появятся после импорта подписки.</p>'}<div class="actions">{action('toggle','Отключить' if enabled else 'Включить')}{action('rotate','Сменить ссылку',confirm='Сменить ссылку и отозвать ключи всех устройств?')}{action('delete','Удалить',confirm='Удалить подписку и отозвать все её ключи?')}</div></details>'''
    return f'<article class="account" id="account-{esc(sid)}" data-account data-kind="subscription" data-name="{esc(sub["name"].lower())}">{head}{buttons}{details}</article>'


def direct_card(user, path, csrf, traffic, proxy_link, compact=False):
    uid=user['id']; proto=user.get('protocol','web'); port=int(user.get('backend_port',443))
    label={'web':'WEB Proxy','vless':'VLESS XHTTP','hysteria':'Hysteria2','mtproto':'MTProto','awg20':'AWG 2.0','awg31':'AWG 3.1'}.get(proto,proto)
    total=aggregate([uid],traffic,user.get('enabled',True))
    device_secrets=user.get('device_secrets') if proto=='mtproto' else None
    if not isinstance(device_secrets,list) or not device_secrets: device_secrets=[user['secret']]
    link=proxy_link(proto,device_secrets[0],port,user.get('name','Proxy'),user.get('username',''))
    qr=(path+'/__qr?'+urlencode({'id':uid}) if proto in ('awg20','awg31') else
        path+'/__qr?'+urlencode({'secret':user['secret'],'protocol':proto,
            'port':port if proto in ('hysteria','mtproto') else 443}))
    buttons=f'<button class="primary" data-copy="{esc(link)}">'+('Скопировать конфигурацию' if proto in ('awg20','awg31') else 'Скопировать ссылку')+'</button>'
    if not compact: buttons+='<button '+qr_attributes(qr,user['name'],link,[proto],user_port=port)+'>QR</button>'
    else: buttons+=f'<a class="btn" href="{esc(path)}/users#account-{esc(uid)}">Управление</a>'
    details=''
    if not compact:
        removal='<small>Основное подключение установки</small>' if uid=='primary' else f'<form method="post" action="{esc(path)}/delete-user" data-confirm="Удалить это подключение?">{hidden(csrf,id=uid)}<button class="danger">Удалить подключение</button></form>'
        secret_editor=''
        if proto in ('web','mtproto'):
            secret_editor=f'''<form method="post" action="{esc(path)}/client-action" data-client-action data-client-confirm="После сохранения прежний секрет сразу перестанет работать. Продолжить?">{hidden(csrf,id=uid,kind='direct',operation='secret')}<label for="secret-{esc(uid)}">Секрет {esc(label)}</label><div class="secret-editor"><input id="secret-{esc(uid)}" name="secret" type="password" value="{esc(user['secret'])}" minlength="32" maxlength="34" pattern="(?:dd)?[0-9A-Fa-f]{{32}}" autocomplete="off" spellcheck="false" required><button type="button" data-secret-reveal="secret-{esc(uid)}">Показать</button><button class="primary">Сохранить</button></div><small>32 символа 0–9, a–f. Для MTProto можно вставить секрет из Telegram с префиксом dd. Порт подключения не изменяется.</small><p data-form-status role="status"></p></form>'''
        value_title='Конфигурация AWG' if proto in ('awg20','awg31') else 'Ссылка подключения'
        value_control=f'<textarea class="sub-url" readonly rows="8" aria-label="{value_title} {esc(user["name"])}">{esc(link)}</textarea>' if proto in ('awg20','awg31') else f'<input class="sub-url" value="{esc(link)}" readonly aria-label="Ссылка {esc(user["name"])}">'
        if proto=='mtproto':
            device_rows=[]
            for index,secret in enumerate(device_secrets,1):
                device_link=proxy_link('mtproto',secret,port,user.get('name','MTProto')+' · '+str(index),'')
                device_qr=path+'/__qr?'+urlencode({'secret':secret,'protocol':'mtproto','port':port})
                device_rows.append(f'<div class="mtproto-device"><div><b>Устройство {index}</b><small>Отдельный ключ доступа</small></div><button type="button" data-copy="{esc(device_link)}">Скопировать</button><button type="button" '+qr_attributes(device_qr,user.get('name','MTProto')+' · устройство '+str(index),device_link,['mtproto'],user_port=port)+'>QR</button></div>')
            value_control=f'<div class="mtproto-access-head"><span>TCP-порт</span><b>{port}</b><small>Открыт панелью в firewall</small></div><div class="mtproto-devices">{"".join(device_rows)}</div>'
        download=f'<a class="btn" href="{esc(path)}/awg-config?{urlencode({"id":uid})}">Скачать .conf</a>' if proto in ('awg20','awg31') else ''
        access_note=(f'{len(device_secrets)} отдельных ключей устройств · Telegram не передаёт серверу HWID' if proto=='mtproto' else 'Отдельное подключение · без ограничения устройств')
        details=f'<details><summary>Параметры подключения</summary><p class="muted">{access_note}</p>{value_control}{download}{secret_editor}{removal}</details>'
    return f'''<article class="account" id="account-{esc(uid)}" data-account data-kind="direct" data-name="{esc(user['name'].lower())}"><div class="account-head"><div class="identity"><div class="avatar">{icon('users')}</div><div><h3>{esc(user['name'])}</h3><div class="pills"><span class="pill">{esc(label)}</span><span class="pill">Отдельная ссылка</span></div></div></div>{badge(total['active'],user.get('enabled',True))}</div><div class="account-metrics"><div><span>Получено</span><b>{size(total['down'])}</b></div><div><span>Отправлено</span><b>{size(total['up'])}</b></div><div><span>Всего</span><b>{size(total['up']+total['down'])}</b></div></div><div class="actions">{buttons}</div>{details}</article>'''


def live_subscriptions(subs, profiles):
    # Keep historical traffic, but never report a revoked profile as active.
    return [dict(s, live_profile_ids=[u['id'] for u in profiles
                 if u.get('subscription_id') == s['id'] and u.get('enabled', True)]) for s in subs]


def client_records(subs, profiles, traffic, domain, proxy_link, expires=None):
    records=[]
    for s in live_subscriptions(subs,profiles):
        totals=aggregate(s.get('profile_ids',[]),traffic,s.get('enabled',True))
        totals['active']=aggregate(s['live_profile_ids'],traffic,s.get('enabled',True))['active']
        records.append(dict(id=s['id'],name=s['name'],kind='subscription',protocols=s['protocols'],
            enabled=s.get('enabled',True),created=s.get('created_at',0),totals=totals,
            link='https://'+domain+'/onyx-sub/'+s['token'],source=s,
            devices=sum(not d.get('revoked') for d in s['devices']),limit=s['max_devices'],
            expires=(expires or {}).get(s['id'])))
    for u in profiles:
        if u.get('subscription_id'): continue
        proto=u.get('protocol','web')
        # Old experimental builds could leave Mieru or NaiveProxy records in
        # users.json. Preserve them for rollback without rendering them.
        if proto not in {'web','vless','hysteria','mtproto','awg20','awg31'}:
            continue
        try:
            link=proxy_link(proto,u['secret'],int(u.get('backend_port',443)),u['name'],u.get('username',''))
        except (KeyError, TypeError, ValueError, RuntimeError):
            continue
        mt_devices=u.get('device_secrets') if proto=='mtproto' else None
        if proto=='mtproto' and (not isinstance(mt_devices,list) or not mt_devices): mt_devices=[u.get('secret','')]
        records.append(dict(id=u['id'],name=u['name'],kind='direct',protocols=[proto],
            enabled=u.get('enabled',True),created=u.get('created_at',0),totals=aggregate([u['id']],traffic,u.get('enabled',True)),
            link=link,source=u,devices=len(mt_devices) if proto=='mtproto' else None,
            limit=len(mt_devices) if proto=='mtproto' else None,
            expires=(expires or {}).get(u['id'])))
    return records


def client_protocols(protocols):
    names={'web':'WEB Proxy','vless':'VLESS XHTTP','hysteria':'Hysteria2','mtproto':'MTProto','awg20':'AWG 2.0','awg31':'AWG 3.1','openflux':'OpenFlux'}
    return '<div class="pills">'+''.join('<span class="pill proto-'+esc(p)+'">'+esc(names.get(p,p))+'</span>' for p in protocols)+'</div>'


def client_summary(records):
    counts=[('Всего',len(records)),('Передают данные',sum(bool(r['totals']['active']) for r in records)),
            ('Подписки',sum(r['kind']=='subscription' for r in records)),
            ('Трафик',size(sum(r['totals']['up']+r['totals']['down'] for r in records)))]
    return '<div class="clients-summary">'+''.join(f'<div class="client-stat"><span>{label}</span><b>{value}</b></div>' for label,value in counts)+'</div>'


def client_glances(records,path):
    rows=[]
    for r in records:
        t=r['totals']; kind='Подписка' if r['kind']=='subscription' else 'Отдельная ссылка'
        rows.append(f'<div class="client-glance"><div><strong>{esc(r["name"])}</strong><small>{kind}</small></div>{client_protocols(r["protocols"])}<div class="traffic-value">{size(t["up"]+t["down"])}</div><a class="btn quiet" href="{esc(path)}/users#account-{esc(r["id"])}">Управление ↗</a></div>')
    return '<div class="dashboard-clients">'+(''.join(rows) or '<p class="empty">Клиентов пока нет</p>')+'</div>'


def openflux_profiles_ui(profiles, path, csrf):
    cards=[]
    for profile in profiles:
        pid=profile['id']; ios=profile.get('platform')=='ios'; active=profile.get('active',False)
        platform='iOS' if ios else 'Android'
        transport=profile.get('transport','yandex')
        provider='Mail.ru Docs' if transport=='mailru' else 'Яндекс Документы'
        key='' if ios else f'''<div class="flux-profile-secret"><span>Ключ</span><input value="{esc(profile.get('key',''))}" readonly type="password" aria-label="Ключ OpenFlux — {esc(profile.get('name',''))}"><button type="button" data-copy="{esc(profile.get('key',''))}">{icon('copy')}</button></div>'''
        controls=f'''<form method="post" action="{esc(path)}/openflux-profile">{hidden(csrf,operation='disable' if profile.get('enabled') else 'enable',id=pid)}<button>{'Остановить' if profile.get('enabled') else 'Запустить'}</button></form>'''
        if not ios:
            controls+=f'''<form method="post" action="{esc(path)}/openflux-profile" data-confirm="Создать новый ключ для этого Android-профиля?">{hidden(csrf,operation='rotate',id=pid)}<button>Новый ключ</button></form>'''
        controls+=f'''<form method="post" action="{esc(path)}/openflux-profile" data-confirm="Удалить профиль OpenFlux «{esc(profile.get('name',''))}» и остановить его службу?">{hidden(csrf,operation='delete',id=pid)}<button class="danger">Удалить</button></form>'''
        cards.append(f'''<article class="flux-profile"><div class="flux-profile-head"><span class="flux-platform">{platform}</span><div><h3>{esc(profile.get('name','OpenFlux'))}</h3><small>{esc(provider)} · {'без AES · System VPN' if ios else 'AES-256-GCM'} · batched</small></div><span class="badge {'on' if active else ''}">{'Работает' if active else 'Остановлен'}</span></div><div class="flux-profile-secret"><span>{esc(provider)}</span><input value="{esc(profile.get('url',''))}" readonly aria-label="Документ OpenFlux — {esc(profile.get('name',''))}"><button type="button" data-copy="{esc(profile.get('url',''))}">{icon('copy')}</button></div>{key}<div class="actions">{controls}</div></article>''')
    empty='<div class="flux-empty"><b>Профилей пока нет</b><span>Создайте отдельный доступ для iPhone, iPad или Android.</span></div>'
    return f'''<section class="openflux-users"><div class="section-head"><div><span class="eyebrow">DOCUMENT TUNNEL</span><h2>Пользователи OpenFlux</h2><p>Яндекс или Mail.ru · каждому пользователю отдельный документ</p></div><button class="primary" type="button" data-open-dialog="newOpenFlux">＋ Добавить</button></div><div class="flux-profile-grid">{''.join(cards) if cards else empty}</div></section><dialog id="newOpenFlux" class="create-dialog"><div class="dialog-head"><div><h2>Новый профиль OpenFlux</h2><small>Используйте отдельный публичный документ</small></div><button type="button" data-close-dialog>×</button></div><form method="post" action="{esc(path)}/openflux-profile">{hidden(csrf,operation='create')}<label>Имя пользователя</label><input name="name" maxlength="80" required placeholder="Например, iPhone Анны"><label>Транспорт</label><div class="create-mode-grid flux-platform-picker"><label class="choice-card"><input type="radio" name="transport" value="yandex" checked><span><strong>Яндекс Документы</strong><small>Публичная ссылка disk.yandex.ru</small></span></label><label class="choice-card"><input type="radio" name="transport" value="mailru"><span><strong>Mail.ru Документы</strong><small>Публичная ссылка cloud.mail.ru</small></span></label></div><label>Ссылка на публичный документ</label><input name="url" type="url" maxlength="2048" required placeholder="https://disk.yandex.ru/i/… или https://cloud.mail.ru/public/…"><label>Устройство</label><div class="create-mode-grid flux-platform-picker"><label class="choice-card"><input type="radio" name="platform" value="ios" checked><span><strong>iOS</strong><small>iPhone и iPad · без AES-ключа</small></span></label><label class="choice-card"><input type="radio" name="platform" value="android"><span><strong>Android</strong><small>AES-256-GCM · ссылка и ключ</small></span></label></div><p class="note">Один документ нельзя одновременно использовать в нескольких активных профилях. В приложении выберите тот же транспорт, что и в панели.</p><div class="actions create-actions"><button type="button" data-close-dialog>Отмена</button><button class="primary">Создать профиль</button></div></form></dialog>'''


def openflux_create_dialog(path, csrf):
    markup = openflux_profiles_ui([], path, csrf)
    return markup[markup.index('<dialog id="newOpenFlux"'):]


def users_ui(subs, profiles, traffic, path, domain, csrf, proxy_link, openflux_profiles=None, expires=None):
    records=client_records(subs,profiles,traffic,domain,proxy_link,expires)
    rows=[]; dialogs=[]
    for r in records:
        uid=r['id']; sid=esc(uid); name=esc(r['name']); t=r['totals']; enabled=r['enabled']; total=t['up']+t['down']
        primary=uid=='primary'; kind=r['kind']; sub=kind=='subscription'
        proto=r['protocols'][0]
        exp=r.get('expires')
        exp_pill=(f'<span class="pill expiry-pill{" expired" if exp<int(time.time()) else ""}" title="Автоотключение доступа">до {time.strftime("%d.%m.%Y",time.localtime(exp))}</span>') if exp else ''
        qr=(path+'/subscription-qr?'+urlencode({'id':uid}) if sub else
            path+'/__qr?'+urlencode({'id':uid}) if proto in ('awg20','awg31') else
            path+'/__qr?'+urlencode({'secret':r['source']['secret'],'protocol':proto,
                'port':r['source'].get('backend_port',443) if proto in ('hysteria','mtproto') else 443}))
        disabled='disabled title="Основное подключение установки"' if primary else ''
        state=f'<button class="access-switch" type="button" role="switch" aria-label="Доступ — {name}" aria-checked="{str(bool(enabled)).lower()}" data-state="{sid}" data-kind="{kind}" {disabled}></button>'
        action=f'<button class="icon-btn" {qr_attributes(qr,r["name"],r["link"],r["protocols"],kind,user_port=r["source"].get("backend_port"))} aria-label="QR — {name}" title="QR">{icon("qr")}</button><button class="icon-btn" data-copy="{esc(r["link"])}" aria-label="Скопировать — {name}" title="Копировать">{icon("copy")}</button><button class="icon-btn" data-open-client="{sid}" aria-label="Настройки — {name}" title="Настройки">{icon("edit")}</button>'
        if not primary:
            route='subscription-action' if sub else 'delete-user'
            action+=f'<form method="post" action="{esc(path)}/{route}" data-confirm="Удалить клиента {name} и его ключи?">{hidden(csrf,id=uid,**({"operation":"delete"} if sub else {}))}<button class="icon-btn danger" aria-label="Удалить — {name}" title="Удалить">{icon("trash")}</button></form>'
        used=(str(r['devices'])+' / '+str(r['limit'])) if r['limit'] else 'Без лимита' if sub else '—'
        device_hint='HWID' if r['limit'] else 'Без привязки' if sub else 'Отдельная ссылка'
        share=t['up']/total*100 if total else 0
        split=f'<div class="traffic-split" title="Доля отправки и получения, не лимит"><i class="up" style="width:{share:.2f}%"></i><i class="down" style="width:{100-share if total else 0:.2f}%"></i></div>'
        rows.append(f'''<tr data-client data-id="{sid}" data-kind="{kind}" data-protocols="{esc(' '.join(r['protocols']))}" data-name="{name}" data-enabled="{int(bool(enabled))}" data-active="{int(bool(t['active']))}" data-created="{int(r['created'])}" data-traffic="{int(total)}" data-link="{esc(r['link'])}"><td class="select-col"><input type="checkbox" data-select-client aria-label="Выбрать — {name}" {'disabled' if primary else ''}></td><td class="client-name" data-label="Клиент"><div class="client-identity"><span class="client-initial" aria-hidden="true">{esc(r['name'].strip()[:1].upper() or '•')}</span><div><strong>{name}</strong><small>{'Подписка' if sub else 'Основное подключение' if primary else 'Отдельная ссылка'}</small>{badge(t['active'],enabled)}{exp_pill}</div></div></td><td class="state-col" data-label="Доступ">{state}</td><td class="activity-col" data-label="Активность">{badge(t['active'],enabled)}</td><td class="protocol-col" data-label="Протоколы">{client_protocols(r['protocols'])}</td><td class="traffic-cell" data-label="Трафик"><b>{size(total)}</b><small>↑ {size(t['up'])} · ↓ {size(t['down'])}</small>{split}</td><td class="hwid-cell" data-label="Устройства">{used}<small>{device_hint}</small></td><td class="actions-col" data-label="Действия"><div class="row-actions">{action}</div></td></tr>''')
        detail=subscription_card(r['source'],path,domain,csrf,traffic) if sub else direct_card(r['source'],path,csrf,traffic,proxy_link)
        detail=detail.replace('<details>','<details open>')
        if not sub and not primary:
            rename=f'<form method="post" action="{esc(path)}/client-action" data-client-action>{hidden(csrf,id=uid,kind=kind,operation="rename")}<label for="rename-{sid}">Имя клиента</label><input id="rename-{sid}" name="name" value="{name}" required maxlength="80"><button style="margin:12px 0" class="primary">Сохранить имя</button><p data-form-status role="status"></p></form>'
            detail=detail.replace('<details open>','<details open>'+rename,1)
        if not primary:
            expiry_value=time.strftime("%Y-%m-%d",time.localtime(r["expires"])) if r.get("expires") else ""
            expiry=f'<form method="post" action="{esc(path)}/client-action" data-client-action style="margin-top:16px;border-top:1px solid var(--line);padding-top:14px">{hidden(csrf,id=uid,kind=kind,operation="expiry")}<label for="expiry-{sid}">Дата автоотключения</label><div class="onyx-cal" id="expiry-{sid}"><input type="hidden" name="expires" value="{expiry_value}" autocomplete="off"><button type="button" class="onyx-cal-field" aria-label="Выбрать дату автоотключения"><svg class="onyx-cal-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/></svg><span class="onyx-cal-value"></span><svg class="onyx-cal-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div class="onyx-cal-pop" role="dialog" aria-label="Календарь"><div class="onyx-cal-head"><button type="button" class="onyx-cal-nav" data-cal-prev aria-label="Предыдущий месяц">‹</button><div class="onyx-cal-title"></div><button type="button" class="onyx-cal-nav" data-cal-next aria-label="Следующий месяц">›</button></div><div class="onyx-cal-week"><span>пн</span><span>вт</span><span>ср</span><span>чт</span><span>пт</span><span>сб</span><span>вс</span></div><div class="onyx-cal-grid"></div><div class="onyx-cal-foot"><button type="button" class="onyx-cal-clear" data-cal-clear>Без даты окончания</button></div></div></div><button style="margin:12px 0" class="primary">Сохранить срок</button><p data-form-status role="status"></p></form>'
            detail=detail+expiry
        dialogs.append(f'<dialog class="client-detail" id="client-{sid}"><div class="dialog-head"><h2>Профиль клиента</h2><button data-close-dialog aria-label="Закрыть профиль">×</button></div>{detail}</dialog>')
    flux_profiles=openflux_profiles or []
    for profile in flux_profiles:
        pid=str(profile.get('id','')); sid=esc('openflux-'+pid); name=esc(profile.get('name','OpenFlux'))
        enabled=bool(profile.get('enabled',True)); active=bool(profile.get('active',False)); ios=profile.get('platform')=='ios'
        platform='iOS' if ios else 'Android'; transport=profile.get('transport','yandex')
        provider='Mail.ru' if transport=='mailru' else 'Яндекс'; created=int(profile.get('created_at',0) or 0)
        document_url=str(profile.get('url') or '')
        state=f'''<form method="post" action="{esc(path)}/openflux-profile">{hidden(csrf,operation='disable' if enabled else 'enable',id=pid)}<button class="access-switch" type="submit" role="switch" aria-label="Доступ OpenFlux — {name}" aria-checked="{str(enabled).lower()}" title="{'Остановить' if enabled else 'Запустить'} OpenFlux"></button></form>'''
        qr=esc(path)+'/openflux-qr?'+urlencode({'id':pid})
        action=f'''<button class="icon-btn" {qr_attributes(qr,profile.get('name','OpenFlux'),document_url,['openflux'],'direct')} aria-label="QR ссылки — {name}" title="QR ссылки на документ">{icon('qr')}</button><button class="icon-btn" data-copy="{esc(document_url)}" aria-label="Скопировать ссылку — {name}" title="Копировать ссылку на документ">{icon('copy')}</button><form method="post" action="{esc(path)}/openflux-profile" data-confirm="Удалить профиль OpenFlux «{name}» и остановить его службу?">{hidden(csrf,operation='delete',id=pid)}<button class="icon-btn danger" aria-label="Удалить — {name}" title="Удалить">{icon('trash')}</button></form>'''
        rows.append(f'''<tr data-client data-id="{sid}" data-kind="openflux" data-protocols="openflux" data-name="{name}" data-enabled="{int(enabled)}" data-active="{int(active)}" data-created="{created}" data-traffic="0" data-link="{esc(document_url)}"><td class="select-col"><input type="checkbox" data-select-client aria-label="OpenFlux управляется отдельно" disabled></td><td class="client-name" data-label="Клиент"><div class="client-identity"><span class="client-initial" aria-hidden="true">OF</span><div><strong>{name}</strong><small>Отдельное подключение · {esc(platform)}</small>{badge(active,enabled)}</div></div></td><td class="state-col" data-label="Доступ">{state}</td><td class="activity-col" data-label="Активность">{badge(active,enabled)}</td><td class="protocol-col" data-label="Протоколы">{client_protocols(['openflux'])}</td><td class="traffic-cell" data-label="Трафик"><b>—</b><small>Счётчики OpenFlux недоступны</small></td><td class="hwid-cell" data-label="Устройства">{esc(platform)}<small>{esc(provider)} Docs</small></td><td class="actions-col" data-label="Действия"><div class="row-actions">{action}</div></td></tr>''')
    summary_records=records+[{'kind':'direct','totals':{'active':bool(p.get('active',False)),'up':0,'down':0}} for p in flux_profiles]
    controls='''<div class="clients-toolbar"><div class="search-field">'''+icon('search')+'''<input type="search" id="accountSearch" aria-label="Поиск клиентов" placeholder="Поиск клиентов"></div><select id="clientFilter" aria-label="Фильтр клиентов"><option value="all">Все клиенты</option><option value="subscription">Подписки</option><option value="direct">Отдельные подключения</option><option value="openflux">OpenFlux</option><option value="active">Передают данные</option><option value="enabled">Доступ включён</option><option value="disabled">Отключены</option></select><select id="protocolFilter" aria-label="Фильтр протоколов"><option value="all">Все протоколы</option><option value="web">WEB Proxy</option><option value="mtproto">MTProto</option><option value="vless">VLESS XHTTP</option><option value="hysteria">Hysteria2</option><option value="awg20">AWG 2.0</option><option value="awg31">AWG 3.1</option><option value="openflux">OpenFlux</option></select><select id="clientSort" aria-label="Сортировка клиентов"><option value="default">По порядку</option><option value="name">По имени</option><option value="traffic">По трафику</option><option value="active">По активности</option><option value="newest">Сначала новые</option></select></div>'''
    content=f'''<div class="page-head"><div><h1>Клиенты</h1><p>Доступ, подписки и OpenFlux</p></div><div class="actions"><button id="reloadClients" aria-label="Обновить список">{icon('refresh')}</button><button class="primary" id="newAccount">＋ Добавить клиента</button></div></div>{client_summary(summary_records)}<p id="clientNotice" class="note" role="status" hidden></p><section class="clients-panel">{controls}<div id="bulkBar" class="bulk-bar" hidden><strong id="selectedCount"></strong><button data-bulk="1">Включить</button><button data-bulk="0">Отключить</button><button id="copySelected">Копировать ссылки</button><button id="clearSelected">Снять выбор</button></div><div class="table-scroll"><table class="clients-table"><thead><tr><th class="select-col"><input type="checkbox" id="selectAllClients" aria-label="Выбрать видимых клиентов"></th><th>Клиент</th><th>Доступ</th><th class="activity-col">Активность · 90 с</th><th>Протоколы</th><th>Трафик</th><th class="hwid-cell">Устройства</th><th>Действия</th></tr></thead><tbody id="clientRows">{''.join(rows)}</tbody></table><p id="noAccounts" class="empty" hidden>Ничего не найдено. Измените поиск или фильтр.</p></div><div class="list-footer"><span id="visibleCount"></span><span>↑ Отправка · ↓ Получение · OpenFlux показывает состояние службы</span></div></section><details class="note client-help"><summary>Что означают доступ, активность и HWID?</summary><p>Переключатель управляет разрешением доступа, а активность означает передачу данных за последние 90 секунд — не точное присутствие онлайн. Для OpenFlux показывается состояние отдельной службы профиля.</p><p>Лимит HWID ограничивает регистрацию идентификаторов клиента. HWID и ключ можно скопировать: это не аппаратная защита. Квоты гигабайтов и срок действия здесь не настроены. Основное подключение установки защищено от отключения и удаления.</p><p>Изменение доступа может кратковременно перезапустить службы. При массовом действии клиенты обрабатываются последовательно; OpenFlux управляется отдельно своим переключателем.</p></details>'''
    creation=f'''<dialog id="createAccount" class="create-dialog"><div class="dialog-head"><div><h2>Новый клиент</h2><small>Настройте доступ за два понятных шага</small></div><button type="button" data-close-dialog aria-label="Закрыть">×</button></div><form id="createClientForm" method="post" action="{esc(path)}/create-account">{hidden(csrf)}<input type="hidden" id="accountKind" name="kind" value="subscription"><label for="accountName">Имя клиента</label><input id="accountName" name="name" placeholder="Например, Александр или Телефон" maxlength="80" required autocomplete="off"><section class="create-step"><div class="create-step-title"><i>1</i><span>Как клиент будет получать доступ?</span></div><div class="create-mode-grid"><label class="choice-card"><input type="radio" name="access_mode" value="subscription" checked><span><strong>Одна подписка</strong><small>Одна ссылка для проверенных VLESS и Hysteria2.</small></span></label><label class="choice-card"><input type="radio" name="access_mode" value="direct"><span><strong>Отдельное подключение</strong><small>WEB Proxy, MTProto или один выбранный VPN-протокол.</small></span></label></div></section><section class="create-step" id="subscriptionFields"><div class="create-step-title"><i>2</i><span>Выберите протоколы подписки</span></div><div class="protocol-picker"><label class="choice-card"><input type="checkbox" name="vless" value="1" checked><span><strong>VLESS XHTTP</strong><small>TLS через домен · TCP 443</small><em>УНИВЕРСАЛЬНЫЙ</em></span></label><label class="choice-card"><input type="checkbox" name="hysteria" value="1" checked><span><strong>Hysteria2</strong><small>Быстрый QUIC · UDP 8443</small><em>ДЛЯ НЕСТАБИЛЬНЫХ СЕТЕЙ</em></span></label></div><div class="device-row"><p class="note">Лимит HWID относится к подписке. Значение 0 создаёт общую подписку без привязки.</p><div><label for="deviceLimit">Устройств</label><input id="deviceLimit" name="max_devices" type="number" min="0" max="20" value="2" inputmode="numeric"></div></div></section><section class="create-step" id="directFields" hidden><div class="create-step-title"><i>2</i><span>Выберите один протокол</span></div><div class="protocol-picker"><label class="choice-card"><input type="radio" name="direct_protocol" value="web" checked><span><strong>WEB Proxy</strong><small>Готовая ссылка для Telegram через HTTPS</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="mtproto"><span><strong>MTProto</strong><small>Прямое подключение Telegram · отдельный TCP-порт</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="vless"><span><strong>VLESS XHTTP</strong><small>TLS через домен · TCP 443</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="hysteria"><span><strong>Hysteria2</strong><small>QUIC · UDP 8443</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="awg20"><span><strong>AWG 2.0</strong><small>Совместимость с роутерами и прежними клиентами · уникальный UDP-порт</small><em>ОТДЕЛЬНЫЙ ОТПЕЧАТОК</em></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="awg31"><span><strong>AWG 3.1</strong><small>Защита заголовков и дополнительное заполнение · безопасный MTU</small><em>РЕКОМЕНДУЕТСЯ</em></span></label></div><p class="note">Каждый AWG-клиент получает собственные ключи, порт, подсеть и параметры маскировки. Если у провайдера VPS есть облачный firewall, разрешите показанный UDP-порт.</p></section><div class="create-summary"><span>Будет создано</span><b id="createSummary">Подписка · VLESS XHTTP + Hysteria2 · 2 устройства</b></div><div class="actions create-actions"><button type="button" data-close-dialog>Отмена</button><button class="primary" id="createClientSubmit">Создать клиента</button></div></form></dialog>'''
    creation=creation.replace('type="radio" name="hysteria"','type="radio" name="direct_protocol" value="hysteria"')
    creation=creation.replace('<label class="choice-card"><input type="checkbox" name="web" value="1"><span><strong>WEB Proxy</strong><small>Telegram через HTTPS · отдельный секрет устройству</small><em>С ЛИМИТОМ HWID</em></span></label>','')
    creation=creation.replace('Одна ссылка для VPN и WEB Proxy с общим лимитом устройств.','Одна ссылка для VLESS и Hysteria2 с общим лимитом устройств.')
    creation=creation.replace('Лимит работает по X-HWID и распространяется на все выбранные протоколы, включая WEB Proxy.','Лимит работает по X-HWID для VLESS и Hysteria2.')
    creation=creation.replace('Для ограничения WEB Proxy выберите «Одна подписка» и отметьте WEB Proxy. ','')
    creation=f'''<dialog id="createAccount" class="create-dialog"><div class="dialog-head"><div><h2>Новый доступ</h2><small>Выберите, что получит клиент</small></div><button type="button" data-close-dialog aria-label="Закрыть">×</button></div><form id="createClientForm" method="post" action="{esc(path)}/create-account">{hidden(csrf)}<input type="hidden" id="accountKind" name="kind" value="subscription"><div class="access-kind-grid"><label class="choice-card"><input type="radio" name="access_mode" value="subscription" checked><span><strong>Подписка</strong><small>Несколько протоколов в одной ссылке</small><span class="compatible-protocols"><i>VLESS</i><i>Hysteria2</i></span></span></label><label class="choice-card"><input type="radio" name="access_mode" value="direct"><span><strong>Отдельное подключение</strong><small>Один протокол или сервис для конкретного устройства</small><span class="compatible-protocols"><i>VPN</i><i>Telegram</i><i>OpenFlux</i></span></span></label></div><section class="create-step"><label for="accountName">Имя клиента или устройства</label><input id="accountName" name="name" placeholder="Например, Анна или Apple TV" maxlength="80" required autocomplete="off"></section><section class="create-step" id="subscriptionFields"><div class="create-step-title"><i>1</i><span>Протоколы подписки</span></div><div class="protocol-picker"><label class="choice-card"><input type="checkbox" name="vless" value="1" checked><span><strong>VLESS XHTTP</strong><small>Универсальное TLS-подключение</small></span></label><label class="choice-card"><input type="checkbox" name="hysteria" value="1" checked><span><strong>Hysteria2</strong><small>Быстрое подключение через QUIC</small></span></label></div><div class="device-row"><p class="note">Одна ссылка для выбранных протоколов и всех подключённых нод.</p><div><label for="deviceLimit">Устройств · 0 без лимита</label><input id="deviceLimit" name="max_devices" type="number" min="0" max="20" value="2" inputmode="numeric"></div></div></section><section class="create-step" id="directFields" hidden><div class="create-step-title"><i>1</i><span>Выберите одно подключение</span></div><div class="protocol-picker"><label class="choice-card"><input type="radio" name="direct_protocol" value="vless" checked><span><strong>VLESS XHTTP</strong><small>Универсальное TLS-подключение</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="hysteria"><span><strong>Hysteria2</strong><small>Быстрое подключение через QUIC</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="awg20"><span><strong>AWG 2.0</strong><small>Совместимость с прежними клиентами</small></span></label><label class="choice-card"><input type="radio" name="direct_protocol" value="awg31"><span><strong>AWG 3.1</strong><small>Новая маскировка и собственные параметры</small></span></label></div><div class="quick-access-title">Сервисы</div><div class="quick-access-grid"><button type="button" class="quick-access" data-quick-protocol="mtproto"><span class="quick-radio" aria-hidden="true"></span><span><b>MTProto</b><small>Прямое подключение для Telegram</small></span></button><button type="button" class="quick-access" data-quick-protocol="web"><span class="quick-radio" aria-hidden="true"></span><span><b>Web Proxy</b><small>Ссылка Telegram через HTTPS</small></span></button><button type="button" class="quick-access" data-open-openflux><span class="quick-radio" aria-hidden="true"></span><span><b>OpenFlux</b><small>Отдельный профиль для iOS или Android</small></span></button></div><p class="quick-access-note">Выберите VPN-протокол или один отдельный сервис.</p></section><section class="create-step quick-fields" id="quickFields" hidden><b id="quickTitle"></b><p id="quickDescription"></p></section><section class="create-step" id="expiryField"><div class="create-step-title"><i>2</i><span>Дата отключения — необязательно</span></div><div class="onyx-cal" id="accountExpiresCal"><input type="hidden" id="accountExpires" name="expires" value="" autocomplete="off"><button type="button" class="onyx-cal-field" aria-label="Выбрать дату отключения"><svg class="onyx-cal-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="17" rx="3"/><path d="M16 2v4M8 2v4M3 10h18"/></svg><span class="onyx-cal-value"></span><svg class="onyx-cal-caret" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div class="onyx-cal-pop" role="dialog" aria-label="Календарь"><div class="onyx-cal-head"><button type="button" class="onyx-cal-nav" data-cal-prev aria-label="Предыдущий месяц">‹</button><div class="onyx-cal-title"></div><button type="button" class="onyx-cal-nav" data-cal-next aria-label="Следующий месяц">›</button></div><div class="onyx-cal-week"><span>пн</span><span>вт</span><span>ср</span><span>чт</span><span>пт</span><span>сб</span><span>вс</span></div><div class="onyx-cal-grid"></div><div class="onyx-cal-foot"><button type="button" class="onyx-cal-clear" data-cal-clear>Без даты окончания</button></div></div></div><p class="note">Клиент работает до конца выбранного дня, затем доступ отключится автоматически. Кнопка «Без даты окончания» убирает ограничение по сроку.</p></section><div class="create-summary"><span>Будет создано</span><b id="createSummary">Подписка · VLESS XHTTP + Hysteria2 · 2 устройства</b></div><div class="actions create-actions"><button type="button" data-close-dialog>Отмена</button><button class="primary" id="createClientSubmit">Создать доступ</button></div></form></dialog>'''
    creation=creation.replace('<input type="hidden" id="accountKind"', '<div id="createError" class="create-error" role="alert" hidden></div><input type="hidden" id="accountKind"',1)
    confirmation='''<dialog id="accessConfirm"><div class="dialog-head"><h2>Изменить доступ?</h2></div><p data-access-message></p><form method="dialog"><div class="actions"><button value="cancel">Отмена</button><button class="primary" value="apply">Подтвердить</button></div></form></dialog>'''
    return '<div class="clients-layout"><div class="clients-content">'+content+'</div><div class="connection-slot">'+qr_dialog()+'</div></div>'+openflux_create_dialog(path,csrf)+''.join(dialogs)+creation+confirmation+CLIENTS_JS.replace('@@PATH@@',json.dumps(path)).replace('@@CSRF@@',json.dumps(csrf))


NODE_COUNTRIES = [
    ('UN','Не указано'), ('DE','Германия'), ('FI','Финляндия'),
    ('NL','Нидерланды'), ('FR','Франция'), ('GB','Великобритания'), ('US','США'),
    ('CA','Канада'), ('SE','Швеция'), ('NO','Норвегия'), ('PL','Польша'),
    ('CZ','Чехия'), ('AT','Австрия'), ('CH','Швейцария'), ('ES','Испания'),
    ('IT','Италия'), ('LT','Литва'), ('LV','Латвия'), ('EE','Эстония'),
    ('RO','Румыния'), ('BG','Болгария'), ('TR','Турция'), ('KZ','Казахстан'),
    ('RU','Россия'), ('UA','Украина'), ('JP','Япония'), ('SG','Сингапур'),
    ('HK','Гонконг'), ('AE','ОАЭ')
]


def node_flag(code):
    code=str(code or 'UN').upper()
    return ''.join(chr(127397+ord(c)) for c in code) if len(code)==2 and code!='UN' and code.isalpha() else '🌐'


def node_flag_image(code, path):
    code=str(code or 'UN').lower()
    if not re.fullmatch(r'[a-z]{2}',code): code='un'
    return f'<img src="{esc(path)}/__flag/{esc(code)}.svg" alt="{esc(node_flag(code))}" width="48" height="36">'


def node_country_select(local):
    current=str(local.get('country_code','UN')).upper()
    countries=list(NODE_COUNTRIES)
    if current not in {code for code,_ in countries}:
        countries.insert(1,(current,str(local.get('country_name') or current)))
    options=[]
    for code,name in countries:
        title=str(local.get('country_name')) if code==current and local.get('country_name') else name
        options.append(f'<option value="{esc(code)}" data-country-name="{esc(title)}" {"selected" if code==current else ""}>{node_flag(code)} {esc(title)}</option>')
    return ''.join(options)


def nodes_ui(nodes, local, connection_token, path, csrf):
    cards=[]
    for node in nodes:
        icon_flag=node_flag_image(node.get('country_code','UN'),path)
        cards.append(f'''<article class="card node-card">
<div class="node-card-head"><span class="node-flag">{icon_flag}</span><div class="node-card-name"><h2>{esc(node.get('name','Локация'))}</h2><span>{esc(node.get('country_name','Сервер'))}</span></div><span class="badge {'on' if node.get('enabled',True) else ''}">{'Подключена' if node.get('enabled',True) else 'Отключена'}</span></div>
<div class="node-endpoint">{icon('link')}<span>{esc(node.get('url',''))}</span></div>
<div class="node-card-meta"><div><span>Версия</span><strong>{esc(node.get('version','—'))}</strong></div><div><span>Подключения</span><strong>VLESS · Hysteria2</strong></div></div>
<form class="node-remove" method="post" action="{esc(path)}/node-action" data-confirm="Удалить ноду из этой панели?"><input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="operation" value="delete"><input type="hidden" name="id" value="{esc(node.get('id',''))}"><button class="danger">Удалить ноду</button></form></article>''')
    local_flag=node_flag_image(local.get('country_code','UN'),path)
    country_options=node_country_select(local)
    local_country=local.get('country_name','Сервер')
    local_city=local.get('name') or local_country
    empty=f'''<div class="nodes-empty"><span>{icon('nodes')}</span><h3>Здесь появятся ваши локации</h3><p>Установите Onyx Panel на другом VPS и вставьте его Node API token в форму выше.</p></div>'''
    return f'''<div class="page-head nodes-page-head"><div><span class="eyebrow">DISTRIBUTED ACCESS</span><h1>Ноды и локации</h1><p>Объединяйте несколько VPS в одну подписку и управляйте ими из этой панели</p></div><div class="nodes-count"><strong>{len(nodes)+1}</strong><span>локаций<br>в системе</span></div></div>
<div class="nodes-grid">
<section class="card local-node-card"><div class="local-node-head"><span class="local-node-flag">{local_flag}</span><div><span class="eyebrow">ТЕКУЩАЯ НОДА</span><h2>{esc(local_city)}</h2><small>{esc(local_country)}</small></div><span class="badge on">Активна</span></div>
<form class="node-location-form" method="post" action="{esc(path)}/node-action"><input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="operation" value="location"><input id="nodeCountryName" type="hidden" name="country_name" value="{esc(local.get('country_name','Сервер'))}"><div class="location-fields"><div class="country-flag-field"><label>Страна ноды</label><select id="nodeCountry" name="country_code" required>{country_options}</select></div><div><label>Город / название локации</label><input name="name" maxlength="80" value="{esc(local.get('name','Основная локация'))}" placeholder="Хельсинки" required></div></div><div class="location-actions"><small>Страна и город определяются по IP автоматически. Здесь их можно исправить вручную.</small><button class="primary">Сохранить</button></div></form><script>(()=>{{const select=document.getElementById('nodeCountry'),name=document.getElementById('nodeCountryName');if(select&&name)select.addEventListener('change',()=>{{name.value=select.selectedOptions[0].dataset.countryName||'Сервер'}})}})();</script>
<div class="node-token-box"><div class="node-token-title"><span>{icon('link')}</span><div><strong>Node API token</strong><small>Адрес и защищённый ключ подключения этой ноды</small></div></div><div class="node-token-copy"><input value="{esc(connection_token)}" readonly spellcheck="false" aria-label="Node API token"><button type="button" data-copy="{esc(connection_token)}">{icon('copy')}<span>Копировать</span></button></div><p>Храните токен как пароль. Он нужен только администратору другой Onyx-панели.</p><details><summary>Доступные методы API</summary><div class="api-methods"><code>GET · /status</code><code>GET · /profiles</code><code>POST · /profiles/create</code><code>POST · /profiles/delete</code></div></details></div></section>
<section class="card node-connect-card"><div class="connect-mark">{icon('nodes')}</div><span class="eyebrow">НОВАЯ ЛОКАЦИЯ</span><h2>Подключить удалённую ноду</h2><p>Добавьте ещё один VPS в общую подписку. Все параметры загрузятся автоматически.</p><ol class="node-connect-steps"><li><i>1</i><span>Скопируйте Node API token на другом сервере</span></li><li><i>2</i><span>Вставьте его в поле ниже</span></li><li><i>3</i><span>Панель проверит домен, страну и доступность API</span></li></ol><form method="post" action="{esc(path)}/node-action"><input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="operation" value="add"><label>Node API token</label><div class="node-connect-input"><input name="connection_token" autocomplete="off" spellcheck="false" placeholder="onyxnode1_…" required><button class="primary">Проверить и добавить</button></div><small class="secure-hint">Соединение проверяется через HTTPS. Токен не передаётся сторонним сервисам.</small></form></section></div>
<section class="nodes-section"><div class="nodes-section-head"><div><span class="eyebrow">NETWORK MAP</span><h2>Подключённые ноды</h2></div><span class="pill">{len(nodes)} / 16</span></div><div class="nodes-list">{''.join(cards) if cards else empty}</div></section>'''


CSS += '''
.nodes-page-head{padding-bottom:22px;border-bottom:1px solid var(--line)}.nodes-count{display:flex;align-items:center;gap:11px;padding:10px 14px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}.nodes-count strong{font:500 25px/1 ui-monospace,monospace;color:var(--accent)}.nodes-count span{font-size:10px;line-height:1.35;color:var(--muted)}.nodes-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(340px,.85fr);gap:18px;align-items:start}.local-node-card,.node-connect-card{margin:0}.local-node-card{padding:0;overflow:hidden}.local-node-head{display:flex;align-items:center;gap:14px;padding:22px 23px;border-bottom:1px solid var(--line);background:linear-gradient(135deg,var(--tint),transparent 60%)}.local-node-flag,.node-flag{display:grid;place-items:center;flex:0 0 auto;width:48px;height:48px;border:1px solid var(--line);border-radius:14px;background:var(--input);font-size:25px}.local-node-head>div{min-width:0}.local-node-head h2{font-size:19px}.local-node-head small{display:block;margin-top:4px}.local-node-head>.badge{margin-left:auto}.node-location-form{padding:20px 23px 22px}.location-fields{display:grid;grid-template-columns:90px 1fr 1fr;gap:11px}.location-fields label{margin-top:0}.location-fields input{text-overflow:ellipsis}.country-code-field input{text-align:center;text-transform:uppercase;font:600 14px ui-monospace,monospace}.location-actions{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:14px}.location-actions small{max-width:480px;font-size:10px}.location-actions button{min-width:110px}.node-token-box{margin:0 23px 23px;padding:18px;border:1px solid color-mix(in srgb,var(--accent) 36%,var(--line));border-radius:13px;background:linear-gradient(135deg,var(--tint),var(--input))}.node-token-title{display:flex;align-items:center;gap:11px;margin-bottom:13px}.node-token-title>span{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;background:var(--accent);color:var(--on-accent)}.node-token-title .ico{width:16px}.node-token-title strong{display:block;font-size:12px}.node-token-title small{display:block;font-size:9px;margin-top:2px}.node-token-copy{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px}.node-token-copy input{font:10px ui-monospace,monospace}.node-token-copy button{white-space:nowrap}.node-token-box>p{margin:10px 0 0;font-size:10px;color:var(--muted)}.node-token-box details{margin-top:10px}.node-token-box summary{width:max-content;cursor:pointer;font-size:10px;color:var(--accent)}.api-methods{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:10px}.api-methods code{padding:7px 9px;border:1px solid var(--line);border-radius:7px;background:var(--surface);font-size:9px;color:var(--muted)}.node-connect-card{position:relative;padding:28px;overflow:hidden;background:radial-gradient(circle at 100% 0,var(--tint),transparent 42%),var(--surface)}.connect-mark{display:grid;place-items:center;width:52px;height:52px;margin-bottom:24px;border:1px solid color-mix(in srgb,var(--accent) 38%,var(--line));border-radius:15px;background:var(--tint);color:var(--accent)}.connect-mark .ico{width:25px;height:25px}.node-connect-card h2{font-size:22px}.node-connect-card>p{max-width:460px;margin:8px 0 22px;color:var(--muted);font-size:12px}.node-connect-steps{display:grid;gap:10px;margin:0 0 24px;padding:0;list-style:none}.node-connect-steps li{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:11px}.node-connect-steps i{display:grid;place-items:center;flex:0 0 23px;height:23px;border:1px solid var(--line);border-radius:50%;color:var(--accent);font:600 10px ui-monospace,monospace}.node-connect-card form{padding-top:20px;border-top:1px solid var(--line)}.node-connect-card form label{margin-top:0;color:var(--text)}.node-connect-input{display:grid;gap:9px}.node-connect-input input{font:10px ui-monospace,monospace}.node-connect-input button{width:100%;padding:12px}.secure-hint{display:block;margin-top:10px;font-size:9px}.nodes-section{margin-top:27px}.nodes-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}.nodes-list{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.node-card{display:flex;flex-direction:column;margin:0;padding:19px}.node-card-head{display:flex;align-items:center;gap:11px}.node-flag{width:41px;height:41px;border-radius:11px;font-size:21px}.node-card-name{min-width:0}.node-card-name h2{font-size:15px}.node-card-name span{display:block;margin-top:2px;color:var(--muted);font-size:10px}.node-card-head>.badge{margin-left:auto}.node-endpoint{display:flex;align-items:center;gap:7px;margin:16px 0;padding:9px 10px;border-radius:8px;background:var(--input);color:var(--muted);font:9px ui-monospace,monospace}.node-endpoint .ico{width:13px}.node-endpoint span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.node-card-meta{display:grid;grid-template-columns:.7fr 1.3fr;gap:9px}.node-card-meta>div{padding:10px;border:1px solid var(--line);border-radius:8px}.node-card-meta span{display:block;font-size:8px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}.node-card-meta strong{display:block;margin-top:4px;font-size:10px}.node-remove{margin-top:auto;padding-top:14px}.node-remove button{width:100%;font-size:10px}.nodes-empty{grid-column:1/-1;display:grid;justify-items:center;padding:43px 20px;border:1px dashed var(--line);border-radius:14px;text-align:center;background:var(--surface)}.nodes-empty>span{display:grid;place-items:center;width:45px;height:45px;border-radius:13px;background:var(--tint);color:var(--accent)}.nodes-empty h3{margin-top:14px}.nodes-empty p{max-width:440px;margin:6px 0 0;color:var(--muted);font-size:11px}@media(max-width:1000px){.nodes-grid{grid-template-columns:1fr}.nodes-list{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.nodes-count{display:none}.local-node-head{align-items:flex-start;padding:19px}.local-node-head>.badge{margin-left:auto}.node-location-form{padding:18px 19px}.location-fields{grid-template-columns:76px 1fr}.location-fields>div:last-child{grid-column:1/-1}.location-actions{align-items:stretch;flex-direction:column}.location-actions button{width:100%}.node-token-box{margin:0 19px 19px;padding:15px}.node-token-copy{grid-template-columns:1fr}.node-token-copy button span{display:inline}.api-methods{grid-template-columns:1fr}.node-connect-card{padding:21px}.nodes-list{grid-template-columns:1fr}}'''


CSS += '''
.node-location-form .location-fields{grid-template-columns:1fr 1fr}.country-flag-field select{font-size:13px}.country-flag-field option{background:var(--surface);color:var(--text)}
.openflux-users{margin-top:26px;padding-top:24px;border-top:1px solid var(--line)}.openflux-users .section-head{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;margin-bottom:14px}.openflux-users .section-head h2{margin-top:4px}.openflux-users .section-head p{margin:5px 0 0;color:var(--muted);font-size:11px}.flux-profile-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px}.flux-profile{padding:18px;border:1px solid var(--line);border-radius:14px;background:radial-gradient(circle at 100% 0,var(--tint),transparent 42%),var(--surface)}.flux-profile-head{display:flex;align-items:center;gap:11px;margin-bottom:15px}.flux-profile-head>div{min-width:0}.flux-profile-head h3{font-size:14px}.flux-profile-head small{display:block;margin-top:3px}.flux-profile-head>.badge{margin-left:auto}.flux-platform{display:grid;place-items:center;width:43px;height:43px;border:1px solid color-mix(in srgb,var(--accent) 35%,var(--line));border-radius:12px;background:var(--tint);color:var(--accent);font-weight:700;font-size:10px}.flux-profile-secret{display:grid;grid-template-columns:62px minmax(0,1fr) 36px;align-items:center;gap:8px;margin-top:8px}.flux-profile-secret>span{font-size:9px;color:var(--muted);text-transform:uppercase}.flux-profile-secret input{min-width:0;padding:9px;font:9px ui-monospace,monospace}.flux-profile-secret button{height:36px;padding:8px}.flux-profile>.actions{margin-top:15px}.flux-empty{grid-column:1/-1;display:grid;gap:5px;padding:30px;border:1px dashed var(--line);border-radius:14px;text-align:center;color:var(--muted)}.flux-empty b{color:var(--text)}.flux-platform-picker{margin-top:8px}
.client-detail{position:fixed;inset:0 0 0 auto;width:min(455px,100vw);height:100dvh;max-height:100dvh;margin:0;border-radius:20px 0 0 20px;overflow:auto}.client-detail .dialog-head{position:sticky;z-index:3;top:-25px;padding:20px 0 15px;background:var(--surface);border-bottom:1px solid var(--line)}
.access-kind-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}.access-kind-grid .choice-card{min-height:104px}.access-kind-grid .choice-card strong{font-size:14px}.compatible-protocols{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}.compatible-protocols i{padding:4px 6px;border:1px solid var(--line);border-radius:6px;color:var(--muted);font:500 8px/1 ui-monospace,monospace;font-style:normal}.quick-access-title{display:flex;align-items:center;gap:11px;margin:20px 0 10px;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em}.quick-access-title:before,.quick-access-title:after{content:"";height:1px;flex:1;background:var(--line)}.quick-access-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.quick-access{display:flex;align-items:flex-start;justify-content:flex-start;gap:12px;min-width:0;min-height:76px;padding:15px;border:1px solid var(--line);border-radius:11px;background:var(--input);text-align:left;color:var(--text);cursor:pointer}.quick-access:hover,.quick-access.selected{border-color:var(--accent);background:var(--tint)}.quick-access.selected{box-shadow:inset 0 0 0 1px var(--accent)}.quick-access .quick-radio{display:block;width:16px;height:16px;flex:0 0 auto;margin-top:3px;border:1px solid var(--muted);border-radius:50%;background:transparent}.quick-access:hover .quick-radio{border-color:var(--accent)}.quick-access.selected .quick-radio{border-color:var(--accent);box-shadow:inset 0 0 0 4px var(--input);background:var(--accent)}.quick-access b{display:block;font-size:13px}.quick-access small{display:block;margin-top:4px;font-size:10px;line-height:1.45}.quick-access-note{margin:10px 0 0;color:var(--muted);font-size:9px}.quick-fields{padding:14px;border:1px solid var(--line);border-radius:10px;background:var(--raised)}.quick-fields b{display:block;font-size:12px}.quick-fields p{margin:5px 0 0;color:var(--muted);font-size:10px;line-height:1.5}
@media(max-width:650px){.node-location-form .location-fields{grid-template-columns:1fr}.node-location-form .location-fields>div:last-child{grid-column:auto}}
@media(max-width:760px){.openflux-users .section-head{align-items:stretch;flex-direction:column}.openflux-users .section-head button{width:100%}.flux-profile-grid{grid-template-columns:1fr}.flux-profile-secret{grid-template-columns:1fr 36px}.flux-profile-secret>span{grid-column:1/-1}.client-detail{width:100vw;border-radius:0}.access-kind-grid{grid-template-columns:1fr}.quick-access-grid{grid-template-columns:1fr}.quick-access{padding:12px}.mtproto-options{grid-template-columns:1fr}.mtproto-device{grid-template-columns:1fr 1fr}.mtproto-device>div{grid-column:1/-1}}
.mtproto-options{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:13px}.mtproto-options label{margin:0}.mtproto-options small{display:block;margin-top:5px;color:var(--muted);font-size:9px}.mtproto-access-head{display:grid;grid-template-columns:1fr auto;align-items:center;gap:4px 12px;margin:12px 0;padding:12px 14px;border:1px solid var(--line);border-radius:10px;background:var(--raised)}.mtproto-access-head span,.mtproto-access-head small{color:var(--muted);font-size:10px}.mtproto-access-head small{grid-column:1/-1}.mtproto-devices{display:grid;gap:8px;margin:12px 0}.mtproto-device{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px;padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:var(--input)}.mtproto-device b,.mtproto-device small{display:block}.mtproto-device small{margin-top:3px;color:var(--muted);font-size:9px}
@media(max-width:760px){.mtproto-options{grid-template-columns:1fr}.mtproto-device{grid-template-columns:1fr 1fr}.mtproto-device>div{grid-column:1/-1}}
'''

# Balanced access dialog and node cards. Dialog content fits on a normal
# desktop viewport without a nested scrollbar; small screens keep responsive
# single-column cards while scrollbars stay visually unobtrusive.
CSS += '''
dialog{scrollbar-width:thin;scrollbar-color:var(--line) transparent}
.create-dialog{width:min(980px,calc(100vw - 28px));max-height:min(860px,calc(100vh - 24px));max-height:min(860px,calc(100dvh - 24px));overflow:hidden}.create-dialog[open]{display:flex;flex-direction:column}
.create-dialog .dialog-head{flex:0 0 auto;padding:18px 22px 14px}
.create-dialog form{flex:1 1 auto;min-height:0;padding:16px 22px 22px;overflow:auto;overscroll-behavior:contain}
.create-dialog .create-actions{position:sticky;bottom:-22px;padding:12px 0 0;background:linear-gradient(transparent,var(--surface) 22%)}
.create-dialog .create-step{margin-top:14px}
.create-dialog .access-kind-grid .choice-card{min-height:88px}
.create-dialog #directFields .protocol-picker{grid-template-columns:repeat(4,minmax(0,1fr))}
.create-dialog .quick-access-title{margin:14px 0 9px}
.create-dialog .quick-access-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
.create-dialog .create-summary{margin-top:14px;padding:11px 14px}
.create-dialog .create-actions{position:static;margin-top:11px;padding:0;background:none}
.create-error{margin:0 0 14px;padding:11px 13px;border:1px solid color-mix(in srgb,var(--red) 45%,var(--line));border-left:3px solid var(--red);border-radius:10px;background:color-mix(in srgb,var(--red) 9%,var(--surface));color:var(--red);font-size:11px;line-height:1.5}.create-error[hidden]{display:none}.create-dialog.is-submitting{cursor:wait}.create-dialog.is-submitting button,.create-dialog.is-submitting input,.create-dialog.is-submitting select{pointer-events:none}.clients-table tr.client-pending{opacity:.55;pointer-events:none}.clients-table tr.client-pending .client-name:after{content:'Применяем…';display:block;margin-top:4px;color:var(--accent);font-size:9px}
.local-node-flag,.node-flag{font-family:"Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji",sans-serif;font-variant-emoji:emoji}
.local-node-flag img,.node-flag img{display:block;width:32px;height:24px;border-radius:4px;object-fit:cover;box-shadow:0 1px 5px #0004}.node-flag img{width:28px;height:21px}
.nodes-grid{align-items:stretch}.local-node-card,.node-connect-card{height:100%}
@media(max-width:900px){.create-dialog #directFields .protocol-picker{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:760px){.create-dialog{width:min(620px,calc(100vw - 18px))}.create-dialog .quick-access-grid{grid-template-columns:1fr}.create-dialog form{padding:15px 18px 17px}.create-dialog .create-actions{bottom:-17px}}
@media(max-width:1000px){.local-node-card,.node-connect-card{height:auto}}
'''

# Full mobile adaptation: dialogs must always scroll, inputs must not trigger
# iOS focus zoom, and touch targets stay comfortable on every device.
CSS += '''
@media(max-width:740px){
  input,select,textarea{font-size:16px}
  input[type=checkbox],input[type=radio]{width:17px;height:17px}
  .page-head{flex-wrap:wrap}
  .page-head .actions{width:100%;justify-content:space-between}
  .page-head .actions .primary{flex:1 1 auto}
  .page-head .actions button{padding:11px 14px}
  .card{padding:16px}
  .dialog-head button{min-width:40px;min-height:40px}
  .release-banner{max-width:calc(100vw - 16px)}
}
@media(max-width:740px){
  dialog{padding:max(18px,env(safe-area-inset-top)) max(18px,env(safe-area-inset-right)) max(18px,env(safe-area-inset-bottom)) max(18px,env(safe-area-inset-left))}
  .create-dialog form{padding:15px 18px 18px}
  .create-dialog .create-actions{bottom:-18px}
}
@media(max-height:560px) and (orientation:landscape){
  .create-dialog{max-height:calc(100dvh - 12px)}
  .create-dialog form{padding:12px 18px 14px}
}
'''

# Burger navigation: below 700px the top navigation becomes a dropdown panel
# anchored to the sticky appbar and toggled by a burger button.
CSS += '''
.burger{display:none}
body.nav-open:after{content:"";position:fixed;inset:0;z-index:38;background:#020d14aa;backdrop-filter:blur(3px)}
@media(max-width:700px){
  .appbar{position:sticky}
  .burger{display:grid;place-items:center;width:37px;height:37px;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--raised);color:var(--muted)}
  .burger:hover,.burger[aria-expanded=true]{color:var(--accent);border-color:var(--accent);background:var(--tint)}
  .burger .ico{width:19px;height:19px}
  .topnav{position:absolute;top:100%;left:0;right:0;z-index:5;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:2px;margin:0;padding:10px 12px 14px;background:var(--surface);border-bottom:1px solid var(--line);box-shadow:var(--shadow);transform:translateY(-8px);opacity:0;visibility:hidden;transition:transform .18s ease,opacity .18s ease,visibility .18s}
  .topnav.open{transform:translateY(0);opacity:1;visibility:visible}
  .topnav a{flex:none;justify-content:flex-start;gap:12px;padding:13px 14px;border-radius:9px;font-size:13px;font-weight:550}
  .topnav .ico{display:block;width:18px;height:18px}
}
@media(max-width:560px){
  .burger{width:34px;height:34px;padding:7px}
  .topnav{padding:8px 10px 12px}
  .topnav a{padding:12px}
}
'''

# ---- Onyx design system: bundled variable fonts + graphite-ice palette ----
_FONT_BASE = "/" + os.environ.get("ONYX_PANEL_PATH", "").strip("/")
FONT_FACES = """
@font-face{font-family:"Manrope";font-style:normal;font-weight:200 800;font-display:swap;src:url("__FONT_BASE__/__font/manrope-cyrillic-wght-normal.woff2") format("woff2");unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}
@font-face{font-family:"Manrope";font-style:normal;font-weight:200 800;font-display:swap;src:url("__FONT_BASE__/__font/manrope-latin-wght-normal.woff2") format("woff2");unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}
@font-face{font-family:"JetBrains Mono";font-style:normal;font-weight:100 800;font-display:swap;src:url("__FONT_BASE__/__font/jetbrains-mono-cyrillic-wght-normal.woff2") format("woff2");unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116}
@font-face{font-family:"JetBrains Mono";font-style:normal;font-weight:100 800;font-display:swap;src:url("__FONT_BASE__/__font/jetbrains-mono-latin-wght-normal.woff2") format("woff2");unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD}
""".replace("__FONT_BASE__", _FONT_BASE.rstrip("/"))
CSS += FONT_FACES

CSS += """
/* ============ ONYX DESIGN SYSTEM ============ */
:root{
  --font-ui:"Manrope",-apple-system,"Segoe UI",system-ui,sans-serif;
  --font-mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --bg:#0a0e14;--surface:#11161f;--raised:#171d28;--input:#0c1119;--line:#222b38;--line-soft:#1a2230;
  --text:#e7edf5;--muted:#8a97ab;
  --accent:#65a8dc;--accent-strong:#8cc0ea;--on-accent:#06121d;--tint:rgba(101,168,220,.11);
  --green:#58c392;--red:#e07f77;--amber:#d8b26a;--sidebar:#0d1219;
  --shadow:0 24px 60px -20px rgba(3,9,18,.65),0 2px 8px rgba(3,9,18,.4)
}
:root[data-theme=light]{
  --bg:#edf1f6;--surface:#fcfdfe;--raised:#f2f5f9;--input:#ffffff;--line:#d9e0e9;--line-soft:#e4e9f0;
  --text:#16212e;--muted:#5d6b7f;
  --accent:#2f6f9f;--accent-strong:#3a80b4;--on-accent:#ffffff;--tint:rgba(47,111,159,.09);
  --green:#2b7d55;--red:#bc4a44;--amber:#8f6a1d;--sidebar:#ffffff;
  --shadow:0 24px 50px -24px rgba(22,42,66,.28),0 2px 6px rgba(22,42,66,.08)
}
html{scroll-behavior:smooth}
body{font-family:var(--font-ui);font-weight:500;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
body:before{content:"";position:fixed;inset:0;z-index:1;pointer-events:none;opacity:.05;
  background-image:url('data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22180%22 height=%22180%22%3E%3Cfilter id=%22n%22%3E%3CfeTurbulence type=%22fractalNoise%22 baseFrequency=%220.9%22 numOctaves=%222%22 stitchTiles=%22stitch%22/%3E%3CfeColorMatrix type=%22saturate%22 values=%220%22/%3E%3C/filter%3E%3Crect width=%22100%25%22 height=%22100%25%22 filter=%22url(%23n)%22/%3E%3C/svg%3E');
  background-size:180px 180px}
:root[data-theme=light] body:before{filter:invert(1);opacity:.045}
::selection{background:color-mix(in srgb,var(--accent) 32%,transparent)}
*{scrollbar-width:thin;scrollbar-color:color-mix(in srgb,var(--text) 18%,transparent) transparent}
::-webkit-scrollbar{width:11px;height:11px}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--text) 16%,transparent);border-radius:99px;border:3px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:color-mix(in srgb,var(--text) 27%,transparent);border:3px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-track,::-webkit-scrollbar-corner{background:transparent}
:where(a,button,input,select,textarea,summary,[role=button]):focus-visible{outline:2px solid color-mix(in srgb,var(--accent) 72%,transparent);outline-offset:2px}
/* Typography */
h1,h2,h3{text-wrap:balance}
p{text-wrap:pretty}
h1{font-size:clamp(28px,3.4vw,38px);font-weight:760;letter-spacing:-.04em;line-height:1.07}
h2{font-weight:680;letter-spacing:-.022em}
h3{font-weight:650}
.overview-stat b,.client-stat b,.graph-speeds b,.resource-head b,.traffic-cell b,.update-release strong,.update-installed strong,.hwid-cell,.sub-url,.client-name small{font-family:var(--font-mono)}
.overview-stat b,.client-stat b{font-weight:640;letter-spacing:-.035em}
/* Buttons: motion, press, focus */
.btn,button{border-radius:11px;font-weight:620;transition:transform .16s ease,background-color .18s ease,border-color .18s ease,box-shadow .2s ease,color .18s ease,filter .18s ease}
@media(hover:hover){.btn:hover,button:hover{transform:translateY(-1px)}}
.btn:active,button:active{transform:translateY(0) scale(.975);transition-duration:.06s}
.btn.primary,button.primary{background:linear-gradient(180deg,color-mix(in srgb,var(--accent) 86%,#fff),var(--accent));border-color:color-mix(in srgb,var(--accent) 74%,#000);color:var(--on-accent);box-shadow:0 10px 24px -12px color-mix(in srgb,var(--accent) 68%,transparent),inset 0 1px 0 color-mix(in srgb,#fff 24%,transparent)}
.btn.primary:hover,button.primary:hover{background:var(--accent-strong);border-color:var(--accent-strong);filter:none;box-shadow:0 14px 30px -12px color-mix(in srgb,var(--accent) 74%,transparent),inset 0 1px 0 color-mix(in srgb,#fff 30%,transparent)}
button.danger:hover,.btn.danger:hover{background:color-mix(in srgb,var(--red) 12%,transparent);border-color:color-mix(in srgb,var(--red) 45%,transparent);color:var(--red)}
button:disabled,.btn:disabled{transform:none!important;box-shadow:none!important}
/* Inputs */
input,textarea,select{border-radius:11px;font-weight:520;transition:border-color .18s ease,box-shadow .18s ease,background-color .18s ease}
input:hover,textarea:hover,select:hover{border-color:color-mix(in srgb,var(--text) 22%,var(--line))}
input:focus,textarea:focus,select:focus{border-color:color-mix(in srgb,var(--accent) 55%,var(--line));box-shadow:0 0 0 3.5px color-mix(in srgb,var(--accent) 16%,transparent)}
input[type=checkbox],input[type=radio]{accent-color:var(--accent)}
/* Surfaces */
.card,.account{border-radius:18px;border-color:var(--line-soft);background:linear-gradient(180deg,color-mix(in srgb,var(--raised) 55%,var(--surface)),var(--surface) 46%);box-shadow:inset 0 1px 0 color-mix(in srgb,var(--text) 4%,transparent),0 16px 40px -28px rgba(2,8,16,.55)}
:root[data-theme=light] .card,:root[data-theme=light] .account{box-shadow:inset 0 1px 0 #fff,0 16px 40px -30px rgba(22,42,66,.35)}
.clients-panel,.clients-summary{border-radius:18px;border-color:var(--line-soft)}
/* App bar */
.appbar{background:color-mix(in srgb,var(--surface) 78%,transparent);border-bottom-color:color-mix(in srgb,var(--text) 8%,transparent);backdrop-filter:blur(20px) saturate(1.5);-webkit-backdrop-filter:blur(20px) saturate(1.5)}
.mini-brand{border-radius:12px;box-shadow:0 4px 14px -6px color-mix(in srgb,var(--accent) 55%,transparent)}
.topnav a{border-radius:9px;font-weight:620;transition:color .16s ease,background-color .16s ease}
/* Dialogs: glass */
dialog{border-radius:22px;background:color-mix(in srgb,var(--surface) 93%,transparent);backdrop-filter:blur(24px) saturate(1.4);-webkit-backdrop-filter:blur(24px) saturate(1.4);border:1px solid color-mix(in srgb,var(--text) 9%,var(--line));box-shadow:0 40px 90px -24px rgba(2,8,16,.7),inset 0 1px 0 color-mix(in srgb,var(--text) 6%,transparent)}
dialog::backdrop{background:color-mix(in srgb,var(--bg) 72%,transparent);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)}
/* Tables */
.clients-table th{background:transparent;color:var(--muted);font-size:9.5px;text-transform:uppercase;letter-spacing:.08em;font-weight:660}
.clients-table td{border-bottom-color:var(--line-soft)}
.clients-table tbody tr{transition:background-color .14s ease}
@media(hover:hover){.clients-table tbody tr:hover{background:color-mix(in srgb,var(--accent) 6%,transparent)}}
/* Badges and marks */
.badge{font-weight:620;letter-spacing:.01em}
.pill{border-radius:7px;font-weight:600;background:color-mix(in srgb,var(--raised) 72%,transparent)}
.choice-card{transition:transform .16s ease,border-color .18s ease,background-color .18s ease,box-shadow .18s ease}
@media(hover:hover){.choice-card:hover{transform:translateY(-1px)}}
/* Login */
.login-page{background:radial-gradient(1100px 700px at 8% -12%,color-mix(in srgb,var(--accent) 17%,transparent),transparent 62%),radial-gradient(900px 620px at 108% 112%,color-mix(in srgb,var(--accent) 11%,transparent),transparent 58%),var(--bg)}
.login-card{border-radius:24px;background:color-mix(in srgb,var(--surface) 86%,transparent);backdrop-filter:blur(18px) saturate(1.4);-webkit-backdrop-filter:blur(18px) saturate(1.4);border:1px solid color-mix(in srgb,var(--text) 10%,var(--line));box-shadow:var(--shadow)}
.signin-logo{width:68px;height:68px;border-radius:19px;box-shadow:0 16px 34px -12px color-mix(in srgb,var(--accent) 55%,transparent)}
.login-card h1{font-weight:780;letter-spacing:-.045em}
@supports ((-webkit-background-clip:text) or (background-clip:text)){.login-card h1{background:linear-gradient(180deg,var(--text) 30%,color-mix(in srgb,var(--accent) 78%,var(--text)));-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;color:transparent}}
.login-theme .quiet{background:color-mix(in srgb,var(--surface) 75%,transparent);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px)}
/* Burger panel glass */
@media(max-width:700px){.topnav{background:color-mix(in srgb,var(--surface) 94%,transparent);backdrop-filter:blur(20px) saturate(1.4);-webkit-backdrop-filter:blur(20px) saturate(1.4)}}
/* Settings: panel card (address, login, password) */
.settings-card .panel-setting{padding:20px 0;border-top:1px solid var(--line-soft)}
.settings-card .panel-setting:first-of-type{border-top:0;padding-top:4px}
.panel-setting{display:grid;gap:4px}
.panel-setting-info b{display:block;font-size:13.5px;font-weight:660}
.panel-setting-info small{display:block;margin-top:4px;color:var(--muted);font-size:11.5px;line-height:1.55;max-width:620px}
.panel-current{display:flex;align-items:center;gap:10px;margin:8px 0 2px;flex-wrap:wrap}
.panel-current span{font-size:11px;color:var(--muted)}
.panel-current code{font-family:var(--font-mono);font-size:12px;padding:7px 11px;border:1px solid var(--line-soft);border-radius:9px;background:var(--input);overflow-wrap:anywhere}
.panel-setting form{display:grid}
.panel-setting form .actions{margin-top:12px}
.panel-setting-status{min-height:18px;margin:8px 0 0;font-size:12px;color:var(--muted)}
.panel-setting-status.ok{color:var(--green)}
.panel-setting-status.err{color:var(--red)}
.panel-setting-status a{color:var(--accent)}
.panel-setting input[name=path],.panel-setting input[name=user]{font-family:var(--font-mono);font-size:13px}
@media(max-width:700px){.panel-setting form .actions .btn{width:100%}}
/* Client access expiry */
.expiry-pill{color:var(--amber)}
.expiry-pill.expired{color:var(--red)}
input[type=date]{color-scheme:dark}
/* Themed dropdowns (progressive enhancement over native selects) */
.selx{position:relative;min-width:0}
.selx-native{position:absolute;opacity:0;pointer-events:none;width:1px;height:1px;min-height:0;padding:0;border:0}
.selx-trigger{display:flex;align-items:center;gap:8px;width:100%;min-height:41px;padding:9px 32px 9px 12px;border:1px solid var(--line);border-radius:10px;background:var(--input);color:var(--text);font:inherit;text-align:left;cursor:pointer;transition:border-color .18s ease,box-shadow .18s ease,background-color .18s ease}
.selx-trigger:hover{border-color:color-mix(in srgb,var(--text) 22%,var(--line))}
.selx-trigger:focus-visible{outline:none;border-color:color-mix(in srgb,var(--accent) 55%,var(--line));box-shadow:0 0 0 3.5px color-mix(in srgb,var(--accent) 16%,transparent)}
.selx.open .selx-trigger{border-color:color-mix(in srgb,var(--accent) 55%,var(--line));box-shadow:0 0 0 3.5px color-mix(in srgb,var(--accent) 16%,transparent)}
.selx-label{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.selx-caret{position:absolute;right:11px;flex:0 0 auto;color:var(--muted);transition:transform .18s ease,color .18s ease}
.selx.open .selx-caret{transform:rotate(180deg);color:var(--accent)}
.selx-pop{position:absolute;z-index:70;top:calc(100% + 6px);left:0;right:0;max-height:286px;overflow:auto;padding:6px;border-radius:13px;background:color-mix(in srgb,var(--surface) 96%,transparent);backdrop-filter:blur(20px) saturate(1.4);-webkit-backdrop-filter:blur(20px) saturate(1.4);border:1px solid color-mix(in srgb,var(--text) 10%,var(--line));box-shadow:0 24px 60px -18px rgba(2,8,16,.65);opacity:0;visibility:hidden;transform:translateY(-6px);transition:transform .16s ease,opacity .16s ease,visibility .16s}
.selx.open .selx-pop{opacity:1;visibility:visible;transform:translateY(0)}
.selx.up .selx-pop{top:auto;bottom:calc(100% + 6px);transform:translateY(6px)}
.selx.up.open .selx-pop{transform:translateY(0)}
.selx-opt{display:flex;align-items:center;gap:8px;min-height:36px;padding:8px 10px;border-radius:8px;cursor:pointer;font-size:13px;color:var(--text);overflow-wrap:anywhere}
.selx-opt:hover,.selx-opt.act{background:var(--tint)}
.selx-opt.sel{color:var(--accent);font-weight:640}
.selx-opt.sel:after{content:"✓";margin-left:auto;font-weight:700}
.selx-opt.dis{opacity:.45;cursor:not-allowed}
.clients-toolbar .selx{flex:1 1 160px;max-width:180px}
.clients-toolbar .selx[data-for=clientSort]{max-width:140px}
.clients-toolbar .selx-trigger{font-size:12px;min-height:38px}
.version-row .selx{min-width:0}
.version-row .selx-trigger{min-height:36px;padding:7px 30px 7px 10px;font-size:12px}
.update-control .selx{width:100%}
.country-flag-field .selx-trigger{font-size:13px}
@media(max-width:700px){.clients-toolbar .selx{flex:1 1 calc(50% - 8px);max-width:none}.clients-toolbar .selx[data-for=clientSort]{max-width:none}.selx-trigger{font-size:15px}}
/* Themed expiry calendar: replaces the native date picker */
.onyx-cal{position:relative}
.onyx-cal-field{width:100%;display:flex;align-items:center;gap:9px;padding:11px 34px 11px 12px;border:1px solid var(--line);border-radius:10px;background:var(--input);color:var(--text);font-size:13px;text-align:left}
.onyx-cal-field:hover{border-color:color-mix(in srgb,var(--accent) 55%,var(--line))}
.onyx-cal-field:focus-visible,.onyx-cal.open .onyx-cal-field{outline:none;border-color:color-mix(in srgb,var(--accent) 55%,var(--line));box-shadow:0 0 0 3.5px color-mix(in srgb,var(--accent) 16%,transparent)}
.onyx-cal-ico{width:17px;height:17px;flex:0 0 auto;color:var(--muted)}
.onyx-cal:not(.filled) .onyx-cal-ico{color:var(--muted)}
.onyx-cal.filled .onyx-cal-ico{color:var(--accent)}
.onyx-cal-value{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.onyx-cal:not(.filled) .onyx-cal-value{color:var(--muted)}
.onyx-cal-caret{position:absolute;right:11px;top:50%;width:16px;height:16px;flex:0 0 auto;color:var(--muted);transform:translateY(-50%);transition:transform .18s ease,color .18s ease;pointer-events:none}
.onyx-cal.open .onyx-cal-caret{transform:translateY(-50%) rotate(180deg);color:var(--accent)}
.onyx-cal-pop{position:absolute;z-index:71;top:calc(100% + 6px);left:0;width:min(330px,100%);min-width:0;padding:12px;border-radius:13px;background:color-mix(in srgb,var(--surface) 96%,transparent);backdrop-filter:blur(20px) saturate(1.4);-webkit-backdrop-filter:blur(20px) saturate(1.4);border:1px solid color-mix(in srgb,var(--text) 10%,var(--line));box-shadow:0 24px 60px -18px rgba(2,8,16,.65);opacity:0;visibility:hidden;transform:translateY(-6px);transition:transform .16s ease,opacity .16s ease,visibility .16s}
.onyx-cal.open .onyx-cal-pop{opacity:1;visibility:visible;transform:translateY(0)}
.onyx-cal.up .onyx-cal-pop{top:auto;bottom:calc(100% + 6px);transform:translateY(6px)}
.onyx-cal.up.open .onyx-cal-pop{transform:translateY(0)}
.onyx-cal-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
.onyx-cal-title{font-size:13px;font-weight:650;letter-spacing:-.01em;text-transform:capitalize}
.onyx-cal-nav{width:30px;height:30px;padding:0;display:grid;place-items:center;border:1px solid var(--line);border-radius:8px;background:transparent;color:var(--muted);font-size:16px;line-height:1}
.onyx-cal-nav:hover{color:var(--accent);border-color:var(--accent);background:var(--tint)}
.onyx-cal-week{display:grid;grid-template-columns:repeat(7,1fr);gap:2px;margin-bottom:3px}
.onyx-cal-week span{text-align:center;font-size:9px;font-weight:550;letter-spacing:.05em;text-transform:uppercase;color:var(--muted);padding:4px 0}
.onyx-cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.onyx-cal-day{aspect-ratio:1;display:grid;place-items:center;min-width:0;padding:0;border:1px solid transparent;border-radius:8px;background:transparent;color:var(--text);font:500 12px/1 var(--font-mono);cursor:pointer}
.onyx-cal-day:hover{background:var(--tint);border-color:var(--accent)}
.onyx-cal-day.out{color:var(--muted);opacity:.55}
.onyx-cal-day.today{border-color:var(--line)}
.onyx-cal-day.sel{background:var(--accent);border-color:var(--accent);color:var(--on-accent);font-weight:700}
.onyx-cal-foot{margin-top:10px;padding-top:10px;border-top:1px solid var(--line-soft)}
.onyx-cal-clear{width:100%;display:flex;align-items:center;justify-content:center;gap:7px;padding:9px 10px;border:1px dashed var(--line);border-radius:9px;background:transparent;color:var(--muted);font-size:12px}
.onyx-cal-clear:hover{color:var(--text);border-color:var(--accent)}
/* Move modal: shown while the panel changes its address */
.move-overlay{position:fixed;inset:0;z-index:95;display:grid;place-items:center;padding:16px;background:color-mix(in srgb,var(--bg) 45%,transparent);backdrop-filter:blur(16px) saturate(1.2);-webkit-backdrop-filter:blur(16px) saturate(1.2);opacity:0;visibility:hidden;transition:opacity .25s ease,visibility .25s}
.move-overlay.show{opacity:1;visibility:visible}
.move-card{width:min(460px,100%);padding:30px 26px;text-align:center;border:1px solid color-mix(in srgb,var(--text) 10%,var(--line));border-radius:24px;background:color-mix(in srgb,var(--surface) 92%,transparent);box-shadow:var(--shadow);transform:scale(.92) translateY(12px);transition:transform .3s cubic-bezier(.2,.9,.3,1.25)}
.move-overlay.show .move-card{transform:none}
.move-ring{position:relative;width:104px;height:104px;margin:0 auto 16px}
.move-ring svg{width:100%;height:100%;transform:rotate(-90deg)}
.move-ring-bg{fill:none;stroke:var(--line);stroke-width:6}
.move-ring-fg{fill:none;stroke:var(--accent);stroke-width:6;stroke-linecap:round;stroke-dasharray:276.5;stroke-dashoffset:0;transition:stroke-dashoffset 1s linear;filter:drop-shadow(0 0 6px color-mix(in srgb,var(--accent) 55%,transparent))}
.move-ring b{position:absolute;inset:0;display:grid;place-items:center;font:700 30px/1 var(--font-mono);color:var(--accent)}
.move-card h3{font-size:19px;font-weight:720;letter-spacing:-.02em;margin:0 0 8px}
.move-card p{margin:0 0 14px;color:var(--muted);font-size:12.5px;line-height:1.6}
.move-card code{display:block;margin:0 0 16px;padding:9px 12px;border-radius:10px;border:1px solid var(--line-soft);background:var(--input);font-family:var(--font-mono);font-size:12px;overflow-wrap:anywhere}
.move-card .btn{width:100%}
/* Update modal states: spinning arc while installing, countdown before reload */
.move-ring.spin svg{animation:updspin 1.1s linear infinite}
@keyframes updspin{from{transform:rotate(-90deg)}to{transform:rotate(270deg)}}
.move-ring.spin .move-ring-fg{stroke-dasharray:64 212.5;stroke-dashoffset:0;transition:none}
.move-ring.time b{font-size:19px;letter-spacing:.04em}
.move-card.upd-done .move-ring b{color:var(--green)}
.move-card.upd-done .move-ring-fg{stroke:var(--green)}
.move-card.upd-err .move-ring b{color:var(--red)}
.move-card.upd-err .move-ring-fg{stroke:var(--red)}
.upd-actions{justify-content:center;margin-top:6px}
.upd-actions[hidden],.upd-actions button[hidden]{display:none}
/* "Update available" flag on the Updates page */
.update-flag{display:inline-flex;align-items:center;gap:8px;padding:9px 13px;border:1px solid color-mix(in srgb,var(--green) 50%,var(--line));border-radius:10px;background:color-mix(in srgb,var(--green) 11%,var(--surface));color:var(--green);font-size:12px;font-weight:600;white-space:nowrap}
.update-flag[hidden]{display:none}
.update-flag b{font:700 12px var(--font-mono)}
.update-flag-dot{width:7px;height:7px;border-radius:50%;background:var(--green);box-shadow:0 0 10px var(--green);animation:updflag 1.6s ease-in-out infinite;flex:0 0 auto}
@keyframes updflag{0%,100%{opacity:.4;transform:scale(.85)}50%{opacity:1;transform:scale(1.15)}}
/* Themed confirm dialog */
.onyx-confirm-actions{justify-content:flex-end;margin-top:14px}
.onyx-confirm-actions button.danger{background:var(--red);border-color:var(--red);color:#fff}
.onyx-confirm-actions button.danger:hover{filter:brightness(1.08)}
/* Settings page: two-column card layout */
.settings-grid{display:grid;grid-template-columns:minmax(0,1.02fr) minmax(0,.98fr);gap:18px;align-items:start;margin-bottom:18px}
.settings-grid>.card{margin:0}
.settings-col{display:grid;gap:18px;min-width:0}
.settings-col>.card{margin:0}
@media(max-width:1100px){.settings-grid{grid-template-columns:1fr}}
/* Combined admin access block */
.admin-access-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.admin-access-grid small{display:block;margin-top:5px;color:var(--muted);font-size:10px}
@media(max-width:640px){.admin-access-grid{grid-template-columns:1fr}}
/* Themed file picker */
.file-field{position:relative;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.file-field input[type=file]{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden;clip:rect(0 0 0 0)}
.file-btn{display:inline-flex;align-items:center;gap:7px;padding:9px 15px;border:1px dashed var(--line);border-radius:10px;background:var(--input);color:var(--text);font-size:12px;font-weight:550;cursor:pointer;touch-action:manipulation}
.file-btn:hover{border-color:var(--accent);color:var(--accent);background:var(--tint)}
.file-btn:focus-visible{outline:none;border-color:var(--accent);box-shadow:0 0 0 3.5px color-mix(in srgb,var(--accent) 16%,transparent)}
.file-btn .ico{width:15px;height:15px}
.file-name{color:var(--muted);font-size:12px;overflow-wrap:anywhere}
/* Component cards in two columns inside settings */
.settings-col .component-stack{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
@media(max-width:640px){.settings-col .component-stack{grid-template-columns:1fr}}
"""


CLIENTS_JS='''<script>
const clientPath=@@PATH@@,clientCsrf=@@CSRF@@,clientRows=document.getElementById('clientRows'),allRows=Array.from(clientRows.querySelectorAll('[data-client]')),search=document.getElementById('accountSearch'),filter=document.getElementById('clientFilter'),proto=document.getElementById('protocolFilter'),sort=document.getElementById('clientSort'),notice=document.getElementById('clientNotice');let changing=false;
document.querySelectorAll('[data-open-dialog]').forEach(button=>button.addEventListener('click',()=>document.getElementById(button.dataset.openDialog).showModal()));
function selected(){return allRows.filter(r=>!r.hidden&&r.querySelector('[data-select-client]').checked)}
function selection(){const n=selected().length,visible=allRows.filter(r=>!r.hidden&&!r.querySelector('[data-select-client]').disabled),header=document.getElementById('selectAllClients');document.getElementById('bulkBar').hidden=!n;document.getElementById('selectedCount').textContent='Выбрано: '+n;header.checked=visible.length>0&&visible.every(r=>r.querySelector('[data-select-client]').checked);header.indeterminate=n>0&&!header.checked}
function list(){const q=search.value.trim().toLocaleLowerCase('ru'),mode=filter.value,p=proto.value;let visible=0;allRows.forEach(r=>{const d=r.dataset,match=(d.name+' '+d.id+' '+(d.kind==='subscription'?'подписка':'отдельная ссылка')).toLocaleLowerCase('ru').includes(q)&&(p==='all'||d.protocols.split(' ').includes(p))&&(mode==='all'||d.kind===mode||mode==='active'&&d.active==='1'||mode==='enabled'&&d.enabled==='1'||mode==='disabled'&&d.enabled==='0');r.hidden=!match;if(!match)r.querySelector('[data-select-client]').checked=false;else visible++});const ordered=allRows.slice().sort((a,b)=>{const x=a.dataset,y=b.dataset;switch(sort.value){case'name':return x.name.localeCompare(y.name,'ru');case'traffic':return Number(y.traffic)-Number(x.traffic);case'active':return Number(y.active)-Number(x.active);case'newest':return Number(y.created)-Number(x.created);default:return allRows.indexOf(a)-allRows.indexOf(b)}});ordered.forEach(r=>clientRows.appendChild(r));document.getElementById('visibleCount').textContent='Показано '+visible+' из '+allRows.length;document.getElementById('noAccounts').hidden=visible>0;selection();document.dispatchEvent(new Event('onyx-filtered'))}
[search,filter,proto,sort].forEach(e=>e.addEventListener(e===search?'input':'change',list));document.getElementById('selectAllClients').addEventListener('change',e=>{allRows.forEach(r=>{const c=r.querySelector('[data-select-client]');if(!r.hidden&&!c.disabled)c.checked=e.target.checked});selection()});allRows.forEach(r=>r.querySelector('[data-select-client]').addEventListener('change',selection));document.getElementById('clearSelected').addEventListener('click',()=>{allRows.forEach(r=>r.querySelector('[data-select-client]').checked=false);selection()});
const createDialog=document.getElementById('createAccount'),createForm=document.getElementById('createClientForm'),kindField=document.getElementById('accountKind'),subFields=document.getElementById('subscriptionFields'),directFields=document.getElementById('directFields'),quickFields=document.getElementById('quickFields'),createSummary=document.getElementById('createSummary'),createError=document.getElementById('createError'),createSubmit=document.getElementById('createClientSubmit');let quickProtocol='';
quickFields.insertAdjacentHTML('beforeend','<div class="mtproto-options" id="mtprotoOptions" hidden><label>TCP-порт<input name="mtproto_port" id="mtprotoPort" type="number" min="1024" max="65535" value="2399" inputmode="numeric" required><small>Панель проверит и откроет порт автоматически</small></label><label>Устройств<input name="mtproto_devices" id="mtprotoDevices" type="number" min="1" max="20" value="1" inputmode="numeric" required><small>Отдельный ключ и QR для каждого устройства</small></label></div>');const mtprotoOptions=document.getElementById('mtprotoOptions'),mtprotoPort=document.getElementById('mtprotoPort'),mtprotoDevices=document.getElementById('mtprotoDevices');
const protocolNames={vless:'VLESS XHTTP',hysteria:'Hysteria2',mtproto:'MTProto',web:'WEB Proxy',awg20:'AWG 2.0',awg31:'AWG 3.1'};
function clearQuick(){quickProtocol='';createForm.querySelectorAll('[data-quick-protocol]').forEach(b=>b.classList.remove('selected'))}
function updateCreate(){const mode=createForm.querySelector('[name=access_mode]:checked').value,isSub=mode==='subscription',isQuick=Boolean(quickProtocol),isMtproto=quickProtocol==='mtproto';subFields.hidden=!isSub;directFields.hidden=isSub;quickFields.hidden=!isQuick;mtprotoOptions.hidden=!isMtproto;mtprotoPort.disabled=!isMtproto;mtprotoDevices.disabled=!isMtproto;if(isSub){kindField.value='subscription';const chosen=Array.from(subFields.querySelectorAll('input[type=checkbox]:checked')).map(x=>protocolNames[x.name]),limit=document.getElementById('deviceLimit').value;createSummary.textContent='Подписка · '+(chosen.join(' + ')||'выберите протокол')+' · '+(limit==='0'?'без лимита':limit+' устр.')}else if(isQuick){kindField.value=quickProtocol;document.getElementById('quickTitle').textContent=protocolNames[quickProtocol];document.getElementById('quickDescription').textContent=isMtproto?'Выберите порт и количество отдельных ключей Telegram.':'Будет создана отдельная HTTPS-ссылка для Telegram.';createSummary.textContent='Отдельное подключение · '+protocolNames[quickProtocol]+(isMtproto?' · порт '+mtprotoPort.value+' · '+mtprotoDevices.value+' устр.':'')}else{let direct=createForm.querySelector('[name=direct_protocol]:checked');if(!direct){direct=createForm.querySelector('[name=direct_protocol][value=vless]');direct.checked=true}kindField.value=direct.value;createSummary.textContent='Отдельное подключение · '+protocolNames[direct.value]}}
createForm.querySelectorAll('[name=access_mode]').forEach(x=>x.addEventListener('change',()=>{clearQuick();if(x.value==='direct'&&x.checked&&!createForm.querySelector('[name=direct_protocol]:checked'))createForm.querySelector('[name=direct_protocol][value=vless]').checked=true;updateCreate()}));createForm.querySelectorAll('[name=direct_protocol]').forEach(x=>x.addEventListener('change',()=>{clearQuick();updateCreate()}));createForm.querySelectorAll('#subscriptionFields input').forEach(x=>x.addEventListener('change',updateCreate));createForm.querySelectorAll('[data-quick-protocol]').forEach(button=>button.addEventListener('click',()=>{quickProtocol=button.dataset.quickProtocol;createForm.querySelector('[name=access_mode][value=direct]').checked=true;createForm.querySelectorAll('[name=direct_protocol]').forEach(input=>input.checked=false);createForm.querySelectorAll('[data-quick-protocol]').forEach(b=>b.classList.toggle('selected',b===button));updateCreate()}));const openFluxShortcut=createForm.querySelector('[data-open-openflux]');if(openFluxShortcut)openFluxShortcut.addEventListener('click',()=>{createDialog.close();document.getElementById('newOpenFlux').showModal()});document.getElementById('deviceLimit').addEventListener('input',updateCreate);createForm.addEventListener('submit',e=>{if(kindField.value==='subscription'&&!subFields.querySelector('input[type=checkbox]:checked')){e.preventDefault();createSummary.textContent='Выберите хотя бы один протокол';subFields.scrollIntoView({block:'center',behavior:'smooth'})}});document.getElementById('newAccount').addEventListener('click',()=>{createForm.reset();clearQuick();kindField.value='subscription';updateCreate();createDialog.showModal();setTimeout(()=>document.getElementById('accountName').focus(),30)});updateCreate();document.querySelectorAll('[data-open-client]').forEach(b=>b.addEventListener('click',()=>document.getElementById('client-'+b.dataset.openClient).showModal()));
mtprotoPort.addEventListener('input',updateCreate);mtprotoDevices.addEventListener('input',updateCreate);
function showCreateError(message){createError.textContent=message||'Не удалось создать подключение.';createError.hidden=false;createError.scrollIntoView({block:'nearest',behavior:'smooth'})}
createForm.addEventListener('input',()=>{createError.hidden=true});document.getElementById('newAccount').addEventListener('click',()=>{createError.hidden=true},{capture:true});
createForm.addEventListener('submit',async e=>{e.preventDefault();e.stopImmediatePropagation();if(kindField.value==='subscription'&&!subFields.querySelector('input[type=checkbox]:checked')){showCreateError('Выберите хотя бы один протокол.');return}createError.hidden=true;createDialog.classList.add('is-submitting');createSubmit.disabled=true;createSubmit.textContent='Создаём…';try{const response=await fetch(createForm.action,{method:'POST',headers:{'X-Onyx-Async':'1'},body:new URLSearchParams(new FormData(createForm))});if(response.redirected)throw new Error('Сессия завершена. Войдите заново.');let result;try{result=await response.json()}catch(error){throw new Error('Панель вернула некорректный ответ. Повторите попытку.')}if(!response.ok||!result.ok)throw new Error(result.message||'Не удалось создать подключение.');location.href=clientPath+'/users'}catch(error){showCreateError(error.message)}finally{createDialog.classList.remove('is-submitting');createSubmit.disabled=false;createSubmit.textContent='Создать доступ'}},true);
async function requestClient(fields){const r=await fetch(clientPath+'/client-action',{method:'POST',body:new URLSearchParams({csrf:clientCsrf,...fields})});if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');let d;try{d=await r.json()}catch(e){throw new Error('Нет корректного ответа. Обновите список перед повторной попыткой.')}if(!r.ok||!d.ok)throw new Error(d.message||'Изменение не применено');if(window.onyxToast)onyxToast(d.message||'Сохранено');return d}
function updateClientStats(){const values=[allRows.length,allRows.filter(r=>r.dataset.active==='1').length,allRows.filter(r=>r.dataset.kind==='subscription').length,bytes(allRows.reduce((sum,r)=>sum+Number(r.dataset.traffic||0),0))];document.querySelectorAll('.client-stat b').forEach((b,i)=>b.textContent=values[i])}
function paintAccess(row,enabled,active=false){row.dataset.enabled=enabled?'1':'0';row.dataset.active=active?'1':'0';const toggle=row.querySelector('[role=switch]');if(toggle)toggle.setAttribute('aria-checked',enabled?'true':'false');row.querySelectorAll('.badge').forEach(badge=>{badge.classList.toggle('on',enabled&&active);badge.textContent=!enabled?'Отключена':row.dataset.kind==='openflux'?(active?'Работает':'Остановлен'):(active?'Передаёт трафик':'Нет трафика')});updateClientStats();list()}
function removeClientRow(row){const index=allRows.indexOf(row);if(index>=0)allRows.splice(index,1);const detail=document.getElementById('client-'+row.dataset.id);if(detail?.open)detail.close();detail?.remove();row.remove();updateClientStats();list()}
async function requestForm(form){const response=await fetch(form.action,{method:'POST',headers:{'X-Onyx-Async':'1'},body:new URLSearchParams(new FormData(form))});if(response.redirected)throw new Error('Сессия завершена. Войдите заново.');let result;try{result=await response.json()}catch(error){throw new Error('Панель вернула некорректный ответ.')}if(!response.ok||!result.ok)throw new Error(result.message||'Операция не выполнена.');if(window.onyxToast)onyxToast(result.message||'Готово');return result}
function lockClients(value){changing=value}
function confirmClientAccess(message){const d=document.getElementById('accessConfirm');if(d.open)return Promise.resolve(false);d.querySelector('[data-access-message]').textContent=message;d.returnValue='';return new Promise(resolve=>{d.addEventListener('close',()=>resolve(d.returnValue==='apply'),{once:true});d.showModal()})}
async function setAccess(rows,value,ask=false){if(changing||!rows.length)return;if(ask&&!await confirmClientAccess((value?'Включить':'Отключить')+' доступ для '+rows.length+' клиент(а/ов)? Соединения могут кратковременно прерваться.'))return;const previous=rows.map(r=>({enabled:r.dataset.enabled,active:r.dataset.active}));rows.forEach(r=>{paintAccess(r,Boolean(value),false);r.classList.add('client-pending')});lockClients(true);notice.hidden=false;let done=0;try{for(const r of rows){notice.textContent='Применение: '+(done+1)+' / '+rows.length;await requestClient({id:r.dataset.id,kind:r.dataset.kind,operation:'state',enabled:String(value)});done++}notice.textContent='Готово. Доступ изменён без перезагрузки страницы.';allRows.forEach(r=>{const c=r.querySelector('[data-select-client]');if(c)c.checked=false});selection()}catch(e){for(let i=done;i<rows.length;i++)paintAccess(rows[i],previous[i].enabled==='1',previous[i].active==='1');notice.textContent='Применено '+done+' из '+rows.length+'. '+e.message}finally{rows.forEach(r=>r.classList.remove('client-pending'));lockClients(false)}}
document.querySelectorAll('[data-state]').forEach(b=>b.addEventListener('click',()=>setAccess([b.closest('[data-client]')],b.getAttribute('aria-checked')==='true'?0:1)));document.querySelectorAll('[data-bulk]').forEach(b=>b.addEventListener('click',()=>setAccess(selected(),Number(b.dataset.bulk),true)));document.getElementById('reloadClients').addEventListener('click',()=>{if(!changing)location.reload()});
document.querySelectorAll('[data-secret-reveal]').forEach(b=>b.addEventListener('click',()=>{const field=document.getElementById(b.dataset.secretReveal),show=field.type==='password';field.type=show?'text':'password';b.textContent=show?'Скрыть':'Показать'}));
document.querySelectorAll('form[data-client-action]').forEach(f=>f.addEventListener('submit',async e=>{e.preventDefault();if(changing||(f.dataset.clientConfirm&&!(await onyxConfirm(f.dataset.clientConfirm,{danger:true}))))return;const p=f.querySelector('[data-form-status]'),b=f.querySelector('button[type="submit"],button:not([type])'),fields=Object.fromEntries(new FormData(f));b.disabled=true;changing=true;try{await requestClient(fields);const row=allRows.find(r=>r.dataset.id===fields.id);if(fields.operation==='rename'&&row){row.dataset.name=fields.name.trim();row.querySelector('.client-name strong').textContent=fields.name.trim();list()}if(fields.operation==='expiry'&&row){const pill=row.querySelector('.expiry-pill');if(pill){if(fields.expires){pill.hidden=false;pill.textContent='до '+fields.expires.split('-').reverse().join('.');pill.classList.toggle('expired',new Date(fields.expires+'T23:59:59').getTime()<Date.now())}else{pill.hidden=true}}}p.textContent=fields.operation==='secret'?'Секрет сохранён.':'Изменение сохранено.'}catch(err){p.textContent=err.message}finally{b.disabled=false;changing=false}}));
document.addEventListener('submit',async e=>{const form=e.target.closest('form');if(!form||form===createForm||form.matches('[data-client-action]'))return;const action=new URL(form.action,location.href).pathname;if(!['/delete-user','/subscription-action','/openflux-profile'].some(s=>action.endsWith(s)))return;e.preventDefault();e.stopImmediatePropagation();if(form.dataset.confirm&&!(await onyxConfirm(form.dataset.confirm,{danger:true})))return;const fields=Object.fromEntries(new FormData(form)),operation=String(fields.operation||''),rawId=String(fields.id||''),row=form.closest('[data-client]')||allRows.find(r=>r.dataset.id===(action.endsWith('/openflux-profile')?'openflux-'+rawId:rawId)),button=form.querySelector('button[type="submit"],button:not([type])');if(button)button.disabled=true;if(row)row.classList.add('client-pending');notice.hidden=false;notice.textContent=operation==='delete'||action.endsWith('/delete-user')?'Удаляем клиента…':'Применяем изменение…';try{await requestForm(form);const deleting=operation==='delete'||action.endsWith('/delete-user');if(deleting&&row){removeClientRow(row);notice.textContent='Клиент удалён.'}else if(row&&action.endsWith('/openflux-profile')&&(operation==='enable'||operation==='disable')){const enabled=operation==='enable';row.classList.remove('client-pending');paintAccess(row,enabled,enabled);const input=form.querySelector('[name=operation]');if(input)input.value=enabled?'disable':'enable';if(button)button.disabled=false;notice.textContent='Состояние OpenFlux изменено.'}else{notice.textContent='Готово. Обновляем список…';location.reload();return}}catch(error){if(row)row.classList.remove('client-pending');if(button)button.disabled=false;notice.textContent=error.message}},true);
document.getElementById('copySelected').addEventListener('click',async()=>{const links=selected().map(r=>r.dataset.link).join('\\n');try{await navigator.clipboard.writeText(links);notice.textContent='Ссылки выбранных клиентов скопированы.'}catch(e){notice.textContent='Браузер не разрешил копирование. Используйте кнопки в строках.'}notice.hidden=false});list();if(location.hash.startsWith('#account-')){const a=document.getElementById(location.hash.slice(1));if(a&&a.closest('dialog'))a.closest('dialog').showModal()}
function bytes(value){let n=Math.max(0,Number(value)||0);for(const u of ['Б','КБ','МБ','ГБ','ТБ']){if(n<1024||u==='ТБ')return (u==='Б'?n.toFixed(0):n.toFixed(1))+' '+u;n/=1024}}
let polling=false;async function pollClients(){if(polling||changing||selected().length||document.querySelector('dialog:modal'))return;polling=true;try{const response=await fetch(clientPath+'/clients-state',{cache:'no-store'});if(response.redirected)throw new Error('Сессия завершена. Войдите заново.');if(!response.ok)throw new Error('Статистика не обновляется. Проверьте связь с панелью.');const data=await response.json();if(changing||selected().length||document.querySelector('dialog:modal'))return;const records=data.clients;if(records.length!==allRows.length||records.some(c=>!allRows.some(r=>r.dataset.id===c.id&&r.dataset.name===c.name&&r.dataset.protocols===c.protocols.join(' ')))){notice.hidden=false;notice.textContent='Данные клиентов изменились. Нажмите «Обновить список».';return}for(const c of records){const row=allRows.find(r=>r.dataset.id===c.id),total=c.up+c.down,flux=c.kind==='openflux';if(c.kind==='subscription'){const cell=row.querySelector('.hwid-cell');cell.firstChild.textContent=c.limit?c.devices+' / '+c.limit:'Без лимита';cell.querySelector('small').textContent=c.limit?'HWID':'Без привязки'}row.dataset.enabled=c.enabled?'1':'0';row.dataset.active=c.active?'1':'0';row.dataset.traffic=String(total);const access=row.querySelector('[role=switch]');if(access)access.setAttribute('aria-checked',c.enabled?'true':'false');row.querySelectorAll('.badge').forEach(badge=>{badge.classList.toggle('on',c.active&&c.enabled);badge.textContent=!c.enabled?'Отключена':flux?(c.active?'Работает':'Остановлен'):(c.active?'Передаёт трафик':'Нет трафика')});if(!flux){row.querySelector('.traffic-cell b').textContent=bytes(total);row.querySelector('.traffic-cell small').textContent='↑ '+bytes(c.up)+' · ↓ '+bytes(c.down);row.querySelector('.traffic-split .up').style.width=(total?c.up/total*100:0)+'%';row.querySelector('.traffic-split .down').style.width=(total?c.down/total*100:0)+'%'}}const counts=[records.length,records.filter(c=>c.active).length,records.filter(c=>c.kind==='subscription').length,bytes(records.reduce((n,c)=>n+c.up+c.down,0))];document.querySelectorAll('.client-stat b').forEach((b,i)=>b.textContent=counts[i]);list()}catch(err){notice.hidden=false;notice.textContent=err.message}finally{polling=false}}
setInterval(pollClients,30000);
(function(){
const MONTHS=["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"];
function fmtISO(y,m,d){return y+"-"+String(m+1).padStart(2,"0")+"-"+String(d).padStart(2,"0")}
function fmtRU(v){const p=v.split("-");return p[2]+"."+p[1]+"."+p[0]}
document.addEventListener("click",e=>{document.querySelectorAll(".onyx-cal.open").forEach(w=>{if(!w.contains(e.target))w.classList.remove("open")})},true);
document.querySelectorAll(".onyx-cal").forEach(wrap=>{
  if(wrap.dataset.calReady)return;wrap.dataset.calReady="1";
  const input=wrap.querySelector("input[type=hidden]"),field=wrap.querySelector(".onyx-cal-field"),valEl=wrap.querySelector(".onyx-cal-value"),grid=wrap.querySelector(".onyx-cal-grid"),title=wrap.querySelector(".onyx-cal-title");
  const today=new Date();let view=null;
  function label(){const v=input.value;valEl.textContent=v?fmtRU(v):"Без даты окончания";wrap.classList.toggle("filled",Boolean(v))}
  function render(){
    const y=view.getFullYear(),m=view.getMonth();
    title.textContent=MONTHS[m]+" "+y;grid.innerHTML="";
    const lead=(new Date(y,m,1).getDay()+6)%7,start=new Date(y,m,1-lead);
    for(let i=0;i<42;i++){
      const d=new Date(start.getFullYear(),start.getMonth(),start.getDate()+i);
      const b=document.createElement("button");b.type="button";b.className="onyx-cal-day";b.textContent=d.getDate();
      const iso=fmtISO(d.getFullYear(),d.getMonth(),d.getDate());
      if(d.getMonth()!==m)b.classList.add("out");
      if(iso===input.value)b.classList.add("sel");
      if(d.getFullYear()===today.getFullYear()&&d.getMonth()===today.getMonth()&&d.getDate()===today.getDate())b.classList.add("today");
      b.addEventListener("click",()=>{input.value=iso;label();wrap.classList.remove("open")});
      grid.append(b);
    }
  }
  function open(){
    document.querySelectorAll(".onyx-cal.open").forEach(x=>{if(x!==wrap)x.classList.remove("open")});
    if(input.value){const p=input.value.split("-");view=new Date(Number(p[0]),Number(p[1])-1,1)}else{view=new Date(today.getFullYear(),today.getMonth(),1)}
    render();
    wrap.classList.add("open");
    const r=field.getBoundingClientRect();
    if(r.bottom+390>window.innerHeight&&r.top>410)wrap.classList.add("up");else wrap.classList.remove("up");
  }
  field.addEventListener("click",()=>{wrap.classList.contains("open")?wrap.classList.remove("open"):open()});
  wrap.addEventListener("keydown",e=>{if(e.key==="Escape"&&wrap.classList.contains("open")){e.preventDefault();wrap.classList.remove("open");field.focus({preventScroll:true})}});
  wrap.querySelectorAll("[data-cal-prev]").forEach(b=>b.addEventListener("click",()=>{view.setMonth(view.getMonth()-1);render()}));
  wrap.querySelectorAll("[data-cal-next]").forEach(b=>b.addEventListener("click",()=>{view.setMonth(view.getMonth()+1);render()}));
  wrap.querySelectorAll("[data-cal-clear]").forEach(b=>b.addEventListener("click",()=>{input.value="";label();wrap.classList.remove("open")}));
  label();
});
})();
</script>'''


# Preset cards: live thumbnails. The stub HTML is injected into a fully
# sandboxed iframe (no scripts, no forms, no same-origin) scaled to the card
# width, so the card shows the page as visitors see it. Hover (desktop) or a
# first tap (touch) fades in the blurred veil with the description and
# actions; the full preview dialog keeps using the sanitized server render.
PRESET_THUMBS_JS='''<script>
(()=>{const presets=@@PRESETS@@,cards=[...document.querySelectorAll('.preset[data-preset-card]')];
const fit=card=>{const f=card.querySelector('.preset-frame');if(f)card.style.setProperty('--s',(card.clientWidth/1280).toFixed(4))};
const load=card=>{const p=presets[card.dataset.presetId],f=card.querySelector('.preset-frame');
  if(!p||!p.html||!f||f.dataset.loaded)return;f.dataset.loaded='1';f.srcdoc=p.html;card.classList.add('has-frame');fit(card)};
cards.forEach(fit);addEventListener('resize',()=>cards.forEach(fit));
if('IntersectionObserver'in window){const io=new IntersectionObserver(es=>{es.forEach(en=>{if(en.isIntersecting){io.unobserve(en.target);load(en.target)}})},{rootMargin:'240px'});cards.forEach(c=>io.observe(c))}
else cards.forEach(load);
if(window.matchMedia&&!matchMedia('(hover: hover) and (pointer: fine)').matches){
  document.addEventListener('click',e=>{
    const card=e.target.closest('.preset[data-preset-card]');
    document.querySelectorAll('.preset[data-preset-card].revealed').forEach(c=>{if(c!==card)c.classList.remove('revealed')});
    if(!card)return;
    if(e.target.closest('.preset-veil')&&e.target.closest('button,form,a,input,label'))return;
    card.classList.toggle('revealed');
  });
}
})();
</script>'''


def editor_ui(source, path, csrf, presets, has_draft):
    art={'countdown':'◷','cars':'🏎','cats-repair':'🐱','loading':'↻'}
    card_items=[]
    for preset in presets:
        editable=bool(preset.get('custom') or str(preset.get('id','')).startswith('custom-'))
        edit=''
        if editable:
            edit=f'''<button type="button" class="preset-edit-btn" data-edit-preset="{esc(preset['id'])}">Редактировать</button><form class="preset-delete" method="post" action="{esc(path)}/custom-preset" data-confirm="Удалить свою заглушку «{esc(preset['name'])}»?"><input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="operation" value="delete"><input type="hidden" name="preset" value="{esc(preset['id'])}"><button class="danger">Удалить</button></form>'''
        card_items.append(f'''<div class="preset" data-preset-card data-preset-id="{esc(preset['id'])}"><div class="preset-thumb"><div class="preset-art">{art.get(preset["id"],"✦")}</div><iframe class="preset-frame" aria-hidden="true" tabindex="-1" sandbox="" referrerpolicy="no-referrer" title=" "></iframe></div><div class="preset-veil"><b>{esc(preset["name"])}</b><p>{esc(preset["description"])}</p><div class="actions"><button type="button" data-preview-preset="{esc(preset['id'])}">Предпросмотр</button><form method="post" action="{esc(path)}/apply-preset" data-confirm="Заменить рабочую заглушку пресетом «{esc(preset['name'])}»?">{hidden(csrf,preset=preset["id"])}<button class="primary">Применить</button></form>{edit}</div></div></div>''')
    cards=''.join(card_items)
    preset_data={p['id']:{'name':p['name'],'description':p.get('description',''),'html':p.get('html',''),'custom':bool(p.get('custom') or str(p.get('id','')).startswith('custom-'))} for p in presets}
    import json as _json
    presets_json=_json.dumps(preset_data,ensure_ascii=False).replace('</',r'<\/')
    return f'''<div class="card editor-presets-card"><div class="card-title"><div><h2>Заглушка главной страницы</h2><p>Выберите готовую страницу, создайте свою или отредактируйте существующую</p></div><div class="actions"><button type="button" class="primary" id="openCustomPreset">{icon("plus")}Создать заглушку</button>{'<span class="pill">Черновик не опубликован</span>' if has_draft else ''}</div></div><div class="preset-grid">{cards}</div><p class="muted" style="font-size:12px;margin-bottom:0">«Применить» сразу публикует заглушку на сайте. Кнопка <b>Редактировать</b> открывает редактирование своей заглушки, <b>Предпросмотр</b> — предпросмотр без публикации.</p></div>
<dialog id="customPresetDialog" class="create-dialog preset-create-dialog"><div class="dialog-head"><div><h2 id="customPresetTitle">Своя заглушка</h2><small>После сохранения она появится среди остальных заглушек</small></div><button type="button" data-close-dialog aria-label="Закрыть">×</button></div><form id="customPresetForm" method="post" action="{esc(path)}/custom-preset"><input type="hidden" name="csrf" value="{esc(csrf)}"><input type="hidden" name="operation" value="create" id="customPresetOp"><input type="hidden" name="preset" value="" id="customPresetId"><div class="form-grid"><div><label for="customPresetName">Название</label><input id="customPresetName" name="name" maxlength="80" required placeholder="Например, Скоро открытие"></div><div><label for="customPresetDescription">Краткое описание</label><input id="customPresetDescription" name="description" maxlength="180" placeholder="Что увидит посетитель"></div></div><label for="customPresetHtml">HTML заглушки</label><div class="editor-bar"><span>index.html</span><i>до 1 МБ</i></div><textarea class="code-editor" id="customPresetHtml" name="html" spellcheck="false" required placeholder="<!doctype html>…"></textarea><div class="actions create-actions"><button type="button" data-close-dialog>Отмена</button><button class="primary" id="customPresetSave">Сохранить</button></div></form></dialog>
<dialog id="previewDialog" class="preview-dialog"><div class="preview-top"><strong>Предпросмотр заглушки</strong><div class="actions"><div class="range"><button type="button" class="selected" id="previewDesktop">Компьютер</button><button type="button" id="previewPhone">Телефон</button></div><button type="button" data-close-dialog aria-label="Закрыть предпросмотр">×</button></div></div><div id="previewStage" class="preview-stage"><iframe id="landingPreview" title="Изолированный предпросмотр заглушки" sandbox="allow-scripts" referrerpolicy="no-referrer"></iframe></div><p class="preview-caption">Изолированный предпросмотр · рабочий сайт не изменён</p></dialog>
<script>(()=>{{const presets={presets_json};const cp=document.getElementById('customPresetDialog'),cpf=document.getElementById('customPresetForm'),cpOp=document.getElementById('customPresetOp'),cpId=document.getElementById('customPresetId'),cpName=document.getElementById('customPresetName'),cpDesc=document.getElementById('customPresetDescription'),cpHtml=document.getElementById('customPresetHtml'),cpTitle=document.getElementById('customPresetTitle'),cpSave=document.getElementById('customPresetSave');document.getElementById('openCustomPreset').addEventListener('click',()=>{{cpOp.value='create';cpId.value='';cpTitle.textContent='Своя заглушка';cpSave.textContent='Создать заглушку';cpName.value='';cpDesc.value='';cpHtml.value='';cp.showModal();setTimeout(()=>cpName.focus(),30)}});document.querySelectorAll('[data-edit-preset]').forEach(b=>b.addEventListener('click',()=>{{const p=presets[b.dataset.editPreset];if(!p)return;cpOp.value='save';cpId.value=b.dataset.editPreset;cpTitle.textContent='Редактирование заглушки';cpSave.textContent='Сохранить изменения';cpName.value=p.name;cpDesc.value=p.description;cpHtml.value=p.html;cp.showModal();setTimeout(()=>cpName.focus(),30)}}));cpf.addEventListener('submit',e=>{{if(!cpName.value.trim()||!cpHtml.value.trim()){{e.preventDefault();return}}cpSave.disabled=true;cpSave.textContent='Сохраняем…'}});const pd=document.getElementById('previewDialog'),pf=document.getElementById('landingPreview');document.querySelectorAll('[data-preview-preset]').forEach(b=>b.addEventListener('click',async()=>{{const p=presets[b.dataset.previewPreset];if(!p||!p.html)return;b.disabled=true;try{{const r=await fetch('{esc(path)}/preview-html',{{method:'POST',body:new URLSearchParams({{csrf:'{esc(csrf)}',html:p.html}})}});if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');if(!r.ok){{let msg='Ошибка предпросмотра ('+r.status+').';try{{msg=(await r.json()).message||msg}}catch(_){{}}throw new Error(msg)}}let d;try{{d=await r.json()}}catch(e){{throw new Error('Панель вернула некорректный ответ.')}}if(!d.document)throw new Error('Ошибка предпросмотра.');pf.srcdoc=d.document;pd.showModal()}}catch(err){{alert(err.message)}}finally{{b.disabled=false}}}}));['Desktop','Phone'].forEach(mode=>document.getElementById('preview'+mode).addEventListener('click',()=>{{document.getElementById('previewStage').classList.toggle('phone',mode==='Phone');['Desktop','Phone'].forEach(m=>document.getElementById('preview'+m).classList.toggle('selected',m===mode))}}));pd.addEventListener('close',()=>pf.removeAttribute('srcdoc'))}})();</script>''' + PRESET_THUMBS_JS.replace('@@PRESETS@@',presets_json)


def openflux_ui(state, path, csrf):
    configured=bool(state.get('configured'))
    active=bool(state.get('active'))
    enabled=bool(state.get('enabled'))
    ios=bool(state.get('ios_compatible'))
    status='Запущен' if active else 'Остановлен' if configured else 'Не настроен'
    details=''
    if configured:
        key_field='' if ios else f'''<div class="openflux-field wide"><span>Ключ шифрования</span><div class="openflux-value"><input id="openfluxKey" type="password" readonly value="{esc(state.get("key",""))}" spellcheck="false"><button type="button" data-openflux-reveal="openfluxKey">Показать</button><button type="button" data-openflux-copy="openfluxKey">Копировать</button></div></div>'''
        rotate_action='' if ios else f'''<form method="post" action="{esc(path)}/openflux" data-confirm="Создать новый ключ? Старый ключ сразу перестанет подключаться.">{hidden(csrf,operation='rotate')}<button class="quiet">Новый ключ</button></form>'''
        client_hint=('На iPhone выберите Yandex Docs, вставьте ссылку и нажмите Start VPN. Поле ключа в iOS-клиенте не требуется.' if ios else 'В OpenFlux 1.0.0 для Android выберите Yandex Docs, режим VPN и кодек Batched, затем вставьте ссылку и ключ.')
        details=f'''<div class="openflux-client"><div class="openflux-field"><span>Транспорт</span><b>Yandex Docs</b></div><div class="openflux-field"><span>Клиент</span><b>{'iOS · System VPN' if ios else 'Android · AES-256-GCM'}</b></div><div class="openflux-field"><span>Защита канала</span><b>{'Без AES-шифрования' if ios else 'AES-256-GCM'}</b></div><div class="openflux-field wide"><span>Ссылка для клиента</span><div class="openflux-value"><input id="openfluxUrl" readonly value="{esc(state.get("url",""))}" spellcheck="false"><button type="button" data-openflux-copy="openfluxUrl">Копировать</button></div></div>{key_field}</div><p class="openflux-copy-status" id="openfluxCopyStatus" role="status"></p><div class="openflux-controls"><small>{client_hint} Документ должен открываться в классическом редакторе.</small><div class="actions"><form method="post" action="{esc(path)}/openflux">{hidden(csrf,operation='disable' if enabled else 'enable')}<button>{'Остановить' if enabled else 'Запустить'}</button></form>{rotate_action}</div></div>'''
    checked=' checked' if ios else ''
    mode_note=('Режим iOS отключает AES-шифрование OpenFlux, потому что текущий клиент TestFlight не принимает общий ключ.' if ios else 'Android-режим использует отдельный ключ AES-256-GCM. Для iPhone включите совместимость ниже.')
    return f'''<section class="card openflux-card"><div class="openflux-head"><div class="openflux-title"><span class="openflux-mark">OF</span><div><h2>OpenFlux через Яндекс Документы</h2><p>Экспериментальный TCP-туннель без открытого входящего порта</p></div></div><span class="openflux-status {'on' if active else ''}"><i></i>{status}</span></div><form class="openflux-form" method="post" action="{esc(path)}/openflux">{hidden(csrf,operation='save')}<label for="openfluxDocument">Ссылка на документ Яндекса</label><div class="openflux-input"><input id="openfluxDocument" name="url" type="url" required maxlength="2048" autocomplete="off" spellcheck="false" placeholder="https://disk.yandex.ru/i/…" value="{esc(state.get('url',''))}"><button class="primary">{'Применить настройки' if configured else 'Настроить OpenFlux'}</button></div><label style="display:flex;align-items:flex-start;gap:10px;margin-top:14px;padding:13px;border:1px solid var(--line);border-radius:10px;background:var(--input);cursor:pointer"><input type="checkbox" name="ios_compatible" value="1"{checked} style="width:17px;height:17px;margin-top:1px;accent-color:var(--accent)"><span><b style="display:block;margin-bottom:4px">Совместимость с iOS</b><small style="display:block;color:var(--muted);font-weight:400;line-height:1.5">{mode_note}</small></span></label></form>{details}</section><script>(()=>{{const status=document.getElementById('openfluxCopyStatus');document.querySelectorAll('[data-openflux-copy]').forEach(button=>button.addEventListener('click',async()=>{{const field=document.getElementById(button.dataset.openfluxCopy);try{{await onyxCopy(field.value,button);if(status)status.textContent='Скопировано.'}}catch(e){{field.type='text';field.focus();field.select();if(status)status.textContent='Скопируйте выделенное значение вручную.'}}}}));document.querySelectorAll('[data-openflux-reveal]').forEach(button=>button.addEventListener('click',()=>{{const field=document.getElementById(button.dataset.openfluxReveal),show=field.type==='password';field.type=show?'text':'password';button.textContent=show?'Скрыть':'Показать'}}))}})();</script>'''


def chart(history, hours):
    end=int(time.time()); start=end-hours*3600
    points=[p for p in history if start<=p.get('time',0)<=end]
    valid=[p for p in points if p.get('up_rate') is not None and p.get('down_rate') is not None]
    if len(valid)<2: return '<div class="chart-empty">'+icon('chart')+'<span>История ещё накапливается<br>Первые точки появятся примерно через минуту</span></div>'
    # A newly installed graph should not be an invisible line at the far right.
    start=max(start,min(p['time'] for p in valid)-15)
    span=max(60,end-start)
    ceiling=max(1,max(max(p['up_rate'],p['down_rate']) for p in valid))*1.15
    paths=[]
    for key,color in [('up_rate','var(--accent)'),('down_rate','var(--amber)')]:
        segments=[]; last=None
        for p in points:
            value=p.get(key)
            if value is None: last=None; continue
            x=52+(p['time']-start)/span*738; y=184-min(1,max(0,value)/ceiling)*166
            segments.append(('M' if last is None or p['time']-last>120 else 'L')+f'{x:.1f},{y:.1f}')
            last=p['time']
        paths.append(f'<path d="{" ".join(segments)}" fill="none" stroke="{color}" stroke-width="2" vector-effect="non-scaling-stroke"/>')
    grid=''.join(f'<line x1="52" y1="{18+i*55.3:.1f}" x2="790" y2="{18+i*55.3:.1f}" stroke="var(--line)"/><text x="45" y="{22+i*55.3:.1f}" text-anchor="end">{size(ceiling*(1-i/3))}</text>' for i in range(4))
    ticks=''.join(f'<text x="{52+i*246}" y="210" text-anchor="{"start" if i==0 else "end" if i==3 else "middle"}">{time.strftime("%H:%M",time.gmtime(start+i*span/3))}</text>' for i in range(4))
    return '<svg viewBox="0 0 810 220" role="img" aria-label="Скорость трафика прокси за выбранный период">'+grid+''.join(paths)+ticks+'</svg>'


def _dashboard_body_legacy(data, subs, profiles, traffic, path, domain, csrf, proxy_link, current, hours=1):
    subs = live_subscriptions(subs, profiles)
    latest=data.get('latest',{}); age=max(0,int(time.time())-latest.get('time',0)); fresh=bool(latest) and age<=120
    fault=data.get('collector_error',{})
    if fault and fault.get('time',0)>=latest.get('time',0): fresh=False
    traffic_fresh=fresh and latest.get('traffic_fresh',True)
    health=''
    if not fresh:
        reason='Измерения VPS ещё не получены.' if not latest else 'Измерения VPS не обновляются.'
        health='<div class="note warning" role="status">'+reason+' Проверьте сборщик через SSH: <code>systemctl status onyx-panel-metrics.service onyx-panel-metrics.timer</code>. Журнал: <code>journalctl -u onyx-panel-metrics.service -n 30 --no-pager</code>.</div>'
    elif not traffic_fresh:
        health='<div class="note warning" role="status">Ресурсы VPS измеряются, но нет свежих счётчиков трафика. Проверьте через SSH: <code>systemctl status onyx-panel-traffic.service onyx-panel-traffic.timer</code>.</div>'
    graph=chart(data.get('history',[]),hours)
    if not fresh or not traffic_fresh:
        graph='<div class="chart-empty">'+icon('chart')+'<span>Нет свежих измерений<br>Диагностика сборщика указана выше</span></div>'
    resources=[]
    for key,label,used,total in [('cpu','Процессор',latest.get('cpu'),100),('ram','Память',latest.get('ram_used'),latest.get('ram_total')),('swap','Подкачка',latest.get('swap_used'),latest.get('swap_total')),('disk','Диск',latest.get('disk_used'),latest.get('disk_total'))]:
        percent=used/total*100 if used is not None and total and fresh else None
        text=f'{percent:.1f}%' if percent is not None else '—'
        detail=f'Ядер: {latest.get("cores", "—")} · средняя загрузка' if key=='cpu' else ('Не используется' if key=='swap' and total==0 else size(used)+' / '+size(total))
        resources.append(f'<div class="resource"><div class="resource-ring" style="--value:{max(0,min(100,percent or 0)):.2f}%"><b>{text}</b></div><div class="resource-copy"><strong>{label}</strong><small>{detail}</small></div></div>')
    direct=[u for u in profiles if not u.get('subscription_id')]
    active=sum(aggregate(s['live_profile_ids'],traffic,s.get('enabled',True))['active'] for s in subs)+sum(aggregate([u['id']],traffic,u.get('enabled',True))['active'] for u in direct)
    total_up=sum(max(0,int(v.get('up',0))) for v in traffic.values() if isinstance(v,dict)); total_down=sum(max(0,int(v.get('down',0))) for v in traffic.values() if isinstance(v,dict))
    stats=''.join(f'<div class="overview-stat"><span>{label}</span><b>{value}</b></div>' for label,value in [('Клиенты',len(subs)+len(direct)),('Подписок',len(subs)),('Передают трафик',active),('Всего трафика',size(total_up+total_down))])
    services=latest.get('services',{}); names={'xray':'Xray · VLESS / Hysteria2','relay':'Telegram WEB Proxy / MTProto','awg':'AmneziaWG 2.0 / 3.1','openflux':'OpenFlux · Yandex Docs','caddy':'Caddy · HTTPS','panel':'Панель управления'}
    services_html=''.join('<div class="service-line"><span>'+label+'</span><span class="badge '+('on' if fresh and services.get(key,{}).get('state')=='active' else '')+'">'+('Запущен' if fresh and services.get(key,{}).get('state')=='active' else esc(services.get(key,{}).get('state','Нет данных')) if fresh else 'Нет свежих данных')+'</span></div>' for key,label in names.items())
    xray=services.get('xray',{}); start=xray.get('start_us'); xu=max(0,latest.get('uptime',0)-start/1e6) if start and latest.get('uptime') else None
    detail=[('Время работы VPS',duration(latest.get('uptime'))),('Время работы Xray',duration(xu)),('Память Xray',size(xray.get('memory'))),('Задачи Xray',str(xray.get('tasks') if xray.get('tasks') is not None else '—')),('Нагрузка · 1 / 5 / 15 мин.',' / '.join(f'{v:.2f}' for v in latest.get('load',[])) or '—')]
    details=''.join(f'<div class="detail-line"><span>{k}</span><strong>{v}</strong></div>' for k,v in detail)
    controls=''.join(f'<button data-range="{n}" class="{"selected" if n==hours else ""}">{n} ч</button>' for n in (1,6,24))
    records=client_records(subs,profiles,traffic,domain,proxy_link)
    shown=sorted(records,key=lambda r:(bool(r['totals']['active']),r['totals']['up']+r['totals']['down']),reverse=True)[:8]
    return f'''<div data-live-block="health" class="live-block">{health}</div><section class="card resource-deck live-block" data-live-block="resources"><div class="resource-grid">{''.join(resources)}</div></section><div class="overview-stats live-block" data-live-block="overview">{stats}</div><div class="dashboard-grid"><section class="card graph-card"><div class="card-title"><div><span class="eyebrow">TRAFFIC / LIVE HISTORY</span><h2>Трафик прокси</h2></div><div class="range">{controls}</div></div><div class="graph-speeds live-block" data-live-block="speeds"><div><span>↑ Отправка</span><b>{size(latest.get('up_rate')) if traffic_fresh else '—'}</b><small> / с</small></div><div><span>↓ Получение</span><b>{size(latest.get('down_rate')) if traffic_fresh else '—'}</b><small> / с</small></div></div><div class="chart-wrap live-block" data-live-block="chart">{graph}</div><div class="legend"><span><i></i>Отправка</span><span class="down"><i></i>Получение</span><span>До 24 часов · замер ~10 с · UTC</span></div></section><section class="card"><div class="card-title"><h2>Службы и версия</h2><span class="pill">{esc(current)}</span></div><div class="node-label"><i></i><div class="node-domain">{esc(domain)}</div></div><div class="service-list live-block" data-live-block="services">{services_html}</div><div class="update-box"><div class="actions"><button id="checkUpdate">{icon('refresh')}Загрузить версии</button></div><div class="version-row"><label for="panelRelease">Панель</label><select id="panelRelease" aria-label="Версия панели"><option>Сначала загрузите список</option></select><button class="primary" id="startUpdate" hidden>Установить</button></div><p id="updateStatus" role="status">Можно обновиться или вернуться на прежний стабильный релиз GitLab</p></div></section></div><section class="card version-manager"><div class="card-title"><div><h2>Версии компонентов</h2><p>Обновление и откат без выпуска новой версии панели</p></div><button id="checkComponents">{icon('refresh')}Загрузить версии</button></div><div class="version-row"><label for="xrayRelease">Xray</label><select id="xrayRelease"><option>Сначала загрузите список</option></select><button data-component-install="xray" class="primary" disabled>Установить</button><small class="version-state" id="xrayCurrent">Текущая версия определяется…</small></div><div class="version-row"><label for="openfluxRelease">OpenFlux</label><select id="openfluxRelease"><option>Сначала загрузите список</option></select><button data-component-install="openflux" class="primary" disabled>Установить</button><small class="version-state" id="openfluxCurrent">Текущая версия определяется…</small></div><p id="componentStatus" class="note" role="status">Перед заменой создаётся резервная копия. Если служба не запустится, прежний бинарник восстановится автоматически.</p></section><div class="two-col equal"><section class="card"><div class="card-title"><h2>Ресурсы сервера</h2><span class="pill">VPS</span></div><div class="detail-list live-block" data-live-block="server-details">{details}</div></section><section class="card"><div class="card-title"><h2>Накопленный трафик</h2></div><div class="detail-list live-block" data-live-block="traffic-details"><div class="detail-line"><span>Отправлено</span><strong>↑ {size(total_up)}</strong></div><div class="detail-line"><span>Получено</span><strong>↓ {size(total_down)}</strong></div><div class="detail-line"><span>Последнее измерение</span><strong>{str(age)+' с назад' if latest else 'Нет измерений'}</strong></div></div><p class="note">Только трафик прокси. Активность — передача данных за последние 90 секунд, не число устройств онлайн.</p></section></div><section class="card"><div class="card-title"><h2>Пользователи и подписки</h2><a href="{esc(path)}/users" class="btn quiet">Управление →</a></div><div class="live-block" data-live-block="clients">{client_glances(shown,path)}<small>Показано {len(shown)} из {len(records)} · сначала передающие данные</small></div></section>'''



def _dashboard_page_legacy(body,path,csrf):
    return f'''<div class="page-head"><div><h1>Дашборд</h1><p>Сервер, подключения и использование трафика</p></div><div class="actions"><span id="liveIndicator" class="live-indicator"><i></i><b>Онлайн</b><small id="liveAge">сейчас</small></span><button id="refreshDashboard">{icon('refresh')}Обновить</button></div></div><p id="dashboardNotice" class="note" role="status" hidden></p><div id="dashboardContent">{body}</div><dialog id="updateAvailableDialog" class="update-dialog" aria-labelledby="updateDialogTitle"><div class="dialog-head"><div><small class="eyebrow">НОВАЯ ВЕРСИЯ</small><h2 id="updateDialogTitle">Доступно обновление</h2></div><button type="button" data-close-dialog aria-label="Закрыть уведомление">×</button></div><div class="update-dialog-body"><div class="update-release"><span class="update-release-mark">{icon('refresh')}</span><div><span>Onyx Panel</span><strong><span id="updateCurrentVersion"></span> → <span id="updateLatestVersion"></span></strong></div></div><p>Перед установкой панель создаст резервную копию. Подключения могут кратковременно прерваться.</p></div><div class="update-dialog-actions"><button type="button" id="updateNoticeLater">Позже</button><button type="button" class="primary" id="updateNoticeInstall">Обновить</button></div></dialog><script>
const root=document.getElementById('dashboardContent'),notice=document.getElementById('dashboardNotice'),live=document.getElementById('liveIndicator'),liveAge=document.getElementById('liveAge'),updateDialog=document.getElementById('updateAvailableDialog');let range=1,busy=false,updating=false,lastSuccess=Date.now();
function updateDismissed(version){{try{{return localStorage.getItem('onyx-update-dismissed:'+version)==='1'}}catch(e){{return false}}}}
function dismissUpdate(version){{try{{localStorage.setItem('onyx-update-dismissed:'+version,'1')}}catch(e){{}}}}
function maybeNotifyUpdate(d){{window.dispatchEvent(new CustomEvent('onyx-update-status',{{detail:d}}))}}
function updateView(d){{const p=document.getElementById('updateStatus'),b=document.getElementById('startUpdate'),select=document.getElementById('panelRelease');if(!p||!b||!select)return;updating=['queued','running'].includes(d.phase);if(Array.isArray(d.releases)&&d.releases.length){{const old=select.value;select.innerHTML=d.releases.map(v=>'<option value="'+v+'">'+v.replace(/^v/,'')+(v.replace(/^v/,'')===(d.current||'').replace(/^v/,'')?' · установлена':'')+'</option>').join('');const installed='v'+String(d.current||'').replace(/^v/,'');select.value=d.releases.includes(old)&&old!==installed?old:(d.releases.includes(d.latest)?d.latest:(d.releases[0]||''))}}p.textContent=d.message||(d.checked?'Версии загружены.':'Опубликованные стабильные релизы GitLab');b.hidden=!Array.isArray(d.releases)||!d.releases.length||updating;b.textContent='Установить выбранную';document.getElementById('checkUpdate').disabled=updating;select.disabled=updating;if(updating){{notice.hidden=false;notice.textContent='Изменение версии выполняется. Панель может временно отключиться; не запускайте повторную установку.'}}if(d.available)maybeNotifyUpdate(d)}}
function patchLive(html){{const template=document.createElement('template');template.innerHTML=html;template.content.querySelectorAll('[data-live-block]').forEach(next=>{{const current=root.querySelector('[data-live-block="'+CSS.escape(next.dataset.liveBlock)+'"]');if(!current||current.innerHTML===next.innerHTML)return;current.classList.add('refreshing');requestAnimationFrame(()=>{{current.innerHTML=next.innerHTML;current.className=next.className;current.setAttribute('data-live-block',next.dataset.liveBlock)}})}});root.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('selected',Number(b.dataset.range)===range))}}
function updateClock(){{const seconds=Math.floor((Date.now()-lastSuccess)/1000);liveAge.textContent=seconds<2?'сейчас':seconds+' с назад';live.classList.toggle('stale',seconds>20);live.classList.toggle('offline',seconds>45)}}
async function refresh(){{if(busy||document.hidden)return;busy=true;try{{const r=await fetch('{esc(path)}/dashboard-data?hours='+range,{{cache:'no-store'}});if(r.redirected){{location.href='{esc(path)}/login';return}}if(!r.ok)throw new Error('Нет ответа от панели');const d=await r.json();patchLive(d.html);updateView(d.update);lastSuccess=Date.now();updateClock();if(!updating)notice.hidden=true}}catch(e){{live.classList.add('offline');notice.hidden=false;notice.textContent=updating?'Панель перезапускается во время обновления. Ожидаем восстановления связи…':'Нет связи с панелью. Данные на экране могут быть устаревшими.'}}finally{{busy=false}}}}
async function automaticUpdateCheck(status){{if(status?.checked&&Date.now()/1000-Number(status.checked)<21600)return;try{{const r=await fetch('{esc(path)}/update-check',{{method:'POST',body:new URLSearchParams({{csrf:'{esc(csrf)}'}})}});if(!r.ok||r.redirected)return;updateView(await r.json())}}catch(e){{}}}}
document.getElementById('updateNoticeLater').addEventListener('click',()=>updateDialog.close());document.getElementById('updateNoticeInstall').addEventListener('click',()=>{{const button=document.getElementById('startUpdate');updateDialog.close();if(button&&!button.hidden)button.click()}});updateDialog.addEventListener('close',()=>{{if(updateDialog.dataset.version)dismissUpdate(updateDialog.dataset.version)}});
document.getElementById('refreshDashboard').addEventListener('click',refresh);root.addEventListener('click',async e=>{{const r=e.target.closest('[data-range]');if(r){{range=Number(r.dataset.range);refresh();return}}const b=e.target.closest('#checkUpdate,#startUpdate');if(!b||busy)return;const start=b.id==='startUpdate',target=document.getElementById('panelRelease').value;if(start&&!(await onyxConfirm('Установить версию '+target+'? Будет создана резервная копия. Панель и подключения могут временно прерваться.',{{title:'Установка обновления',ok:'Установить'}})))return;busy=true;b.disabled=true;try{{const body={{csrf:'{esc(csrf)}'}};if(start)body.target=target;const r=await fetch('{esc(path)}/'+(start?'update-start':'update-check'),{{method:'POST',body:new URLSearchParams(body)}});if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');const d=await r.json();if(!r.ok)throw new Error(d.message||'Ошибка обновления');updateView(d)}}catch(err){{document.getElementById('updateStatus').textContent=err.message}}finally{{busy=false;b.disabled=false}}}});
function componentView(d){{const catalog=d.catalog||{{}},current=d.current||{{}},running=['queued','running'].includes(d.phase);for(const name of ['xray','openflux']){{const select=document.getElementById(name+'Release'),button=document.querySelector('[data-component-install="'+name+'"]'),versions=catalog[name]||[];if(versions.length){{const old=select.value;select.innerHTML=versions.map(v=>'<option value="'+v+'">'+v.replace(/^v/,'')+'</option>').join('');if(versions.includes(old))select.value=old}}select.disabled=running||!versions.length;button.disabled=running||!versions.length;document.getElementById(name+'Current').textContent='Установлено: '+(current[name]||'неизвестно')}}document.getElementById('componentStatus').textContent=d.message||'Выберите опубликованную версию GitHub.'}}
document.getElementById('checkComponents').addEventListener('click',async e=>{{const b=e.currentTarget;b.disabled=true;try{{const r=await fetch('{esc(path)}/component-check',{{method:'POST',body:new URLSearchParams({{csrf:'{esc(csrf)}'}})}}),d=await r.json();if(!r.ok)throw new Error(d.message||'Ошибка загрузки версий');componentView(d)}}catch(err){{document.getElementById('componentStatus').textContent=err.message}}finally{{b.disabled=false}}}});document.querySelectorAll('[data-component-install]').forEach(button=>button.addEventListener('click',async()=>{{const component=button.dataset.componentInstall,target=document.getElementById(component+'Release').value;if(!(await onyxConfirm('Установить '+component+' '+target+'? При ошибке будет выполнен автоматический откат.',{{title:'Обновление компонента',ok:'Установить'}})))return;button.disabled=true;try{{const r=await fetch('{esc(path)}/component-install',{{method:'POST',body:new URLSearchParams({{csrf:'{esc(csrf)}',component,target}})}}),d=await r.json();if(!r.ok)throw new Error(d.message||'Ошибка установки');componentView(d)}}catch(err){{document.getElementById('componentStatus').textContent=err.message}}}}));
setInterval(refresh,5000);setInterval(updateClock,1000);setInterval(()=>fetch('{esc(path)}/component-status',{{cache:'no-store'}}).then(r=>r.ok?r.json():null).then(d=>d&&componentView(d)).catch(()=>{{}}),5000);document.addEventListener('visibilitychange',()=>{{if(!document.hidden)refresh()}});fetch('{esc(path)}/update-status',{{cache:'no-store'}}).then(r=>r.ok&&!r.redirected?r.json():null).then(d=>{{if(d){{updateView(d);automaticUpdateCheck(d)}}}}).catch(()=>automaticUpdateCheck(null));fetch('{esc(path)}/component-status',{{cache:'no-store'}}).then(r=>r.ok?r.json():null).then(d=>d&&componentView(d)).catch(()=>{{}});
</script>'''


def dashboard_body(data, subs, profiles, traffic, path, domain, csrf, proxy_link, current, hours=1):
    """Dashboard overview without version management controls."""
    body = _dashboard_body_legacy(data, subs, profiles, traffic, path, domain, csrf, proxy_link, current, hours)
    replacement = (f'<div class="update-box"><div class="actions">'
                   f'<a class="btn quiet" href="{esc(path)}/updates">{icon("refresh")}Управление обновлениями</a>'
                   f'</div><p>Версии панели, Xray и OpenFlux находятся в отдельном разделе.</p></div>'
                   f'</section></div><div class="two-col equal">')
    return re.sub(r'<div class="update-box">.*?</div></section></div><section class="card version-manager">.*?</section><div class="two-col equal">',
                  replacement, body, count=1, flags=re.S)


def dashboard_page(body, path, csrf):
    return f'''<div class="page-head"><div><h1>Дашборд</h1><p>Сервер, подключения и использование трафика</p></div><div class="actions"><span id="liveIndicator" class="live-indicator"><i></i><b>Онлайн</b><small id="liveAge">сейчас</small></span><button id="refreshDashboard">{icon('refresh')}Обновить</button></div></div><p id="dashboardNotice" class="note" role="status" hidden></p><div id="dashboardContent">{body}</div><dialog id="updateAvailableDialog" class="update-dialog" aria-labelledby="updateDialogTitle"><div class="dialog-head"><div><small class="eyebrow">НОВАЯ ВЕРСИЯ</small><h2 id="updateDialogTitle">Доступно обновление</h2></div><button type="button" data-close-dialog aria-label="Закрыть уведомление">×</button></div><div class="update-dialog-body"><div class="update-release"><span class="update-release-mark">{icon('refresh')}</span><div><span>Onyx Panel</span><strong><span id="updateCurrentVersion"></span> → <span id="updateLatestVersion"></span></strong></div></div><p>Подробности, выбор версии и безопасная установка находятся в разделе «Обновления».</p></div><div class="update-dialog-actions"><button type="button" id="updateNoticeLater">Позже</button><a class="btn primary" href="{esc(path)}/updates">Открыть обновления</a></div></dialog><script>
const root=document.getElementById('dashboardContent'),notice=document.getElementById('dashboardNotice'),live=document.getElementById('liveIndicator'),liveAge=document.getElementById('liveAge'),updateDialog=document.getElementById('updateAvailableDialog');let range=1,busy=false,updating=false,lastSuccess=Date.now();
function updateDismissed(version){{try{{return localStorage.getItem('onyx-update-dismissed:'+version)==='1'}}catch(e){{return false}}}}
function dismissUpdate(version){{try{{localStorage.setItem('onyx-update-dismissed:'+version,'1')}}catch(e){{}}}}
function maybeNotifyUpdate(d){{window.dispatchEvent(new CustomEvent('onyx-update-status',{{detail:d}}))}}
function updateView(d){{if(!d)return;updating=['queued','running'].includes(d.phase);if(updating){{notice.hidden=false;notice.textContent='Изменение версии выполняется. Откройте раздел «Обновления», чтобы увидеть статус.'}}if(d.available)maybeNotifyUpdate(d)}}
function patchLive(html){{const template=document.createElement('template');template.innerHTML=html;template.content.querySelectorAll('[data-live-block]').forEach(next=>{{const current=root.querySelector('[data-live-block="'+CSS.escape(next.dataset.liveBlock)+'"]');if(!current||current.innerHTML===next.innerHTML)return;current.classList.add('refreshing');requestAnimationFrame(()=>{{current.innerHTML=next.innerHTML;current.className=next.className;current.setAttribute('data-live-block',next.dataset.liveBlock)}})}});root.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('selected',Number(b.dataset.range)===range))}}
function updateClock(){{const seconds=Math.floor((Date.now()-lastSuccess)/1000);liveAge.textContent=seconds<2?'сейчас':seconds+' с назад';live.classList.toggle('stale',seconds>20);live.classList.toggle('offline',seconds>45)}}
async function refresh(){{if(busy||document.hidden)return;busy=true;try{{const r=await fetch('{esc(path)}/dashboard-data?hours='+range,{{cache:'no-store'}});if(r.redirected){{location.href='{esc(path)}/login';return}}if(!r.ok)throw new Error('Нет ответа от панели');const d=await r.json();patchLive(d.html);updateView(d.update);lastSuccess=Date.now();updateClock();if(!updating)notice.hidden=true}}catch(e){{live.classList.add('offline');notice.hidden=false;notice.textContent=updating?'Панель перезапускается во время обновления. Ожидаем восстановления связи…':'Нет связи с панелью. Данные на экране могут быть устаревшими.'}}finally{{busy=false}}}}
async function automaticUpdateCheck(status){{if(status?.checked&&Date.now()/1000-Number(status.checked)<21600)return;try{{const r=await fetch('{esc(path)}/update-check',{{method:'POST',body:new URLSearchParams({{csrf:'{esc(csrf)}'}})}});if(!r.ok||r.redirected)return;updateView(await r.json())}}catch(e){{}}}}
document.getElementById('updateNoticeLater').addEventListener('click',()=>updateDialog.close());updateDialog.addEventListener('close',()=>{{if(updateDialog.dataset.version)dismissUpdate(updateDialog.dataset.version)}});document.getElementById('refreshDashboard').addEventListener('click',refresh);root.addEventListener('click',e=>{{const r=e.target.closest('[data-range]');if(r){{range=Number(r.dataset.range);refresh()}}}});setInterval(refresh,5000);setInterval(updateClock,1000);document.addEventListener('visibilitychange',()=>{{if(!document.hidden)refresh()}});fetch('{esc(path)}/update-status',{{cache:'no-store'}}).then(r=>r.ok&&!r.redirected?r.json():null).then(d=>{{if(d){{updateView(d);automaticUpdateCheck(d)}}}}).catch(()=>automaticUpdateCheck(null));
</script>'''


CSS += '''
.cascade-card{padding:20px}.cascade-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap}.cascade-head h2{font-size:16px;overflow-wrap:anywhere}.cascade-meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:7px}.cascade-endpoint{font:11px ui-monospace,monospace;color:var(--muted);overflow-wrap:anywhere}.cascade-check{margin-top:12px;font-size:12px;color:var(--muted)}.cascade-latency.ok{color:var(--green)}.cascade-latency.err{color:var(--red)}.cascade-status{min-height:18px;font-size:11px;color:var(--muted);margin:10px 0 0}.cascade-status.err{color:var(--red)}.badge.warn{color:var(--amber)}.badge.warn:before{background:var(--amber)}
.cascade-section{border-top:1px solid var(--line);margin-top:14px;padding-top:12px}.cascade-section details{margin:0}.cascade-section summary{display:flex;align-items:center;gap:9px;cursor:pointer;font-size:12px;font-weight:550;color:var(--muted);list-style:none;user-select:none}.cascade-section summary::-webkit-details-marker{display:none}.cascade-section summary:hover{color:var(--text)}.cascade-section summary:before{content:"";flex:0 0 auto;width:6px;height:6px;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;transform:rotate(-45deg);transition:transform .15s}.cascade-section[open] summary:before{transform:rotate(45deg)}.cascade-section form{margin-top:13px}
.cascade-mode{display:grid;grid-template-columns:1fr 1fr;gap:8px}.cascade-mode .choice-card{min-height:0;gap:9px;padding:12px 13px;border-radius:12px}.cascade-mode .choice-card strong{display:flex;align-items:center;gap:7px;font-size:12.5px}.cascade-mode .choice-card strong .ico{width:15px;height:15px;color:var(--accent)}.cascade-mode .choice-card small{font-size:10.5px;margin-top:3px}
.cascade-clients{margin-top:13px}.cascade-clients-head{display:flex;align-items:center;gap:9px;margin-bottom:9px;font-size:11px}.cascade-clients-head b{margin-right:auto;font-size:11px;font-weight:550;color:var(--muted)}.cascade-count{font:550 11px ui-monospace,monospace;color:var(--accent);white-space:nowrap}.cascade-clients-tools{display:flex;gap:4px}.cascade-clients-tools button{padding:3px 10px;font-size:10px}
.cascade-clients-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(185px,1fr));gap:7px}.cascade-client{position:relative;display:flex;align-items:center;gap:9px;margin:0;padding:8px 11px;border:1px solid var(--line);border-radius:11px;background:var(--input);color:var(--text);cursor:pointer;transition:border-color .15s,background .15s}.cascade-client:hover{border-color:var(--accent)}.cascade-client input{position:absolute;opacity:0;width:1px;height:1px}.cascade-client:has(input:checked){border-color:var(--accent);background:var(--tint);box-shadow:inset 0 0 0 1px var(--accent)}.cascade-client:after{content:"";flex:0 0 auto;width:17px;height:17px;margin-left:auto;border:1.5px solid var(--line);border-radius:50%;transition:border .15s}.cascade-client:has(input:checked):after{border:5.5px solid var(--accent)}.cascade-client .client-initial{width:26px;height:26px;border-radius:8px;font-size:12px}.cascade-client-name{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:500}
@media(max-width:560px){.cascade-mode{grid-template-columns:1fr}.cascade-clients-grid{grid-template-columns:1fr 1fr}}
.cascade-section form>button.primary{margin-top:14px}
.onyx-toasts{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:140;display:grid;gap:8px;justify-items:center;pointer-events:none;width:min(480px,calc(100vw - 24px))}
.onyx-toast{display:flex;align-items:center;gap:9px;max-width:100%;padding:11px 16px;border:1px solid var(--line);border-radius:12px;background:var(--surface);box-shadow:var(--shadow);font-size:12px;font-weight:550;opacity:0;transform:translateY(-14px) scale(.97);transition:opacity .25s,transform .25s}
.onyx-toast.show{opacity:1;transform:translateY(0) scale(1)}
.onyx-toast .ico{width:16px;height:16px;flex:0 0 auto;color:var(--green)}
.onyx-toast.err{border-color:var(--red)}.onyx-toast.err .ico{color:var(--red)}
.onyx-ops{position:fixed;inset:0;z-index:150;display:grid;place-items:center;background:#020d14aa;backdrop-filter:blur(7px);opacity:0;transition:opacity .2s}
.onyx-ops.show{opacity:1}
.onyx-ops-card{width:min(380px,calc(100vw - 32px));padding:28px 26px;text-align:center;background:var(--surface);border:1px solid var(--line);border-radius:20px;box-shadow:var(--shadow)}
.onyx-ops-card h3{font-size:16px;margin:0 0 6px}
.onyx-ops-card p{font-size:12px;color:var(--muted);margin:0;min-height:18px}
.onyx-ops-ring{width:60px;height:60px;margin:0 auto 16px;display:block}
.onyx-ops-ring circle{fill:none;stroke-width:5;stroke-linecap:round;transform-origin:center}
.onyx-ops-ring .bg{stroke:var(--line)}
.onyx-ops-ring .fg{stroke:var(--accent);stroke-dasharray:113;stroke-dashoffset:70;animation:onyx-spin 1s linear infinite}
@keyframes onyx-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.onyx-ops-ring .fg{animation:none}}
.routing-row{display:grid;grid-template-columns:minmax(220px,320px) minmax(0,1fr);gap:20px;padding:20px 0;border-top:1px solid var(--line);align-items:start}.routing-row:first-of-type{border-top:0;padding-top:4px}.routing-row h3{font-size:14px;margin:0}.routing-row small{display:block;font-size:11px;color:var(--muted);margin-top:5px;line-height:1.55}@media(max-width:760px){.routing-row{grid-template-columns:1fr;gap:10px}}
.routing-presets{display:flex;flex-wrap:wrap;gap:7px}
.routing-preset{display:inline-flex;align-items:center;gap:6px;padding:7px 11px;border:1px dashed var(--line);border-radius:10px;background:var(--raised);font-size:11px;font-weight:550;color:var(--muted)}
.routing-preset:hover{border-color:var(--accent);color:var(--text)}
.routing-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px}
.routing-chips:empty{display:none}
.routing-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 7px 5px 10px;border:1px solid var(--line);border-radius:9px;background:var(--input);font:11px ui-monospace,monospace;max-width:100%}
.routing-chip>span{overflow-wrap:anywhere}
.routing-chip button{padding:0 3px;border:0;background:transparent;color:var(--muted);font-size:14px;line-height:1}
.routing-chip button:hover{color:var(--red)}
.routing-add{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;margin-top:12px}
.routing-add input{font:11px ui-monospace,monospace}
.routing-switch-row{display:flex;justify-content:flex-end;align-items:center;gap:16px}
'''

ROUTING_IP_PRESETS=[
    ('🏠','Приватные',['geoip:private']),
    ('🇮🇷','Иран',['geoip:ir']),
    ('🇨🇳','Китай',['geoip:cn']),
    ('🇷🇺','Россия',['geoip:ru']),
    ('🇻🇳','Вьетнам',['geoip:vn']),
    ('🇪🇸','Испания',['geoip:es']),
    ('🇮🇩','Индонезия',['geoip:id']),
    ('🇺🇦','Украина',['geoip:ua']),
]

ROUTING_DOMAIN_PRESETS=[
    ('🏠','Локальные',['geosite:private']),
    ('🇮🇷','Иран',['domain:ir','geosite:ir']),
    ('🇨🇳','Китай',['domain:cn','geosite:cn']),
    ('🇷🇺','Россия',['domain:ru','domain:su','domain:рф','domain:xn--p1ai']),
    ('🇻🇳','Вьетнам',['domain:vn','geosite:vn']),
    ('🇺🇦','Украина',['domain:ua','geosite:ua']),
    ('🇪🇸','Испания',['domain:es','geosite:es']),
    ('🇮🇩','Индонезия',['domain:id','geosite:id']),
]

ROUTING_JS='''<script>
(()=>{const PATH=@@PATH@@,CSRF=@@CSRF@@,LISTS=['direct_ips','direct_domains','ipv4_domains'],state={};
function escHtml(v){return String(v).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
function render(list){
  const box=document.querySelector('.chip-editor[data-list="'+list+'"] [data-chips]');
  if(!box)return;
  box.innerHTML=state[list].map((v,i)=>'<span class="routing-chip"><span>'+escHtml(v)+'</span><button type="button" data-i="'+i+'" aria-label="Убрать">×</button></span>').join('');}
function addEntries(list,raw){
  const parts=String(raw||'').split(',').map(s=>s.trim()).filter(Boolean);
  let added=0;
  parts.forEach(p=>{if(p.length<200&&!state[list].some(v=>v.toLowerCase()===p.toLowerCase())){state[list].push(p);added++}});
  if(added)render(list);
  return added;}
LISTS.forEach(list=>{
  const ed=document.querySelector('.chip-editor[data-list="'+list+'"]');
  if(!ed)return;
  state[list]=(ed.dataset.initial||'').split(',').filter(Boolean);
  render(list);
  ed.querySelectorAll('[data-entries]').forEach(btn=>btn.addEventListener('click',()=>{
    const n=addEntries(list,btn.dataset.entries);
    if(window.onyxToast)onyxToast(n?'Пресет добавлен — не забудьте сохранить':'Эти значения уже в списке');}));
  const input=ed.querySelector('.routing-input'),addBtn=ed.querySelector('.routing-add-btn');
  const submit=()=>{if(!input.value.trim())return;
    const n=addEntries(list,input.value);
    if(n)input.value='';else if(window.onyxToast)onyxToast('Некорректно или уже добавлено','err')};
  addBtn.addEventListener('click',submit);
  input.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();submit()}});
  ed.querySelector('[data-chips]').addEventListener('click',e=>{
    const b=e.target.closest('[data-i]');if(!b)return;
    state[list].splice(Number(b.dataset.i),1);render(list)});
});
const save=document.getElementById('routingSave');
if(save)save.addEventListener('click',async()=>{
  if(save.disabled)return;
  save.disabled=true;const old=save.innerHTML;save.textContent='Сохраняю…';
  try{const payload={};LISTS.forEach(l=>payload[l]=state[l].join(','));
    const tsw=document.querySelector('[data-routing-torrent]');
    if(tsw)payload.block_torrents=tsw.getAttribute('aria-checked')==='true'?'1':'0';
    const r=await fetch(PATH+'/routing-save',{method:'POST',headers:{'X-Onyx-Async':'1'},
      body:new URLSearchParams({csrf:CSRF,...payload})});
    if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');
    let res;try{res=await r.json()}catch(e){throw new Error('Панель вернула некорректный ответ.')}
    if(!r.ok||!res.ok)throw new Error(res.message||'Операция не выполнена.');
    if(window.onyxToast)onyxToast(res.message||'Правила сохранены — применяются в фоне…');}
  catch(e){if(window.onyxToast)onyxToast(e.message,'err')}
  finally{save.disabled=false;save.innerHTML=old}});
const sw=document.querySelector('[data-routing-torrent]');
if(sw)sw.addEventListener('click',async()=>{
  if(sw.disabled)return;
  const previous=sw.getAttribute('aria-checked');
  sw.disabled=true;sw.setAttribute('aria-checked',previous==='true'?'false':'true');
  try{const r=await fetch(PATH+'/routing-torrent',{method:'POST',headers:{'X-Onyx-Async':'1'},
      body:new URLSearchParams({csrf:CSRF,enabled:previous==='true'?'0':'1'})});
    if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');
    let res;try{res=await r.json()}catch(e){throw new Error('Панель вернула некорректный ответ.')}
    if(!r.ok||!res.ok)throw new Error(res.message||'Операция не выполнена.');
    if(window.onyxToast)onyxToast(res.message||'Сохранено — применяется в фоне…');}
  catch(e){sw.setAttribute('aria-checked',previous);if(window.onyxToast)onyxToast(e.message,'err')}
  finally{sw.disabled=false}});
})();
</script>'''


def _chip_editor(list_key, presets, values, placeholder):
    preset_html=''.join(
        f'<button type="button" class="routing-preset" data-entries="{esc(",".join(entries))}">{flag} {esc(name)}</button>'
        for flag,name,entries in presets)
    return (f'<div class="chip-editor" data-list="{list_key}" data-initial="{esc(",".join(values))}">'
            f'<div class="routing-presets">{preset_html}</div>'
            f'<div class="routing-chips" data-chips></div>'
            f'<div class="routing-add"><input class="routing-input" placeholder="{esc(placeholder)}" spellcheck="false" autocomplete="off">'
            f'<button type="button" class="routing-add-btn">Добавить</button></div></div>')


def routing_ui(routing, path, csrf, domain):
    routing = routing or {}
    torrents_enabled=bool(routing.get('block_torrents'))
    banner='<p class="note"><b>Прямое соединение</b> означает, что определённый трафик не будет перенаправлен через другой сервер. Правила из этой вкладки проверяются <b>до</b> каскада: совпавший трафик всегда уходит с этого сервера напрямую.</p>'
    ip_editor=_chip_editor('direct_ips',ROUTING_IP_PRESETS,routing.get('direct_ips',[]),'geoip:cn, 1.2.3.4 или 10.0.0.0/8')
    domain_editor=_chip_editor('direct_domains',ROUTING_DOMAIN_PRESETS,routing.get('direct_domains',[]),'domain:example.com, geosite:cn')
    ipv4_editor=_chip_editor('ipv4_domains',ROUTING_DOMAIN_PRESETS,routing.get('ipv4_domains',[]),'domain:example.com')
    return f'''<div class="page-head"><div><h1>Маршрутизация</h1><p>Прямые подключения, IPv4 и блокировки</p></div><div class="actions"><button class="primary" id="routingSave">{icon('refresh')}Сохранить правила</button></div></div>{banner}
<section class="card">
<div class="routing-row"><div><h3>Прямые IP-адреса</h3><small>Трафик на эти адреса и сети уходит напрямую, минуя каскад. Пресеты добавляют geoip-списки Xray.</small></div>{ip_editor}</div>
<div class="routing-row"><div><h3>Прямые домены</h3><small>Домены в формате Xray: domain:example.com, geosite:cn или regexp:… Совпавшие запросы идут напрямую.</small></div>{domain_editor}</div>
<div class="routing-row"><div><h3>Правила IPv4</h3><small>Эти параметры позволяют клиентам обращаться к перечисленным доменам только через IPv4.</small></div>{ipv4_editor}</div>
</section>
<section class="card"><div class="card-title"><h2>Блокировки</h2></div><div class="routing-row" style="border-top:0;padding-top:4px"><div><h3>Заблокировать Торренты</h3><small>BitTorrent-трафик распознаётся сниффером Xray и блокируется. Работает для VLESS и Hysteria2.</small></div><div class="routing-switch-row"><button type="button" class="access-switch" data-routing-torrent role="switch" aria-label="Заблокировать торренты" aria-checked="{str(torrents_enabled).lower()}" title="{'Выключить блокировку торрентов' if torrents_enabled else 'Включить блокировку торрентов'}"></button></div></div></section>{ROUTING_JS.replace('@@PATH@@',json.dumps(path)).replace('@@CSRF@@',json.dumps(csrf))}'''

CASCADE_JS='''<script>
(()=>{const PATH=@@PATH@@,CSRF=@@CSRF@@;
async function post(action,data){
  const body=new URLSearchParams(data);body.set('csrf',CSRF);
  const r=await fetch(PATH+'/'+action,{method:'POST',headers:{'X-Onyx-Async':'1'},body});
  if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');
  let res;try{res=await r.json()}catch(e){throw new Error('Панель вернула некорректный ответ.')}
  if(!r.ok||!res.ok)throw new Error(res.message||'Операция не выполнена.');
  return res;}
/* Long work (probe + Xray restart) runs in the background on the server.
   The live poller fetches /cascade-state every few seconds and patches each
   card in place: badge, switch, check result and the job status line. */
function statePatch(d){
  const card=document.querySelector('[data-cascade="'+window.CSS.escape(d.id)+'"]');
  if(!card)return false;
  const badge=card.querySelector('.cascade-meta .badge');
  if(badge){badge.textContent=d.state_text;badge.className='badge '+(d.state_class||'')}
  const sw=card.querySelector('.access-switch');
  if(sw){sw.setAttribute('aria-checked',d.switch_checked);sw.setAttribute('title',d.switch_title);
    const form=sw.closest('form'),op=form&&form.querySelector('[name=operation]');
    if(op)op.value=d.switch_checked==='true'?'disable':'enable'}
  const check=card.querySelector('[data-check]');
  if(check){const tpl=document.createElement('template');tpl.innerHTML=d.check_html;
    if(tpl.content.firstElementChild)check.replaceWith(tpl.content.firstElementChild)}
  const job=card.querySelector('[data-job]');
  if(job)job.innerHTML=d.job_html||'';
  return true}
let liveTimer=null;
function startLive(){
  if(liveTimer)return;
  liveTimer=setInterval(async()=>{
    if(document.hidden)return;
    try{const r=await fetch(PATH+'/cascade-state',{cache:'no-store'});
      if(!r.ok||r.redirected)return;
      const d=await r.json(),list=d.cascades||[];
      let unknown=false;
      list.forEach(c=>{if(!statePatch(c))unknown=true});
      document.querySelectorAll('[data-cascade]').forEach(el=>{
        if(!list.some(c=>c.id===el.dataset.cascade))el.remove()});
      if(unknown)location.reload();
    }catch(e){}},3000);}
startLive();
document.querySelectorAll('[data-cascade-ping]').forEach(button=>{
  button.addEventListener('click',async()=>{
    if(button.disabled)return;
    const card=button.closest('[data-cascade]'),out=card.querySelector('[data-check]');
    const old=button.innerHTML;button.disabled=true;button.textContent='Проверяю…';
    if(out)out.textContent='Проверка выполняется…';
    try{const res=await post('cascade-ping',{id:card.dataset.cascade});
      if(window.onyxToast)onyxToast(res.message||'Проверка запущена.');}
    catch(e){if(window.onyxToast)onyxToast(e.message,'err');
      if(out){out.textContent=e.message;out.classList.add('err');out.classList.remove('ok')}}
    finally{button.disabled=false;button.innerHTML=old}});
});
document.querySelectorAll('form[data-cascade-toggle]').forEach(form=>{
  const button=form.querySelector('button');
  button.addEventListener('click',async()=>{
    if(button.disabled)return;
    const previous=button.getAttribute('aria-checked');
    button.disabled=true;button.setAttribute('aria-checked',previous==='true'?'false':'true');
    try{const res=await post('cascade-toggle',new URLSearchParams(new FormData(form)));
      if(window.onyxToast)onyxToast(res.message||'Сохранено — применяется в фоне…')}
    catch(e){button.setAttribute('aria-checked',previous);
      if(window.onyxToast)onyxToast(e.message,'err')}
    finally{button.disabled=false}});
});
document.querySelectorAll('form[data-cascade-users]').forEach(form=>{
  const block=form.querySelector('[data-users-block]'),boxes=[...form.querySelectorAll('input[name=users]')],
        count=form.querySelector('[data-users-count]');
  const sync=()=>{if(block)block.hidden=form.querySelector('input[name=mode]:checked').value!=='users'};
  const counter=()=>{if(count)count.textContent=boxes.filter(b=>b.checked).length+' из '+boxes.length};
  boxes.forEach(b=>b.addEventListener('change',counter));
  form.querySelectorAll('[data-users-all],[data-users-none]').forEach(btn=>btn.addEventListener('click',()=>{
    const on=btn.hasAttribute('data-users-all');boxes.forEach(b=>b.checked=on);counter()}));
  form.querySelectorAll('input[name=mode]').forEach(r=>r.addEventListener('change',sync));
  sync();counter();
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    const status=form.querySelector('[data-form-status]'),button=form.querySelector('button.primary');
    button.disabled=true;status.textContent='Сохраняю…';status.classList.remove('err');
    /* The backend flattens repeated fields, so selected clients travel as one
       comma-joined value instead of several "users" checkboxes. */
    const payload={id:form.querySelector('[name=id]').value,
      mode:form.querySelector('input[name=mode]:checked').value,
      users:boxes.filter(b=>b.checked).map(b=>b.value).join(',')};
    try{const res=await post('cascade-users',payload);
      status.textContent='';if(window.onyxToast)onyxToast(res.message||'Сохранено — применяется в фоне…')}
    catch(err){status.textContent=err.message;status.classList.add('err');
      if(window.onyxToast)onyxToast(err.message,'err')}
    finally{button.disabled=false}});
});
const dialog=document.getElementById('cascadeAdd');
if(dialog){
  const open=document.getElementById('addCascade'),form=document.getElementById('cascadeAddForm');
  if(open)open.addEventListener('click',()=>{form.reset();dialog.showModal();form.querySelector('textarea').focus()});
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    const status=form.querySelector('[data-form-status]'),button=form.querySelector('button.primary');
    button.disabled=true;status.textContent='Добавляю каскад…';status.classList.remove('err');
    try{const res=await post('cascade-add',new URLSearchParams(new FormData(form)));
      if(window.onyxToast)onyxToast(res.message||'Каскад добавлен.');location.reload()}
    catch(err){status.textContent=err.message;status.classList.add('err');
      if(window.onyxToast)onyxToast(err.message,'err');button.disabled=false}});
}})();
</script>'''


def cascade_check_html(item):
    check=item.get('last_check') or {}
    when=' · '+time.strftime('%d.%m.%Y %H:%M',time.localtime(check['checked_at'])) if check.get('checked_at') else ''
    if check.get('ok'):
        exit_ip=' · выход '+esc(check['exit_ip']) if check.get('exit_ip') else ''
        return f'<span class="cascade-latency ok" data-check>Проверка пройдена · {int(check.get("ms",0))} мс{exit_ip}{when}</span>'
    if check.get('message'):
        return f'<span class="cascade-latency err" data-check>Проверка не прошла: {esc(check.get("message"))}{when}</span>'
    return '<span class="cascade-latency" data-check>Ещё не проверялся</span>'


def cascade_state_view(item, carriers=None):
    """Display state of one cascade card, shared by the page render and the
    /cascade-state JSON the live poller patches the DOM with."""
    carriers = carriers or {}
    enabled=bool(item.get('enabled'))
    pending=bool(item.get('pending'))
    op_error=str(item.get('op_error') or '')
    carries=carriers.get(item.get('id'), item.get('carries', False))
    if not enabled: state,state_class='Выключен',''
    elif carries: state,state_class='Передаёт трафик','on'
    elif item.get('mode')=='all': state,state_class='В резерве','warn'
    elif not item.get('users'): state,state_class='Клиенты не выбраны',''
    else: state,state_class='Перекрыт другим каскадом','warn'
    if pending: job='<span class="cascade-latency">Выполняется: проверка и применение конфигурации…</span>'
    elif op_error: job=f'<span class="cascade-latency err">Не удалось применить: {esc(op_error)}</span>'
    else: job=''
    return {'id':item.get('id'),'state_text':state,'state_class':state_class,
            'switch_checked':str(enabled).lower(),
            'switch_title':'Отключить каскад' if enabled else 'Включить каскад',
            'check_html':cascade_check_html(item),'job_html':job,'pending':pending}


CASCADE_PROTO_LABELS={'vless':('VLESS','proto-vless'),'hysteria':('Hysteria2','proto-hysteria')}


def cascade_card(item, vless_users, path, csrf):
    sid=esc(item['id'])
    view=cascade_state_view(item,{item.get('id'):bool(item.get('carries'))})
    pending=bool(item.get('pending'))
    enabled_bool=view['switch_checked']=='true'
    mode=item.get('mode','all')
    rows=[]
    for user in vless_users:
        uid=str(user['id'])
        name=str(user.get('name') or uid)
        selected=' checked' if uid in (item.get('users') or []) else ''
        plabel,pclass=CASCADE_PROTO_LABELS.get(user.get('protocol'),(str(user.get('protocol') or '?'),''))
        rows.append(f'<label class="cascade-client"><span class="client-initial" aria-hidden="true">{esc(name.strip()[:1].upper() or "•")}</span><span class="cascade-client-name" title="{esc(name)}">{esc(name)}</span><span class="pill {pclass}">{esc(plabel)}</span><input type="checkbox" name="users" value="{esc(uid)}"{selected}></label>')
    if rows:
        users_block=('<div class="cascade-clients" data-users-block><div class="cascade-clients-head"><b>Клиенты</b>'
                     '<span class="cascade-count" data-users-count></span>'
                     '<span class="cascade-clients-tools"><button type="button" data-users-all>Все</button>'
                     '<button type="button" data-users-none>Снять</button></span></div>'
                     '<div class="cascade-clients-grid">'+''.join(rows)+'</div></div>')
    else:
        users_block='<div class="cascade-clients" data-users-block><p class="sub">VLESS и Hysteria2 клиентов нет. Создайте их в разделе «Пользователи».</p></div>'
    return f'''<div class="card cascade-card" data-cascade="{sid}" data-pending="{int(pending)}"><div class="cascade-head"><div><h2>{esc(item.get("name"))}</h2><div class="cascade-meta"><span class="pill">{esc(item.get("transport"))}</span><span class="cascade-endpoint">{esc(item.get("address"))}:{int(item.get("port",443))}</span><span class="badge {view["state_class"]}">{view["state_text"]}</span></div></div><div class="actions"><button type="button" data-cascade-ping>{icon("refresh")}Проверить</button><form method="post" action="{esc(path)}/cascade-toggle" data-cascade-toggle>{hidden(csrf,id=item["id"],operation='disable' if enabled_bool else 'enable')}<button type="button" class="access-switch" role="switch" aria-label="Каскад {esc(item.get("name"))}" aria-checked="{view["switch_checked"]}" title="{view["switch_title"]}"></button></form><form method="post" action="{esc(path)}/cascade-delete" data-confirm="Удалить каскад «{esc(item.get("name"))}»? Клиенты мгновенно вернутся на прямое подключение.">{hidden(csrf,id=item["id"])}<button type="submit" class="icon-btn danger" aria-label="Удалить каскад {esc(item.get("name"))}" title="Удалить">{icon("trash")}</button></form></div></div><div class="cascade-check">{view["check_html"]}</div><div class="cascade-check cascade-job" data-job>{view["job_html"]}</div><details class="cascade-section"><summary>Режим и клиенты</summary><form data-cascade-users>{hidden(csrf,id=item["id"])}<div class="cascade-mode"><label class="choice-card"><input type="radio" name="mode" value="all" {"checked" if mode=="all" else ""}><span><strong>{icon("cascade")}Все VLESS и Hysteria2</strong><small>Клиенты VLESS и Hysteria2 пойдут через каскад</small></span></label><label class="choice-card"><input type="radio" name="mode" value="users" {"checked" if mode=="users" else ""}><span><strong>{icon("users")}Только выбранные</strong><small>Через каскад пойдут отмеченные, остальные — напрямую</small></span></label></div>{users_block}<button class="primary">Сохранить</button><p class="cascade-status" data-form-status role="status"></p></form></details></div>'''


def cascade_ui(items, users, path, csrf, domain):
    vless_users=[{'id':user['id'],'name':user.get('name',''),'protocol':user.get('protocol','')} for user in (users or [])
                 if user.get('protocol') in ('vless','hysteria') and user.get('enabled',True) and isinstance(user.get('id'),str)]
    cards=''.join(cascade_card(item,vless_users,path,csrf) for item in (items or []))
    listing=cards if cards else '<section class="card empty">Каскадов нет. Вставьте vless:// ключ клиента верхней панели — трафик этой панели начнёт выходить через неё.</section>'
    help_note=f'''<details class="note cascade-help"><summary>Как работает каскад</summary><p>Каскад — это аутбаунд Xray: клиенты по-прежнему подключаются к <code>{esc(domain)}</code>, но их трафик уходит в интернет через верхнюю панель. Отключение каскада мгновенно возвращает прямое подключение. Каскадируются <b>VLESS и Hysteria2</b>; UDP внутри Hysteria2 едет через каскад как UDP-over-TCP — на обеих панелях должен быть современный Xray (в Onyx он такой). AmneziaWG, MTProto, WEB Proxy и OpenFlux идут напрямую всегда: их трафик технически не проходит через Xray.</p><p>Режим «Все VLESS и Hysteria2» перенаправляет клиентов обоих протоколов, «Только выбранные» — отмеченных. Если несколько каскадов претендуют на один и тот же трафик, работает тот, что выше в списке, а правило по конкретному клиенту сильнее общего режима.</p><p>Не направляйте две панели друг на друга в режиме «Все» — получится петля: на ответственной панели включите режим выбранных клиентов и не выбирайте ключ, который обслуживает нижнюю панель. Цепочка из трёх и более панелей собирается сама, если у верхней панели настроен собственный каскад.</p></details>'''
    add_dialog=f'''<dialog id="cascadeAdd"><div class="dialog-head"><div><h2>Новый каскад</h2><small>Ключ клиента верхней панели</small></div><button type="button" data-close-dialog aria-label="Закрыть">×</button></div><form id="cascadeAddForm">{hidden(csrf)}<label for="cascadeLink">vless:// ключ</label><textarea id="cascadeLink" name="link" rows="4" required spellcheck="false" placeholder="vless://…"></textarea><label for="cascadeName">Название — необязательно</label><input id="cascadeName" name="name" maxlength="80" autocomplete="off" placeholder="Из метки ключа или адрес сервера"><p class="note">Скопируйте ключ в разделе «Пользователи» верхней панели Onyx или в любой другой Xray-панели. Понимаются транспорты TCP, WebSocket, gRPC, XHTTP, HTTPUpgrade и HTTP/2, защита TLS и Reality. После добавления каскад сразу включается в режиме «Все VLESS и Hysteria2» и проверяется живым запросом.</p><p class="cascade-status" data-form-status role="status"></p><div class="actions create-actions"><button type="button" data-close-dialog>Отмена</button><button class="primary">Проверить и добавить</button></div></form></dialog>'''
    return f'''<div class="page-head"><div><h1>Каскад</h1><p>Выпуск трафика через другие панели</p></div><div class="actions"><button class="primary" id="addCascade">＋ Добавить каскад</button></div></div>{help_note}{listing}{add_dialog}{CASCADE_JS.replace('@@PATH@@',json.dumps(path)).replace('@@CSRF@@',json.dumps(csrf))}'''


def updates_ui(path, csrf, current):
    return f'''<div class="page-head"><div><span class="eyebrow">ONYX PANEL / RELEASE CONTROL</span><h1>Обновления</h1><p>Версии панели и системных компонентов в одном месте</p></div><div class="actions"><span class="update-flag" id="updateFlag" hidden><i class="update-flag-dot"></i>Доступно обновление&nbsp;<b id="updateFlagVer"></b></span><button id="refreshAll">{icon('refresh')}Проверить обновление</button></div></div>
<section class="card updates-hero"><div class="updates-hero-copy"><span class="updates-hero-icon">{icon('refresh')}</span><div><h2>Центр обновлений</h2><p>Можно установить новую версию или вернуться на предыдущую. Перед заменой автоматически создаётся резервная копия.</p></div></div><div class="actions"><span class="pill">RC · ручная установка</span></div></section>
<div class="updates-grid">
<section class="card updates-card"><div class="card-title"><div><h2>Onyx Panel</h2><p>Интерфейс, менеджер подключений и служебные модули</p></div><span class="pill">Панель</span></div><div class="update-installed"><span>Установленная версия</span><strong id="panelCurrent">{esc(current)}</strong></div><div class="update-control"><label for="panelRelease">Доступная версия</label><select id="panelRelease" aria-label="Версия панели"><option>Загрузите список версий</option></select><button class="primary" id="startUpdate" disabled>Установить</button></div><p id="updateStatus" class="note update-status" role="status">Проверяем опубликованные релизы…</p></section>
<section class="card updates-card"><div class="card-title"><div><h2>Компоненты</h2><p>Xray и OpenFlux обновляются независимо от панели</p></div><span class="pill">Ядро</span></div><div class="component-stack"><div class="component-item"><div class="component-item-head"><strong>Xray</strong><small id="xrayCurrent">Версия определяется…</small></div><div class="update-control"><label for="xrayRelease">Версия</label><select id="xrayRelease"><option>Загрузите список версий</option></select><button class="primary" data-component-install="xray" disabled>Установить</button></div></div><div class="component-item"><div class="component-item-head"><strong>OpenFlux</strong><small id="openfluxCurrent">Версия определяется…</small></div><div class="update-control"><label for="openfluxRelease">Версия</label><select id="openfluxRelease"><option>Загрузите список версий</option></select><button class="primary" data-component-install="openflux" disabled>Установить</button></div></div></div><p id="componentStatus" class="note update-status" role="status">Проверяем версии компонентов…</p></section>
</div><div class="update-safety"><div><b>Резервная копия</b><small>Создаётся до замены файлов и бинарников.</small></div><div><b>Проверка запуска</b><small>После установки служба проходит автоматическую проверку.</small></div><div><b>Автоматический откат</b><small>Если новая версия не запустится, прежняя будет восстановлена.</small></div></div>
<div class="move-overlay" id="updOverlay" hidden><div class="move-card" id="updCard"><div class="move-ring"><svg viewBox="0 0 100 100" aria-hidden="true"><circle class="move-ring-bg" cx="50" cy="50" r="44"/><circle class="move-ring-fg" id="updRing" cx="50" cy="50" r="44"/></svg><b id="updSecs">↑</b></div><h3 id="updTitle">Обновить панель?</h3><p id="updText"></p><div class="actions upd-actions" id="updActions" hidden><button type="button" id="updCancel">Отмена</button><button type="button" class="primary" id="updGo">Обновить</button></div></div></div>
<script>
const panelSelect=document.getElementById('panelRelease'),panelButton=document.getElementById('startUpdate'),panelStatus=document.getElementById('updateStatus'),componentStatus=document.getElementById('componentStatus');let panelBusy=false;
function panelView(d){{if(!d)return;panelBusy=['queued','running'].includes(d.phase);document.getElementById('panelCurrent').textContent=d.current||'{esc(current)}';const flag=document.getElementById('updateFlag'),latest=String(d.latest||''),cur=String(d.current||'');const newerV=(a,b)=>{{const p=s=>s.replace(/^v/,'').split('.').map(Number);const x=p(a),y=p(b);for(let i=0;i<3;i++){{if((x[i]||0)!==(y[i]||0))return (x[i]||0)>(y[i]||0)}}return false}};if(latest&&cur&&newerV(latest,cur)){{flag.hidden=false;document.getElementById('updateFlagVer').textContent=latest.replace(/^v/,'')}}else{{flag.hidden=true}}const releases=Array.isArray(d.releases)?d.releases:[];if(releases.length){{const old=panelSelect.value;panelSelect.innerHTML=releases.map(v=>'<option value="'+v+'">'+v.replace(/^v/,'')+(v.replace(/^v/,'')===(d.current||'').replace(/^v/,'')?' · установлена':'')+'</option>').join('');const installed='v'+String(d.current||'').replace(/^v/,'');panelSelect.value=releases.includes(old)&&old!==installed?old:(releases.includes(d.latest)?d.latest:(releases[0]||''))}}panelSelect.disabled=panelBusy||!releases.length;panelButton.disabled=panelBusy||!releases.length;panelButton.textContent=panelBusy?'Установка…':'Установить';panelStatus.textContent=d.message||(d.checked?'Версии панели загружены.':'Нажмите «Проверить обновление».')}}
function componentView(d){{if(!d)return;const catalog=d.catalog||{{}},current=d.current||{{}},running=['queued','running'].includes(d.phase);for(const name of ['xray','openflux']){{const select=document.getElementById(name+'Release'),button=document.querySelector('[data-component-install="'+name+'"]'),versions=catalog[name]||[];if(versions.length){{const old=select.value;select.innerHTML=versions.map(v=>'<option value="'+v+'">'+v.replace(/^v/,'')+(v.replace(/^v/,'')===String(current[name]||'').replace(/^v/,'')?' · установлена':'')+'</option>').join('');if(versions.includes(old))select.value=old}}select.disabled=running||!versions.length;button.disabled=running||!versions.length;document.getElementById(name+'Current').textContent='Установлено: '+(current[name]||'неизвестно')}}componentStatus.textContent=d.message||(d.checked?'Версии компонентов загружены.':'Нажмите «Проверить обновление».')}}
async function request(endpoint,data,status){{const r=await fetch('{esc(path)}/'+endpoint,{{method:'POST',body:new URLSearchParams({{csrf:'{esc(csrf)}',...data}})}});if(r.redirected)throw new Error('Сессия завершена. Войдите заново.');let result;try{{result=await r.json()}}catch(e){{throw new Error('Панель вернула некорректный ответ.')}}if(!r.ok)throw new Error(result.message||'Операция завершилась ошибкой.');return result}}
async function loadPanel(check=false){{try{{const d=check?await request('update-check',{{}},panelStatus):await fetch('{esc(path)}/update-status',{{cache:'no-store'}}).then(r=>r.ok?r.json():null);if(!check&&!d)return;panelView(d)}}catch(e){{panelStatus.textContent=e.message}}}}
async function loadComponents(check=false){{try{{const d=check?await request('component-check',{{}},componentStatus):await fetch('{esc(path)}/component-status',{{cache:'no-store'}}).then(r=>r.ok?r.json():null);if(!check&&!d)return;componentView(d)}}catch(e){{componentStatus.textContent=e.message}}}}
document.getElementById('refreshAll').addEventListener('click',async e=>{{const b=e.currentTarget;b.disabled=true;b.textContent='Загрузка…';await Promise.all([loadPanel(true),loadComponents(true)]);b.disabled=false;b.innerHTML='{icon('refresh')}Проверить обновление'}});
const updOverlay=document.getElementById('updOverlay'),updCard=document.getElementById('updCard'),updRing=document.getElementById('updRing'),updSecs=document.getElementById('updSecs'),updTitle=document.getElementById('updTitle'),updText=document.getElementById('updText'),updActions=document.getElementById('updActions'),updGo=document.getElementById('updGo'),updCancel=document.getElementById('updCancel'),RING=276.5,sleep=ms=>new Promise(r=>setTimeout(r,ms));let updActive=false,updClock=null,updRun=0;
function ringSet(f){{updRing.style.strokeDashoffset=(RING*(1-Math.max(0,Math.min(1,f)))).toFixed(1)}}
function updShow(state,target,message){{updCard.classList.remove('spin','time','upd-done','upd-err');ringSet(1);updGo.dataset.mode=state==='failed'?'close':'go';updGo.textContent=state==='failed'?'Закрыть':'Обновить';updGo.disabled=false;updCancel.hidden=state!=='confirm';updActions.hidden=state!=='confirm'&&state!=='failed';if(state==='confirm'){{updTitle.textContent='Обновить панель?';updText.textContent='Версия '+target+' установится поверх текущей. Резервная копия создаётся автоматически, панель кратковременно уйдёт и вернётся.';updSecs.textContent='↑'}}else if(state==='running'){{updCard.classList.add('spin','time');updTitle.textContent='Обновляем панель';updText.textContent=message||'Создаём резервную копию и устанавливаем обновление…';updSecs.textContent='0:00'}}else if(state==='done'){{updCard.classList.add('upd-done');updTitle.textContent='Обновление установлено';updText.textContent='Панель вернулась. Обновляем страницу…';updSecs.textContent='✓'}}else{{updCard.classList.add('upd-err');updTitle.textContent='Обновление не удалось';updText.textContent=message||'Проверьте журнал через Onyx или SSH и попробуйте ещё раз.';updSecs.textContent='!'}}updOverlay.hidden=false;requestAnimationFrame(()=>updOverlay.classList.add('show'))}}
function updHide(){{updOverlay.classList.remove('show');setTimeout(()=>{{updOverlay.hidden=true}},260);clearInterval(updClock);updRun++}}
function updReloadCountdown(){{let left=5;updSecs.textContent=left;const my=updRun,iv=setInterval(()=>{{if(my!==updRun){{clearInterval(iv);return}}left-=1;if(left>0){{updSecs.textContent=left;ringSet(left/5)}}else{{clearInterval(iv);location.reload()}}}},1000)}}
async function updWatch(){{const my=updRun,startedAt=Date.now();let down=false;updClock=setInterval(()=>{{if(my!==updRun)return;const s=Math.floor((Date.now()-startedAt)/1000);updSecs.textContent=Math.floor(s/60)+':'+String(s%60).padStart(2,'0')}},500);for(let i=0;i<450;i++){{await sleep(2000);if(my!==updRun)return;let d=null;try{{const r=await fetch('{esc(path)}/update-status',{{cache:'no-store'}});if(r.ok)d=await r.json()}}catch(e){{}}if(my!==updRun)return;if(!d){{if(!down){{down=true;updCard.classList.add('spin','time');updTitle.textContent='Панель перезапускается';updText.textContent='Обновление устанавливается. Ждём, когда панель вернётся…'}}continue}}if(down&&['queued','running'].includes(d.phase)){{down=false;if(d.message)updText.textContent=d.message;continue}}if(['queued','running'].includes(d.phase)){{if(d.message)updText.textContent=d.message;continue}}clearInterval(updClock);if(d.phase==='done'){{updShow('done');updReloadCountdown()}}else{{updShow('failed',null,d.message)}}return}}updShow('failed',null,'Обновление слишком долго не отвечает. Проверьте статус через SSH.')}}
panelButton.addEventListener('click',()=>{{const target=panelSelect.value;if(!target)return;updActive=true;updShow('confirm',target)}});
updGo.addEventListener('click',async()=>{{if(updGo.dataset.mode==='close'){{updHide();updActive=false;loadPanel(true);return}}const target=panelSelect.value;updGo.disabled=true;try{{panelView(await request('update-start',{{target}},panelStatus));updShow('running');updWatch()}}catch(e){{updShow('failed',null,e.message)}}finally{{updGo.disabled=false}}}});
updCancel.addEventListener('click',()=>{{updHide();updActive=false}});
document.querySelectorAll('[data-component-install]').forEach(button=>button.addEventListener('click',async()=>{{const component=button.dataset.componentInstall,target=document.getElementById(component+'Release').value;if(!(await onyxConfirm('Установить '+component+' '+target+'? При ошибке будет выполнен автоматический откат.',{{title:'Обновление компонента',ok:'Установить'}})))return;button.disabled=true;try{{componentView(await request('component-install',{{component,target}},componentStatus))}}catch(e){{componentStatus.textContent=e.message;button.disabled=false}}}}));
loadPanel().then(()=>{{if(panelBusy&&!updActive){{updActive=true;updShow('running');updWatch()}}}});loadComponents();setInterval(()=>{{loadPanel();loadComponents()}},5000);
</script>'''
