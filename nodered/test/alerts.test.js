'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const alerts = require('../lib/alerts');

const RES = { fake: 'response' };

function grafanaBody() {
  return {
    status: 'firing',
    alerts: [
      {
        status: 'firing',
        labels: { alertname: 'High temperature', device_id: 'device-01', severity: 'warning' },
        annotations: { summary: 'Temperature above 32 C' },
      },
      { status: 'resolved', labels: { alertname: 'High temperature' }, annotations: {} },
    ],
  };
}

test('each alert in a webhook becomes an insert and the caller gets a 200', () => {
  const [inserts, reply] = alerts.webhook({ payload: grafanaBody(), res: RES });
  assert.equal(inserts.length, 2);
  assert.deepEqual(inserts[0].params.slice(0, 4), [
    'firing',
    'High temperature',
    'device-01',
    'Temperature above 32 C',
  ]);
  assert.equal(inserts[1].params[2], null);
  assert.equal(reply.statusCode, 200);
  assert.equal(reply.res, RES);
});

test('payloads that are not Grafana notifications get a 400 and no insert', () => {
  for (const payload of [null, 'text', {}, { alerts: 'x' }, { alerts: [{ status: 'weird' }] }]) {
    const [inserts, reply] = alerts.webhook({ payload, res: RES });
    assert.equal(inserts, null);
    assert.equal(reply.statusCode, 400);
  }
});
