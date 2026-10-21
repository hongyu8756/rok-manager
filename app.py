"""
=============================================================================
File Name   : app.py
Project     : Rise of Kingdoms (ROK) Kingdom Account Management System
Version     : 1.1 (Performance Optimized)
Author      : ROK Kingdom Management Team
Created     : 2026-10-21
Description : Flask core server application providing REST APIs for player 
              searches, farm bindings/unbindings, and administrative 
              hierarchy dashboards.
=============================================================================
"""

import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

def get_db_connection():
    db_url = os.environ.get('DATABASE_URL')
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        conn = psycopg2.connect(db_url)
        return conn
    else:
        conn = sqlite3.connect('rok_data.db')
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    db_url = os.environ.get('DATABASE_URL')
    conn = get_db_connection()
    
    if db_url:
        query = query.replace('?', '%s')
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    else:
        cursor = conn.cursor()

    cursor.execute(query, params)
    
    result = None
    if fetchone:
        row = cursor.fetchone()
        result = dict(row) if row else None
    elif fetchall:
        rows = cursor.fetchall()
        result = [dict(r) for r in rows] if rows else []
        
    if commit:
        conn.commit()
        
    cursor.close()
    conn.close()
    return result

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/search/<int:gov_id>')
def search_gov(gov_id):
    farm_check = execute_query('SELECT main_id FROM bindings WHERE farm_id = ?', (gov_id,), fetchone=True)
    if farm_check:
        return jsonify({
            'status': 'redirect', 
            'main_id': farm_check['main_id'], 
            'msg': 'Farm account detected, redirected to main. / 该账号为农场号，已自动跳转至主账号。'
        })

    gov = execute_query('''
        SELECT "Governor ID" AS id, 
               "Governor Name" AS name, 
               "Power" AS power, 
               "Total KP" AS kp, 
               "Clickable" AS clickable 
        FROM governors WHERE "Governor ID" = ?
    ''', (gov_id,), fetchone=True)
    
    if not gov:
        return jsonify({
            'status': 'error', 
            'msg': 'ID not found in database. / 未查找到该账号 ID，请检查。'
        })

    farms = execute_query('''
        SELECT g."Governor ID" AS id, 
               g."Governor Name" AS name, 
               g."Power" AS power, 
               g."Total KP" AS kp 
        FROM bindings b 
        JOIN governors g ON b.farm_id = g."Governor ID" 
        WHERE b.main_id = ? 
        ORDER BY g."Power" DESC
    ''', (gov_id,), fetchall=True)
    
    farms_list = []
    kp_warnings = []
    
    for f in farms:
        f_dict = dict(f)
        if f_dict['kp'] > gov['kp']:
            f_dict['kp_warning'] = True
            kp_warnings.append(f_dict['name'])
        else:
            f_dict['kp_warning'] = False
        farms_list.append(f_dict)

    return jsonify({
        'status': 'success',
        'gov': dict(gov),
        'farms': farms_list,
        'farm_count': len(farms_list),
        'kp_warnings': kp_warnings
    })

@app.route('/api/bind', methods=['POST'])
def bind_farm():
    data = request.json or {}
    main_id = data.get('main_id')
    farm_id = data.get('farm_id')
    
    if main_id == farm_id:
        return jsonify({'status': 'error', 'msg': 'Cannot bind yourself! / 不能绑定自己！'})

    farm = execute_query('SELECT "Governor ID" AS id FROM governors WHERE "Governor ID" = ?', (farm_id,), fetchone=True)
    if not farm:
        return jsonify({'status': 'error', 'msg': 'Farm ID not found! / 未找到该农场 ID！'})

    is_bound = execute_query('SELECT * FROM bindings WHERE farm_id = ?', (farm_id,), fetchone=True)
    if is_bound:
        return jsonify({'status': 'error', 'msg': 'This farm is already bound to another main! / 该农场已被其他账号绑定！'})

    is_main = execute_query('SELECT * FROM bindings WHERE main_id = ?', (farm_id,), fetchone=True)
    if is_main:
        return jsonify({'status': 'error', 'msg': 'This ID is already a Main Account with farms bound to it! / 该账号已是主账号且绑定了农场，无法被绑定为农场！'})

    try:
        execute_query(
            'INSERT INTO bindings (main_id, farm_id, bind_date) VALUES (?, ?, CURRENT_TIMESTAMP)', 
            (main_id, farm_id), 
            commit=True
        )
        msg = 'Binding successful! / 绑定成功！'
        status = 'success'
    except Exception as e:
        msg = 'Failed / 绑定失败：' + str(e)
        status = 'error'
        
    return jsonify({'status': status, 'msg': msg})

