export function aggregateSafeStopState(results) {
  const statuses = Object.values(results);

  if (statuses.length === 0) {
    return 'PENDING';
  }

  if (statuses.includes('FAILED')) {
    return 'FAILED';
  }

  if (statuses.every((status) => status === 'ACKNOWLEDGED')) {
    return 'ACKNOWLEDGED';
  }

  return 'PENDING';
}


export function recordSafeStopResult(results, commandId, status) {
  if (!Object.prototype.hasOwnProperty.call(results, commandId)) {
    return results;
  }

  if (results[commandId] === 'FAILED') {
    return results;
  }

  return {
    ...results,
    [commandId]: status,
  };
}
