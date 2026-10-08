"""Build a public quota snapshot for GitHub Pages in one Actions run."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

ORIGIN = 'https://gpu.ai-galaxy.com'
READ_PATHS = {'/api/deepai/get_app_configs', '/api/deepai/get_key_list'}
MAX_RESPONSE = 8 * 1024 * 1024
SYNC_INTERVAL_SECONDS = 600
SITE = Path(__file__).resolve().parent / 'site'


class SyncError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_form(path, data):
    if path not in READ_PATHS | {'/api/login'}:
        raise ValueError('Endpoint is not allowed')
    request = urllib.request.Request(ORIGIN + path,
        data=urllib.parse.urlencode(data).encode(), method='POST', headers={
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
            'Accept': 'application/json', 'Origin': ORIGIN,
            'Referer': ORIGIN + ('/login' if path == '/api/login' else '/modelBusiness/key'),
            'User-Agent': 'TeamBalancePanel/1.0',
        })
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except urllib.error.HTTPError as error:
        if error.code == 429 or error.code >= 500:
            raise SyncError('upstream_unavailable') from None
        if error.code == 401 and path != '/api/login':
            raise SyncError('auth_required') from None
        raise SyncError('login_rejected' if path == '/api/login' else 'upstream_error') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SyncError('network_error') from None
    if len(raw) > MAX_RESPONSE:
        raise SyncError('invalid_data')
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise SyncError('invalid_data') from None
    if not isinstance(result, dict):
        raise SyncError('invalid_data')
    if result.get('status') != 0:
        reason = str(result.get('reason', '')).lower()
        if path == '/api/login':
            verification = any(word in reason for word in ('验证码', '验证', 'captcha', 'verify'))
            raise SyncError('verification_required' if verification else 'login_rejected')
        expired = result.get('status') == 2 or '获取token失败' in reason
        raise SyncError('auth_required' if expired else 'upstream_error')
    return result.get('data')


def login(phone, password_md5, post_fn=post_form):
    if (not re.fullmatch(r'[0-9]{11}', phone or '')
            or not re.fullmatch(r'[0-9a-f]{32}', password_md5 or '')):
        raise SyncError('auth_config_error')
    session = post_fn('/api/login', {
        'phone': phone, 'password': password_md5, 'registerSite': 'gpu', 'session': '',
    })
    if not isinstance(session, str) or not session.strip() or any(c.isspace() for c in session.strip()):
        raise SyncError('login_rejected')
    return session.strip()


def api_request(path, session, params=None, post_fn=post_form):
    if path not in READ_PATHS:
        raise ValueError('Only quota read endpoints are allowed')
    return post_fn(path, {**(params or {}), 'session': session})


def number(value):
    if isinstance(value, bool) or value is None:
        raise SyncError('invalid_data')
    try:
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal('1e24'):
            raise SyncError('invalid_data')
        return result
    except (InvalidOperation, ValueError):
        raise SyncError('invalid_data') from None


def money(quota, rate, per_dollar):
    amount = (number(quota) / per_dollar * rate).quantize(Decimal('.0001'), rounding=ROUND_HALF_UP)
    return format(amount.quantize(Decimal('.01'), rounding=ROUND_HALF_UP), '.2f')


def normalize_row(row, rate, per_dollar):
    if not isinstance(row, dict) or not isinstance(row.get('name'), str):
        raise SyncError('invalid_data')
    unlimited = row.get('unlimited_quota', False)
    if type(unlimited) not in (bool, int) or unlimited not in (True, False, 0, 1):
        raise SyncError('invalid_data')
    used = number(row.get('used_quota'))
    remain = number(row.get('remain_quota'))
    statuses = {0: '启用', 1: '启用', 2: '禁用', 3: '已过期', 4: '额度耗尽', -1: '禁用'}
    return {
        'name': row['name'][:200],
        'remaining': None if unlimited else money(remain, rate, per_dollar),
        'used': money(used, rate, per_dollar),
        'total': None if unlimited else money(remain + used, rate, per_dollar),
        'unlimited': bool(unlimited),
        'status': statuses.get(row.get('status'), '未知'),
    }


def fetch_snapshot(session, request_fn=api_request):
    config = request_fn('/api/deepai/get_app_configs', session)
    if not isinstance(config, dict):
        raise SyncError('invalid_data')
    rate, per_dollar = number(config.get('DollarRate')), number(config.get('QuotaPerDollar'))
    if rate <= 0 or per_dollar <= 0:
        raise SyncError('invalid_data')
    rows, seen, expected_total = [], set(), None
    for page in range(1, 101):
        data = request_fn('/api/deepai/get_key_list', session, {'page': page, 'page_size': 100})
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise SyncError('invalid_data')
        total = data.get('total')
        if total is not None:
            if type(total) is not int or total < 0:
                raise SyncError('invalid_data')
            if expected_total is not None and expected_total != total:
                raise SyncError('incomplete_data')
            expected_total = total
        for item in data['items']:
            if not isinstance(item, dict) or type(item.get('id')) not in (int, str):
                raise SyncError('invalid_data')
            identity = str(item['id'])
            if identity in seen:
                raise SyncError('incomplete_data')
            seen.add(identity)
            rows.append(normalize_row(item, rate, per_dollar))
        if expected_total is not None and len(rows) == expected_total:
            break
        if expected_total is not None and (len(rows) > expected_total or not data['items']):
            raise SyncError('incomplete_data')
        if expected_total is None and len(data['items']) < 100:
            break
    else:
        raise SyncError('incomplete_data')
    return {'rows': rows, 'updated_at': datetime.now(timezone.utc).isoformat(),
            'sync_interval_seconds': SYNC_INTERVAL_SECONDS}


def publish(snapshot, path=SITE / 'usage.json'):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='usage-', suffix='.tmp', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            json.dump(snapshot, output, ensure_ascii=False, separators=(',', ':'))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    try:
        session = login(os.environ.get('GALAXY_PHONE'), os.environ.get('GALAXY_PASSWORD_MD5'))
        snapshot = fetch_snapshot(session)
        publish(snapshot)
    except SyncError as error:
        if error.code in ('verification_required', 'login_rejected'):
            output = os.environ.get('GITHUB_OUTPUT')
            if output:
                with open(output, 'a', encoding='utf-8') as stream:
                    stream.write('auth_blocked=true\n')
        print('Sync failed: ' + error.code, file=sys.stderr)
        return 1
    except Exception:
        print('Sync failed: internal_error', file=sys.stderr)
        return 1
    print('Quota snapshot ready; member count:', len(snapshot['rows']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