@app.route('/api/unbind', methods=['POST'])
def unbind_farm():
    data = request.json or {}
    farm_id = data.get('farm_id')
    
    try:
        execute_query('DELETE FROM bindings WHERE farm_id = ?', (farm_id,), commit=True)
        msg = 'Unbound successfully! / 解绑成功！'
        status = 'success'
    except Exception as e:
        msg = 'Failed / 解绑失败：' + str(e)
        status = 'error'
        
    return jsonify({'status': status, 'msg': msg})

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/admin/data')
def admin_data():
    hidden = execute_query('''
        SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
        FROM governors 
        WHERE "Clickable" = 'FALSE' OR "Clickable" = '0' 
        ORDER BY "Power" DESC
    ''', fetchall=True)
    
    unbound_high = execute_query('''
        SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
        FROM governors 
        WHERE ("Clickable" = 'TRUE' OR "Clickable" = '1' OR "Clickable" IS NULL) 
        AND "Power" >= 30000000 
        AND "Governor ID" NOT IN (SELECT main_id FROM bindings)
        AND "Governor ID" NOT IN (SELECT farm_id FROM bindings)
        ORDER BY "Power" DESC
    ''', fetchall=True)
    
    mains = execute_query('''
        SELECT "Governor ID" AS id, "Governor Name" AS name, "Power" AS power, "Total KP" AS kp 
        FROM governors 
        WHERE ("Clickable" = 'TRUE' OR "Clickable" = '1' OR "Clickable" IS NULL) 
        AND "Governor ID" NOT IN (SELECT farm_id FROM bindings)
        ORDER BY "Power" DESC
    ''', fetchall=True)
    
    # 极速批量查询：用 1 次查询查出所有绑定农场，替代循环单条查询
    all_farms = execute_query('''
        SELECT b.main_id, 
               g."Governor ID" AS id, 
               g."Governor Name" AS name, 
               g."Power" AS power, 
               g."Total KP" AS kp 
        FROM bindings b 
        JOIN governors g ON b.farm_id = g."Governor ID" 
        WHERE (g."Clickable" = 'TRUE' OR g."Clickable" = '1' OR g."Clickable" IS NULL)
        ORDER BY g."Power" DESC
    ''', fetchall=True)
    
    farms_by_main = {}
    for f in all_farms:
        f_dict = dict(f)
        m_id = f_dict['main_id']
        if m_id not in farms_by_main:
            farms_by_main[m_id] = []
        farms_by_main[m_id].append(f_dict)

    hierarchy = []
    for m in mains:
        m_dict = dict(m)
        m_id = m_dict['id']
        m_kp = m_dict['kp']
        
        farms = farms_by_main.get(m_id, [])
        farms_processed = []
        for f in farms:
            f_copy = dict(f)
            f_copy['kp_warning'] = f_copy['kp'] > m_kp
            farms_processed.append(f_copy)

        hierarchy.append({
            'main': m_dict,
            'farms': farms_processed
        })
        
    return jsonify({
        'hidden': hidden,
        'unbound_high': unbound_high,
        'hierarchy': hierarchy
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
