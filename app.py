from flask import Flask, request, jsonify, render_template, redirect, url_for, session, Response, g
import sqlite3
import csv
import os
from datetime import datetime,date, timezone, timedelta
from functools import wraps
import io
import pytz

app = Flask(__name__)
secret_key = os.urandom(24)
app.secret_key = secret_key

DATABASE = os.path.join(os.path.dirname(__file__), 'eshop.db')

def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.executescript('''
        CREATE TABLE IF NOT EXISTS clients (
            NRIC CHAR(9),
            client_name TEXT NOT NULL,
            client_DOB DATE,
            PRIMARY KEY (NRIC)
        );

        CREATE TABLE IF NOT EXISTS inventory_movements (
            movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            movement TEXT NOT NULL,
            movement_type TEXT CHECK(movement_type IN ('redeemed', 'damaged', 'donation', 'expired', 'purchase', 'office consumption', 'return', 'other programme consumption')),
            movement_source TEXT,
            movement_quantity INTEGER,
            movement_date DATE,
            movement_remarks TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            product_id TEXT NOT NULL,
            name TEXT,
            brand TEXT,
            bundle_size TEXT,
            price REAL,
            total_quantity INTEGER,
            PRIMARY KEY (product_id)
        );

        CREATE TABLE IF NOT EXISTS shop_items (
            product_id TEXT,
            display_name TEXT NOT NULL,
            display_price INTEGER,
            item_image TEXT NOT NULL,
            PRIMARY KEY (display_name),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        );

        CREATE TABLE IF NOT EXISTS staff (
            Username TEXT NOT NULL,
            Password TEXT
        );

        CREATE TABLE IF NOT EXISTS transaction_details (
            detail_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER,
            product_id TEXT,
            transaction_quantity INTEGER,
            FOREIGN KEY (product_id) REFERENCES products(product_id),
            FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_ID)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            transaction_ID INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date DATE,
            NRIC CHAR(9),
            client_name TEXT,
            total_spent INTEGER,
            FOREIGN KEY (NRIC) REFERENCES clients(NRIC)
        );

        -- Create triggers
        CREATE TRIGGER IF NOT EXISTS adjust_quantity_on_movement
        AFTER INSERT ON inventory_movements
        FOR EACH ROW
        BEGIN
            UPDATE products
            SET total_quantity = total_quantity + CASE
                WHEN NEW.movement = 'in' THEN NEW.movement_quantity
                WHEN NEW.movement = 'out' THEN -NEW.movement_quantity
                ELSE 0
            END
            WHERE product_id = NEW.product_id;
        END;

        CREATE TRIGGER IF NOT EXISTS movement_on_transaction
        AFTER INSERT ON transaction_details
        FOR EACH ROW
        BEGIN
            INSERT INTO inventory_movements (
                product_id,
                movement,
                movement_type,
                movement_source,
                movement_quantity,
                movement_date,
                movement_remarks
            )
            VALUES (
                NEW.product_id,
                'out',
                'redeemed',
                'eshop',
                NEW.transaction_quantity,
                (SELECT transaction_date FROM transactions WHERE transaction_ID = NEW.transaction_id),
                'Auto-generated from transaction'
            );
        END;

        CREATE TRIGGER IF NOT EXISTS set_movement 
        BEFORE INSERT ON inventory_movements
        FOR EACH ROW
        BEGIN
            UPDATE inventory_movements
            SET movement = CASE
                WHEN NEW.movement_type IN ('donation', 'purchase', 'return in') THEN 'in'
                ELSE 'out'
            END
            WHERE rowid = NEW.rowid;
        END;

        ''')
        conn.commit()


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.before_request
def before_request():
    g.db = get_db()

@app.teardown_appcontext
def close_db(error):
    if 'db' in g:
        g.db.close()

#Query Operation
def query_db(query, args =(), single=False):
    with app.app_context():
        cur = get_db().execute(query, args)
        rv = cur.fetchall()
        cur.close()
        return (rv[0] if rv else None) if single else rv

#Write Operation
def insert_db(query, args=(), single=False):
    with app.app_context():
        db = get_db()
        try:
            cur = db.cursor()
            if single:
                cur.execute(query, args)
            else:
                cur.executemany(query, args)
            db.commit()
        except sqlite3.Error as e:
            db.rollback()
            print(f"An error occurred: {e}")
        finally:
            cur.close()

#Generates item details as a dictionary
def generate_items_dict():
    items_query = query_db('''
    SELECT
        si.product_id,
        si.display_name,
        si.display_price,
        si.item_image,
        p.total_quantity
    FROM
        shop_items si
    JOIN
        products p ON si.product_id = p.product_id
    ''')

    # Construct the list of dictionaries, items with <4 quantity are not included
    items_dict = [
        {
            "name": row['display_name'],
            "image": row['item_image'],
            "price": row['display_price'],
        }
        for row in items_query if row['total_quantity'] > 4
    ]
    return items_dict

