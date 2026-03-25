import sqlite3, json, hashlib

conn = sqlite3.connect('/app/backend/data/regos_breaches.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT * FROM threshold_evaluations ORDER BY id LIMIT 1').fetchone()
conn.close()

if not row:
    print('No records found in breach DB')
    exit()

d = {
    'parameter': row['parameter'],
    'user_value': row['user_value'],
    'threshold_value': row['threshold_value'],
    'threshold_direction': row['threshold_direction'],
    'threshold_unit': row['threshold_unit'],
    'status': row['status'],
    'timestamp': row['timestamp'],
    'section_ref': row['section_ref'],
}

print('=== FIELD VALUES & TYPES ===')
for k, v in d.items():
    print('  %-25s = %-40r type=%s' % (k, v, type(v).__name__))

stored = row['evidence_hash']
print()
print('=== STORED HASH ===')
print('  ' + stored)

j_compact = json.dumps(d, sort_keys=True, separators=(',', ':'))
h_compact = hashlib.sha256(j_compact.encode()).hexdigest()
print()
print('=== WITH separators (compact) ===')
print('  JSON: ' + j_compact[:120])
print('  Hash: ' + h_compact)
print('  Match: ' + str(h_compact == stored))

j_default = json.dumps(d, sort_keys=True)
h_default = hashlib.sha256(j_default.encode()).hexdigest()
print()
print('=== WITHOUT separators (default) ===')
print('  JSON: ' + j_default[:120])
print('  Hash: ' + h_default)
print('  Match: ' + str(h_default == stored))

if h_compact != stored and h_default != stored:
    print()
    print('=== NEITHER MATCHED - deeper investigation ===')
    print('  Checking all columns in the row:')
    for key in row.keys():
        print('    %-25s = %r' % (key, row[key]))
