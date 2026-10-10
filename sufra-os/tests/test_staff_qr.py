"""Run with python -m unittest discover -s tests. Uses a temporary database only."""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, create_engine, select
from app import permissions
from app.models import Staff, Role, AuthSession, StaffQR, AuditLog
from app.enterprise_models import HRProfile
from app.routers import auth_api, enterprise
from app.security import hash_pin, session_expiry, verify_pin


class StaffAccessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + self.tmp.name + '/test.db', connect_args={'check_same_thread': False})
        SQLModel.metadata.create_all(self.engine)
        self.patches = [patch.object(m, 'engine', self.engine) for m in (permissions, auth_api, enterprise)]
        self.patches.append(patch.dict(os.environ, {'SUFRA_STAFF_QR_KEY': Fernet.generate_key().decode(), 'SUFRA_PUBLIC_URL': 'https://restaurant.test'}))
        for p in self.patches: p.start()
        self.app = FastAPI()
        self.app.include_router(auth_api.router)
        self.app.include_router(enterprise.router)
        self.client = TestClient(self.app)
        with Session(self.engine) as s:
            admin = Staff(name='Manager', role=Role.OWNER, pin_hash=hash_pin('1234'))
            s.add(admin); s.commit(); s.refresh(admin)
            self.admin_id = admin.id
            s.add(AuthSession(token='admin-test', staff_id=admin.id, expires_at=session_expiry()))
            s.commit()
        self.headers = {'Authorization': 'Bearer admin-test'}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches): p.stop()
        self.engine.dispose()
        self.tmp.cleanup()

    def provision(self):
        r = self.client.post('/api/enterprise/hr/staff', headers=self.headers, json={'name': 'Waiter', 'role': 'waiter'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.headers['cache-control'], 'no-store')
        data = r.json()
        data['qr_token'] = parse_qs(urlparse(data['qr_url']).fragment)['staff_qr'][0]
        return data

    def login(self, data, **overrides):
        return self.client.post('/api/auth/login', json={'staff_id': data['staff_id'], 'qr_token': data['qr_token'], 'pin': data['temporary_pin'], **overrides})

    def test_create_scan_login_and_no_credential_leaks(self):
        d = self.provision()
        self.assertEqual(len(d['temporary_pin']), 4)
        self.assertTrue(d['qr_image'].startswith('data:image/png;base64,'))
        r = self.client.post('/api/auth/qr/identify', json={'qr_token': d['qr_token']})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('token', r.json())
        self.assertEqual(self.login(d).status_code, 200)
        with Session(self.engine) as s:
            person = s.get(Staff, d['staff_id'])
            self.assertNotEqual(person.pin_hash, d['temporary_pin'])
            self.assertTrue(verify_pin(d['temporary_pin'], person.pin_hash))
            self.assertNotEqual(s.get(StaffQR, person.id).token_hash, d['qr_token'])
            for log in s.exec(select(AuditLog)).all():
                self.assertNotIn(d['qr_token'], log.detail)
        public = self.client.get('/api/auth/roster').text
        self.assertNotIn(d['temporary_pin'], public)
        self.assertNotIn(d['qr_token'], public)

    def test_pin_or_qr_login_and_tampering_rejected(self):
        d = self.provision()
        self.assertEqual(self.client.post('/api/auth/login', json={'staff_id': d['staff_id'], 'pin': d['temporary_pin']}).status_code, 200)
        self.assertEqual(self.login(d, qr_token=d['qr_token'][:-8]+'AAAAAAAA').status_code, 401)
        self.assertEqual(self.login(d, pin=('0000' if d['temporary_pin'] != '0000' else '9999')).status_code, 401)
        self.assertEqual(self.client.post('/api/enterprise/biometric/auth/verify', json={'staff_id': d['staff_id']}).status_code, 401)

    def test_rotation_revokes_badge_pin_and_sessions(self):
        d = self.provision()
        token = self.login(d).json()['token']
        r = self.client.post(f"/api/enterprise/hr/staff/{d['staff_id']}/credentials", headers=self.headers, json={})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.login(d).status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization':'Bearer '+token}).status_code, 401)
        n = r.json(); n['qr_token'] = parse_qs(urlparse(n['qr_url']).fragment)['staff_qr'][0]
        self.assertEqual(self.login(n).status_code, 200)

    def test_lockout_and_reset(self):
        d = self.provision()
        for _ in range(4): self.assertEqual(self.login(d, pin=('0000' if d['temporary_pin'] != '0000' else '9999')).status_code, 401)
        self.assertEqual(self.login(d, pin=('0000' if d['temporary_pin'] != '0000' else '9999')).status_code, 429)
        self.assertEqual(self.login(d).status_code, 429)
        r = self.client.post('/api/enterprise/security/pin/reset', headers=self.headers, json={'staff_id': d['staff_id']})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.login(d, pin=r.json()['temporary_pin']).status_code, 200)

    def test_idle_expiry_and_polling_does_not_extend_activity(self):
        d = self.provision(); token = self.login(d).json()['token']; headers = {'Authorization':'Bearer '+token}
        with Session(self.engine) as s:
            sess = s.get(AuthSession, token); old = datetime.now()-timedelta(minutes=7)
            sess.last_seen_at = old; s.add(sess); s.commit()
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 200)
        with Session(self.engine) as s: self.assertEqual(s.get(AuthSession,token).last_seen_at,old)
        self.assertEqual(self.client.post('/api/auth/activity', headers=headers).status_code, 200)
        with Session(self.engine) as s:
            sess=s.get(AuthSession,token); sess.last_seen_at=datetime.now()-timedelta(minutes=9); s.add(sess); s.commit()
        self.assertEqual(self.client.post('/api/auth/activity', headers=headers).status_code, 401)
        self.assertEqual(self.client.get('/api/auth/me', headers=headers).status_code, 401)

    def test_permissions_and_inactive_accounts(self):
        d=self.provision(); token=self.login(d).json()['token']
        r=self.client.post(f"/api/enterprise/hr/staff/{d['staff_id']}/credentials", headers={'Authorization':'Bearer '+token}, json={})
        self.assertEqual(r.status_code,403)
        r=self.client.post(f"/api/enterprise/hr/staff/{d['staff_id']}/credentials", json={})
        self.assertEqual(r.status_code,401)
        self.client.post(f"/api/enterprise/hr/staff/{d['staff_id']}/profile", headers=self.headers, json={'status':'suspended'})
        self.assertEqual(self.login(d).status_code,403)
        self.assertEqual(self.login(d, qr_token=None).status_code,403)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization':'Bearer '+token}).status_code,401)

    def test_removal_restore_needs_new_badge(self):
        d = self.provision()
        path = f"/api/enterprise/hr/staff/{d['staff_id']}"
        self.assertEqual(self.client.post(path+'/remove', headers=self.headers, json={}).status_code, 200)
        self.assertEqual(self.client.post(path+'/restore', headers=self.headers, json={}).status_code, 200)
        self.assertEqual(self.login(d).status_code, 401)
        self.assertEqual(self.client.post('/api/auth/login', json={'staff_id':d['staff_id'], 'pin':d['temporary_pin']}).status_code, 200)

    def test_reset_revokes_sessions_but_keeps_badge(self):
        d = self.provision()
        token = self.login(d).json()['token']
        r = self.client.post('/api/enterprise/security/pin/reset', headers=self.headers, json={'staff_id':d['staff_id']})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me', headers={'Authorization':'Bearer '+token}).status_code, 401)
        self.assertEqual(self.login(d, pin=r.json()['temporary_pin']).status_code, 200)

    def test_failed_provisioning_rolls_back_employee(self):
        with patch('app.staff_access.cipher', side_effect=ValueError('Invalid test key')):
            with self.assertRaises(ValueError):
                self.client.post('/api/enterprise/hr/staff', headers=self.headers, json={'name':'Must roll back'})
        with Session(self.engine) as s:
            self.assertIsNone(s.exec(select(Staff).where(Staff.name == 'Must roll back')).first())

    def test_four_digit_limit_and_admin_badge_without_pin_reset(self):
        for pin in ['12345','123456','abc1','１２３４']:
            self.assertEqual(self.client.post('/api/auth/login',json={'staff_id':self.admin_id,'pin':pin}).status_code,400)
        d=self.provision()
        path=f"/api/enterprise/hr/staff/{d['staff_id']}/badge"
        token=self.login(d).json()['token']
        waiter_headers={'Authorization':'Bearer '+token}
        self.assertEqual(self.client.post(path,headers=waiter_headers,json={}).status_code,403)
        self.assertEqual(self.client.get(path,headers=waiter_headers).status_code,403)
        r=self.client.post(path,headers=self.headers,json={})
        self.assertEqual(r.status_code,200,r.text)
        self.assertNotIn('temporary_pin',r.json())
        self.assertEqual(self.client.get(path,headers=self.headers).json()['qr_url'],r.json()['qr_url'])
        new=r.json();new['temporary_pin']=d['temporary_pin'];new['qr_token']=parse_qs(urlparse(new['qr_url']).fragment)['staff_qr'][0]
        self.assertEqual(self.login(new).status_code,200)
        self.assertEqual(self.login(new, qr_token=None).status_code,200)
        self.assertEqual(self.login(d).status_code,401)

    def test_self_regeneration_preserves_only_issuing_admin_session(self):
        with Session(self.engine) as s:
            s.add(AuthSession(token='other-admin',staff_id=self.admin_id,expires_at=session_expiry()));s.commit()
        path=f'/api/enterprise/hr/staff/{self.admin_id}/badge'
        for _ in range(2):
            r=self.client.post(path,headers=self.headers,json={})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(self.client.get('/api/auth/me',headers=self.headers).status_code,200)
        self.assertEqual(self.client.get('/api/auth/me',headers={'Authorization':'Bearer other-admin'}).status_code,401)

    def test_local_qr_uses_reachable_waiter_address(self):
        from starlette.requests import Request
        from app.staff_access import staff_base_url
        req=Request({'type':'http','scheme':'http','server':('127.0.0.1',8123),'path':'/','root_path':'','headers':[],'query_string':b''})
        with patch.dict(os.environ,{'SUFRA_STAFF_URL':'','SUFRA_PUBLIC_URL':''}), patch('app.staff_access.local_staff_host',return_value='192.168.1.20'):
            self.assertEqual(staff_base_url(req),'http://192.168.1.20:8123')
        d=self.provision()
        self.assertEqual(urlparse(d['qr_url']).path,'/waiter')
        self.assertEqual(d['app_path'],'/waiter')

    def test_pin_login_without_badge(self):
        r=self.client.post('/api/auth/login',json={'staff_id':self.admin_id,'pin':'1234'})
        self.assertEqual(r.status_code,200)


if __name__ == '__main__': unittest.main()
