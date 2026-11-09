'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const ingest = require('../lib/ingest');

const NOW = Date.parse('2030-01-01T12:00:00Z');

function telemetryBody(overrides = {}) {
  return JSON.stringify({
    device_id: 'device-01',
    ts: '2030-01-01T12:00:00+00:00',
    temperature_c: 22.13,
    humidity_pct: 49.8,
    ...overrides,
  });
}

function rejectedReason(topic, payload) {
  const [valid, rejected] = ingest.telemetry({ topic, payload }, NOW);
  assert.equal(valid, null);
  return rejected.params[2];
}

test('a valid reading becomes an insert with parameters', () => {
  const [valid, rejected] = ingest.telemetry(
    { topic: 'devices/device-01/telemetry', payload: Buffer.from(telemetryBody()) },
    NOW,
  );
  assert.equal(rejected, null);
  assert.match(valid.query, /INSERT INTO readings/);
  assert.deepEqual(valid.params, ['2030-01-01T12:00:00+00:00', 'device-01', 22.13, 49.8]);
  assert.equal(valid.reading.deviceId, 'device-01');
});

test('broken JSON is rejected with the original payload', () => {
  const [valid, rejected] = ingest.telemetry(
    { topic: 'devices/device-01/telemetry', payload: Buffer.from('{"temperature_c": ') },
    NOW,
  );
  assert.equal(valid, null);
  assert.match(rejected.query, /INSERT INTO rejected_messages/);
  assert.deepEqual(rejected.params.slice(0, 2), [
    'devices/device-01/telemetry',
    '{"temperature_c": ',
  ]);
  assert.match(rejected.params[2], /not valid JSON/);
});

test('payloads that are not objects are rejected', () => {
  for (const payload of ['null', '[1, 2]', '42', '"text"']) {
    assert.match(rejectedReason('devices/device-01/telemetry', payload), /not a JSON object/);
  }
});

test('a device cannot report on behalf of another one', () => {
  const reason = rejectedReason(
    'devices/device-01/telemetry',
    telemetryBody({ device_id: 'device-02' }),
  );
  assert.match(reason, /does not match the topic/);
});

test('missing, malformed and far future timestamps are rejected', () => {
  const topic = 'devices/device-01/telemetry';
  assert.match(rejectedReason(topic, telemetryBody({ ts: undefined })), /ts is not/);
  assert.match(rejectedReason(topic, telemetryBody({ ts: '2030-01-01 12:00:00' })), /ts is not/);
  assert.match(rejectedReason(topic, telemetryBody({ ts: '2030-13-45T99:00:00Z' })), /ts is not/);
  assert.match(
    rejectedReason(topic, telemetryBody({ ts: '2030-01-05T12:00:00Z' })),
    /too far in the future/,
  );
});

test('values outside the physical range or of the wrong type are rejected', () => {
  const topic = 'devices/device-01/telemetry';
  assert.match(rejectedReason(topic, telemetryBody({ temperature_c: 400 })), /temperature_c/);
  assert.match(rejectedReason(topic, telemetryBody({ temperature_c: '22' })), /temperature_c/);
  assert.match(rejectedReason(topic, telemetryBody({ temperature_c: null })), /temperature_c/);
  assert.match(rejectedReason(topic, telemetryBody({ humidity_pct: 120 })), /humidity_pct/);
  assert.match(rejectedReason(topic, telemetryBody({ humidity_pct: -1 })), /humidity_pct/);
});

test('topics of other shapes are rejected', () => {
  assert.match(rejectedReason('devices/Device 01/telemetry', telemetryBody()), /valid device/);
  assert.match(rejectedReason('devices/device-01/other', telemetryBody()), /telemetry topic/);
});

test('payloads are truncated and cleaned before being stored', () => {
  const [, rejected] = ingest.telemetry(
    { topic: 'devices/device-01/telemetry', payload: Buffer.from('a\u0000'.repeat(5000)) },
    NOW,
  );
  assert.equal(rejected.params[1].length, 2000);
  assert.ok(!rejected.params[1].includes('\u0000'));
});

test('a valid state becomes an upsert and an invalid relay is rejected', () => {
  const body = { device_id: 'device-01', ts: '2030-01-01T12:00:00+00:00', relay: 'on' };
  const [valid] = ingest.state(
    { topic: 'devices/device-01/state', payload: Buffer.from(JSON.stringify(body)) },
    NOW,
  );
  assert.deepEqual(valid.params, ['device-01', 'on', '2030-01-01T12:00:00+00:00']);
  const [none, rejected] = ingest.state(
    {
      topic: 'devices/device-01/state',
      payload: Buffer.from(JSON.stringify({ ...body, relay: 'maybe' })),
    },
    NOW,
  );
  assert.equal(none, null);
  assert.match(rejected.params[2], /relay/);
});
