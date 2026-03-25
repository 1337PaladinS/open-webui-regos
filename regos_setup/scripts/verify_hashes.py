import sqlite3, json, hashlib

conn = sqlite3.connect('/app/backend/data/regos_breaches.db')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM threshold_evaluations ORDER BY id').fetchall()
conn.close()

if not rows:
    print('No records found')
    exit()

print('SHA-256 Verification Report')
print('=' * 70)
verified = 0
tampered = 0

for row in rows:
    canonical = json.dumps({
        'parameter': row['parameter'],
        'user_value': row['user_value'],
        'threshold_value': row['threshold_value'],
        'threshold_direction': row['threshold_direction'],
        'threshold_unit': row['threshold_unit'],
        'status': row['status'],
        'timestamp': row['timestamp'],
        'section_ref': row['section_ref'],
    }, sort_keys=True, separators=(',', ':'))
    recomputed = hashlib.sha256(canonical.encode()).hexdigest()
    stored = row['evidence_hash']
    if recomputed == stored:
        match = 'VERIFIED'
        verified += 1
    else:
        match = 'TAMPERED'
        tampered += 1
    print('ID %-3s | %-35s | %-9s | %s' % (
        row['id'],
        row['parameter'][:35],
        row['status'],
        match,
    ))

print('=' * 70)
print('Total: %d verified, %d tampered, %d records' % (verified, tampered, len(rows)))
