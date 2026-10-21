"""
=============================================================================
File Name   : app.py
Project     : Rise of Kingdoms (ROK) Kingdom Account Management System
Author      : ROK Kingdom Management Team
Created     : 2026-10-21
Description : Flask core server application providing REST APIs for player 
              searches, farm bindings/unbindings, and administrative 
              hierarchy dashboards.
=============================================================================
"""

import os
import sqlite3
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('rok_data.db')
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------------------------
# 玩家前端页面路由 (Player Frontend Route)
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

# ---------------------------------------------------------------------------
# API: 玩家搜索接口 (Search Governor API)
# ---------------------------------------------------------------------------
@app.route('/api/search/<int:gov_id>')
def search_gov(gov_id):
    conn = get_db_connection()
    
    # 1. 若为农场号，自动跳转至主账号
    farm_check = conn.execute('SELECT main_id FROM bindings WHERE farm_id = ?', (gov_id,)).fetchone()
    if farm_check:
        conn.close()
        return jsonify({
            'status': 'redirect', 
            'main_id': farm_check['main_id'], 
            'msg': 'Farm account detected, redirected to main. / 该账号为农场号，已自动跳转至主账号。'
        })

    # 2. 查询主账号信息
    gov = conn.execute('SELECT * FROM governors WHERE id = ?', (gov_id,)).fetchone()
    if not gov:
        conn.close()
        return jsonify({
            'status': 'error', 
            'msg': 'ID not found in database. / 未查找到该账号 ID，请检查。'
        })

    # 3. 查询名下绑定的农场
    farms = conn.execute('''
        SELECT g.id, g.name, g.power, g.kp 
        FROM bindings b 
        JOIN governors g ON b.farm_id = g.id 
        WHERE b.main_id = ? 
        ORDER BY g.power DESC
    ''', (gov_id,)).fetchall()
    
    conn.close()
    
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

# ---------------------------------------------------------------------------
# API: 绑定农场接口 (Bind Farm API)
# ---------------------------------------------------------------------------
@app.route('/api/bind', methods=['POST'])
def bind_farm():
    data = request.json
    main_id = data.get('main_id')
    farm_id = data.get('farm_id')
    
    if main_id == farm_id:
        return jsonify({'status': 'error', 'msg': 'Cannot bind yourself! / 不能绑定自己！'})

    conn = get_db_connection()
    
    farm = conn.execute('SELECT * FROM governors WHERE id = ?', (farm_id,)).fetchone()
    if not farm:
        conn.close()
        return jsonify({'status': 'error', 'msg': 'Farm ID not found! / 未找到该农场 ID！'})

    is_bound = conn.execute('SELECT * FROM bindings WHERE farm_id = ?', (farm_id,)).fetchone()
    if is_bound:
        conn.close()
        return jsonify({'status': 'error', 'msg': 'This farm is already bound to another main! / 该农场已被其他账号绑定！'})

    is_main = conn.execute('SELECT * FROM bindings WHERE main_id = ?', (farm_id,)).fetchone()
    if is_main:
        conn.close()
        return jsonify({'status': 'error', 'msg': 'This ID is already a Main Account with farms bound to it! / 该账号已是主账号且绑定了农场，无法被绑定为农场！'})

    try:
        conn.execute('INSERT INTO bindings (main_id, farm_id, bind_date) VALUES (?, ?, CURRENT_TIMESTAMP)', (main_id, farm_id))
        conn.commit()
        msg = 'Binding successful! / 绑定成功！'
        status = 'success'
    except Exception as e:
        msg = 'Failed / 绑定失败：' + str(e)
        status = 'error'
        
    conn.close()
    return jsonify({'status': status, 'msg': msg})

# ---------------------------------------------------------------------------
# API: 解绑接口 (Unbind Farm API)
# ---------------------------------------------------------------------------
@app.route('/api/unbind', methods=['POST'])
def unbind_farm():
    data = request.json
    farm_id = data.get('farm_id')
    
    conn = get_db_connection()
    try:
        conn.execute('DELETE FROM bindings WHERE farm_id = ?', (farm_id,))
        conn.commit()
        msg = 'Unbound successfully! / 解绑成功！'
        status = 'success'
    except Exception as e:
        msg = 'Failed / 解绑失败：' + str(e)
        status = 'error'
        
    conn.close()
    return jsonify({'status': status, 'msg': msg})

# ---------------------------------------------------------------------------
# 管理员页面与数据 API (Admin Routes)
# ---------------------------------------------------------------------------
@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/api/admin/data')
def admin_data():
    conn = get_db_connection()
    
    hidden = conn.execute('SELECT id, name, power, kp FROM governors WHERE clickable = 0 ORDER BY power DESC').fetchall()
    
    unbound_high = conn.execute('''
        SELECT id, name, power, kp FROM governors 
        WHERE clickable = 1 AND power >= 30000000 
        AND id NOT IN (SELECT main_id FROM bindings)
        AND id NOT IN (SELECT farm_id FROM bindings)
        ORDER BY power DESC
    ''').fetchall()
    
    mains = conn.execute('''
        SELECT id, name, power, kp FROM governors 
        WHERE clickable = 1 AND id NOT IN (SELECT farm_id FROM bindings)
        ORDER BY power DESC
    ''').fetchall()
    
    hierarchy = []
    for m in mains:
        farms = conn.execute('''
            SELECT g.id, g.name, g.power, g.kp 
            FROM bindings b 
            JOIN governors g ON b.farm_id = g.id 
            WHERE b.main_id = ? AND g.clickable = 1
            ORDER BY g.power DESC
        ''', (m['id'],)).fetchall()
        
        farms_processed = []
        for f in farms:
            f_dict = dict(f)
            f_dict['kp_warning'] = f_dict['kp'] > m['kp']
            farms_processed.append(f_dict)

        hierarchy.append({
            'main': dict(m),
            'farms': farms_processed
        })
        
    conn.close()
    return jsonify({
        'hidden': [dict(h) for h in hidden],
        'unbound_high': [dict(u) for u in unbound_high],
        'hierarchy': hierarchy
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)