const https = require('https');

const endpoints = [
  { type: 'auth', name: 'Auth Endpoint' },
  { type: 'csv', name: 'CSV Technical Data' },
  { type: 'docs', name: 'Docs Endpoint' },
  { type: 'flota', name: 'Fleet Data' },
  { type: 'vacaciones', name: 'Vacaciones' },
  { type: 'cumplimiento', name: 'Cumplimiento' },
  { type: 'rm', name: 'Remote Maintenance' },
  { type: 'medalia-coord', name: 'Medalia Coordinadores' }
];

const deploymentId = 'AKfycbz0lVQF2dmoXNQ5mKYJpyEjrUubsxWxjaow27KE1pC3eLbmHQSbwRbgDUOnG5xcxti_';

function followRedirect(url, depth = 0) {
  return new Promise((resolve) => {
    if (depth > 5) {
      resolve({ success: false, error: 'Too many redirects' });
      return;
    }

    https.get(url, { timeout: 5000 }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        followRedirect(res.headers.location, depth + 1).then(resolve);
      } else {
        let data = '';
        res.on('data', (chunk) => { data += chunk; });
        res.on('end', () => {
          resolve({
            success: res.statusCode === 200,
            statusCode: res.statusCode,
            contentLength: data.length,
            preview: data.substring(0, 50)
          });
        });
      }
    }).on('error', (err) => {
      resolve({ success: false, error: err.message });
    }).on('timeout', function() {
      this.destroy();
      resolve({ success: false, error: 'Timeout' });
    });
  });
}

async function testEndpoint(endpoint) {
  const url = `https://script.google.com/macros/s/${deploymentId}/exec?type=${endpoint.type}`;
  const result = await followRedirect(url);

  if (result.success) {
    console.log(`✓ ${endpoint.name.padEnd(25)} - OK (${result.contentLength} bytes)`);
  } else {
    console.log(`✗ ${endpoint.name.padEnd(25)} - ${result.error || `HTTP ${result.statusCode}`}`);
  }
  return result;
}

async function runTests() {
  console.log(`Testing New Deployment:`);
  console.log(`${deploymentId}\n`);
  console.log('Endpoint Results:');
  console.log('='.repeat(60));

  let passed = 0;
  for (const endpoint of endpoints) {
    const result = await testEndpoint(endpoint);
    if (result.success) passed++;
  }

  console.log('='.repeat(60));
  console.log(`\n${passed}/${endpoints.length} endpoints working`);
  console.log('\n✓ Verification complete\n');
}

runTests();
