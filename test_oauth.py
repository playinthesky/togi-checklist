"""togi-checklist 소셜 로그인 단위 테스트 (네트워크/DB 격리).

실행: python -m unittest test_oauth
"""

import os
import tempfile
import unittest
from unittest import mock
from urllib.parse import urlparse, parse_qs

import oauth_providers as op


class ProviderConfigTest(unittest.TestCase):
    def test_enabled_only_with_credentials(self):
        env = {"GOOGLE_CLIENT_ID": "g", "GOOGLE_CLIENT_SECRET": "s", "KAKAO_CLIENT_ID": "k"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual({p.key for p in op.enabled_providers()}, {"google", "kakao"})

    def test_google_requires_secret(self):
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "g"}, clear=True):
            self.assertFalse(op.get_provider("google").configured)

    def test_order(self):
        env = {"GOOGLE_CLIENT_ID": "g", "GOOGLE_CLIENT_SECRET": "s",
               "KAKAO_CLIENT_ID": "k", "NAVER_CLIENT_ID": "n", "NAVER_CLIENT_SECRET": "s"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual([p.key for p in op.enabled_providers()], ["kakao", "google", "naver"])

    def test_authorize_url(self):
        with mock.patch.dict(os.environ, {"NAVER_CLIENT_ID": "n", "NAVER_CLIENT_SECRET": "s"}, clear=True):
            p = op.get_provider("naver")
            url = op.build_authorize_url(p, "https://x/auth/callback/naver", "st")
        qs = parse_qs(urlparse(url).query)
        self.assertEqual(qs["client_id"], ["n"])
        self.assertEqual(qs["redirect_uri"], ["https://x/auth/callback/naver"])
        self.assertEqual(qs["state"], ["st"])
        self.assertEqual(qs["response_type"], ["code"])

    def test_profile_parsing(self):
        with mock.patch.dict(os.environ, {"KAKAO_CLIENT_ID": "k"}, clear=True):
            out = op.get_provider("kakao").parse_profile(
                {"id": 7, "kakao_account": {"email": "A@B.com", "profile": {"nickname": "카"}}})
        self.assertEqual(out["provider"], "kakao")
        self.assertEqual(out["provider_uid"], "7")
        self.assertEqual(out["email"], "a@b.com")
        self.assertEqual(out["name"], "카")


class SocialStaffTest(unittest.TestCase):
    def setUp(self):
        # 임시 sqlite DB로 격리
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        import server
        self.server = server
        self._orig_path = server.DB_PATH
        server.DB_PATH = self.tmp.name
        server.init_db()

    def tearDown(self):
        self.server.DB_PATH = self._orig_path
        os.unlink(self.tmp.name)

    def test_create_then_match_by_uid(self):
        prof = {"provider": "google", "provider_uid": "u1", "email": "x@y.com", "name": "신규"}
        user, created = self.server.find_or_create_social_staff(prof)
        self.assertTrue(created)
        self.assertEqual(user["name"], "신규")
        self.assertEqual(user["role"], "staff")
        # 두 번째는 신규 아님
        user2, created2 = self.server.find_or_create_social_staff(prof)
        self.assertFalse(created2)
        self.assertEqual(user2["id"], user["id"])

    def test_link_by_email(self):
        # provider_uid는 다르지만 이메일이 같으면 기존 계정에 연결
        a, _ = self.server.find_or_create_social_staff(
            {"provider": "google", "provider_uid": "g9", "email": "same@x.com", "name": "갑"})
        b, created = self.server.find_or_create_social_staff(
            {"provider": "kakao", "provider_uid": "k9", "email": "same@x.com", "name": "갑"})
        self.assertFalse(created)
        self.assertEqual(a["id"], b["id"])

    def test_new_social_id_does_not_collide_with_seed(self):
        # 시드(0~8) 이후 새 id가 부여되는지
        user, _ = self.server.find_or_create_social_staff(
            {"provider": "naver", "provider_uid": "n1", "email": "", "name": "무이메일"})
        self.assertGreater(user["id"], 8)


if __name__ == "__main__":
    unittest.main()
