"""
=============================================================================
File Name   : import_data.py
Project     : Rise of Kingdoms (ROK) Kingdom Account Management System
Author      : ROK Kingdom Management Team
Created     : 2026-10-21
Description : Data synchronization script. Reads the latest Excel file and 
              updates governor power/KP while preserving all active account
              bindings in SQLite database (rok_data.db).
=============================================================================
"""

import pandas as pd
import sqlite3
import glob
import os

def update_database_from_excel():
    excel_files = glob.glob("*.xlsx")
    if not excel_files:
        print("❌ 错误 / Error: 未找到任何 .xlsx 文件！/ No .xlsx file found!")
        return

    latest_file = max(excel_files, key=os.path.getmtime)
    print(f"📄 正在读取最新数据文件 / Reading latest data file: {latest_file} ...")

    try:
        df = pd.read_excel(latest_file)
    except Exception as e:
        print(f"❌ 读取 Excel 失败 / Failed to read Excel: {e}")
        return

    df.columns = df.columns.str.strip()

    conn = sqlite3.connect('rok_data.db')
    cursor = conn.cursor()

    updated_count = 0
    for _, row in df.iterrows():
        gov_id = int(row['id'])
        name = str(row['name'])
        power = int(row['power'])
        kp = int(row['kp'])
        clickable = int(row['clickable']) if 'clickable' in row and pd.notnull(row['clickable']) else 1

        # 使用 ON CONFLICT 更新玩家信息，保留 bindings 绑定表不动
        cursor.execute('''
            INSERT INTO governors (id, name, power, kp, clickable)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                power = excluded.power,
                kp = excluded.kp,
                clickable = excluded.clickable
        ''', (gov_id, name, power, kp, clickable))
        updated_count += 1

    conn.commit()
    conn.close()
    print(f"✅ 数据同步完成！已成功同步 {updated_count} 条玩家最新数据。")
    print("🔒 历史绑定关系（Bindings）已完整保留。")

if __name__ == '__main__':
    update_database_from_excel()