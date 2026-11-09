'use strict';

const INSERT_ALERT =
  'INSERT INTO alert_events (status, alert_name, device_id, summary, payload) ' +
  'VALUES ($1, $2, $3, $4, $5::jsonb)';
const STATUSES = ['firing', 'resolved'];

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseAlerts(body) {
  if (!isObject(body) || !Array.isArray(body.alerts)) {
    return null;
  }
  const events = [];
  for (const alert of body.alerts) {
    if (!isObject(alert) || !STATUSES.includes(alert.status)) {
      return null;
    }
    const labels = isObject(alert.labels) ? alert.labels : {};
    const annotations = isObject(alert.annotations) ? alert.annotations : {};
    events.push({
      status: alert.status,
      alertName: String(labels.alertname || 'unknown'),
      deviceId: labels.device_id === undefined ? null : String(labels.device_id),
      summary: annotations.summary === undefined ? null : String(annotations.summary),
      payload: JSON.stringify(alert),
    });
  }
  return events;
}

function webhook(msg) {
  const events = parseAlerts(msg.payload);
  if (events === null) {
    return [null, { res: msg.res, statusCode: 400, payload: 'invalid alert payload' }];
  }
  const inserts = events.map((event) => ({
    query: INSERT_ALERT,
    params: [event.status, event.alertName, event.deviceId, event.summary, event.payload],
  }));
  return [inserts, { res: msg.res, statusCode: 200, payload: 'ok' }];
}

module.exports = { parseAlerts, webhook };
