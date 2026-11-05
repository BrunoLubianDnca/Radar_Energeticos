#!/usr/bin/env python3
"""Monitor de páginas de produto Monster 473 ml. Sem APIs pagas.

Usa apenas preços explicitamente associados ao produto na página. Não adivinha
preços em páginas bloqueadas ou listagens multiloja sem oferta inequívoca.
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import smtplib
import ssl
import sys
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; MonsterOfferMonitor/1.0; +https://github.com)", "Accept-Language": "pt-BR,pt;q=0.9"})
CURRENCY_RE = re.compile(r"R\$\s*([\d.]+,\d{2})", re.I)
PACK_RE = re.compile(r"(?:kit|pack|fardo|caixa|combo|c\/|com)\s*(?:de\s*)?(6|12|24)\s*(?:latas|unidades|un|und)?", re.I)
PRICE_KEYS = ("price", "lowPrice", "salePrice")


def amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        s = str(value).strip().replace('R$', '').replace('\xa0', '').strip()
        if ',' in s:
            s = s.replace('.', '').replace(',', '.')
        elif s.count('.') > 1:
            s = s.replace('.', '')
        d = Decimal(s)
        return d if Decimal('0') < d < Decimal('20000') else None
    except (InvalidOperation, ValueError):
        return None


def units(text):
    match = PACK_RE.search(text or '')
    return int(match.group(1)) if match else 1


def valid_monster(text):
    t = re.sub(r'\s+', ' ', text or '').lower()
    return bool(re.search(r'\bmonster\b', t) and re.search(r'\b473\s*ml\b', t))


def walk_jsonld(node):
    if isinstance(node, list):
        for child in node:
            yield from walk_jsonld(child)
    elif isinstance(node, dict):
        yield node
        if '@graph' in node:
            yield from walk_jsonld(node['@graph'])


def get_offer_prices(offers):
    if isinstance(offers, list):
        for item in offers:
            yield from get_offer_prices(item)
    elif isinstance(offers, dict):
        typ = str(offers.get('@type', '')).lower()
        if 'aggregateoffer' in typ:  # lowPrice pode agregar outras lojas/embalagens
            return
        currency = offers.get('priceCurrency')
        if currency and str(currency).upper() != 'BRL':
            return
        for k in PRICE_KEYS:
            if offers.get(k) is not None:
                a = amount(offers[k])
                if a:
                    yield a
                    return
        if isinstance(offers.get('priceSpecification'), dict):
            yield from get_offer_prices(offers['priceSpecification'])


def extract(page, src):
    soup = BeautifulSoup(page, 'html.parser')
    candidates = []
    for script in soup.find_all('script', type=re.compile(r'application/ld\+json', re.I)):
        try:
            obj = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        for node in walk_jsonld(obj):
            if 'product' not in str(node.get('@type', '')).lower():
                continue
            name = str(node.get('name', ''))
            if not valid_monster(name):
                continue
            prices = list(get_offer_prices(node.get('offers')))
            if not prices:
                continue
            image = node.get('image', '')
            if isinstance(image, list):
                image = image[0] if image else ''
            if isinstance(image, dict):
                image = image.get('url', '')
            candidates.append((name, min(prices), str(image or '')))

    # Meta product:price:amount só é aceitável se título da página é do produto.
    if not candidates:
        title = ((soup.find('h1') or soup.find('title')) or '').get_text(' ', strip=True) if (soup.find('h1') or soup.find('title')) else ''
        if valid_monster(title):
            meta = soup.find('meta', attrs={'property': 'product:price:amount'})
            currency = soup.find('meta', attrs={'property': 'product:price:currency'})
            if meta and (not currency or currency.get('content', 'BRL').upper() == 'BRL'):
                a = amount(meta.get('content'))
                if a:
                    pic = soup.find('meta', attrs={'property': 'og:image'})
                    candidates.append((title, a, pic.get('content', '') if pic else ''))

    if len(candidates) != 1:
        raise ValueError(f'Oferta inequívoca não encontrada (produtos com preço: {len(candidates)})')
    name, price, pic = candidates[0]
    quantity = units(name)
    unit_price = (price / quantity).quantize(Decimal('0.01'))
    if quantity not in (1, 6, 12, 24):
        raise ValueError('Embalagem não permitida')
    return {
        'id': src['store'] + '|' + src['url'], 'store': src['store'],
        'name': name, 'url': src['url'], 'image': pic,
        'pack': quantity, 'price': float(price), 'unit_price': float(unit_price),
        'shipping_sc': src.get('shipping_sc', 'não verificado'),
        'region': src.get('region', 'BR')
    }


def fetch(src, timeout):
    url = src['url']
    if urlparse(url).scheme != 'https':
        raise ValueError('Somente URLs HTTPS')
    res = SESSION.get(url, timeout=timeout)
    res.raise_for_status()
    if len(res.content) > 2_000_000:
        raise ValueError('Página grande demais')
    return extract(res.text, src)


def brl(value):
    return 'R$ ' + f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def render_email(offers, checked_at):
    rows = []
    for o in offers:
        discount = o.get('discount_pct')
        badge = 'SUPEROFERTA' if o['unit_price'] < 6.5 else 'OFERTA'
        pic = o.get('image') or ''
        # Evita injeção HTML em strings de lojas e produtos.
        photo = f'<img src="{html.escape(pic, quote=True)}" width="82" style="max-width:82px;border-radius:10px" alt="Lata Monster">' if pic.startswith('https://') else '<span style="color:#999">Monster 473 ml</span>'
        line = (f'<b>{html.escape(o["name"])}</b><br><span style="color:#666">{html.escape(o["store"])} · {o["pack"]} lata(s)</span><br>'
                f'<span style="font-size:23px;color:#166534;font-weight:800">{brl(o["unit_price"])}/lata</span><br>'
                f'<span>Preço total: {brl(o["price"])}</span><br>'
                f'<small>Envio para SC: {html.escape(o["shipping_sc"])}</small>')
        if discount is not None:
            line += f'<br><small>Queda desde último preço medido: {discount:.0f}%</small>'
        rows.append(f'<tr><td style="padding:17px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top">{photo}</td>'
                    f'<td style="padding:17px 10px;border-bottom:1px solid #e5e7eb">'
                    f'<div style="font-size:11px;letter-spacing:1px;color:#666">{badge}</div>{line}<br>'
                    f'<a href="{html.escape(o["url"], quote=True)}" style="display:inline-block;background:#111827;color:white;padding:10px 15px;text-decoration:none;border-radius:7px;margin-top:10px">Ver oferta</a></td></tr>')
    return ('<!doctype html><html><body style="margin:0;background:#f3f4f6;font-family:Arial,sans-serif;color:#111827">'
            '<div style="max-width:650px;margin:20px auto;background:white;border-radius:15px;overflow:hidden">'
            '<div style="padding:24px;background:#111827;color:white"><h1 style="margin:0;font-size:25px">Monster Radar</h1>'
            '<p style="margin:7px 0 0;color:#d1d5db">Ofertas de Monster Energy 473 ml</p></div>'
            f'<div style="padding:12px 22px"><p><b>{len(offers)} oferta(s)</b> abaixo do limite configurado.</p>'
            '<table cellspacing="0" cellpadding="0" width="100%">' + ''.join(rows) + '</table>'
            f'<p style="color:#6b7280;font-size:12px">Verificado em {html.escape(checked_at)}. Preço, frete e estoque devem ser confirmados na loja. Comparação considera preço por lata e não inclui frete.</p>'
            '</div></div></body></html>')


def mail(offers, checked_at, preview=False):
    content = render_email(offers, checked_at)
    if preview:
        (ROOT / 'preview.html').write_text(content, encoding='utf-8')
        return
    email = os.environ.get('EMAIL_TO')
    username = os.environ.get('SMTP_USER')
    password = os.environ.get('SMTP_PASSWORD')
    if not (email and username and password):
        raise RuntimeError('Faltam secrets EMAIL_TO, SMTP_USER, SMTP_PASSWORD')
    host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    port = int(os.environ.get('SMTP_PORT', '465'))
    msg = EmailMessage()
    msg['From'] = username
    msg['To'] = email
    msg['Subject'] = f'Monster Radar | {len(offers)} oferta(s) abaixo de R$ 8'
    msg.set_content('\n'.join(f'{x["name"]} | {brl(x["unit_price"])}/lata | {x["url"]}' for x in offers))
    msg.add_alternative(content, subtype='html')
    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=25) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)


def run(args):
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    sources = json.loads((ROOT / 'sources.json').read_text(encoding='utf-8'))
    path = ROOT / config['state_file']
    before = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'items': {}}
    items = dict(before.get('items', {}))
    checked_at = dt.datetime.now(dt.timezone(dt.timedelta(hours=-3))).isoformat(timespec='seconds')
    found, errors = [], []
    for s in sources:
        try:
            p = fetch(s, config['timeout_seconds'])
            found.append(p)
            print(f'OK {s["store"]}: {brl(p["unit_price"])}/lata')
        except (requests.RequestException, ValueError, KeyError) as exc:
            errors.append({'store': s.get('store', '?'), 'error': str(exc)[:250]})
            print(f'WARN {s.get("store")}: {exc}')
    report = {'checked_at': checked_at, 'success': len(found), 'failed': len(errors), 'errors': errors,
              'offers': sorted(found, key=lambda p: p['unit_price'])}
    if not args.dry_run:
        report_path = ROOT / config['report_file']
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if len(found) < config['min_sources_succeeded']:
        print('ERRO: nenhuma fonte válida. Histórico mantido; não envia e-mail.', file=sys.stderr)
        return 2
    alerts = []
    for p in found:
        old = items.get(p['id'])
        if old and old.get('unit_price') and p['unit_price'] < old['unit_price']:
            p['discount_pct'] = round((1 - p['unit_price'] / old['unit_price']) * 100, 1)
        if p['unit_price'] < config['price_alert_brl']:
            if not old and config.get('alert_on_first_seen', True):
                alerts.append(p)
            elif old and p['unit_price'] < old['unit_price']:
                alerts.append(p)
        items[p['id']] = {'unit_price': p['unit_price'], 'price': p['price'], 'last_seen': checked_at,
                          'name': p['name'], 'store': p['store']}
    alerts = sorted(alerts, key=lambda p: p['unit_price'])[:config['max_per_email']]
    print(f'Fontes válidas: {len(found)}; alertas novos: {len(alerts)}')
    if args.preview:
        # Demonstração de layout usando dados fictícios, sem enviar.
        demo = [{'name': 'Monster Mango Loco 473 ml', 'store': 'LOJA FICTÍCIA', 'pack': 1,
                 'price': 5.99, 'unit_price': 5.99, 'url': 'https://example.com',
                 'image': '', 'shipping_sc': 'a confirmar', 'discount_pct': 40}]
        mail(demo, checked_at, preview=True)
        print('preview.html criado (DADOS FICTÍCIOS)')
    if args.dry_run:
        print('DRY RUN: sem atualizar histórico e sem disparar e-mail')
        return 0
    # Importante: atualiza o histórico apenas após o envio bem-sucedido.
    if alerts and not args.no_email:
        mail(alerts, checked_at)
        print('E-mail enviado por SMTP')
    elif args.no_email:
        print('Modo --no-email: histórico atualizado sem envio')
    else:
        print('Sem novos descontos: e-mail não enviado')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'items': items}, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Consulta sem gravar ou mandar e-mail')
    parser.add_argument('--no-email', action='store_true', help='Atualiza histórico sem enviar')
    parser.add_argument('--preview', action='store_true', help='Cria preview.html com valores fictícios')
    args = parser.parse_args()
    try:
        sys.exit(run(args))
    except (RuntimeError, smtplib.SMTPException, OSError) as exc:
        print(f'ERRO: {exc}', file=sys.stderr)
        sys.exit(1)
