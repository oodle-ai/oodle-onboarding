'use strict';

const http = require('http');
const logger = require('./logger');

const PORT = Number(process.env.PORT || 8100);

const CATALOG = {
  'sku-100': { name: 'Espresso beans, 1kg', price: 24.0 },
  'sku-200': { name: 'Pour-over kettle', price: 59.5 },
  'sku-300': { name: 'Ceramic dripper', price: 18.0 },
};

let orderSeq = 1000;

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(body));
}

// Places an order: a handful of structured log lines at different
// levels, with a child logger carrying the order id on each one.
function placeOrder(req, res, url) {
  const sku = url.searchParams.get('sku') || 'sku-100';
  const qty = Number(url.searchParams.get('qty') || 1);
  const orderId = `ord-${orderSeq++}`;
  const log = logger.child({ orderId, sku, qty });

  log.info('order received');

  const item = CATALOG[sku];
  if (!item) {
    log.warn({ reason: 'unknown_sku' }, 'order rejected');
    return json(res, 404, { error: `unknown sku ${sku}`, orderId });
  }
  if (qty > 10) {
    log.warn({ reason: 'qty_over_limit', limit: 10 }, 'order rejected');
    return json(res, 400, { error: 'quantity over limit', orderId });
  }

  const total = Number((item.price * qty).toFixed(2));
  log.debug({ unitPrice: item.price, total }, 'priced order');

  // Simulate a payment step that fails now and then.
  if (Math.random() < 0.15) {
    const err = new Error('payment gateway timeout');
    log.error({ err, total, step: 'payment' }, 'order failed');
    return json(res, 502, { error: err.message, orderId });
  }

  log.info({ total, item: item.name }, 'order placed');
  json(res, 201, { orderId, item: item.name, qty, total });
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (url.pathname === '/health') {
    return json(res, 200, { status: 'ok', service: 'pino-logs-demo' });
  }
  if (url.pathname === '/order' && req.method === 'POST') {
    return placeOrder(req, res, url);
  }
  if (url.pathname === '/crash') {
    const err = new Error('unhandled route failure');
    logger.error({ err, path: url.pathname }, 'request failed');
    return json(res, 500, { error: err.message });
  }
  logger.warn({ path: url.pathname, method: req.method }, 'route not found');
  json(res, 404, { error: 'not found' });
});

server.listen(PORT, () => {
  logger.info({ port: PORT }, 'pino-logs-demo listening');
});
