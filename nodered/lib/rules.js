'use strict';

const DEFAULT_HIGH_C = 28;
const DEFAULT_LOW_C = 25;

function thresholdsFromEnv(env) {
  const high = Number(env.TEMP_HIGH_C === undefined ? DEFAULT_HIGH_C : env.TEMP_HIGH_C);
  const low = Number(env.TEMP_LOW_C === undefined ? DEFAULT_LOW_C : env.TEMP_LOW_C);
  if (!Number.isFinite(high) || !Number.isFinite(low) || low >= high) {
    throw new Error('TEMP_LOW_C must be lower than TEMP_HIGH_C and both must be numbers');
  }
  return { high, low };
}

function decide(currentRelay, temperatureC, thresholds) {
  const relay = currentRelay === 'on' ? 'on' : 'off';
  if (temperatureC >= thresholds.high && relay !== 'on') {
    return 'on';
  }
  if (temperatureC <= thresholds.low && relay !== 'off') {
    return 'off';
  }
  return null;
}

function track(relays, state) {
  relays[state.deviceId] = state.relay;
}

function react(relays, reading, thresholds) {
  const relay = decide(relays[reading.deviceId], reading.temperatureC, thresholds);
  if (relay === null) {
    return null;
  }
  return {
    topic: `devices/${reading.deviceId}/commands`,
    payload: JSON.stringify({ relay }),
    qos: 1,
  };
}

const thresholds = thresholdsFromEnv(process.env);

module.exports = { thresholdsFromEnv, decide, track, react, thresholds };