def generate_stock_dict():
    stock_query = query_db('SELECT product_id, name, brand, bundle_size, total_quantity FROM products')
    stock_dict = [
        {
            "product_id": row['product_id'],
            "name": row['name'],
            "brand": row['brand'],
            "bundle_size": row['bundle_size'],
            "total_quantity": row['total_quantity']
        }
        for row in stock_query
    ]
    return stock_dict

init_db()
ITEMS = generate_items_dict()
generate_items_dict()

def get_current_gmt8_time():
    gmt8 = pytz.timezone('Asia/Singapore')  # GMT+8 timezone
    current_time = datetime.now(gmt8)
    return current_time.strftime('%d-%m-%Y %H:%M:%S')

# Authenticates log-in details from /login
def staff_authenticate(username, password):
    user = query_db('SELECT Username, Password FROM Staff WHERE UPPER(Username) = UPPER(?)', (username,), single=True)

    if user is None:
        return False

    if user['password'] != password:
        print('Incorrect Password')
        return False

    return True

def login_required(func):
    @wraps(func)
    def secure_function(*args, **kwargs):
        if "user" not in session:
            print("User not in session, redirecting to login.")
            return redirect(url_for("login"))
        print(f"{session['user']} is in session.")
        return func(*args, **kwargs)
    return secure_function

@app.route('/initialize-database')
def initialize_database():
    """Route to initialize the database only if it doesn't exist."""
    if not os.path.exists(DATABASE):
        init_db()
        return "Database created and initialized!"
    else:
        return "Database already exists."
    
@app.route('/', methods=['GET', "POST"])
def index():
    return redirect(url_for("login"))

@app.route('/login', methods=['GET', "POST"])
def login():
    session.pop('user', None)
    print('session user popped')
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        if username:
            if staff_authenticate(username, password):
                session['user'] = username
                print(f"User has logged in: {username}")
                return redirect(url_for('mainpage'))
            else:
                print(f"Username {username} not found in database")
        else:
            print('No username provided')
    return render_template('login.html')

@app.route('/mainpage', methods = ['GET', 'POST'])
@login_required
def mainpage():
    return render_template('mainpage.html', items = ITEMS)

@app.route('/query', methods = ['GET', 'POST'])
def update_status():
    message = ""
    if request.method == "POST":
        nric = request.form.get('nric', '').upper().strip()
        client = query_db('SELECT client_name, client_DOB FROM clients where NRIC = ?', (nric,), single= True)
        if client:
            now = datetime.now()
            redemption_date_query = query_db('SELECT transaction_date FROM transactions where NRIC = ? ORDER BY transaction_date DESC LIMIT 1', (nric,), single= True)
            if redemption_date_query:
                client_yob = datetime.strptime(client['client_DOB'], "%d/%m/%Y").year
                current_year = now.year
                client_age = int(current_year - client_yob)
                session['nric'] = nric       # Stores the request-cycle NRIC in flask's current session
                redemption_date = redemption_date_query[0]
                message = f"{client['client_name']} last redeemed on {redemption_date}."
                response = jsonify({'message': message, 'age': client_age})
                print(f"{session['user']} queried: {message}")
            else:
                client_yob = datetime.strptime(client['client_DOB'], "%d/%m/%Y").year
                current_year = now.year
                client_age = int(current_year - client_yob)
                message = f"{client['client_name']}"
                session['nric'] = nric       # Stores the request-cycle NRIC in flask's current session
                response = jsonify({'message': message, 'age': client_age})
                print(f"{session['user']} queried: {message}")
        else:
            message = f"NRIC not found. Please enter new NRIC."
            response = jsonify({'message': message})
            print(f"{session['user']} queried {nric}: {message}")
    return response

@app.route('/check_out', methods = ['GET', 'POST'])
def check_out():
    try:
        data = request.json['data']
        summary = [
            {
                "ID": query_db('SELECT product_id FROM shop_items WHERE display_name = ?', (entry['ItemName'],), single= True)['product_id'],
                "Quantity": int(entry['ItemQuantity']),
                "Price": int(entry['TotalPrice']),
                "TotalSpent": int(entry['TotalSpent'])
            }
            for entry in data
            ]
        print(f"{session['user']} attempting to check out: {summary}")
        update_db(summary) # Update transaction log with the data
        return jsonify({'message': 'Transaction processed successfully!'})
    except Exception as e:
        print(f"Check-out Error: {e}")
        return jsonify({'message': 'Error processing transaction'}), 500

