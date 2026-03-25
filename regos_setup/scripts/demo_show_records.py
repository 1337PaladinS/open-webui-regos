"""
RegOS Demo Script: Show All Compliance Records
Displays all threshold evaluation records with their integrity status.
"""
import sqlite3, json, hashlib

DB_PATH = '/app/backend/data/regos_breaches.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT * FROM threshold_evaluations ORDER BY id').fetchall()
conn.close()

if not rows:
    print()
    print('  No compliance records found.')
    print('  Ask RegOS a compliance question first, e.g.:')
    print('    "What are the BOD limits for industrial wastewater?"')
    print()
    exit()

print()
print('  RegOS Compliance Records — SHA-256 Integrity Check')
print('  ' + '=' * 62)
print()

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
        status = 'INTACT'
        verified += 1
    else:
        status = '** TAMPERED **'
        tampered += 1

    print('  Record #%-3s  %-30s  %s' % (
        row['id'],
        row['parameter'][:30],
        status,
    ))
    print('              Status: %-10s  Value: %s %s' % (
        row['status'],
        row['user_value'],
        row['threshold_unit'],
    ))
    print('              Hash:   %s...' % stored[:24])
    print()

print('  ' + '=' * 62)
if tampered == 0:
    print('  Result: ALL %d records verified intact.' % verified)
    print('  No evidence of tampering detected.')
else:
    print('  WARNING: %d of %d records show signs of tampering!' % (tampered, verified + tampered))
    print('  Data integrity has been compromised.')
print()
