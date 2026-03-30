"""
RegOS Demo Script: Reset After Tampering Demo
Deletes the breach database so a fresh query produces clean records.
"""
import os

DB_PATH = '/app/backend/data/regos_breaches.db'

print()
print('  Resetting Compliance Database')
print('  ' + '=' * 40)
print()

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
    print('  Database removed.')
    print('  Next compliance query will create fresh,')
    print('  properly-hashed records.')
else:
    print('  Database not found (already clean).')

print()
print('  Ready for a new demo run.')
print()
