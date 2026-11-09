'use strict';

const { writeCredentialsFile } = require('/iot/lib/credentials');
const ingest = require('/iot/lib/ingest');

writeCredentialsFile('/data/flows_cred.json', process.env);

module.exports = {
  flowFile: 'flows.json',
  uiPort: 1880,
  credentialSecret: false,
  functionExternalModules: false,
  functionGlobalContext: { ingest },
  logging: { console: { level: 'info', metrics: false, audit: false } },
  editorTheme: { projects: { enabled: false } },
};
