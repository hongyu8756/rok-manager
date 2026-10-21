"""
=============================================================================
File Name   : app.py
Project     : Rise of Kingdoms (ROK) Kingdom Account Management System
Version     : 1.2 (Ultra-Fast Connection Pooling & Query Merging)
Author      : ROK Kingdom Management Team
Created     : 2026-10-21
=============================================================================
"""

import os
import sqlite3
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# 1. 建立长连接池（避免每次请求都重新连接数据库）
# ---------------------------------------------------------------------------
db_url = os.environ.get('DATABASE_URL')
pg_pool = None

if db_url:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    # 建立 1 到 10 个可复用的持久数据库连接
    pg_pool = SimpleConnectionPool(1, 10, db_url)

def get_db():
    if pg_pool:
        conn = pg_pool.getconn()
        return conn, True
    else:
        conn = sqlite3.connect('rok_data.db')
        conn.row_factory = sqlite3.Row
        return conn, False

def release_db(conn, is_pg):
    if is_pg and pg_pool:
        pg_pool.putconn(conn)
    elif not is_pg:
        conn.close()

# ---------------------------------------------------------------------------
# 路由与 API
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search/<int:gov_id>')
def search_gov(gov_id):
    conn, is_pg = get_db()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor) if is_pg else conn.cursor()
        placeholder = '%s' if is_pg else '?'

        # 1. 检查是否为农场号
        query_farm = f'SELECT main_id FROM bindings WHERE farm_id = {placeholder}'
        cursor.execute(query_farm, (gov_id,))
        farm_check = cursor.fetchone()
        
        if farm_check:
            farm_dict = dict(farm_check)
            return jsonify({
                'status': 'redirect', 
                'main_id': farm_dict['main_id'], 
                'msg': 'Farm account detected, redirected to main. / 该账号为农场号，已自动跳转至主账号。'
            })

        # 2. 极速合并查询：同时查出主账号信息及其所有绑定的农场
        query_main = f'''
            SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
            FROM governors WHERE "Governor ID" = {placeholder}
        '''
        cursor.execute(query_main, (gov_id,))
        gov_row = cursor.fetchone()
        
        if not gov_row:
            return jsonify({'status': 'error', 'msg': 'ID not found in database. / 未查找到该账号 ID，请检查。'})

        gov = dict(gov_row)

        query_farms = f'''
            SELECT g."Governor ID" AS id, g."Governor Name" AS name, g."Power" AS power, g."Total KP" AS kp 
            FROM bindings b 
            JOIN governors g ON b.farm_id = g."Governor ID" 
            WHERE b.main_id = {placeholder} 
            ORDER BY g."Power" DESC
        '''
        cursor.execute(query_farms, (gov_id,))
        farms_rows = cursor.fetchall() or []

        farms_list = []
        kp_warnings = []
        for f in farms_rows:
            f_dict = dict(f)
            if f_dict['kp'] > gov['kp']:
                f_dict['kp_warning'] = True
                kp_warnings.append(f_dict['name'])
            else:
                f_dict['kp_warning'] = False
            farms_list.append(f_dict)

        cursor.close()
        return jsonify({
            'status': 'success',
            'gov': gov,
            'farms': farms_list,
            'farm_count': len(farms_list),
            'kp_warnings': kp_warnings
        })
    finally:
        release_db(conn, is_pg)

