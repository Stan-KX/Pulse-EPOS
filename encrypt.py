import sqlite3
import os
import base64
import hashlib
import secrets

DATABASE = 'eshop.db'

# Generate a 32-byte pepper (256 bits)
# pepper = secrets.token_bytes(32)

# pepper_hex = os.environ.get("ESHOP_PEPPER_HEX")  # 32 bytes = 256 bits
# print(pepper_hex)
# pepper = bytes.fromhex(pepper_hex)
# print(pepper)
# CLIENT_ID = os.getenv("CLIENT_ID")
# CLIENT_SECRET = os.getenv("CLIENT_SECRET")
# TENANT_ID = os.getenv("TENANT_ID", "common")  # "common" for multi-tenant, or your tenant GUID
# print(CLIENT_ID, CLIENT_SECRET, TENANT_ID)

secret_key = secrets.token_hex(32)  # 64 hex characters
print(secret_key)
# def hash_nric(nric, pepper):
#     nric = nric.lower()
#     combined = nric.encode('utf-8') + pepper
#     return hashlib.sha256(combined).hexdigest()

# with sqlite3.connect(DATABASE) as conn:
#     cursor = conn.cursor()
#     # Migrate clients table
#     cursor.execute("SELECT rowid, NRIC FROM clients")
#     for rowid, nric in cursor.fetchall():
#         nric_hash = hash_nric(nric, pepper)
#         cursor.execute(
#             "UPDATE clients SET nric = ? WHERE rowid = ?",
#             (nric_hash, rowid)
#         )
#     # Migrate transactions table
#     cursor.execute("SELECT rowid, NRIC FROM transactions")  
#     for rowid, nric in cursor.fetchall():
#         nric_hash = hash_nric(nric, pepper)
#         cursor.execute(
#             "UPDATE transactions SET NRIC = ? WHERE rowid = ?",
#             (nric_hash, rowid)
#         )
#     conn.commit()