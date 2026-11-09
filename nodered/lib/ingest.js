'use strict';

const DEVICE_ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const TELEMETRY_TOPIC = /^devices\/([^/]+)\/telemetry$/;
const STATE_TOPIC = /^devices\/([^/]+)\/state$/;
const ISO_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const RELAY_STATES = ['on', 'off'];
const MAX_PAYLOAD_CHARS = 2000;
const MAX_FUTURE_MS = 24 * 60 * 60 * 1000;

const INSERT_READING =
  'INSERT INTO readings (ts, device_id, temperature_c, humidity_pct) ' +
  'VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING';
const UPSERT_STATE =
  'INSERT INTO device_states (device_id, relay, updated_at) VALUES ($1, $2, $3) ' +
  'ON CONFLICT (device_id) DO UPDATE SET relay = EXCLUDED.relay, updated_at = EXCLUDED.updated_at';
const INSERT_REJECTED =
  'INSERT INTO rejected_messages (topic, payload, reason) VALUES ($1, $2, $3)';

function payloadText(payload) {
  const text = Buffer.isBuffer(payload) ? payload.toString('utf8') : String(payload);
  return text.replace(/\u0000/g, '�').slice(0, MAX_PAYLOAD_CHARS);
}

function isNumberInRange(value, min, max) {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
}

function parseObject(payload) {
  let parsed;
  try {
    parsed = JSON.parse(payloadText(payload));
  } catch (error) {
    return { reason: 'payload is not valid JSON' };
  }
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { reason: 'payload is not a JSON object' };
  }
  return { value: parsed };
}

function checkEnvelope(body, deviceId, now) {
  if (body.device_id !== deviceId) {
    return 'device_id does not match the topic';
  }
  if (typeof body.ts !== 'string' || !ISO_TIMESTAMP.test(body.ts) || Number.isNaN(Date.parse(body.ts))) {
    return 'ts is not an ISO 8601 timestamp with a time zone';
  }
  if (Date.parse(body.ts) - now > MAX_FUTURE_MS) {
    return 'ts is too far in the future';
  }
  return null;
}

function validateTelemetry(topic, payload, now = Date.now()) {
  const match = TELEMETRY_TOPIC.exec(topic);
  if (!match || !DEVICE_ID.test(match[1])) {
    return { reason: 'topic is not a telemetry topic of a valid device' };
  }
  const parsed = parseObject(payload);
  if (parsed.reason) {
    return { reason: parsed.reason };
  }
  const body = parsed.value;
  const envelopeError = checkEnvelope(body, match[1], now);
  if (envelopeError) {
    return { reason: envelopeError };
  }
  if (!isNumberInRange(body.temperature_c, -50, 100)) {
    return { reason: 'temperature_c is missing or outside -50..100' };
  }
  if (!isNumberInRange(body.humidity_pct, 0, 100)) {
    return { reason: 'humidity_pct is missing or outside 0..100' };
  }
  return {
    reading: {
      deviceId: match[1],
      ts: body.ts,
      temperatureC: body.temperature_c,
      humidityPct: body.humidity_pct,
    },
  };
}

function validateState(topic, payload, now = Date.now()) {
  const match = STATE_TOPIC.exec(topic);
  if (!match || !DEVICE_ID.test(match[1])) {
    return { reason: 'topic is not a state topic of a valid device' };
  }
  const parsed = parseObject(payload);
  if (parsed.reason) {
    return { reason: parsed.reason };
  }
  const body = parsed.value;
  const envelopeError = checkEnvelope(body, match[1], now);
  if (envelopeError) {
    return { reason: envelopeError };
  }
  if (!RELAY_STATES.includes(body.relay)) {
    return { reason: 'relay must be "on" or "off"' };
  }
  return { state: { deviceId: match[1], ts: body.ts, relay: body.relay } };
}

function rejection(msg, reason) {
  return {
    topic: msg.topic,
    query: INSERT_REJECTED,
    params: [msg.topic, payloadText(msg.payload), reason],
  };
}

function telemetry(msg, now = Date.now()) {
  const result = validateTelemetry(msg.topic, msg.payload, now);
  if (result.reason) {
    return [null, rejection(msg, result.reason)];
  }
  const { reading } = result;
  return [
    {
      topic: msg.topic,
      reading,
      query: INSERT_READING,
      params: [reading.ts, reading.deviceId, reading.temperatureC, reading.humidityPct],
    },
    null,
  ];
}

function state(msg, now = Date.now()) {
  const result = validateState(msg.topic, msg.payload, now);
  if (result.reason) {
    return [null, rejection(msg, result.reason)];
  }
  const { state: device } = result;
  return [
    {
      topic: msg.topic,
      state: device,
      query: UPSERT_STATE,
      params: [device.deviceId, device.relay, device.ts],
    },
    null,
  ];
}

module.exports = { validateTelemetry, validateState, telemetry, state };
