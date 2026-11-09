'use strict';

const { writeCredentialsFile } = require('/iot/lib/credentials');
const ingest = require('/iot/lib/ingest');
const rules = require('/iot/lib/rules');

writeCredentialsFile('/data/flows_cred.json', process.env);

module.exports = {
  flowFile: 'flows.json',
  uiPort: 1880,
  credentialSecret: false,
  functionExternalModules: false,
  functionGlobalContext: { ingest, rules },
  logging: { console: { level: 'info', metrics: false, audit: false } },
  editorTheme: { projects: { enabled: false } },
};
