import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 5,
  duration: '2m',
};

const base = __ENV.BASE_URL || 'http://127.0.0.1:8080';

export default function () {
  const res = http.post(
    `${base}/order`,
    JSON.stringify({ item: 'coffee' }),
    { headers: { 'Content-Type': 'application/json' } },
  );

  check(res, {
    'order created': (r) => r.status === 201,
  });

  sleep(0.2);
}
