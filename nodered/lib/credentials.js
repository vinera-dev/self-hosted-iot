'use strict';

const fs = require('fs');

function brokerCredentials(env) {
  if (!env.MQTT_USERNAME || !env.MQTT_PASSWORD) {
    throw new Error('MQTT_USERNAME and MQTT_PASSWORD must be set');
  }
  return { broker: { user: env.MQTT_USERNAME, password: env.MQTT_PASSWORD } };
}

function writeCredentialsFile(file, env) {
  fs.writeFileSync(file, JSON.stringify(brokerCredentials(env)), { mode: 0o600 });
}

module.exports = { brokerCredentials, writeCredentialsFile };
