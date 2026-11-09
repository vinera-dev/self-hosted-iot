'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const rules = require('../lib/rules');

const THRESHOLDS = { high: 28, low: 25 };

function replay(temperatures, thresholds = THRESHOLDS) {
  const relays = {};
  const commands = [];
  for (const temperatureC of temperatures) {
    const command = rules.react(relays, { deviceId: 'device-01', temperatureC }, thresholds);
    if (command) {
      commands.push(JSON.parse(command.payload).relay);
      rules.track(relays, { deviceId: 'device-01', relay: commands[commands.length - 1] });
    }
  }
  return commands;
}

test('thresholds default to 28 and 25 and can be set from the environment', () => {
  assert.deepEqual(rules.thresholdsFromEnv({}), { high: 28, low: 25 });
  assert.deepEqual(rules.thresholdsFromEnv({ TEMP_HIGH_C: '30', TEMP_LOW_C: '27.5' }), {
    high: 30,
    low: 27.5,
  });
});

test('invalid thresholds are refused', () => {
  assert.throws(() => rules.thresholdsFromEnv({ TEMP_HIGH_C: '25', TEMP_LOW_C: '25' }));
  assert.throws(() => rules.thresholdsFromEnv({ TEMP_HIGH_C: '20', TEMP_LOW_C: '25' }));
  assert.throws(() => rules.thresholdsFromEnv({ TEMP_HIGH_C: 'hot' }));
});

test('a reading above the limit turns the relay on with a command on the device topic', () => {
  const command = rules.react({}, { deviceId: 'device-07', temperatureC: 29.5 }, THRESHOLDS);
  assert.equal(command.topic, 'devices/device-07/commands');
  assert.deepEqual(JSON.parse(command.payload), { relay: 'on' });
  assert.equal(command.qos, 1);
});

test('readings inside the band send nothing', () => {
  assert.equal(rules.react({}, { deviceId: 'device-01', temperatureC: 26 }, THRESHOLDS), null);
  assert.equal(
    rules.react({ 'device-01': 'on' }, { deviceId: 'device-01', temperatureC: 26 }, THRESHOLDS),
    null,
  );
});

test('an already active relay is not commanded again', () => {
  const relays = { 'device-01': 'on' };
  assert.equal(rules.react(relays, { deviceId: 'device-01', temperatureC: 35 }, THRESHOLDS), null);
});

test('readings on the edge do not make the relay oscillate', () => {
  const edge = [27.9, 28.0, 27.9, 28.1, 27.5, 26, 25.1, 25.4, 27.9, 28.0, 25.1, 25.0, 25.5, 27.9];
  assert.deepEqual(replay(edge), ['on', 'off']);
});

test('without a gap between the thresholds the same readings would oscillate', () => {
  const edge = [27.9, 28.0, 27.9, 28.1, 27.5, 28.0, 27.9, 28.0];
  const commands = replay(edge, { high: 28, low: 27.99 });
  assert.ok(commands.length > 4, `expected oscillation, got ${commands.length} commands`);
});

test('relays are tracked per device', () => {
  const relays = {};
  rules.track(relays, { deviceId: 'device-01', relay: 'on' });
  assert.equal(
    rules.react(relays, { deviceId: 'device-02', temperatureC: 30 }, THRESHOLDS).topic,
    'devices/device-02/commands',
  );
  assert.equal(rules.react(relays, { deviceId: 'device-01', temperatureC: 30 }, THRESHOLDS), null);
});
