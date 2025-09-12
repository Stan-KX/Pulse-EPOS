from flask import Flask, flash, request, jsonify, render_template, redirect, url_for, session, Response, g, Blueprint, current_app
import sqlite3
import csv
import os
from datetime import datetime,date, timezone, timedelta
from functools import wraps
import io
import pytz
import hashlib
import re
import dash
from dash import html, dcc, dash_table
import plotly.express as px
import pandas as pd
from authlib.integrations.flask_client import OAuth
import os
from auth.utils import login_required, user_required
import db


def create_app():
    app = Flask(__name__)
    app.config.from_object("config.Config")
    app.config['SERVER_NAME'] = 'localhost:5000'  # Set the server name for URL generation, remove for prod

    # ✅ Import and register blueprint
    from auth import auth_bp, init_oauth
    # print("Registering auth_bp blueprint...")
    app.register_blueprint(auth_bp, url_prefix="/auth")

    # ✅ Initialize OAuth
    print("Initializing OAuth...")
    init_oauth(app)

    @app.before_request
    def before_request():
        g.db = db.get_db()

    @app.teardown_appcontext
    def close_db(error):
        db.close_db(error)

    #Generates item details as a dictionary
    def generate_items_dict():
        # Fetch all required columns in a single query
        items_query = db.query_db('''
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

        # Construct the list of dictionaries, items with <4 quantity are not included (Replace with business logic)
        items_dict = [
            {
                "name": row['display_name'],
                "image": row['item_image'],
                "price": row['display_price'],
            }
            for row in items_query if row['total_quantity'] > 4
        ]
        return items_dict

    def generate_stock_types():
        stock_types_query = db.query_db('SELECT DISTINCT type FROM products',single=False)
        stock_types = [row['type'] for row in stock_types_query]
        return stock_types
        
    def generate_stock_dict():
        stock_query = db.query_db('''
            SELECT p.product_id, p.name, p.brand, p.bundle_size, p.price, p.total_quantity, p.type
            FROM products p
            ORDER BY 
                CASE 
                    WHEN p.product_id IN (SELECT si.product_id FROM shop_items si) THEN 0
                    ELSE 1
                END,
                p.product_id
        ''')

        stock_dict = [
            {
                "product_id": row['product_id'],
                "name": row['name'],
                "brand": row['brand'],
                "bundle_size": row['bundle_size'],
                "total_quantity": row['total_quantity'],
                "type": row['type'],
            }
            for row in stock_query
        ]

        return stock_dict

    def generate_shop_dict():
        shop_query = db.query_db('''
            SELECT product_id, display_name, display_price FROM shop_items
        ''')

        shop_dict = [
            {
                "product_id": row['product_id'],
                "display_name": row['display_name'],
                "display_price": row['display_price'],
                "purchase_limit": 2  # Default purchase limit
            }
            for row in shop_query
        ]

        return shop_dict

    # SHA-256 hashing with pepper for PII
    pepper_hex = os.environ.get("ESHOP_PEPPER_HEX")
    pepper = bytes.fromhex(pepper_hex)
    def hash_nric(nric, pepper):
        nric = nric.lower()
        combined = nric.encode('utf-8') + pepper
        return hashlib.sha256(combined).hexdigest()

    def get_current_gmt8_time():
        gmt8 = pytz.timezone('Asia/Singapore')  # GMT+8 timezone
        current_time = datetime.now(gmt8)
        return current_time.strftime('%d-%m-%Y %H:%M:%S')

    # Authenticates log-in details from /login, deprecated
    # def staff_authenticate(username, password):
    #     user = db.query_db('SELECT Username, Password FROM Staff WHERE UPPER(Username) = UPPER(?)', (username,), single=True)

    #     if user is None:
    #         return False

    #     if user['password'] != password:
    #         print('incorrect password')
    #         return False

    #     return True

    @app.route('/', methods=['GET', "POST"])
    def index():
        return redirect(url_for("login"))

    @app.route('/login', methods=['GET', "POST"])
    def login():
        session.pop("user", None)
        # if request.method == "POST":                   # Deprecated 
        #     username = request.form.get("username")
        #     password = request.form.get("password")
        #     if username and staff_authenticate(username, password):
        #         session["user"] = {
        #             "id": "deprecated_flow",
        #             "name": username,
        #             "email": username
        #         }
        # flash(f"Welcome, {username}!", "success")
        # return redirect(url_for("mainpage"))
        return render_template("login.html", show_sidebar=False)

    @app.route('/mainpage', methods = ['GET', 'POST'])
    @login_required
    def mainpage():
        ITEMS = generate_items_dict()
        generate_items_dict()
        return render_template('mainpage.html', items = ITEMS)

    @app.route('/query', methods=['POST'])
    def query_client():
        queried_nric = request.form.get('nric', '').strip().upper()
        nric_hash = hash_nric(queried_nric, pepper)
        client = db.query_db(
            'SELECT client_name, client_DOB FROM clients WHERE NRIC = ?',
            (nric_hash,),
            single=True
        )

        if not client:
            message = f"{queried_nric} not found. Please enter new NRIC."
            response = {'message': message, 'age': None, 'type': 'NF'} # Not Found
            current_app.logger.info(f"{session.get('user')} queried {queried_nric}: {message}")
            return jsonify(response)

        now = datetime.strptime(get_current_gmt8_time(), '%d-%m-%Y %H:%M:%S')
        client_age = now.year - client['client_DOB']
        session['nric'] = nric_hash
        client_name = client['client_name']

        redemption = db.query_db(
            'SELECT transaction_date as redemption_date '
            'FROM transactions WHERE NRIC = ? '
            'ORDER BY transaction_ID DESC LIMIT 1',
            (nric_hash,),
            single=True
        )

        if redemption:
            redemption_date = datetime.strptime(redemption['redemption_date'], '%d-%m-%Y %H:%M:%S')
            if redemption_date.year == now.year and redemption_date.month == now.month:
                msg = f"{client_name} last redeemed on {redemption_date}. Cannot redeem again this month."
                resp_type = 'R'  #Redeemed this month
            else:
                msg = f"{client['client_name']} last redeemed on {redemption_date}."
                resp_type = 'NR' # Not redeemed this month
        else:
            msg = f"{client['client_name']}"
            resp_type = 'N' # New client

        response = {'name': client_name, 'message': msg, 'age': client_age, 'type': resp_type}
        current_app.logger.info(f"{session.get('user')} queried: {msg}")
        return jsonify(response)

    @app.route('/check_out', methods = ['GET', 'POST'])
    def check_out():
        try:
            data = request.json['data']
            summary = [
                {
                    "ID": db.query_db('SELECT product_id FROM shop_items WHERE display_name = ?', (entry['ItemName'],), single= True)['product_id'],
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
        client_name = db.query_db('SELECT client_name FROM clients where NRIC = ?', (nric,), single= True)['client_name']
        total_spent = summary[0]['TotalSpent'] if summary else 0
        db.insert_db('INSERT INTO transactions (transaction_date, client_name, NRIC, total_spent) VALUES (?, ?, ?, ?)',(transaction_date, client_name, nric, total_spent), single=True)
        for item in summary:
            transaction_id = db.query_db('SELECT transaction_id FROM transactions ORDER BY transaction_id DESC LIMIT 1', single = True)[0]
            db.insert_db('INSERT INTO transaction_details (transaction_id, product_id, transaction_quantity) VALUES (?, ?, ?)',(transaction_id, item['ID'], item['Quantity']), single=True)

    @app.route('/admin', methods = ['GET', 'POST'])
    @login_required
    def admin():
        return render_template('admin.html')

    
    @app.route('/download_csv')
    @login_required
    def download_csv():
        data = db.query_db('SELECT transaction_date, client_name, total_spent FROM Transactions', single = False)
        headers = data[0].keys()
        rows = data
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        response = Response(output.getvalue(),mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=transactions.csv'
        return response

    @login_required
    @app.route('/download_inventory')
    def download_inventory():
        data = db.query_db('SELECT * FROM Products', single = False)
        headers = data[0].keys()
        rows = data
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        response = Response(output.getvalue(),mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
        return response
    
    @login_required
    @app.route('/orders', methods = ['GET', 'POST'])
    def orders():
        return render_template('orders.html')

    @login_required
    @app.route('/fetch')
    def fetch_transaction():
        req_type = request.args.get('type', 'latest')
        req_id = request.args.get('id', None)
        print(f"Request type: {req_type}, Request ID: {req_id}")  # Debug print

        transaction_id = None
        if req_type == 'latest':
            result = db.query_db('SELECT transaction_id FROM transactions ORDER BY transaction_id DESC LIMIT 1', single=True)
            if result:
                transaction_id = result[0]
        elif req_type == 'previous' and req_id:
            transaction_id = int(req_id) - 1
        elif req_type == 'next' and req_id:
            transaction_id = int(req_id) + 1

        if transaction_id is None:
            return jsonify({'error': 'Transaction not found'}), 404

        transaction_details = db.query_db(
            '''SELECT si.display_name, td.transaction_quantity
            FROM transaction_details td
            JOIN shop_items si ON td.product_id = si.product_id
            WHERE td.transaction_id = ?''', (transaction_id,), single=False)

        transaction_date = db.query_db('SELECT transaction_date FROM transactions WHERE transaction_id = ?', (transaction_id,), single=True)
        client_name = db.query_db('SELECT client_name FROM transactions WHERE transaction_id = ?', (transaction_id,), single=True)

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
    
    #Endpoint for inventory management
    @app.route('/inventory', methods = ['GET', 'POST'])
    @user_required(['super-admin'])
    @login_required
    def inventory():
        generate_stock_dict()
        STOCK = generate_stock_dict()
        stock_types = generate_stock_types()
        return render_template('inventory.html', stock = STOCK, stock_types=stock_types, show_sidebar=True)

    #Endpoint for adding new clients
    @login_required
    @app.route('/add_client', methods=['GET', 'POST'])
    def add_client():
        if request.method == 'POST':
            queried_nric = request.form.get('nric', '').strip().upper()
            client_name = request.form.get('client_name', '').strip()
            client_dob = request.form.get('client_dob', '').strip()
            nric_hash = hash_nric(queried_nric,pepper)
            client = db.query_db('SELECT client_name, client_DOB FROM clients WHERE NRIC = ?', (nric_hash,), single=True)

            if queried_nric and client_name and client_dob:
                if not re.match(r"^[STFG]\d{7}[A-Z]$", queried_nric):
                    return jsonify({'message': 'Invalid NRIC format. Please enter a valid NRIC.'}), 400
                elif client:
                    return jsonify({'message': 'Client already exists.'}), 400
                elif not re.match(r"^\d{4}$", client_dob):
                    return jsonify({'message': 'Invalid date of birth format. Please enter a valid year.'}), 400
                else:
                    db.insert_db('INSERT INTO clients (NRIC, client_name, client_DOB) VALUES (?, ?, ?)', (nric_hash, client_name, client_dob), single=True)
                    return jsonify({'message': 'Client added successfully!'})
            else:
                return jsonify({'message': 'Please fill in all fields.'}), 400
            
        return render_template('add_client.html', show_sidebar=True)

    #Endpoint for updating stock levels
    @login_required
    @app.route('/update_stock', methods=['POST'])
    def update_stock():
        try:
            # Get the JSON data from the request
            data = request.get_json()
            movement_list = data.get('movementList', []) 
            local_offset = timezone(timedelta(hours=8))
            movement_date = datetime.now(local_offset).strftime('%d-%m-%Y %H:%M:%S')
            print("Incoming request JSON:", data)
            print("Parsed movementList:", movement_list)
            movement_in = {'purchase', 'donation', 'admin stock in'}                                                                               # Replace with business logic
            movement_out = {'redeemed', 'damaged', 'expired', 'office consumption', 'return', 'other programme consumption', 'admin stock out'}    # As above
            # Iterate over each item in the movementList
            movement_type = None  # store for later use

            for entry in movement_list:
                if 'MovementType' in entry:
                    # Set movement_type for subsequent product entries
                    movement_type = entry['MovementType'].lower()
                    print(f"movement_type: {movement_type}")
                    if movement_type not in movement_in and movement_type not in movement_out:
                        return jsonify({'message': 'Invalid stock in/stock out option'}), 400
                    continue  # go to next entry

                # Process product entries (no MovementType key)
                if not movement_type:
                    return jsonify({'message': 'MovementType must be specified before products'}), 400

                product_id = entry.get('productID')
                movement_quantity = entry.get('movementQuantity')
                movement_source = entry.get('movementSource')
                movement_remarks = entry.get('movementRemarks')
                movement = 'in' if movement_type in movement_in else 'out'

                db.insert_db(
                    'INSERT INTO inventory_movements (product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks) VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks),
                    single=True
                )
                print(f"Product ID: {product_id}, Quantity: {movement_quantity}, Source: {movement_source}, Remarks: {movement_remarks}")

            return jsonify({'message': 'Transaction processed successfully!'})

        except Exception as e:
            print(f"Check-out Error: {e}")
            return jsonify({'message': 'Error processing transaction'}), 500

    #Endpoint for shop configuration, WIP
    @app.route('/shop_config', methods = ['GET', 'POST'])
    @login_required
    def shop_config():
        generate_shop_dict()
        SHOP = generate_shop_dict()
        return render_template('shop_config.html', shop = SHOP, show_sidebar=True)

    @login_required
    @app.route("/add_stock", methods=["POST"])
    def add_stock():
        try:
            last = db.query_db("SELECT product_id FROM products ORDER BY product_id DESC LIMIT 1", single=True)
            next_id = int(last['product_id']) + 1 if last else 1
            product_id = f"{next_id:04d}"  # zero-padded 4 digits
            name = request.form.get("product_name").strip()
            brand = request.form.get("brand").strip()
            bundle_size = request.form.get("bundle_size").strip()
            quantity = int(request.form.get("quantity"))
            price =  float(request.form.get("price"))
            # movement_source = request.form.get("movement_source")
            # remarks = request.form.get("remarks")
            total_quantity = 0

            print(f'{product_id, name, brand, bundle_size, price, total_quantity}')
            # Insert into database
            db.insert_db(
                "INSERT INTO products (product_id, name, brand, bundle_size, price, total_quantity) VALUES (?, ?, ?, ?, ?, ?)",
                (product_id, name, brand, bundle_size, price, total_quantity), single = True
            )
            
            
            flash(f"{name} added successfully!")
            return redirect(url_for("inventory"))  # redirect back to inventory page
        except Exception as e:
            print(f"Error adding stock: {e}")
            flash("Error adding stock. Please try again or contact Administrator.", "danger")
            return redirect(url_for("inventory"))


    dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dashboard/')

    # Sample data and figure
    df = px.data.iris()
    fig = px.scatter(df, x="sepal_width", y="sepal_length", color="species")

    dash_app.layout = html.Div([
        html.H1("Dashboard embedded in Flask"),
        dcc.Graph(figure=fig)
    ])

    def get_monthly_transactions_for_years(year1, year2):
        query = """
        SELECT 
            substr(transaction_date, 7, 4) AS year,
            substr(transaction_date, 4, 2) AS month,
            COUNT(*) AS transaction_count
        FROM transactions
        WHERE substr(transaction_date, 7, 4) IN (?, ?)
        GROUP BY year, month
        ORDER BY year, month
        """
        results = db.query_db(query, (str(year1), str(year2)))
        return results  # List of tuples or dicts depending on your setup


    def get_monthly_transactions_for_years(year1, year2):
        query = """
        SELECT 
            substr(transaction_date, 7, 4) AS year,
            substr(transaction_date, 4, 2) AS month,
            COUNT(*) AS transaction_count
        FROM transactions
        WHERE substr(transaction_date, 7, 4) IN (?, ?)
        GROUP BY year, month
        ORDER BY year, month
        """
        results = db.query_db(query, (str(year1), str(year2)))
        return results  # List of tuples or dicts depending on your setup

    def get_low_stock_products(threshold):
        query = """
        SELECT p.product_id, p.name, p.total_quantity 
        FROM products p
        INNER JOIN shop_items s ON p.product_id = s.product_id
        WHERE p.total_quantity < ?
        """
        return db.query_db(query, (threshold,))

    # Dash layout with dynamic data for monthly transactions volume and low stocks display
    def serve_layout():
        with dash_app.server.app_context(): 
        # --- Monthly Transactions Data ---
            results = get_monthly_transactions_for_years(2024, 2025)
            x_labels = [f"{year}-{month}" for year, month, count in results]
            y_values = [count for year, month, count in results]
            total_transactions = sum(y_values)

            transaction_fig = px.bar(
                x=x_labels,
                y=y_values,
                labels={'x': 'Year-Month', 'y': 'Number of Transactions'},
                title="Monthly Transactions (2024-2025)"
            )

            # --- Low Stock Products Data ---
            low_stock = get_low_stock_products(10)      # Threshold set to 10, replace as necessary

            return html.Div([
                # Section 1: Monthly Transactions
                html.H1("Dashboard Overview"),
                html.A("← Back to Main Page", href="/mainpage",target="_self", style={"marginBottom": "20px"}),
                html.Div([
                    html.H2("Monthly Transactions"),
                    html.H3(f"Total Transactions: {total_transactions}"),
                    dcc.Graph(figure=transaction_fig)
                ], style={"marginBottom": "50px"}),

                # Section 2: Low Stock Alert
                html.Div([
                    html.H2("Low Stock Products (Below 10)"),
                    dash_table.DataTable(
                        columns=[
                            {"name": "Product ID", "id": "product_id"},
                            {"name": "Product Name", "id": "name"},
                            {"name": "Quantity", "id": "total_quantity"},
                        ],
                        data=[dict(row) for row in low_stock],
                        style_table={'overflowX': 'auto'},
                        style_cell={'textAlign': 'left'},
                        style_header={'fontWeight': 'bold'}
                    )
                ])
            ])


    dash_app.layout = serve_layout

    return app
if __name__ == '__main__':
    app = create_app()
    app.run()