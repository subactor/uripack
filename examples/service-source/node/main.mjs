import { readFileSync } from 'node:fs';
const uri = 'demo://services/node/count';
const request = JSON.parse(readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify({uri, count: request.items.length}) + '\n');
