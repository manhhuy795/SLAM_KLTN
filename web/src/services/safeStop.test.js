import assert from 'node:assert/strict';

import {
  aggregateSafeStopState,
  recordSafeStopResult,
} from './safeStop.js';


assert.equal(
  aggregateSafeStopState({ one: 'ACKNOWLEDGED' }),
  'ACKNOWLEDGED',
);
assert.equal(
  aggregateSafeStopState({
    one: 'ACKNOWLEDGED',
    two: 'ACKNOWLEDGED',
  }),
  'ACKNOWLEDGED',
);
assert.equal(
  aggregateSafeStopState({
    one: 'ACKNOWLEDGED',
    two: 'PENDING',
  }),
  'PENDING',
);
assert.equal(
  aggregateSafeStopState({
    one: 'FAILED',
    two: 'ACKNOWLEDGED',
  }),
  'FAILED',
);

const failedFirst = recordSafeStopResult(
  { one: 'FAILED', two: 'PENDING' },
  'two',
  'ACKNOWLEDGED',
);
assert.equal(aggregateSafeStopState(failedFirst), 'FAILED');

const failedAfterAck = recordSafeStopResult(
  { one: 'ACKNOWLEDGED', two: 'PENDING' },
  'two',
  'FAILED',
);
assert.equal(aggregateSafeStopState(failedAfterAck), 'FAILED');

console.log('Safe Stop aggregate smoke: PASS');
