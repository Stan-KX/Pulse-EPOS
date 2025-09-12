PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "products" (
	"product_id"	TEXT NOT NULL,
	"name"	TEXT,
	"brand"	TEXT,
	"bundle_size"	TEXT,
	"price"	DECIMAL(10, 2),
	"total_quantity"	INTEGER, type TEXT,
	PRIMARY KEY("product_id")
);

CREATE TABLE IF NOT EXISTS "shop_items" (
	"product_id"	TEXT,
	"display_name"	TEXT NOT NULL,
	"display_price"	INTEGER,
	"item_image"	TEXT NOT NULL,
	PRIMARY KEY("display_name"),
	FOREIGN KEY("product_id") REFERENCES "products"("product_id")
);

CREATE TABLE IF NOT EXISTS "staff" (
	"Username"	TEXT NOT NULL
, role);

CREATE TABLE IF NOT EXISTS "transaction_details" (
	"detail_id"	INTEGER,
	"transaction_id"	INTEGER,
	"product_id"	TEXT,
	"transaction_quantity"	INTEGER,
	PRIMARY KEY("detail_id" AUTOINCREMENT),
	FOREIGN KEY("product_id") REFERENCES "products"("product_id"),
	FOREIGN KEY("transaction_id") REFERENCES "transactions"("transaction_id")
);
ANALYZE sqlite_schema;
INSERT INTO sqlite_stat1 VALUES('shop_items','sqlite_autoindex_shop_items_1','24 1');
INSERT INTO sqlite_stat1 VALUES('products','sqlite_autoindex_products_1','41 1');
ANALYZE sqlite_schema;
CREATE TABLE IF NOT EXISTS "clients_import" (
	"NRIC"	TEXT,
	"client_name"	TEXT,
	"client_DOB"	TEXT
);

CREATE TABLE IF NOT EXISTS "clients" (
	"NRIC" TEXT,
	"client_name"	TEXT NOT NULL,
	"client_DOB"	DATE,
	PRIMARY KEY("NRIC")
);

CREATE TABLE IF NOT EXISTS "transactions" (
	"transaction_ID"	INTEGER,
	"transaction_date"	DATE,
	"NRIC" TEXT,
	"client_name"	TEXT,
	"total_spent"	INTEGER,
	PRIMARY KEY("transaction_ID" AUTOINCREMENT),
	FOREIGN KEY("NRIC") REFERENCES "clients"("NRIC")
);

CREATE TABLE IF NOT EXISTS "inventory_movements" (
	"movement_id"	INTEGER,
	"product_id"	TEXT,
	"movement"	TEXT NOT NULL,
	"movement_type"	TEXT CHECK("movement_type" IN ('redeemed', 'damaged', 'donation', 'expired', 'purchase', 'office consumption', 'return', 'other programme consumption', 'admin stock in', 'admin stock out')),
	"movement_source"	TEXT,
	"movement_quantity"	INTEGER,
	"movement_date"	TEXT,
	"movement_remarks"	TEXT,
	PRIMARY KEY("movement_id" AUTOINCREMENT),
	FOREIGN KEY("product_id") REFERENCES "products"("product_id")
);


CREATE TRIGGER movement_on_transaction

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

    SELECT

        NEW.product_id,  -- Ensure product_id is 4 digits with leading zeros

        'out',  -- Assuming 'purchase' means the movement is 'in'

        'redeemed',

        'eshop',  -- You can adjust this as needed

        NEW.transaction_quantity,

        t.transaction_date,

        'Auto-generated from transaction'

    FROM transactions t

    WHERE t.transaction_id = NEW.transaction_id;

END
;
CREATE TRIGGER adjust_quantity_on_movement
AFTER INSERT ON inventory_movements
FOR EACH ROW
BEGIN
    -- Increase quantity if movement is 'in'
    UPDATE products
    SET total_quantity = total_quantity + NEW.movement_quantity
    WHERE NEW.movement = 'in' AND product_id = NEW.product_id;

    -- Decrease quantity if movement is 'out'
    UPDATE products
    SET total_quantity = total_quantity - NEW.movement_quantity
    WHERE NEW.movement = 'out' AND product_id = NEW.product_id;
END
;
CREATE TRIGGER set_movement
BEFORE INSERT ON inventory_movements
FOR EACH ROW
BEGIN
    UPDATE inventory_movements
    SET movement = CASE
        WHEN NEW.movement_type IN ('donation', 'purchase', 'return in', 'Admin Stock In') THEN 'in'
        ELSE 'out'
    END
    WHERE rowid = NEW.rowid;
END;
COMMIT;
