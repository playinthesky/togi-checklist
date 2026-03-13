#!/usr/bin/env python3
"""청토지 보수교육 준비 체크리스트 서버"""

import json
import sqlite3
import os
import hashlib
import secrets
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import http.client
import ssl
from urllib.request import urlopen, Request, HTTPRedirectHandler, build_opener
from urllib.error import URLError, HTTPError

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'checklist.db')
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'public')

# Simple session store (in-memory)
sessions = {}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def hash_pin(pin):
    return hashlib.sha256(pin.encode()).hexdigest()

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            region TEXT DEFAULT '',
            role TEXT DEFAULT 'staff',
            pin_hash TEXT NOT NULL,
            contact_name TEXT DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            quantity TEXT,
            usage_detail TEXT,
            note TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            FOREIGN KEY (category_id) REFERENCES categories(id)
        );
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            staff_id INTEGER NOT NULL,
            checked INTEGER DEFAULT 0,
            checked_at TEXT,
            UNIQUE(item_id, staff_id),
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (staff_id) REFERENCES staff(id)
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
    """)
    conn.commit()

    count = conn.execute('SELECT COUNT(*) FROM staff').fetchone()[0]
    if count == 0:
        # Admin: default PIN 0000
        conn.execute(
            "INSERT INTO staff (id, name, region, role, pin_hash) VALUES (0, '관리자', '본부', 'admin', ?)",
            (hash_pin('0000'),)
        )

        # 8 regional staff - default PIN: 0014 (fKF 창립기념일)
        regions = [
            (1, '인천지회', '인천', '0014'),
            (2, '경기지회', '경기', '0014'),
            (3, '경북지회', '경북', '0014'),
            (4, '전북지회', '전북', '0014'),
            (5, '광주지회', '광주', '0014'),
            (6, '부산지회', '부산', '0014'),
            (7, '제주지회', '제주', '0014'),
            (8, '서울지회', '서울', '0014'),
        ]
        for sid, name, region, pin in regions:
            conn.execute(
                "INSERT INTO staff (id, name, region, role, pin_hash) VALUES (?, ?, ?, 'staff', ?)",
                (sid, name, region, hash_pin(pin))
            )

        # Categories & items
        seed_items = [
            ('개인 지급 (1인당)', 1, [
                ('비기너/스타터 워크북', '수강생 전원 (1인 1권)', '실습 전 과정 기록용 (여유분 2~3권 추가)', 1),
                ('필기구 (연필, 지우개, 볼펜)', '수강생 전원', '연필과 지우개, 볼펜 개인 지급', 2),
            ]),
            ('팀 세팅 (테이블당)', 2, [
                ('청토카 팀 보드 세트', '팀당 1세트', 'A3 규격 / First LEAF, 리서치 보드', 1),
                ('요약 포스트잇 세트', '팀당 3세트', '팀당 1세트씩 사용', 2),
                ('요약용 네임펜', '팀당 3~4자루', '포스트잇 요약 작성 전용 (굵은 펜)', 3),
                ('오프닝 스티커 세트', '팀당 1세트', 'D-log 작성시 출발 스티커와 발표자 유형 스티커', 4),
                ('그룹 좌석 배치도', '1부', '3인 1팀 원칙 (4인도 가능, 단 출발 스티커세트 부족할 경우 별도 대처)', 5),
            ]),
            ('본부 관리 (운영 데스크)', 3, [
                ('토벤저스 랜딩 스티커', '수강생 인원수', '완주 크루 전원 배포용 (베스트 크루용 포함)', 1),
                ('출석부 및 좌석 배치도', '1부', '3인 1조 편성 확인 및 출석 체크', 2),
                ('예비 문구류 & 기기', '넉넉히', '연필, 지우개, 여분 볼펜, 대여용 스마트기기', 3),
            ]),
            ('환경 점검 (강의장)', 4, [
                ('줌 연결 노트북', '1대', '반드시 사전 한시간전 연결', 1, 'https://us02web.zoom.us/j/88633538990'),
                ('무선 인터넷 (Wi-Fi)', '사전 테스트 완료', '리서치 동시 접속 대비 안정성 체크', 2),
                ('빔프로젝터 & 음향', '1식', '화면 출력 및 BGM, 타이머 출력용', 3),
                ('안내 배너', '필요시', '필수는 아님', 4),
                ('화살표', '필요시', '필수는 아님', 5),
            ]),
        ]

        for cat_name, cat_order, items in seed_items:
            cur = conn.execute(
                "INSERT INTO categories (name, sort_order) VALUES (?, ?)",
                (cat_name, cat_order)
            )
            cat_id = cur.lastrowid
            for item_data in items:
                item_name, qty, usage, sort = item_data[:4]
                note = item_data[4] if len(item_data) > 4 else ''
                conn.execute(
                    "INSERT INTO items (category_id, name, quantity, usage_detail, sort_order, note) VALUES (?, ?, ?, ?, ?, ?)",
                    (cat_id, item_name, qty, usage, sort, note)
                )

        conn.commit()
    conn.close()


class ChecklistHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _read_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(content_length)) if content_length > 0 else {}

    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def _get_session_user(self):
        """Extract session token from Authorization header and return user or None."""
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            return sessions.get(token)
        return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == '/health':
            self._send_json({'status': 'ok'})
        elif path == '/api/staff/list':
            self._handle_staff_public_list()
        elif path == '/api/me':
            self._handle_me()
        elif path == '/api/items':
            self._handle_items()
        elif path == '/api/dashboard':
            self._handle_dashboard()
        elif path == '/api/config':
            self._handle_get_config()
        elif path == '/api/export':
            self._handle_export()
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._read_body()

        if path == '/api/login':
            self._handle_login(body)
        elif path == '/api/logout':
            self._handle_logout()
        elif path == '/api/check':
            self._handle_check(body)
        elif path == '/api/staff/reset-pin':
            self._handle_reset_pin(body)
        elif path == '/api/staff/change-pin':
            self._handle_change_own_pin(body)
        elif path == '/api/staff/update-contact':
            self._handle_update_contact(body)
        elif path == '/api/config':
            self._handle_save_config(body)
        elif path == '/api/sync-sheets':
            self._handle_sync_sheets(body)
        else:
            self._send_json({'error': 'not found'}, 404)

    # --- Auth ---
    def _handle_staff_public_list(self):
        """Return staff list (names only, no secrets) for login screen."""
        conn = get_db()
        rows = conn.execute('SELECT id, name, region, role FROM staff ORDER BY id').fetchall()
        conn.close()
        self._send_json([dict(r) for r in rows])

    def _handle_login(self, body):
        staff_id = body.get('staff_id')
        pin = body.get('pin', '')

        conn = get_db()
        user = conn.execute('SELECT * FROM staff WHERE id = ?', (staff_id,)).fetchone()
        conn.close()

        if not user or user['pin_hash'] != hash_pin(pin):
            self._send_json({'error': 'PIN이 올바르지 않습니다.'}, 401)
            return

        token = secrets.token_hex(24)
        contact_name = user['contact_name'] if 'contact_name' in user.keys() else ''
        sessions[token] = {'id': user['id'], 'name': user['name'], 'region': user['region'], 'role': user['role'], 'contact_name': contact_name}
        self._send_json({
            'token': token,
            'user': {'id': user['id'], 'name': user['name'], 'region': user['region'], 'role': user['role'], 'contact_name': contact_name}
        })

    def _handle_logout(self):
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            sessions.pop(token, None)
        self._send_json({'success': True})

    def _handle_me(self):
        user = self._get_session_user()
        if not user:
            self._send_json({'error': 'unauthorized'}, 401)
            return
        self._send_json(user)

    # --- Checklist ---
    def _handle_items(self):
        user = self._get_session_user()
        if not user:
            self._send_json({'error': 'unauthorized'}, 401)
            return

        conn = get_db()
        categories = conn.execute('SELECT * FROM categories ORDER BY sort_order').fetchall()
        items = conn.execute("""
            SELECT i.*, c.name as category_name,
                COALESCE(ch.checked, 0) as checked,
                ch.checked_at,
                ch.staff_id as checked_by
            FROM items i
            JOIN categories c ON i.category_id = c.id
            LEFT JOIN checks ch ON i.id = ch.item_id AND ch.staff_id = ?
            ORDER BY c.sort_order, i.sort_order
        """, (user['id'],)).fetchall()
        conn.close()

        result = []
        for cat in categories:
            cat_dict = dict(cat)
            cat_dict['items'] = [dict(i) for i in items if i['category_id'] == cat['id']]
            result.append(cat_dict)
        self._send_json(result)

    def _handle_check(self, body):
        user = self._get_session_user()
        if not user:
            self._send_json({'error': 'unauthorized'}, 401)
            return

        item_id = body['item_id']
        checked = body['checked']
        staff_id = user['id']

        conn = get_db()
        if checked:
            conn.execute("""
                INSERT INTO checks (item_id, staff_id, checked, checked_at)
                VALUES (?, ?, 1, datetime('now', 'localtime'))
                ON CONFLICT(item_id, staff_id)
                DO UPDATE SET checked = 1, checked_at = datetime('now', 'localtime')
            """, (item_id, staff_id))
        else:
            conn.execute("""
                INSERT INTO checks (item_id, staff_id, checked, checked_at)
                VALUES (?, ?, 0, NULL)
                ON CONFLICT(item_id, staff_id)
                DO UPDATE SET checked = 0, checked_at = NULL
            """, (item_id, staff_id))
        conn.commit()
        conn.close()
        self._send_json({'success': True})

    # --- Dashboard (admin only) ---
    def _handle_dashboard(self):
        user = self._get_session_user()
        if not user or user['role'] != 'admin':
            self._send_json({'error': 'unauthorized'}, 401)
            return

        conn = get_db()
        total_items = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
        staff_list = conn.execute("SELECT id, name, region, role, contact_name FROM staff WHERE role = 'staff' ORDER BY id").fetchall()
        staff_count = len(staff_list)

        staff_stats = []
        for s in staff_list:
            checked = conn.execute(
                'SELECT COUNT(*) FROM checks WHERE staff_id = ? AND checked = 1', (s['id'],)
            ).fetchone()[0]
            pct = round((checked / total_items * 100)) if total_items > 0 else 0
            d = dict(s)
            d.update({'checked': checked, 'total': total_items, 'percent': pct})
            staff_stats.append(d)

        categories = conn.execute('SELECT * FROM categories ORDER BY sort_order').fetchall()
        cat_stats = []
        for cat in categories:
            item_count = conn.execute('SELECT COUNT(*) FROM items WHERE category_id = ?', (cat['id'],)).fetchone()[0]
            total_checks = item_count * staff_count
            done_checks = conn.execute("""
                SELECT COUNT(*) FROM checks ch
                JOIN items i ON ch.item_id = i.id
                WHERE i.category_id = ? AND ch.checked = 1
            """, (cat['id'],)).fetchone()[0]
            pct = round((done_checks / total_checks * 100)) if total_checks > 0 else 0
            d = dict(cat)
            d.update({'itemCount': item_count, 'totalChecks': total_checks, 'doneChecks': done_checks, 'percent': pct})
            cat_stats.append(d)

        total_checks = total_items * staff_count
        done_checks = conn.execute('SELECT COUNT(*) FROM checks WHERE checked = 1').fetchone()[0]
        overall_pct = round((done_checks / total_checks * 100)) if total_checks > 0 else 0

        recent = conn.execute("""
            SELECT ch.checked_at, s.name as staff_name, i.name as item_name, ch.checked
            FROM checks ch
            JOIN staff s ON ch.staff_id = s.id
            JOIN items i ON ch.item_id = i.id
            WHERE ch.checked_at IS NOT NULL
            ORDER BY ch.checked_at DESC
            LIMIT 20
        """).fetchall()

        item_details = conn.execute("""
            SELECT i.id, i.name, i.category_id, c.name as category_name,
                COUNT(CASE WHEN ch.checked = 1 THEN 1 END) as checked_count
            FROM items i
            JOIN categories c ON i.category_id = c.id
            LEFT JOIN checks ch ON i.id = ch.item_id
            GROUP BY i.id
            ORDER BY c.sort_order, i.sort_order
        """).fetchall()

        conn.close()

        self._send_json({
            'totalItems': total_items,
            'staffCount': staff_count,
            'totalChecks': total_checks,
            'doneChecks': done_checks,
            'overallPercent': overall_pct,
            'staffStats': staff_stats,
            'catStats': cat_stats,
            'recentActivity': [dict(r) for r in recent],
            'itemDetails': [dict(r) for r in item_details],
        })

    # --- Admin: reset PIN ---
    def _handle_reset_pin(self, body):
        user = self._get_session_user()
        if not user or user['role'] != 'admin':
            self._send_json({'error': 'unauthorized'}, 401)
            return

        target_id = body.get('staff_id')
        new_pin = body.get('new_pin', '')
        if len(new_pin) != 4 or not new_pin.isdigit():
            self._send_json({'error': 'PIN은 4자리 숫자여야 합니다.'}, 400)
            return

        conn = get_db()
        conn.execute('UPDATE staff SET pin_hash = ? WHERE id = ?', (hash_pin(new_pin), target_id))
        conn.commit()
        conn.close()
        self._send_json({'success': True})

    # --- Staff: change own PIN ---
    def _handle_change_own_pin(self, body):
        user = self._get_session_user()
        if not user:
            self._send_json({'error': 'unauthorized'}, 401)
            return

        current_pin = body.get('current_pin', '')
        new_pin = body.get('new_pin', '')
        if len(new_pin) != 4 or not new_pin.isdigit():
            self._send_json({'error': 'PIN은 4자리 숫자여야 합니다.'}, 400)
            return

        conn = get_db()
        row = conn.execute('SELECT pin_hash FROM staff WHERE id = ?', (user['id'],)).fetchone()
        if not row or row['pin_hash'] != hash_pin(current_pin):
            conn.close()
            self._send_json({'error': '현재 PIN이 올바르지 않습니다.'}, 401)
            return

        conn.execute('UPDATE staff SET pin_hash = ? WHERE id = ?', (hash_pin(new_pin), user['id']))
        conn.commit()
        conn.close()
        self._send_json({'success': True})

    # --- Staff: update contact name ---
    def _handle_update_contact(self, body):
        user = self._get_session_user()
        if not user:
            self._send_json({'error': 'unauthorized'}, 401)
            return

        contact_name = body.get('contact_name', '').strip()
        conn = get_db()
        conn.execute('UPDATE staff SET contact_name = ? WHERE id = ?', (contact_name, user['id']))
        conn.commit()
        conn.close()

        # Update session
        auth = self.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            token = auth[7:]
            if token in sessions:
                sessions[token]['contact_name'] = contact_name

        self._send_json({'success': True, 'contact_name': contact_name})

    # --- Config ---
    def _handle_get_config(self):
        user = self._get_session_user()
        if not user or user['role'] != 'admin':
            self._send_json({'error': 'unauthorized'}, 401)
            return
        conn = get_db()
        rows = conn.execute('SELECT key, value FROM config').fetchall()
        conn.close()
        self._send_json({r['key']: r['value'] for r in rows})

    def _handle_save_config(self, body):
        user = self._get_session_user()
        if not user or user['role'] != 'admin':
            self._send_json({'error': 'unauthorized'}, 401)
            return
        conn = get_db()
        for key, value in body.items():
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
                (key, value, value)
            )
        conn.commit()
        conn.close()
        self._send_json({'success': True})

    # --- Export (for Google Sheets sync) ---
    def _handle_export(self):
        user = self._get_session_user()
        if not user or user['role'] != 'admin':
            self._send_json({'error': 'unauthorized'}, 401)
            return

        conn = get_db()
        total_items = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
        staff_list = conn.execute("SELECT id, name, region, role, contact_name FROM staff WHERE role = 'staff' ORDER BY id").fetchall()
        staff_count = len(staff_list)

        staff_stats = []
        for s in staff_list:
            checked = conn.execute('SELECT COUNT(*) FROM checks WHERE staff_id = ? AND checked = 1', (s['id'],)).fetchone()[0]
            pct = round((checked / total_items * 100)) if total_items > 0 else 0
            d = dict(s)
            d.update({'checked': checked, 'total': total_items, 'percent': pct})
            staff_stats.append(d)

        categories = conn.execute('SELECT * FROM categories ORDER BY sort_order').fetchall()
        cat_stats = []
        for cat in categories:
            item_count = conn.execute('SELECT COUNT(*) FROM items WHERE category_id = ?', (cat['id'],)).fetchone()[0]
            total_checks = item_count * staff_count
            done_checks = conn.execute("""
                SELECT COUNT(*) FROM checks ch JOIN items i ON ch.item_id = i.id
                WHERE i.category_id = ? AND ch.checked = 1
            """, (cat['id'],)).fetchone()[0]
            pct = round((done_checks / total_checks * 100)) if total_checks > 0 else 0
            d = dict(cat)
            d.update({'itemCount': item_count, 'totalChecks': total_checks, 'doneChecks': done_checks, 'percent': pct})
            cat_stats.append(d)

        total_checks = total_items * staff_count
        done_checks = conn.execute('SELECT COUNT(*) FROM checks WHERE checked = 1').fetchone()[0]
        overall_pct = round((done_checks / total_checks * 100)) if total_checks > 0 else 0

        # Per-item per-staff detail
        items_all = conn.execute("""
            SELECT i.id, i.name, c.name as category_name, i.sort_order, c.sort_order as cat_sort
            FROM items i JOIN categories c ON i.category_id = c.id
            ORDER BY c.sort_order, i.sort_order
        """).fetchall()

        item_detail_rows = []
        for item in items_all:
            row = {'item_name': item['name'], 'category': item['category_name']}
            for s in staff_list:
                ch = conn.execute('SELECT checked FROM checks WHERE item_id = ? AND staff_id = ?', (item['id'], s['id'])).fetchone()
                row[s['name']] = 1 if ch and ch['checked'] else 0
            item_detail_rows.append(row)

        conn.close()

        self._send_json({
            'title': '청토지 보수교육 3/18 1차 대면 실습 준비 체크리스트',
            'exportedAt': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
            'totalItems': total_items,
            'staffCount': staff_count,
            'overallPercent': overall_pct,
            'doneChecks': done_checks,
            'totalChecks': total_checks,
            'staffStats': staff_stats,
            'catStats': cat_stats,
            'itemDetailRows': item_detail_rows,
            'staffNames': [s['name'] for s in staff_list],
        })

    # --- Server-side Google Sheets sync (bypasses CORS) ---
    def _handle_sync_sheets(self, body):
        user = self._get_session_user()
        if not user or user['role'] != 'admin':
            self._send_json({'error': 'unauthorized'}, 401)
            return

        sheets_url = body.get('sheets_url', '').strip()
        if not sheets_url:
            self._send_json({'error': 'Google Apps Script URL이 필요합니다.'}, 400)
            return

        # Get export data
        conn = get_db()
        total_items = conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]
        staff_list = conn.execute("SELECT id, name, region, role, contact_name FROM staff WHERE role = 'staff' ORDER BY id").fetchall()
        staff_count = len(staff_list)

        staff_stats = []
        for s in staff_list:
            checked = conn.execute('SELECT COUNT(*) FROM checks WHERE staff_id = ? AND checked = 1', (s['id'],)).fetchone()[0]
            pct = round((checked / total_items * 100)) if total_items > 0 else 0
            d = dict(s)
            d.update({'checked': checked, 'total': total_items, 'percent': pct})
            staff_stats.append(d)

        categories = conn.execute('SELECT * FROM categories ORDER BY sort_order').fetchall()
        cat_stats = []
        for cat in categories:
            item_count = conn.execute('SELECT COUNT(*) FROM items WHERE category_id = ?', (cat['id'],)).fetchone()[0]
            total_checks_cat = item_count * staff_count
            done_checks_cat = conn.execute("""
                SELECT COUNT(*) FROM checks ch JOIN items i ON ch.item_id = i.id
                WHERE i.category_id = ? AND ch.checked = 1
            """, (cat['id'],)).fetchone()[0]
            pct = round((done_checks_cat / total_checks_cat * 100)) if total_checks_cat > 0 else 0
            d = dict(cat)
            d.update({'itemCount': item_count, 'totalChecks': total_checks_cat, 'doneChecks': done_checks_cat, 'percent': pct})
            cat_stats.append(d)

        total_checks = total_items * staff_count
        done_checks = conn.execute('SELECT COUNT(*) FROM checks WHERE checked = 1').fetchone()[0]
        overall_pct = round((done_checks / total_checks * 100)) if total_checks > 0 else 0

        items_all = conn.execute("""
            SELECT i.id, i.name, c.name as category_name, i.sort_order, c.sort_order as cat_sort
            FROM items i JOIN categories c ON i.category_id = c.id
            ORDER BY c.sort_order, i.sort_order
        """).fetchall()

        item_detail_rows = []
        for item in items_all:
            row = {'item_name': item['name'], 'category': item['category_name']}
            for s in staff_list:
                ch = conn.execute('SELECT checked FROM checks WHERE item_id = ? AND staff_id = ?', (item['id'], s['id'])).fetchone()
                row[s['name']] = 1 if ch and ch['checked'] else 0
            item_detail_rows.append(row)
        conn.close()

        export_data = {
            'title': '청토지 보수교육 3/18 1차 대면 실습 준비 체크리스트',
            'exportedAt': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M'),
            'totalItems': total_items,
            'staffCount': staff_count,
            'overallPercent': overall_pct,
            'doneChecks': done_checks,
            'totalChecks': total_checks,
            'staffStats': staff_stats,
            'catStats': cat_stats,
            'itemDetailRows': item_detail_rows,
            'staffNames': [s['name'] for s in staff_list],
        }

        # POST to Google Apps Script (server-side, no CORS issues)
        # Google Apps Script returns 302 redirects; we need to follow them
        try:
            payload = json.dumps(export_data, ensure_ascii=False).encode('utf-8')
            req = Request(sheets_url, data=payload, headers={
                'Content-Type': 'text/plain',
                'User-Agent': 'TogiChecklist/1.0'
            })
            ctx = ssl.create_default_context()
            response = urlopen(req, timeout=60, context=ctx)
            resp_body = response.read().decode('utf-8')
            try:
                result = json.loads(resp_body)
            except json.JSONDecodeError:
                result = {'success': True, 'message': '동기화 요청 전송됨'}
            self._send_json(result)
        except HTTPError as e:
            # 302 redirect - follow it manually
            if e.code in (301, 302, 303, 307, 308):
                redirect_url = e.headers.get('Location', '')
                if redirect_url:
                    try:
                        redirect_req = Request(redirect_url)
                        resp2 = urlopen(redirect_req, timeout=30, context=ctx)
                        resp_body = resp2.read().decode('utf-8')
                        try:
                            result = json.loads(resp_body)
                        except json.JSONDecodeError:
                            result = {'success': True, 'message': '동기화 완료'}
                        self._send_json(result)
                    except Exception as e2:
                        # Data was already sent to doPost, redirect is just for response
                        self._send_json({'success': True, 'message': '동기화 요청 전송됨 (응답 확인 불가)'})
                else:
                    self._send_json({'success': True, 'message': '동기화 요청 전송됨'})
            else:
                self._send_json({'error': f'Google Sheets 오류 (HTTP {e.code})'}, 502)
        except URLError as e:
            self._send_json({'error': f'Google Sheets 연결 실패: {str(e)}'}, 502)
        except Exception as e:
            self._send_json({'error': f'동기화 실패: {str(e)}'}, 500)

    def log_message(self, format, *args):
        if '/api/' in str(args[0]):
            return
        super().log_message(format, *args)


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 3000))
    server = HTTPServer(('0.0.0.0', port), ChecklistHandler)
    print('=' * 50)
    print('  청토지 보수교육 준비 체크리스트 서버')
    print(f'  http://localhost:{port}')
    print('=' * 50)
    print()
    print('  [초기 로그인 PIN]')
    print('  관리자: 0000')
    print('  전 지회 공통: 0014 (fKF 창립기념일)')
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n서버를 종료합니다.')
        server.server_close()