@app.route('/api/bind', methods=['POST'])
def bind_farm():
    data = request.json or {}
    main_id = data.get('main_id')
    farm_id = data.get('farm_id')
    
    if main_id == farm_id:
        return jsonify({'status': 'error', 'msg': 'Cannot bind yourself! / 不能绑定自己！'})

    conn, is_pg = get_db()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor) if is_pg else conn.cursor()
        p = '%s' if is_pg else '?'

        cursor.execute(f'SELECT "Governor ID" FROM governors WHERE "Governor ID" = {p}', (farm_id,))
        if not cursor.fetchone():
            return jsonify({'status': 'error', 'msg': 'Farm ID not found! / 未找到该农场 ID！'})

        cursor.execute(f'SELECT 1 FROM bindings WHERE farm_id = {p}', (farm_id,))
        if cursor.fetchone():
            return jsonify({'status': 'error', 'msg': 'This farm is already bound to another main! / 该农场已被其他账号绑定！'})

        cursor.execute(f'SELECT 1 FROM bindings WHERE main_id = {p}', (farm_id,))
        if cursor.fetchone():
            return jsonify({'status': 'error', 'msg': 'This ID is already a Main Account with farms bound to it! / 该账号已是主账号且绑定了农场！'})

        cursor.execute(f'INSERT INTO bindings (main_id, farm_id, bind_date) VALUES ({p}, {p}, CURRENT_TIMESTAMP)', (main_id, farm_id))
        conn.commit()
        cursor.close()
        return jsonify({'status': 'success', 'msg': 'Binding successful! / 绑定成功！'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': 'Failed / 绑定失败：' + str(e)})
    finally:
        release_db(conn, is_pg)

@app.route('/api/unbind', methods=['POST'])
def unbind_farm():
    data = request.json or {}
    farm_id = data.get('farm_id')
    conn, is_pg = get_db()
    try:
        cursor = conn.cursor()
        p = '%s' if is_pg else '?'
        cursor.execute(f'DELETE FROM bindings WHERE farm_id = {p}', (farm_id,))
        conn.commit()
        cursor.close()
        return jsonify({'status': 'success', 'msg': 'Unbound successfully! / 解绑成功！'})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': 'Failed / 解绑失败：' + str(e)})
    finally:
        release_db(conn, is_pg)

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/admin/data')
def admin_data():
    conn, is_pg = get_db()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor) if is_pg else conn.cursor()

        cursor.execute('''
            SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
            FROM governors 
            WHERE "Clickable" = 'FALSE' OR "Clickable" = '0' 
            ORDER BY "Power" DESC
        ''')
        hidden = [dict(r) for r in cursor.fetchall() or []]

        cursor.execute('''
            SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
            FROM governors 
            WHERE ("Clickable" = 'TRUE' OR "Clickable" = '1' OR "Clickable" IS NULL) 
            AND "Power" >= 30000000 
            AND "Governor ID" NOT IN (SELECT main_id FROM bindings)
            AND "Governor ID" NOT IN (SELECT farm_id FROM bindings)
            ORDER BY "Power" DESC
        ''')
        unbound_high = [dict(r) for r in cursor.fetchall() or []]

        cursor.execute('''
            SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
            FROM governors 
            WHERE ("Clickable" = 'TRUE' OR "Clickable" = '1' OR "Clickable" IS NULL) 
            AND "Governor ID" NOT IN (SELECT farm_id FROM bindings)
            ORDER BY "Power" DESC
        ''')
        mains = [dict(r) for r in cursor.fetchall() or []]

        cursor.execute('''
            SELECT b.main_id, g."Governor ID" AS id, g."Governor Name" AS name, g."Power" AS power, g."Total KP" AS kp 
            FROM bindings b 
            JOIN governors g ON b.farm_id = g."Governor ID" 
            WHERE (g."Clickable" = 'TRUE' OR g."Clickable" = '1' OR g."Clickable" IS NULL)
            ORDER BY g."Power" DESC
        ''')
        all_farms = [dict(r) for r in cursor.fetchall() or []]

        farms_by_main = {}
        for f in all_farms:
            m_id = f['main_id']
            if m_id not in farms_by_main:
                farms_by_main[m_id] = []
            farms_by_main[m_id].append(f)

        hierarchy = []
        for m in mains:
            m_id = m['id']
            farms = farms_by_main.get(m_id, [])
            farms_processed = []
            for f in farms:
                f_copy = dict(f)
                f_copy['kp_warning'] = f_copy['kp'] > m['kp']
                farms_processed.append(f_copy)

            hierarchy.append({
                'main': m,
                'farms': farms_processed
            })

        cursor.close()
        return jsonify({'hidden': hidden, 'unbound_high': unbound_high, 'hierarchy': hierarchy})
    finally:
        release_db(conn, is_pg)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
