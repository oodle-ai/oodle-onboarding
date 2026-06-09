const express = require('express');
const pino = require('pino');

const logger = pino({ name: 'frontend' });
const app = express();
const port = 3000;

app.use(express.json());

const ORDER_SERVICE_URL = process.env.ORDER_SERVICE_URL || 'http://order-service:5000';
const PAYMENT_SERVICE_URL = process.env.PAYMENT_SERVICE_URL || 'http://payment-service:8080';

app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'frontend' });
});

app.post('/order', async (req, res) => {
  const { item, quantity } = req.body;
  logger.info({ item, quantity }, 'Received order request');
  try {
    const orderResp = await fetch(`${ORDER_SERVICE_URL}/process`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item, quantity }),
    });
    const order = await orderResp.json();

    const paymentResp = await fetch(`${PAYMENT_SERVICE_URL}/charge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item, quantity, total: order.total }),
    });
    const payment = await paymentResp.json();

    logger.info({ item, total: order.total, approved: payment.approved }, 'Order completed');
    res.json({ service: 'frontend', order, payment });
  } catch (err) {
    logger.error({ err, item }, 'Order failed');
    res.status(500).json({ error: err.message });
  }
});

app.get('/trace-demo', async (req, res) => {
  try {
    const resp = await fetch(`${ORDER_SERVICE_URL}/health`);
    const data = await resp.json();
    res.json({ service: 'frontend', downstream: data });
  } catch (err) {
    logger.error({ err }, 'Trace demo failed');
    res.status(500).json({ error: err.message });
  }
});

app.listen(port, () => {
  logger.info({ port }, 'Frontend started');
});
