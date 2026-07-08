#!/bin/bash
set -euo pipefail

ORDERS_HOST=orders-db
ANALYTICS_HOST=analytics-db
INVENTORY_HOST=inventory-db

for host in $ORDERS_HOST $ANALYTICS_HOST $INVENTORY_HOST; do
  echo "Waiting for $host..."
  until pg_isready -h "$host" -p 5432 -U "$PGUSER" -q; do sleep 2; done
done

echo "Seeding orders-db..."
psql -h $ORDERS_HOST -d orders <<'SQL'
CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  user_id INT REFERENCES users(id),
  amount NUMERIC(10,2) NOT NULL,
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

INSERT INTO users (name, email)
SELECT 'User ' || i, 'user' || i || '@example.com'
FROM generate_series(1, 200) i ON CONFLICT DO NOTHING;

INSERT INTO orders (user_id, amount, status, created_at)
SELECT (random()*199+1)::int, (random()*500+5)::numeric(10,2),
  (ARRAY['pending','shipped','delivered','cancelled'])[1+(random()*3)::int],
  NOW() - (random() * interval '30 days')
FROM generate_series(1, 1000);
SQL

echo "Seeding analytics-db..."
psql -h $ANALYTICS_HOST -d analytics <<'SQL'
CREATE TABLE IF NOT EXISTS page_views (
  id SERIAL PRIMARY KEY,
  path TEXT NOT NULL,
  user_agent TEXT,
  duration_ms INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS events (
  id SERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  properties JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_page_views_path ON page_views(path);
CREATE INDEX IF NOT EXISTS idx_page_views_created_at ON page_views(created_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);

INSERT INTO page_views (path, user_agent, duration_ms, created_at)
SELECT
  (ARRAY['/home','/products','/cart','/checkout','/account','/search'])[1+(random()*5)::int],
  (ARRAY['Chrome','Firefox','Safari','Edge'])[1+(random()*3)::int],
  (random()*3000)::int,
  NOW() - (random() * interval '30 days')
FROM generate_series(1, 2000);

INSERT INTO events (event_type, properties, created_at)
SELECT
  (ARRAY['click','scroll','purchase','signup','logout'])[1+(random()*4)::int],
  jsonb_build_object('source', (ARRAY['web','mobile','api'])[1+(random()*2)::int]),
  NOW() - (random() * interval '30 days')
FROM generate_series(1, 1500);
SQL

echo "Seeding inventory-db..."
psql -h $INVENTORY_HOST -d inventory <<'SQL'
CREATE TABLE IF NOT EXISTS products (
  id SERIAL PRIMARY KEY,
  sku TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price NUMERIC(10,2) NOT NULL
);
CREATE TABLE IF NOT EXISTS stock (
  id SERIAL PRIMARY KEY,
  product_id INT REFERENCES products(id),
  warehouse TEXT NOT NULL,
  quantity INT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_stock_product_id ON stock(product_id);
CREATE INDEX IF NOT EXISTS idx_stock_warehouse ON stock(warehouse);

INSERT INTO products (sku, name, category, price)
SELECT 'SKU-' || i, 'Product ' || i,
  (ARRAY['electronics','books','clothing','food','sports'])[1+(i%5)],
  (random()*200+1)::numeric(10,2)
FROM generate_series(1, 100) i ON CONFLICT DO NOTHING;

INSERT INTO stock (product_id, warehouse, quantity, updated_at)
SELECT (random()*99+1)::int,
  (ARRAY['us-west','us-east','eu-central','ap-south'])[1+(random()*3)::int],
  (random()*500)::int,
  NOW() - (random() * interval '7 days')
FROM generate_series(1, 400);
SQL

echo "Starting workload loop..."
while true; do
  # --- orders-db ---
  psql -h $ORDERS_HOST -d orders -c "
    INSERT INTO orders (user_id, amount, status)
    SELECT (random()*199+1)::int, (random()*500+5)::numeric(10,2),
      (ARRAY['pending','shipped','delivered','cancelled'])[1+(random()*3)::int]
    FROM generate_series(1, 5);
  " 2>/dev/null

  psql -h $ORDERS_HOST -d orders -c "
    SELECT u.name, COUNT(o.id) AS order_count, SUM(o.amount) AS total_spent
    FROM users u JOIN orders o ON u.id = o.user_id
    GROUP BY u.id, u.name ORDER BY total_spent DESC LIMIT 10;
  " >/dev/null 2>&1

  psql -h $ORDERS_HOST -d orders -c "
    UPDATE orders SET status = 'shipped'
    WHERE id IN (SELECT id FROM orders WHERE status = 'pending' ORDER BY created_at LIMIT 3);
  " 2>/dev/null

  psql -h $ORDERS_HOST -d orders -c "
    SELECT status, COUNT(*), AVG(amount)::numeric(10,2)
    FROM orders WHERE created_at > NOW() - interval '7 days'
    GROUP BY status;
  " >/dev/null 2>&1

  # --- analytics-db ---
  psql -h $ANALYTICS_HOST -d analytics -c "
    INSERT INTO page_views (path, user_agent, duration_ms)
    SELECT (ARRAY['/home','/products','/cart','/checkout','/account','/search'])[1+(random()*5)::int],
      (ARRAY['Chrome','Firefox','Safari','Edge'])[1+(random()*3)::int],
      (random()*3000)::int
    FROM generate_series(1, 10);
  " 2>/dev/null

  psql -h $ANALYTICS_HOST -d analytics -c "
    SELECT path, COUNT(*) AS views, AVG(duration_ms)::int AS avg_ms
    FROM page_views WHERE created_at > NOW() - interval '1 day'
    GROUP BY path ORDER BY views DESC;
  " >/dev/null 2>&1

  psql -h $ANALYTICS_HOST -d analytics -c "
    INSERT INTO events (event_type, properties)
    SELECT (ARRAY['click','scroll','purchase','signup','logout'])[1+(random()*4)::int],
      jsonb_build_object('source', (ARRAY['web','mobile','api'])[1+(random()*2)::int])
    FROM generate_series(1, 8);
  " 2>/dev/null

  psql -h $ANALYTICS_HOST -d analytics -c "
    SELECT event_type, properties->>'source' AS source, COUNT(*)
    FROM events WHERE created_at > NOW() - interval '1 hour'
    GROUP BY event_type, properties->>'source';
  " >/dev/null 2>&1

  psql -h $ANALYTICS_HOST -d analytics -c "
    WITH hourly AS (
      SELECT date_trunc('hour', created_at) AS hour, COUNT(*) AS cnt
      FROM page_views GROUP BY 1
    )
    SELECT hour, cnt, AVG(cnt) OVER (ORDER BY hour ROWS BETWEEN 3 PRECEDING AND CURRENT ROW)::int AS moving_avg
    FROM hourly ORDER BY hour DESC LIMIT 24;
  " >/dev/null 2>&1

  # --- inventory-db ---
  psql -h $INVENTORY_HOST -d inventory -c "
    UPDATE stock SET quantity = quantity - (random()*5+1)::int, updated_at = NOW()
    WHERE id IN (SELECT id FROM stock WHERE quantity > 10 ORDER BY random() LIMIT 5);
  " 2>/dev/null

  psql -h $INVENTORY_HOST -d inventory -c "
    SELECT p.category, SUM(s.quantity) AS total_stock, COUNT(DISTINCT p.id) AS products
    FROM products p JOIN stock s ON p.id = s.product_id
    GROUP BY p.category ORDER BY total_stock;
  " >/dev/null 2>&1

  psql -h $INVENTORY_HOST -d inventory -c "
    SELECT p.name, p.sku, s.warehouse, s.quantity
    FROM products p JOIN stock s ON p.id = s.product_id
    WHERE s.quantity < 20 ORDER BY s.quantity;
  " >/dev/null 2>&1

  psql -h $INVENTORY_HOST -d inventory -c "
    SELECT warehouse, COUNT(*) AS items, SUM(quantity) AS total,
           AVG(quantity)::int AS avg_qty
    FROM stock GROUP BY warehouse;
  " >/dev/null 2>&1

  sleep $((RANDOM % 3 + 1))
done
