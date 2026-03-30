"""
RegOS Demo Script: Simulate Tampering
Changes the user_value of Record #1 to simulate someone editing compliance data.
This demonstrates what happens when a bad actor modifies a record.
"""
import sqlite3

DB_PATH = '/app/backend/data/regos_breaches.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

# Get first record
row = conn.execute('SELECT id, parameter, user_value FROM threshold_evaluations ORDER BY id LIMIT 1').fetchone()

if not row:
    print()
    print('  No records to tamper. Run a compliance query first.')
    print()
    exit()

original_value = row['user_value']
tampered_value = 999.0

print()
print('  Simulating Tampering on Record #%s' % row['id'])
print('  ' + '=' * 50)
print()
print('  Parameter:      %s' % row['parameter'])
print('  Original value: %s' % original_value)
print('  Tampered value: %s' % tampered_value)
print()

conn.execute(
    'UPDATE threshold_evaluations SET user_value = ? WHERE id = ?',
    (tampered_value, row['id'])
)
conn.commit()
conn.close()

print('  Done. The record has been altered.')
print('  The SHA-256 hash was NOT updated (as a real')
print('  attacker would not know the hashing formula).')
print()
print('  Now run the integrity check to see the detection.')
print()
