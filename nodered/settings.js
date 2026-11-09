'use strict';

const bcrypt = require('bcryptjs');
const { writeCredentialsFile } = require('/iot/lib/credentials');
const ingest = require('/iot/lib/ingest');
const rules = require('/iot/lib/rules');
const alerts = require('/iot/lib/alerts');

writeCredentialsFile('/data/flows_cred.json', process.env);

const adminPassword = process.env.NODE_RED_ADMIN_PASSWORD;
if (!adminPassword) {
  throw new Error('NODE_RED_ADMIN_PASSWORD must be set');
}

module.exports = {
  flowFile: 'flows.json',
  uiPort: 1880,
  httpAdminRoot: '/nodered',
  adminAuth: {
    type: 'credentials',
    users: [
      {
        username: process.env.NODE_RED_ADMIN_USER || 'admin',
        password: bcrypt.hashSync(adminPassword, 8),
        permissions: '*',
      },
    ],
  },
  credentialSecret: false,
  functionExternalModules: false,
  functionGlobalContext: { ingest, rules, alerts },
  logging: { console: { level: 'info', metrics: false, audit: false } },
  editorTheme: { projects: { enabled: false } },
};
