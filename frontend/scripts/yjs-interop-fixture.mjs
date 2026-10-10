import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import * as decoding from 'lib0/decoding';
import * as Y from 'yjs';

const document = new Y.Doc();
const body = document.getText('body');
const metadata = document.getMap('metadata');
body.insert(0, 'Solicitud académica');
metadata.set('document_type', 'SOL');
metadata.set('topic', 'aulas');

const child = spawn(
  'uv',
  ['run', 'python', 'scripts/yjs_interop_fixture.py'],
  {
    cwd: fileURLToPath(new URL('../../backend/', import.meta.url)),
    env: {
      ...process.env,
      UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? '/tmp/scesi-uv-cache',
      UV_LINK_MODE: 'copy',
    },
    stdio: ['pipe', 'pipe', 'pipe'],
  },
);

function sameStateVector(leftBytes, rightBase64) {
  const decodeState = (bytes) => {
    const decoder = decoding.createDecoder(bytes);
    const entries = new Map();
    const count = decoding.readVarUint(decoder);
    for (let index = 0; index < count; index += 1) {
      entries.set(
        decoding.readVarUint(decoder),
        decoding.readVarUint(decoder),
      );
    }
    return entries;
  };
  const left = decodeState(leftBytes);
  const right = decodeState(Buffer.from(rightBase64, 'base64'));
  return left.size === right.size
    && [...left].every(([clientId, clock]) => right.get(clientId) === clock);
}
const lines = createInterface({ input: child.stdout });
const lineIterator = lines[Symbol.asyncIterator]();
let stderr = '';
child.stderr.setEncoding('utf8').on('data', (chunk) => {
  stderr += chunk;
});
const exitCode = new Promise((resolve) => child.once('close', resolve));

const initialStateVector = Y.encodeStateVector(document);
const initialUpdate = Y.encodeStateAsUpdate(document);
const reconnectingClient = new Y.Doc();
Y.applyUpdate(reconnectingClient, initialUpdate);
const reconnectingBody = reconnectingClient.getText('body');
const reconnectingMetadata = reconnectingClient.getMap('metadata');
child.stdin.write(`${JSON.stringify({
  initial_state_vector: Buffer.from(initialStateVector).toString('base64'),
  initial_update: Buffer.from(initialUpdate).toString('base64'),
})}\n`);

const firstLine = await lineIterator.next();
if (firstLine.done) throw new Error(stderr || 'Python CRDT fixture failed');
const response = JSON.parse(firstLine.value);
Y.applyUpdate(document, Buffer.from(response.server_update, 'base64'));
if (body.toString() !== 'Solicitud académica respuesta') {
  throw new Error('JavaScript failed to apply the Python Y.Text update');
}
if (metadata.get('server_note') !== 'saved') {
  throw new Error('JavaScript failed to apply the Python Y.Map update');
}
if (!sameStateVector(Y.encodeStateVector(document), response.server_state_vector)) {
  throw new Error('JavaScript and Python state vectors do not match');
}

const peerStateVector = Y.encodeStateVector(document);
const reconnectStateVector = Y.encodeStateVector(reconnectingClient);
reconnectingBody.insert(reconnectingBody.length, ' edición reconectada');
reconnectingMetadata.set('client_note', 'reconnected');
const reconnectUpdate = Y.encodeStateAsUpdate(
  reconnectingClient,
  reconnectStateVector,
);
child.stdin.write(`${JSON.stringify({
  client_state_vector: Buffer.from(reconnectStateVector).toString('base64'),
  peer_state_vector: Buffer.from(peerStateVector).toString('base64'),
  reconnect_update: Buffer.from(reconnectUpdate).toString('base64'),
})}\n`);
child.stdin.end();

const secondLine = await lineIterator.next();
const status = await exitCode;
if (status !== 0 || secondLine.done) {
  throw new Error(stderr || 'Python reconnect fixture failed');
}
const finalResponse = JSON.parse(secondLine.value);
Y.applyUpdate(
  reconnectingClient,
  Buffer.from(finalResponse.reconnect_update, 'base64'),
);
Y.applyUpdate(document, Buffer.from(finalResponse.peer_update, 'base64'));
if (
  !body.toString().includes('Solicitud académica')
  || !body.toString().includes('respuesta')
  || !body.toString().includes('edición reconectada')
  || body.toString() !== reconnectingBody.toString()
  || metadata.get('client_note') !== reconnectingMetadata.get('client_note')
) {
  throw new Error('Yjs reconnect state did not converge');
}
console.log('Yjs and pycrdt binary interoperability verified.');
