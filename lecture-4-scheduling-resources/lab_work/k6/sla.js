import http from 'k6/http';
import { check, sleep } from 'k6';
export const options = {
  vus: 3,
  duration: '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<1000'],
    checks: ['rate>0.99'],
  },
};
const base = __ENV.BASE_URL || 'http://shop-shop-api:8080';
export default function () {
  const res = http.post(`${base}/order`, JSON.stringify({ item: `sla-${__VU}-${__ITER}` }), {
    headers: { 'Content-Type': 'application/json' },
    timeout: '2s',
  });
  check(res, { 'order created': (r) => r.status === 201 });
  sleep(0.25);
}