def update_db(summary):
    nric = session.get('nric')
    transaction_date = get_current_gmt8_time()
    client_name = query_db('SELECT client_name FROM clients where NRIC = ?', (nric,), single= True)['client_name']
    total_spent = summary[0]['TotalSpent'] if summary else 0
    insert_db('INSERT INTO transactions (transaction_date, NRIC, client_name, total_spent) VALUES (?, ?, ?, ?)',(transaction_date, nric, client_name, total_spent), single=True)
    for item in summary:
        transaction_id = query_db('SELECT transaction_id FROM transactions ORDER BY transaction_id DESC LIMIT 1', single = True)[0]
        insert_db('INSERT INTO transaction_details (transaction_id, product_id, transaction_quantity) VALUES (?, ?, ?)',(transaction_id, item['ID'], item['Quantity']), single=True)

@app.route('/admin', methods = ['GET', 'POST'])
@login_required
def admin():
    return render_template('admin.html')

@app.route('/download_csv')
def download_csv():
    data = query_db('SELECT * from Transactions', single = False)
    headers = data[0].keys()
    rows = data
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    response = Response(output.getvalue(),mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=transactions.csv'
    return response

@app.route('/download_inventory')
def download_inventory():
    data = query_db('SELECT * from Products', single = False)
    headers = data[0].keys()
    rows = data
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    response = Response(output.getvalue(),mimetype='text/csv')
    response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
    return response

@app.route('/orders', methods = ['GET', 'POST'])
def orders():
    return render_template('orders.html')

@app.route('/notify')
def notify():
    return jsonify(message='You have a new transaction!')

@app.route('/fetch')
def fetch_transaction():
    req_type = request.args.get('type', 'latest')
    req_id = request.args.get('id', None)
    print(f"Request type: {req_type}, Request ID: {req_id}")  # Debug print

    transaction_id = None
    if req_type == 'latest':
        result = query_db('SELECT transaction_id FROM transactions ORDER BY transaction_id DESC LIMIT 1', single=True)
        if result:
            transaction_id = result[0]
    elif req_type == 'previous' and req_id:
        transaction_id = int(req_id) - 1
    elif req_type == 'next' and req_id:
        transaction_id = int(req_id) + 1

    if transaction_id is None:
        return jsonify({'error': 'Transaction not found'}), 404

    transaction_details = query_db(
        '''SELECT si.display_name, td.transaction_quantity
           FROM transaction_details td
           JOIN shop_items si ON td.product_id = si.product_id
           WHERE td.transaction_id = ?''', (transaction_id,), single=False)

    transaction_date = query_db('SELECT transaction_date FROM transactions WHERE transaction_id = ?', (transaction_id,), single=True)
    client_name = query_db('SELECT client_name FROM transactions WHERE transaction_id = ?', (transaction_id,), single=True)

    if transaction_date is None or client_name is None:
        return jsonify({'error': 'Transaction details not found'}), 404

    transaction_date = transaction_date[0]
    client_name = client_name[0]

    transaction_dict = {
        "client_name": client_name,
        "transaction_id": transaction_id,
        "transaction_date": transaction_date,
        "details": [
            {"item": row['display_name'], "quantity": row['transaction_quantity']}
            for row in transaction_details
        ]
    }
    print(transaction_dict)
    return jsonify(transaction_dict)


@app.route('/inventory', methods = ['GET', 'POST'])
def inventory():
    generate_stock_dict()
    STOCK = generate_stock_dict()
    return render_template('inventory.html', stock = STOCK)

@app.route('/update_stock', methods=['POST'])
def update_stock():
    try:
        # Get the JSON data from the request
        data = request.get_json() 
        movement_list = data.get('movementList', [])  # Default to empty list if 'movementList' key is missing
        local_offset = timezone(timedelta(hours=8))
        movement_date = datetime.now(local_offset).strftime('%d-%m-%Y %H:%M:%S')
        print("Incoming request JSON:", data)
        print("Parsed movementList:", movement_list)
        movement_in = {'purchase', 'donation'}
        # Iterate over each item in the movementList
        for entry in movement_list:
            if 'MovementType' in entry:
                # Update movement_type for subsequent entries
                movement_type = entry['MovementType'].lower()
            else:
                # Process individual product details
                product_id = entry.get('productID')
                movement_quantity = entry.get('movementQuantity')
                movement_source = entry.get('movementSource')
                movement_remarks = entry.get('movementRemarks')
                movement = 'in' if movement_type in movement_in else 'out'
                
                # Insert into the database
                insert_db(
                    'INSERT INTO inventory_movements (product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks),
                    single=True
                )
                print(f"Product ID: {product_id}, Quantity: {movement_quantity}, Source: {movement_source}, Remarks: {movement_remarks}")

        return jsonify({'message': 'Transaction processed successfully!'})

    except Exception as e:
        print(f"Check-out Error: {e}")
        return jsonify({'message': 'Error processing transaction'}), 500


if __name__ == '__main__':
    app.run()