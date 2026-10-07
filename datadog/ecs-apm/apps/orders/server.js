// orders sits in the middle of the call chain. dd-trace is loaded with
// `--require dd-trace/init` (see Dockerfile), so express and fetch are traced
// and the trace context propagates to inventory automatically.
const express = require('express');

const INVENTORY_URL = process.env.INVENTORY_URL || 'http://localhost:8081';
const app = express();
app.use(express.json());

app.get('/health', (_req, res) => res.sendStatus(200));

app.post('/orders', async (req, res) => {
  const sku = req.body?.sku || 'sku-100';
  try {
    const inv = await fetch(`${INVENTORY_URL}/inventory/${sku}`);
    if (inv.status === 404) {
      return res.status(422).json({ error: `unknown sku ${sku}` });
    }
    if (!inv.ok) {
      throw new Error(`inventory returned ${inv.status}`);
    }
    const stock = await inv.json();

    // Simulated payment step: about 5% of orders fail with a 500.
    if (Math.random() < 0.05) {
      throw new Error('payment provider timeout');
    }
    res.status(201).json({ orderId: Date.now().toString(36), sku, qty: stock.qty });
  } catch (err) {
    console.error(JSON.stringify({ level: 'error', msg: err.message, sku }));
    res.status(500).json({ error: err.message });
  }
});

app.listen(8080, () => console.log('orders listening on :8080'));
