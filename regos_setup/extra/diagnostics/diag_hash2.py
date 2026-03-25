import sqlite3, json, hashlib

conn = sqlite3.connect('/app/backend/data/regos_breaches.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT * FROM threshold_evaluations ORDER BY id LIMIT 1').fetchone()
conn.close()

if not row:
    print('No records found')
    exit()

print('=== ALL COLUMNS ===')
for key in row.keys():
    val = row[key]
    print('  col=%-25s val=%-50r type=%s' % (key, val, type(val).__name__))

print()
print('=== STORED HASH ===')
print(row['evidence_hash'])

print()
print('=== TRYING EVERY COMBINATION ===')

# The 8 fields used in code
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

# Try multiple serialization variants
stored = row['evidence_hash']

tests = [
    ('compact separators', json.dumps(d, sort_keys=True, separators=(',', ':'))),
    ('default separators', json.dumps(d, sort_keys=True)),
    ('no sort, compact', json.dumps(d, separators=(',', ':'))),
    ('no sort, default', json.dumps(d)),
]

for label, j in tests:
    h = hashlib.sha256(j.encode()).hexdigest()
    match = 'MATCH' if h == stored else 'no'
    print('  %-25s %s  json=%s' % (label, match, j[:90]))

# Now try with float() cast explicitly
d2 = dict(d)
d2['user_value'] = float(d2['user_value'])
d2['threshold_value'] = float(d2['threshold_value'])
j2 = json.dumps(d2, sort_keys=True, separators=(',', ':'))
h2 = hashlib.sha256(j2.encode()).hexdigest()
print('  %-25s %s  json=%s' % ('float cast + compact', 'MATCH' if h2 == stored else 'no', j2[:90]))

# Try with int cast (in case values are stored as int)
try:
    d3 = dict(d)
    d3['user_value'] = int(d3['user_value'])
    d3['threshold_value'] = int(d3['threshold_value'])
    j3 = json.dumps(d3, sort_keys=True, separators=(',', ':'))
    h3 = hashlib.sha256(j3.encode()).hexdigest()
    print('  %-25s %s  json=%s' % ('int cast + compact', 'MATCH' if h3 == stored else 'no', j3[:90]))
except:
    pass

# Now the BIG test: read the ACTUAL deployed filter code and find how it hashes
print()
print('=== CHECKING DEPLOYED CODE IN OPEN WEBUI ===')
try:
    import sys
    sys.path.insert(0, '/app/backend')
    # Try to find the deployed filter source
    import glob
    # Open WebUI stores functions in its DB, let's check
    owui_conn = sqlite3.connect('/app/backend/data/webui.db')
    owui_conn.row_factory = sqlite3.Row
    funcs = owui_conn.execute("SELECT id, name, content FROM function WHERE id LIKE '%graphrag%' OR name LIKE '%GraphRAG%' OR name LIKE '%graphrag%'").fetchall()
    if not funcs:
        funcs = owui_conn.execute("SELECT id, name, substr(content, 1, 100) as content FROM function").fetchall()
        print('  No graphrag function found. All functions:')
        for f in funcs:
            print('    id=%s name=%s' % (f['id'], f['name']))
    else:
        for f in funcs:
            code = f['content']
            print('  Found function: id=%s name=%s code_len=%d' % (f['id'], f['name'], len(code)))
            # Find the hash computation in the deployed code
            idx = code.find('evidence_hash')
            if idx > 0:
                snippet = code[max(0,idx-200):idx+200]
                print('  Code around evidence_hash:')
                for line in snippet.split('\n'):
                    line = line.strip()
                    if line:
                        print('    ' + line)
    owui_conn.close()
except Exception as e:
    print('  Could not read Open WebUI DB: %s' % e)
