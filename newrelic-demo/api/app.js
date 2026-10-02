'use strict';
// no agent code here: the Dockerfile loads the New Relic agent and the OTel SDK with `node -r`
const express = require('express');
const { Pool } = require('pg');
const Redis = require('ioredis');
const amqp = require('amqplib');

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const redis = new Redis(process.env.REDIS_URL);
let channel;

async function init() {
  await pool.query(`CREATE TABLE IF NOT EXISTS products (id SERIAL PRIMARY KEY, name TEXT NOT NULL, price_cents INT NOT NULL)`);
  await pool.query(`CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY, product_id INT NOT NULL REFERENCES products(id), qty INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT now())`);
  await pool.query(`INSERT INTO products (name, price_cents)
    SELECT * FROM (VALUES ('widget', 1999), ('gadget', 4999), ('gizmo', 999)) v
    WHERE NOT EXISTS (SELECT 1 FROM products)`);
  const conn = await amqp.connect(process.env.AMQP_URL);
  channel = await conn.createChannel();
  await channel.assertQueue('orders', { durable: true });
}

const app = express();

app.get('/health', (req, res) => res.send('ok'));

// cache-aside: Redis in front of Postgres
app.get('/api/products', async (req, res, next) => {
  try {
    const cached = await redis.get('products');
    if (cached) return res.json({ source: 'cache', products: JSON.parse(cached) });
    const { rows } = await pool.query('SELECT id, name, price_cents FROM products ORDER BY id');
    await redis.set('products', JSON.stringify(rows), 'EX', 10);
    res.json({ source: 'db', products: rows });
  } catch (err) { next(err); }
});

// insert into Postgres, then hand off to the worker over RabbitMQ
app.post('/api/orders', async (req, res, next) => {
  try {
    const productId = Math.random() < 0.05 ? 99 : 1 + Math.floor(Math.random() * 3); // 5% unknown product -> inventory 409 -> api 500, visible error rate
    const qty = 1 + Math.floor(Math.random() * 5);
    const reserve = await fetch(`${process.env.INVENTORY_URL}/reserve`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ product_id: productId, qty }) });
    if (!reserve.ok) throw new Error(`inventory reserve failed: ${reserve.status}`);
    const { rows: [order] } = await pool.query(
      'INSERT INTO orders (product_id, qty) VALUES ($1, $2) RETURNING *', [productId, qty]);
    channel.sendToQueue('orders', Buffer.from(JSON.stringify({ id: order.id })), { persistent: true });
    res.status(202).json(order);
  } catch (err) { next(err); }
});

app.get('/api/orders/:id', async (req, res, next) => {
  try {
    const { rows: [order] } = await pool.query('SELECT * FROM orders WHERE id = $1', [req.params.id]);
    if (!order) return res.status(404).json({ error: 'not found' });
    res.json(order);
  } catch (err) { next(err); }
});

app.get('/api/stats', async (req, res, next) => {
  try {
    const processed = Number(await redis.get('orders:processed')) || 0;
    const { rows: [{ pending }] } = await pool.query(`SELECT count(*)::int AS pending FROM orders WHERE status = 'pending'`);
    res.json({ processed, pending });
  } catch (err) { next(err); }
});

init().then(() => app.listen(8080, () => console.log('api listening on :8080')))
  .catch((err) => { console.error(err); process.exit(1); });
