import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sync


PHONE = '13000000000'
DIGEST = 'a' * 32


def item(identifier=1, **changes):
    row = {'id': identifier, 'name': '测试成员', 'status': 1,
           'remain_quota': 19992, 'used_quota': 8, 'unlimited_quota': False,
           'key': 'sk-DO-NOT-PUBLISH', 'session': 'PRIVATE-SESSION', 'ChatMoney': 9000}
    row.update(changes)
    return row


def source(items):
    def request(path, session, params=None):
        if path.endswith('get_app_configs'):
            return {'DollarRate': 1, 'QuotaPerDollar': 100}
        offset = (params['page'] - 1) * 100
        return {'items': items[offset:offset + 100], 'total': len(items)}
    return request


class SnapshotTests(unittest.TestCase):
    def test_login_passes_only_expected_form_fields(self):
        post = Mock(return_value='session-value')
        self.assertEqual(sync.login(PHONE, DIGEST, post), 'session-value')
        self.assertEqual(post.call_args.args, ('/api/login', {
            'phone': PHONE, 'password': DIGEST, 'registerSite': 'gpu', 'session': '',
        }))

    def test_converts_amounts_and_strips_private_fields(self):
        data = sync.fetch_snapshot('PRIVATE-SESSION', source([item()]))
        self.assertEqual(data['rows'], [{'name': '测试成员', 'remaining': '199.92',
            'used': '0.08', 'total': '200.00', 'unlimited': False, 'status': '启用'}])
        self.assertEqual(data['sync_interval_seconds'], 600)
        output = json.dumps(data)
        for secret in ['sk-DO-NOT-PUBLISH', 'PRIVATE-SESSION', 'ChatMoney', DIGEST]:
            self.assertNotIn(secret, output)

    def test_multiple_pages_are_complete(self):
        data = sync.fetch_snapshot('session', source([item(i) for i in range(212)]))
        self.assertEqual(len(data['rows']), 212)

    def test_repeated_or_missing_pages_are_rejected(self):
        def broken(path, session, params=None):
            if path.endswith('get_app_configs'):
                return {'DollarRate': 1, 'QuotaPerDollar': 100}
            return {'items': [item(i) for i in range(100)], 'total': 150}
        with self.assertRaises(sync.SyncError):
            sync.fetch_snapshot('session', broken)

    def test_invalid_amount_does_not_publish_zero(self):
        for value in (None, 'NaN', 'Infinity'):
            with self.subTest(value=value), self.assertRaises(sync.SyncError):
                sync.fetch_snapshot('session', source([item(remain_quota=value)]))

    def test_unlimited_key_retains_used_amount(self):
        row = sync.fetch_snapshot('session', source([item(unlimited_quota=True)]))['rows'][0]
        self.assertIsNone(row['remaining'])
        self.assertIsNone(row['total'])
        self.assertEqual(row['used'], '0.08')

    def test_failure_leaves_previous_published_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            previous = {'rows': [{'name': 'previous'}], 'updated_at': 'earlier'}
            sync.publish(previous, path)
            with patch.dict(os.environ, {'GALAXY_PHONE': PHONE, 'GALAXY_PASSWORD_MD5': DIGEST}):
                with patch.object(sync, 'login', return_value='session'):
                    with patch.object(sync, 'fetch_snapshot', side_effect=sync.SyncError('network_error')):
                        with patch.object(sync, 'publish') as publish:
                            self.assertEqual(sync.main(), 1)
                            publish.assert_not_called()
            self.assertEqual(json.loads(path.read_text()), previous)

    def test_verification_pauses_workflow_without_leaking_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'job-output.txt'
            output.touch()
            with patch.dict(os.environ, {'GALAXY_PHONE': PHONE,
                         'GALAXY_PASSWORD_MD5': DIGEST, 'GITHUB_OUTPUT': str(output)}):
                with patch.object(sync, 'login', side_effect=sync.SyncError('verification_required')):
                    self.assertEqual(sync.main(), 1)
            self.assertEqual(output.read_text(), 'auth_blocked=true\n')

    def test_static_assets_work_under_repository_subpath(self):
        html = (sync.SITE / 'index.html').read_text()
        script = (sync.SITE / 'app.js').read_text()
        self.assertIn('href="./style.css"', html)
        self.assertIn('src="./app.js"', html)
        self.assertIn("fetch('./usage.json'", script)
        self.assertNotIn("fetch('/api/usage'", script)


if __name__ == '__main__':
    unittest.main()
