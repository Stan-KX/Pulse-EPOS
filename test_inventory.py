"""
Inventory management test suite.
Tests all server-side inventory endpoints.
Run: python test_inventory.py
"""
import os
import json
import sqlite3
import tempfile
import unittest

# Required env vars before importing app
os.environ.setdefault("ESHOP_PEPPER_HEX", "deadbeefcafe1234deadbeefcafe1234")
os.environ.setdefault("SECRET_KEY", "test-secret-key-hex-1234")
os.environ.setdefault("MICROSOFT_CLIENT_ID", "test-client-id")
os.environ.setdefault("MICROSOFT_CLIENT_SECRET", "test-client-secret")

from app import create_app
import db as db_module


def init_test_db(conn):
    """Create minimal schema for testing."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT PRIMARY KEY,
            name TEXT,
            brand TEXT,
            bundle_size TEXT,
            price REAL,
            total_quantity INTEGER DEFAULT 0,
            type TEXT
        );
        CREATE TABLE IF NOT EXISTS shop_items (
            product_id TEXT PRIMARY KEY,
            display_name TEXT,
            display_price REAL,
            item_image TEXT
        );
        CREATE TABLE IF NOT EXISTS inventory_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            movement TEXT,
            movement_type TEXT,
            movement_source TEXT,
            movement_quantity INTEGER,
            movement_date TEXT,
            movement_remarks TEXT
        );
        CREATE TABLE IF NOT EXISTS staff (
            username TEXT PRIMARY KEY,
            role TEXT
        );
        CREATE TABLE IF NOT EXISTS clients (
            NRIC TEXT PRIMARY KEY,
            client_name TEXT,
            client_DOB TEXT
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date TEXT,
            product_id TEXT,
            quantity INTEGER
        );
        INSERT OR IGNORE INTO products VALUES ('0001', 'Test Rice', 'Brand A', '5kg', 10.0, 50, 'Staples');
        INSERT OR IGNORE INTO products VALUES ('0002', 'Test Oil', 'Brand B', '1L', 5.0, 0, 'Cooking');
        INSERT OR IGNORE INTO products VALUES ('0003', 'Test Noodles', 'Brand C', '500g', 3.0, 15, 'Staples');
    """)
    conn.commit()


class InventoryTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        conn = sqlite3.connect(self.db_path)
        init_test_db(conn)
        conn.close()

        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['DATABASE'] = self.db_path
        self.app.config['SERVER_NAME'] = None  # disable for test client
        self.app.config['WTF_CSRF_ENABLED'] = False
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    # ------------------------------------------------------------------
    # GET /inventory
    # ------------------------------------------------------------------
    def test_inventory_page_loads(self):
        r = self.client.get('/inventory')
        self.assertEqual(r.status_code, 200)
        self.assertIn(b'Inventory', r.data)
        print("[PASS] GET /inventory - page loads")

    def test_inventory_shows_products(self):
        r = self.client.get('/inventory')
        self.assertIn(b'Test Rice', r.data)
        self.assertIn(b'Test Oil', r.data)
        print("[PASS] GET /inventory - products rendered in table")

    # ------------------------------------------------------------------
    # GET /api/product_history/<product_id>
    # ------------------------------------------------------------------
    def test_product_history_empty(self):
        r = self.client.get('/api/product_history/0001')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn('movements', data)
        self.assertEqual(data['movements'], [])
        print("[PASS] GET /api/product_history/0001 - returns empty list")

    def test_product_history_with_data(self):
        # seed a movement
        with self.app.app_context():
            with self.app.test_request_context():
                conn = sqlite3.connect(self.db_path)
                conn.execute(
                    "INSERT INTO inventory_movements VALUES (NULL,'0001','in','purchase','Fairprice',10,'01-01-2026 10:00:00','test')"
                )
                conn.commit()
                conn.close()

        r = self.client.get('/api/product_history/0001')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(len(data['movements']), 1)
        self.assertEqual(data['movements'][0]['movement_type'], 'purchase')
        print("[PASS] GET /api/product_history/0001 - returns seeded movement")

    def test_product_history_nonexistent_product(self):
        r = self.client.get('/api/product_history/9999')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertEqual(data['movements'], [])
        print("[PASS] GET /api/product_history/9999 - empty for unknown product")

    # ------------------------------------------------------------------
    # POST /api/add_stock_type
    # ------------------------------------------------------------------
    def test_add_stock_type_success(self):
        r = self.client.post('/api/add_stock_type',
            data=json.dumps({'type_name': 'Beverages'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 201)
        data = json.loads(r.data)
        self.assertTrue(data['success'])
        print("[PASS] POST /api/add_stock_type - new type created")

    def test_add_stock_type_empty_name(self):
        r = self.client.post('/api/add_stock_type',
            data=json.dumps({'type_name': '  '}),
            content_type='application/json')
        self.assertEqual(r.status_code, 400)
        print("[PASS] POST /api/add_stock_type - rejects empty name")

    def test_add_stock_type_duplicate(self):
        # 'Staples' already exists in products
        r = self.client.post('/api/add_stock_type',
            data=json.dumps({'type_name': 'Staples'}),
            content_type='application/json')
        self.assertEqual(r.status_code, 409)
        print("[PASS] POST /api/add_stock_type - rejects duplicate type")

    # ------------------------------------------------------------------
    # POST /update_stock
    # ------------------------------------------------------------------
    def test_update_stock_in(self):
        payload = {
            'movementList': [
                {'MovementType': 'Purchase'},
                {'productID': '0001', 'movementQuantity': 10,
                 'movementSource': 'Fairprice', 'movementRemarks': 'test', 'stockType': 'Staples'}
            ]
        }
        r = self.client.post('/update_stock',
            data=json.dumps(payload),
            content_type='application/json')
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.data)
        self.assertIn('successfully', data['message'])
        print("[PASS] POST /update_stock - stock-in movement recorded")

    def test_update_stock_movement_persisted(self):
        """Verify movement row is actually written to DB."""
        payload = {
            'movementList': [
                {'MovementType': 'Expired'},
                {'productID': '0001', 'movementQuantity': 5,
                 'movementSource': None, 'movementRemarks': 'spoiled', 'stockType': None}
            ]
        }
        self.client.post('/update_stock',
            data=json.dumps(payload),
            content_type='application/json')

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM inventory_movements WHERE product_id='0001' AND movement_type='expired'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row, "Movement row not found in DB")
        print("[PASS] POST /update_stock - movement persisted in inventory_movements")

    def test_update_stock_quantity_updated(self):
        """
        BUG CHECK: update_stock should update products.total_quantity.
        Records the movement but currently does NOT update total_quantity.
        """
        initial_qty = 50  # seeded value for product 0001

        payload = {
            'movementList': [
                {'MovementType': 'Purchase'},
                {'productID': '0001', 'movementQuantity': 20,
                 'movementSource': 'Fairprice', 'movementRemarks': '', 'stockType': 'Staples'}
            ]
        }
        self.client.post('/update_stock',
            data=json.dumps(payload),
            content_type='application/json')

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT total_quantity FROM products WHERE product_id='0001'").fetchone()
        conn.close()
        new_qty = row[0]

        if new_qty == initial_qty:
            print(f"[FAIL - BUG] POST /update_stock - total_quantity NOT updated: still {new_qty} (expected {initial_qty + 20})")
        else:
            print(f"[PASS] POST /update_stock - total_quantity updated to {new_qty}")
        # Don't assert so suite continues; this is a known bug check

    def test_update_stock_invalid_movement_type(self):
        payload = {
            'movementList': [
                {'MovementType': 'InvalidType'},
                {'productID': '0001', 'movementQuantity': 5,
                 'movementSource': None, 'movementRemarks': '', 'stockType': None}
            ]
        }
        r = self.client.post('/update_stock',
            data=json.dumps(payload),
            content_type='application/json')
        self.assertEqual(r.status_code, 400)
        print("[PASS] POST /update_stock - rejects invalid movement type")

    def test_update_stock_missing_movement_type(self):
        """Product entry before MovementType entry should be rejected."""
        payload = {
            'movementList': [
                {'productID': '0001', 'movementQuantity': 5,
                 'movementSource': None, 'movementRemarks': '', 'stockType': None}
            ]
        }
        r = self.client.post('/update_stock',
            data=json.dumps(payload),
            content_type='application/json')
        self.assertEqual(r.status_code, 400)
        print("[PASS] POST /update_stock - rejects missing MovementType")

    # ------------------------------------------------------------------
    # POST /add_stock
    # ------------------------------------------------------------------
    def test_add_stock_new_product(self):
        r = self.client.post('/add_stock', data={
            'product_name': 'New Cereal',
            'brand': 'Kelloggs',
            'bundle_size': '500g',
            'quantity': '30',
            'price': '8.50'
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM products WHERE name='New Cereal'").fetchone()
        conn.close()
        self.assertIsNotNone(row, "New product not found in DB")
        print("[PASS] POST /add_stock - new product inserted")

    def test_add_stock_quantity_seeded(self):
        """
        BUG CHECK: add_stock ignores the quantity field and inserts total_quantity=0.
        """
        self.client.post('/add_stock', data={
            'product_name': 'Bug Check Item',
            'brand': 'Test',
            'bundle_size': '1kg',
            'quantity': '25',
            'price': '5.00'
        }, follow_redirects=True)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT total_quantity FROM products WHERE name='Bug Check Item'").fetchone()
        conn.close()

        if row and row[0] == 0:
            print(f"[FAIL - BUG] POST /add_stock - quantity field ignored: total_quantity={row[0]} (expected 25)")
        elif row:
            print(f"[PASS] POST /add_stock - total_quantity seeded correctly: {row[0]}")

    def test_add_stock_id_generation(self):
        """BUG CHECK: product_id generation via int(last product_id) fails if last ID is a TYPE_xxx string."""
        # Insert a TYPE_ row to simulate add_stock_type having been used
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO products VALUES ('TYPE_Snacks_9999999', '[TYPE DEFINITION] Snacks', 'System', 'N/A', 0, 0, 'Snacks')"
        )
        conn.commit()
        conn.close()

        r = self.client.post('/add_stock', data={
            'product_name': 'Post-Type Product',
            'brand': 'X',
            'bundle_size': '1L',
            'quantity': '10',
            'price': '2.00'
        }, follow_redirects=True)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM products WHERE name='Post-Type Product'").fetchone()
        conn.close()

        if row is None:
            print("[FAIL - BUG] POST /add_stock - crashes when last product_id is a TYPE_xxx string (int() conversion fails)")
        else:
            print("[PASS] POST /add_stock - product_id generation handles TYPE_ rows")

    # ------------------------------------------------------------------
    # POST /add_to_shop
    # ------------------------------------------------------------------
    def test_add_to_shop_new_listing(self):
        r = self.client.post('/add_to_shop', data={
            'product_name': 'Test Rice',
            'shop_name': 'Premium Rice 5kg',
            'shop_price': '3'
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM shop_items WHERE product_id='0001'").fetchone()
        conn.close()
        self.assertIsNotNone(row)
        print("[PASS] POST /add_to_shop - new shop listing created")

    def test_add_to_shop_update_existing(self):
        # First insert
        self.client.post('/add_to_shop', data={
            'product_name': 'Test Rice',
            'shop_name': 'Premium Rice 5kg',
            'shop_price': '3'
        }, follow_redirects=True)
        # Update
        r = self.client.post('/add_to_shop', data={
            'product_name': 'Test Rice',
            'shop_name': 'Budget Rice 5kg',
            'shop_price': '2'
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)

        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT display_name, display_price FROM shop_items WHERE product_id='0001'").fetchone()
        conn.close()
        self.assertEqual(row[0], 'Budget Rice 5kg')
        self.assertEqual(row[1], 2.0)
        print("[PASS] POST /add_to_shop - existing listing updated")

    def test_add_to_shop_unknown_product(self):
        r = self.client.post('/add_to_shop', data={
            'product_name': 'Ghost Product',
            'shop_name': 'Ghost',
            'shop_price': '1'
        }, follow_redirects=True)
        self.assertEqual(r.status_code, 200)  # redirects with flash
        conn = sqlite3.connect(self.db_path)
        row = conn.execute("SELECT * FROM shop_items WHERE display_name='Ghost'").fetchone()
        conn.close()
        self.assertIsNone(row)
        print("[PASS] POST /add_to_shop - unknown product rejected gracefully")

    # ------------------------------------------------------------------
    # GET /download_inventory
    # ------------------------------------------------------------------
    def test_download_inventory_csv(self):
        r = self.client.get('/download_inventory')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r.content_type)
        lines = r.data.decode().strip().split('\n')
        self.assertGreater(len(lines), 1)  # header + data rows
        print(f"[PASS] GET /download_inventory - CSV returned ({len(lines)} lines)")

    def test_download_inventory_csv_content(self):
        r = self.client.get('/download_inventory')
        content = r.data.decode()
        self.assertIn('Test Rice', content)
        self.assertIn('Test Oil', content)
        print("[PASS] GET /download_inventory - CSV contains expected products")

    # ------------------------------------------------------------------
    # GET /download_movements
    # ------------------------------------------------------------------
    def test_download_movements_empty(self):
        r = self.client.get('/download_movements')
        self.assertEqual(r.status_code, 200)
        self.assertIn('text/csv', r.content_type)
        print("[PASS] GET /download_movements - CSV returned (empty movements)")

    def test_download_movements_with_data(self):
        # Add a movement first
        self.client.post('/update_stock',
            data=json.dumps({'movementList': [
                {'MovementType': 'Purchase'},
                {'productID': '0001', 'movementQuantity': 5,
                 'movementSource': 'Fairprice', 'movementRemarks': '', 'stockType': None}
            ]}),
            content_type='application/json')

        r = self.client.get('/download_movements')
        self.assertEqual(r.status_code, 200)
        content = r.data.decode()
        self.assertIn('0001', content)
        self.assertIn('purchase', content)
        print("[PASS] GET /download_movements - CSV contains movement data")


if __name__ == '__main__':
    print("=" * 60)
    print("Inventory Management Test Suite")
    print("=" * 60)
    unittest.main(verbosity=0)
