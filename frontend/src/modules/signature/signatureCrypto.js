let worker;
let nextRequestId = 0;
const pending = new Map();

function getWorker() {
  if (worker) return worker;
  worker = new Worker(new URL('./signatureCrypto.worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = ({ data }) => {
    const request = pending.get(data.id);
    if (!request) return;
    pending.delete(data.id);
    if (data.error) request.reject(new Error(data.error));
    else request.resolve(data.result);
    if (pending.size === 0) {
      worker.terminate();
      worker = undefined;
    }
  };
  worker.onerror = () => {
    for (const request of pending.values()) request.reject(new Error('Signature encryption is unavailable'));
    pending.clear();
    worker.terminate();
    worker = undefined;
  };
  return worker;
}

function runWorker(operation, payload, transfer = []) {
  const id = ++nextRequestId;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    getWorker().postMessage({ id, operation, ...payload }, transfer);
  });
}

export function encryptInWorker(imageBytes, password, userId) {
  const buffer = imageBytes.buffer.slice(
    imageBytes.byteOffset,
    imageBytes.byteOffset + imageBytes.byteLength,
  );
  return runWorker('encrypt', { imageBytes: buffer, password, userId }, [buffer]);
}

export function decryptInWorker(envelope, password, userId) {
  return runWorker('decrypt', { envelope, password, userId });
}

export function rewrapInWorker(envelope, currentPassword, newPassword, userId) {
  return runWorker('rewrap', { envelope, password: currentPassword, newPassword, userId });
}

export function terminateSignatureWorker() {
  worker?.terminate();
  worker = undefined;
  for (const request of pending.values()) request.reject(new Error('Signature operation cancelled'));
  pending.clear();
}
