#!/usr/bin/env python3
"""导出MySQL数据库到SQL文件"""

import pymysql
import os
from datetime import datetime

def export_database():
    # 连接数据库
    conn = pymysql.connect(
        host='localhost',
        port=3306,
        user='root',
        password='trading2024',
        database='trading'
    )
    cursor = conn.cursor()

    # 输出文件名
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'backup_trading_{timestamp}.sql'
    filepath = os.path.join(os.getcwd(), filename)

    # 获取所有表
    cursor.execute('SHOW TABLES')
    tables = [row[0] for row in cursor.fetchall()]

    print(f'正在导出 {len(tables)} 个表...')

    with open(filepath, 'w', encoding='utf-8') as f:
        # 写入文件头
        f.write(f'-- MySQL Backup: trading\n')
        f.write(f'-- Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')

        for table in tables:
            print(f'  导出表: {table}')

            # 获取表结构
            cursor.execute(f'SHOW CREATE TABLE {table}')
            create_stmt = cursor.fetchone()[1]
            f.write(f'-- Table: {table}\n')
            f.write(f'DROP TABLE IF EXISTS {table};\n')
            f.write(f'{create_stmt};\n\n')

            # 导出数据
            cursor.execute(f'SELECT * FROM {table}')
            rows = cursor.fetchall()

            if rows:
                # 获取列名
                cursor.execute(f'SHOW COLUMNS FROM {table}')
                columns = [col[0] for col in cursor.fetchall()]

                for row in rows:
                    values = []
                    for val in row:
                        if val is None:
                            values.append('NULL')
                        elif isinstance(val, datetime):
                            values.append(f'"{val.strftime("%Y-%m-%d %H:%M:%S")}"')
                        elif isinstance(val, (int, float)):
                            values.append(str(val))
                        else:
                            # 转义特殊字符
                            val_str = str(val).replace('\\', '\\\\').replace('"', '\\"')
                            values.append(f'"{val_str}"')

                    cols = ','.join(columns)
                    vals = ','.join(values)
                    f.write(f'INSERT INTO {table} ({cols}) VALUES ({vals});\n')

                print(f'    {len(rows):,} 条记录')

    f.close()
    conn.close()

    # 获取文件大小
    size = os.path.getsize(filepath)
    print(f'\n导出完成: {filepath}')
    print(f'文件大小: {size / 1024 / 1024:.2f} MB')

if __name__ == '__main__':
    export_database()
