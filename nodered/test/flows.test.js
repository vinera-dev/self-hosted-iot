'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const flows = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'flows.json'), 'utf8'));
const ids = new Set(flows.map((node) => node.id));

test('node ids are unique', () => {
  assert.equal(ids.size, flows.length);
});

test('every wire and every reference points to an existing node', () => {
  for (const node of flows) {
    for (const output of node.wires || []) {
      for (const target of output) {
        assert.ok(ids.has(target), `${node.id} wires to missing node ${target}`);
      }
    }
    for (const key of ['broker', 'postgreSQLConfig', 'z']) {
      if (node[key] && node.type !== 'mqtt-broker') {
        assert.ok(ids.has(node[key]), `${node.id} references missing ${key} ${node[key]}`);
      }
    }
  }
});

test('the number of wire groups matches the declared outputs', () => {
  for (const node of flows.filter((item) => item.type === 'function')) {
    assert.equal(node.wires.length, node.outputs, `${node.id} has mismatching outputs`);
  }
});

test('function nodes compile', () => {
  for (const node of flows.filter((item) => item.type === 'function')) {
    assert.doesNotThrow(() => new Function('msg', 'flow', 'global', 'env', node.func), node.id);
  }
});

test('no credentials are stored in the flows file', () => {
  const text = JSON.stringify(flows);
  assert.ok(!/"credentials"/.test(text));
  for (const node of flows.filter((item) => item.type === 'mqtt-broker')) {
    assert.ok(!node.user && !node.password);
  }
});
