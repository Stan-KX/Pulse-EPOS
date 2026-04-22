from flask import Flask, flash, request, jsonify, render_template, redirect, url_for, session, Response, g, Blueprint, current_app
import sqlite3
import csv
import os
import datetime as dt
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
# QR generation imports
from sgqrgen.generate import generatePayNowQR, point_of_initiation, proxy_type, proxy_value, editable, amount as default_amount, expiry
import io
import zipfile
from flask import send_file
from werkzeug.utils import secure_filename
# Heatmap imports
import requests
import folium
from folium.plugins import HeatMap
import db


def create_app():
    app = Flask(__name__)
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        app.config.from_object("config.ProductionConfig")
    else:
        app.config.from_object("config.DevelopmentConfig")

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
            p.total_quantity,
            p.type
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
                "type": row['type'],
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
            SELECT p.product_id, p.name, p.brand, p.bundle_size, p.price, p.total_quantity, p.type,
                   CASE WHEN si.product_id IS NOT NULL THEN 1 ELSE 0 END as in_shop,
                   si.display_name, si.display_price, si.item_image
            FROM products p
            LEFT JOIN shop_items si ON p.product_id = si.product_id
            ORDER BY
                CASE WHEN si.product_id IS NOT NULL THEN 0 ELSE 1 END,
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
                "in_shop": row['in_shop'],
                "display_name": row['display_name'] or '',
                "display_price": row['display_price'] if row['display_price'] is not None else '',
                "item_image": row['item_image'] or '',
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

    def staff_authenticate(username, password):
        user = db.query_db('SELECT Username, Password FROM Staff WHERE UPPER(Username) = UPPER(?)', (username,), single=True)
        if user is None:
            return False
        if user['password'] != password:
            return False
        return True

    @app.route('/', methods=['GET', "POST"])
    def index():
        return redirect(url_for("login"))

    @app.route('/login', methods=['GET', "POST"])
    def login():
        session.pop("user", None)
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")
            if username and staff_authenticate(username, password):
                session["user"] = {
                    "id": "staff_login",
                    "name": username,
                    "email": username
                }
                flash(f"Welcome, {username}!", "success")
                return redirect(url_for("mainpage"))
        return render_template("login.html", show_sidebar=False)

    @app.route('/mainpage', methods = ['GET', 'POST'])
    @login_required
    def mainpage():
        ITEMS = generate_items_dict()
        stock_types = generate_stock_types()
        return render_template('mainpage.html', items = ITEMS, stock_types=stock_types)

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
        if client_age < 60:
            client_limit = 35 
        else: 
            client_limit = 45
        session['nric'] = nric_hash
        client_name = client['client_name']

        redemption = db.query_db(
            'SELECT transaction_date as redemption_date '
            'FROM transactions WHERE NRIC = ? '
            'ORDER BY transaction_ID DESC LIMIT 1',
            (nric_hash,),
            single=True
        )

        if client_name == "Deceased" or client_name == "Expired":
            msg = f"{queried_nric} marked as {client_name}. Cannot proceed with redemption."
            resp_type = "R" # Restricted

        elif redemption:
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

        response = {'name': client_name, 'message': msg, 'limit': client_limit, 'type': resp_type}
        # current_app.logger.info(f"{session.get('user')} queried: {msg}")
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
            print(f"{session.get('user')} attempting to check out: {summary}")
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
        
        # Get the inserted transaction_id once
        transaction_id = db.query_db('SELECT last_insert_rowid()', single=True)[0]
        
        # Aggregate items by product_id to prevent duplicate detail rows
        aggregated = {}
        for item in summary:
            product_id = item['ID']
            if product_id in aggregated:
                aggregated[product_id]['Quantity'] += item['Quantity']
            else:
                aggregated[product_id] = {'ID': product_id, 'Quantity': item['Quantity']}
        
        # Insert deduplicated items
        for product_id, item_data in aggregated.items():
            db.insert_db('INSERT INTO transaction_details (transaction_id, product_id, transaction_quantity) VALUES (?, ?, ?)', (transaction_id, item_data['ID'], item_data['Quantity']), single=True)

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

    @app.route('/download_inventory')
    @login_required
    def download_inventory():
        data = db.query_db('SELECT * FROM Products', single = False)
        output = io.StringIO()
        writer = csv.writer(output)
        if data:
            writer.writerow(data[0].keys())
            writer.writerows(data)
        response = Response(output.getvalue(),mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
        return response

    @app.route('/download_movements')
    @login_required
    def download_movements():
        data = db.query_db('SELECT * FROM inventory_movements', single = False)
        output = io.StringIO()
        writer = csv.writer(output)
        if data:
            writer.writerow(data[0].keys())
            writer.writerows(data)
        response = Response(output.getvalue(),mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename=movements.csv'
        return response
    
    @app.route('/orders', methods = ['GET', 'POST'])
    @login_required
    def orders():
        return render_template('orders.html')

    @app.route('/fetch')
    @login_required
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
    @user_required(['super-admin', 'admin'])
    @login_required
    def inventory():
        STOCK = generate_stock_dict()
        stock_types = generate_stock_types()
        return render_template('inventory.html', stock = STOCK, stock_types=stock_types, show_sidebar=True)

    #Endpoint for fetching product movement history
    @app.route('/api/product_history/<product_id>', methods=['GET'])
    @login_required
    def product_history(product_id):
        try:
            # Query movement history for the product
            movements = db.query_db(
                '''SELECT product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks
                FROM inventory_movements
                WHERE product_id = ?
                ORDER BY substr(movement_date,7,4)||substr(movement_date,4,2)||substr(movement_date,1,2)||substr(movement_date,11) DESC
                LIMIT 50''',
                (product_id,),
                single=False
            )
            
            # Format the response
            movements_list = []
            for row in movements:
                movements_list.append({
                    'product_id': row['product_id'],
                    'movement': row['movement'],
                    'movement_type': row['movement_type'],
                    'source': row['movement_source'],
                    'quantity': row['movement_quantity'],
                    'date': row['movement_date'],
                    'remarks': row['movement_remarks']
                })
            
            return jsonify({'movements': movements_list})
        except Exception as e:
            print(f"Error fetching product history: {e}")
            return jsonify({'error': 'Failed to fetch history'}), 500

    #Endpoint for adding new stock types
    @app.route('/api/add_stock_type', methods=['POST'])
    @login_required
    def add_stock_type():
        try:
            data = request.get_json()
            type_name = data.get('type_name', '').strip()
            
            if not type_name:
                return jsonify({'error': 'Type name cannot be empty'}), 400
            
            # Check if type already exists
            existing_type = db.query_db(
                'SELECT 1 FROM products WHERE type = ?',
                (type_name,),
                single=True
            )
            
            if existing_type:
                return jsonify({'error': f'Type "{type_name}" already exists'}), 409
            
            # Add the type by creating a placeholder product entry
            # This ensures the type appears in dropdowns when pulling DISTINCT types
            try:
                db.insert_db(
                    '''INSERT INTO products (product_id, name, brand, bundle_size, price, total_quantity, type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    (f'TYPE_{type_name}_{int(dt.datetime.now().timestamp())}', 
                     f'[TYPE DEFINITION] {type_name}',
                     'System',
                     'N/A',
                     0,
                     0,
                     type_name),
                    single=True
                )
                
                return jsonify({
                    'success': True,
                    'message': f'Stock type "{type_name}" added successfully',
                    'type_name': type_name
                }), 201
            except sqlite3.IntegrityError:
                return jsonify({'error': 'Failed to add type due to database constraint'}), 400
                
        except Exception as e:
            print(f"Error adding stock type: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/remove_stock_type', methods=['POST'])
    @login_required
    def remove_stock_type():
        try:
            data = request.get_json()
            type_name = data.get('type_name', '').strip()

            if not type_name:
                return jsonify({'error': 'Type name cannot be empty'}), 400

            # Null out the type for all products currently using it
            db.insert_db(
                'UPDATE products SET type = NULL WHERE type = ?',
                (type_name,), single=True
            )
            # Remove the TYPE_ placeholder row for this type
            db.insert_db(
                "DELETE FROM products WHERE name = ? AND brand = 'System'",
                (f'[TYPE DEFINITION] {type_name}',), single=True
            )

            return jsonify({'success': True, 'message': f'Type "{type_name}" removed'})
        except Exception as e:
            print(f"Error removing stock type: {e}")
            return jsonify({'error': str(e)}), 500

    #Endpoint for adding new clients
    @app.route('/add_client', methods=['GET', 'POST'])
    @login_required
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
                elif not re.match(r"^\d{4}$", client_dob):
                    return jsonify({'message': 'Invalid date of birth format. Please enter a valid year.'}), 400
                elif client:
                    db.insert_db('update clients set client_name = ?, client_DOB = ? where NRIC = ?', (client_name, client_dob, nric_hash), single=True)
                    return jsonify({'message':f'{queried_nric} details updated!'})
                else:
                    db.insert_db('INSERT INTO clients (NRIC, client_name, client_DOB) VALUES (?, ?, ?)', (nric_hash, client_name, client_dob), single=True)
                    return jsonify({'message': 'Client added successfully!'})
            else:
                return jsonify({'message': 'Please fill in all fields.'}), 400
            
        return render_template('add_client.html', show_sidebar=True)

    #Endpoint for checking clients
    @app.route('/check_client', methods=['GET', 'POST'])
    @login_required
    def check_client():
        if request.method == 'POST':
            data = request.json
            queried_nric = data.get('nric', '').strip().upper()
            print(f"Checking client NRIC: {queried_nric}")
            nric_hash = hash_nric(queried_nric, pepper
            )
            client = db.query_db(
                'SELECT client_name, client_DOB FROM clients WHERE NRIC = ?',
                (nric_hash,),
                single=True)
            if client:
                    return jsonify({'message': f"{queried_nric} found.", 'client_name': client['client_name'], 'client_DOB': client['client_DOB']})
            else:
                    return jsonify({'message': f"{queried_nric} not found."}), 404
            

    #Endpoint for updating stock levels
    @app.route('/update_stock', methods=['POST'])
    @login_required
    def update_stock():
        try:
            # Get the JSON data from the request
            data = request.get_json()
            movement_list = data.get('movementList', []) 
            local_offset = timezone(timedelta(hours=8))
            movement_date = datetime.now(local_offset).strftime('%d-%m-%Y %H:%M:%S')
            print("Incoming request JSON:", data)
            print("Parsed movementList:", movement_list)
            movement_in = {'purchase', 'donation', 'admin stock in', 'return'}                                                                               # Replace with business logic
            movement_out = {'admin stock out', 'expired', 'damaged', 'redeemed', 'office consumption', 'other programme consumption'}    # As above
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
                stock_type = entry.get('stockType')  # New: Get the stock type from entry
                movement = 'in' if movement_type in movement_in else 'out'

                if movement_quantity and movement_quantity > 0:
                    db.insert_db(
                        'INSERT INTO inventory_movements (product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks) VALUES (?, ?, ?, ?, ?, ?, ?)',
                        (product_id, movement, movement_type, movement_source, movement_quantity, movement_date, movement_remarks),
                        single=True
                    )
                    # Trigger adjust_quantity_on_movement handles the total_quantity update automatically

                # Update product type if it has changed
                if stock_type:
                    db.insert_db(
                        'UPDATE products SET type = ? WHERE product_id = ?',
                        (stock_type, product_id),
                        single=True
                    )
                    print(f"Updated Product ID {product_id} type to {stock_type}")
                
                print(f"Product ID: {product_id}, Quantity: {movement_quantity}, Source: {movement_source}, Type: {stock_type}, Remarks: {movement_remarks}")

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

    @app.route("/add_stock", methods=["POST"])
    @login_required
    def add_stock():
        try:
            last = db.query_db(
                "SELECT product_id FROM products WHERE product_id GLOB '[0-9]*' ORDER BY CAST(product_id AS INTEGER) DESC LIMIT 1",
                single=True
            )
            next_id = int(last['product_id']) + 1 if last else 1
            product_id = f"{next_id:04d}"  # zero-padded 4 digits
            name = request.form.get("product_name").strip()
            brand = request.form.get("brand").strip()
            bundle_size = request.form.get("bundle_size").strip()
            quantity = int(request.form.get("quantity"))
            price = float(request.form.get("price"))
            item_type = request.form.get("item_type", "").strip() or None

            print(f'{product_id, name, brand, bundle_size, price, quantity, item_type}')
            db.insert_db(
                "INSERT INTO products (product_id, name, brand, bundle_size, price, total_quantity, type) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (product_id, name, brand, bundle_size, price, quantity, item_type), single=True
            )
            
            
            flash(f"{name} added successfully!")
            return redirect(url_for("inventory"))  # redirect back to inventory page
        except Exception as e:
            print(f"Error adding stock: {e}")
            flash("Error adding stock. Please try again or contact Administrator.", "danger")
            return redirect(url_for("inventory"))

    @app.route('/add_to_shop', methods=['GET', 'POST'])
    @login_required
    def add_to_shop():
        try:
            product_name = request.form.get("product_name")
            display_name = request.form.get("shop_name")
            display_price_raw = request.form.get("shop_price")

            if not product_name:
                flash("Product name is required.", "danger")
                return redirect(url_for("inventory"))

            prod_row = db.query_db("SELECT product_id FROM products WHERE name = ?", (product_name,), single=True)
            if not prod_row:
                flash(f"Product '{product_name}' not found.", "danger")
                return redirect(url_for("inventory"))
            product_id = prod_row['product_id']

            try:
                display_price = float(display_price_raw) if display_price_raw not in (None, "") else None
            except ValueError:
                flash("Invalid shop price.", "danger")
                return redirect(url_for("inventory"))

            # Handle image upload; fall back to existing image or default filename
            cover_file = request.files.get("cover_image")
            existing = db.query_db("SELECT item_image FROM shop_items WHERE product_id = ?", (product_id,), single=True)

            if cover_file and cover_file.filename:
                filename = secure_filename(cover_file.filename)
                if not filename:
                    flash("Image filename is invalid after sanitisation. Please rename the file and try again.", "danger")
                    return redirect(url_for("inventory"))
                save_path = os.path.join(current_app.static_folder, "images", filename)
                try:
                    cover_file.save(save_path)
                    print(f"[add_to_shop] image saved → {save_path}")
                except Exception as img_err:
                    print(f"[add_to_shop] image save FAILED: {img_err}")
                    flash(f"Image could not be saved: {img_err}", "danger")
                    return redirect(url_for("inventory"))
                display_image = filename
            elif existing:
                display_image = existing['item_image']
            else:
                display_image = (product_name or "item").strip() + ".jpeg"

            if existing:
                db.insert_db(
                    "UPDATE shop_items SET display_name = ?, display_price = ?, item_image = ? WHERE product_id = ?",
                    (display_name, display_price, display_image, product_id), single=True)
                flash(f"{display_name} updated successfully!")
            else:
                db.insert_db(
                    "INSERT INTO shop_items (product_id, display_name, display_price, item_image) VALUES (?, ?, ?, ?)",
                    (product_id, display_name, display_price, display_image), single=True)
                flash(f"{display_name} added to shop successfully!")

            return redirect(url_for("inventory"))

        except Exception as e:
            print(f"Error adding to shop: {e}")
            flash("Error adding to shop. Please try again or contact Administrator.", "danger")
            return redirect(url_for("inventory"))

    @app.route('/remove_from_shop', methods=['POST'])
    @login_required
    def remove_from_shop():
        try:
            product_id = request.form.get("product_id")
            if not product_id:
                flash("Product ID is required.", "danger")
                return redirect(url_for("inventory"))
            db.insert_db("DELETE FROM shop_items WHERE product_id = ?", (product_id,), single=True)
            flash("Shop listing removed.")
            return redirect(url_for("inventory"))
        except Exception as e:
            print(f"Error removing from shop: {e}")
            flash("Error removing listing. Please try again.", "danger")
            return redirect(url_for("inventory"))


    dash_app = dash.Dash(__name__, server=app, url_base_pathname='/dashboard/')

    @app.route('/generate_qrs', methods=['GET', 'POST'])
    @login_required
    def generate_qrs():
        if request.method == 'GET':
            return render_template('generate_qrs.html', show_sidebar=True)

        # POST: generate requested number of QR codes and return zip
        try:
            count = int(request.form.get('count', 10))
            prefix = request.form.get('prefix', '2026P')
            start = int(request.form.get('start', 1))
            amt = request.form.get('amount') or default_amount
            editable_request = request.form.get('editable') or True
            editable = '1' if editable_request.lower() == 'true' else '0'
            expiry = request.form.get('expiry') or "21001231"
            # Validate expiry format
        except Exception:
            return jsonify({'message': 'Invalid input'}), 400

        # Cap to prevent abuse
        MAX = 2500
        if count < 1 or count > MAX:
            return jsonify({'message': f'Count must be 1..{MAX}'}), 400

        mem_zip = io.BytesIO()
        with zipfile.ZipFile(mem_zip, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for i in range(start, start + count):
                bn = f"{prefix}{i:04d}"
                img = generatePayNowQR(point_of_initiation, proxy_type, proxy_value, editable, amt, expiry, bn)
                # img is a PIL Image
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                zf.writestr(f'generated_qr_{bn}.png', img_bytes.read())

        mem_zip.seek(0)
        return send_file(mem_zip, mimetype='application/zip', as_attachment=True, download_name='sgqrs.zip')

    @app.route('/heatmap', methods=['GET', 'POST'])
    @login_required
    def heatmap():
        if request.method == 'GET':
            return render_template('heatmap.html', show_sidebar=True)
        
        # POST: Process postal codes and generate heatmap
        try:
            action = request.form.get('action', 'generate')
            postal_input = request.form.get('postal_codes', '').strip()
            postal_list = [p.strip() for p in postal_input.split('\n') if p.strip()]
            
            if action == 'remove_duplicates':
                # Remove duplicates and return the list
                postal_set = sorted(set(postal_list))
                return jsonify({'success': True, 'postal_codes': postal_set})
            
            elif action == 'generate':
                if not postal_list:
                    return jsonify({'success': False, 'message': 'Please enter postal codes'}), 400
                
                lat_long_list = []
                errors = []
                
                for i, postal in enumerate(postal_list, start=1):
                    try:
                        if postal.isnumeric():
                            url = f"https://www.onemap.gov.sg/api/common/elastic/search?searchVal={postal}&returnGeom=Y&getAddrDetails=Y&pageNum=1"
                            response = requests.get(url, timeout=5)
                            results_dict = response.json()
                            
                            if len(results_dict.get("results", [])) > 0:
                                latitude = float(results_dict["results"][0]["LATITUDE"])
                                longitude = float(results_dict["results"][0]["LONGITUDE"])
                                lat_long_list.append((latitude, longitude))
                            else:
                                errors.append(f"Postal code {postal} not found")
                        else:
                            errors.append(f"Postal code {postal} is not numeric")
                    except Exception as e:
                        errors.append(f"Error processing {postal}: {str(e)}")
                
                if not lat_long_list:
                    return jsonify({'success': False, 'message': 'No valid postal codes processed'}), 400
                
                # Generate the heatmap
                map_object = folium.Map(location=[1.290270, 103.851959], zoom_start=12)
                HeatMap(lat_long_list).add_to(map_object)
                html_map = map_object._repr_html_()
                
                return jsonify({
                    'success': True,
                    'map_html': html_map,
                    'points_count': len(lat_long_list),
                    'errors': errors
                })
        
        except Exception as e:
            print(f"Heatmap Error: {e}")
            return jsonify({'success': False, 'message': 'Error processing heatmap'}), 500

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

            if x_labels and y_values:
                transaction_fig = px.bar(
                    x=x_labels,
                    y=y_values,
                    labels={'x': 'Year-Month', 'y': 'Number of Transactions'},
                    title="Monthly Transactions (2024-2025)"
                )
            else:
                transaction_fig = px.bar(
                    title="Monthly Transactions (2024-2025) — No data"
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