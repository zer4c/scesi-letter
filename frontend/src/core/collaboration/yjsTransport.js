import * as decoding from 'lib0/decoding';
import * as encoding from 'lib0/encoding';
import * as awarenessProtocol from 'y-protocols/awareness';
import * as syncProtocol from 'y-protocols/sync';
import { Awareness } from 'y-protocols/awareness';
import * as Y from 'yjs';

const MESSAGE_SYNC = 0;
const MESSAGE_AWARENESS = 1;
const MESSAGE_SYNC_UPDATE = 2;
const MAX_FRAME_BYTES = 1024 * 1024;

export function createCollaborativeDocument({
  documentId,
  csrfToken,
  onStatusChange = () => {},
  onAwarenessChange = () => {},
  onSynced = () => {},
  onLocalUpdate = () => {},
  onUpdatePersisted = () => {},
  onError = () => {},
}) {
  const document = new Y.Doc();
  const awareness = new Awareness(document);
  let socket;
  let stopped = false;
  let reconnectTimer;
  let reconnectAttempt = 0;

  const socketUrl = () => {
    const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${scheme}//${window.location.host}/ws/documents/${documentId}`;
  };

  const send = (message) => {
    if (message.byteLength > MAX_FRAME_BYTES) {
      onError(new Error('Collaboration message exceeds the size limit'));
      return;
    }
    if (socket?.readyState === WebSocket.OPEN) socket.send(message);
  };

  const connect = () => {
    if (stopped) return;
    onStatusChange('connecting');
    if (!csrfToken) {
      onError(new Error('An authenticated session is required'));
      onStatusChange('unauthorized');
      stopped = true;
      return;
    }
    socket = new WebSocket(socketUrl(), ['yjs']);
    socket.binaryType = 'arraybuffer';

    socket.addEventListener('open', () => {
      reconnectAttempt = 0;
      onStatusChange('connected');
      const encoder = encoding.createEncoder();
      encoding.writeVarUint(encoder, MESSAGE_SYNC);
      syncProtocol.writeSyncStep1(encoder, document);
      send(encoding.toUint8Array(encoder));
    });

    socket.addEventListener('message', ({ data }) => {
      if (!(data instanceof ArrayBuffer) || data.byteLength > MAX_FRAME_BYTES) {
        onError(new Error('The collaboration server sent an invalid frame'));
        socket.close(1009, 'Invalid collaboration frame');
        return;
      }
      try {
        const decoder = decoding.createDecoder(new Uint8Array(data));
        const messageType = decoding.readVarUint(decoder);
        if (messageType === MESSAGE_SYNC) {
          const encoder = encoding.createEncoder();
          encoding.writeVarUint(encoder, MESSAGE_SYNC);
          const syncType = syncProtocol.readSyncMessage(decoder, encoder, document, socket);
          if (syncType === syncProtocol.messageYjsSyncStep2) onSynced();
          if (syncType === MESSAGE_SYNC_UPDATE) onUpdatePersisted();
          if (encoding.length(encoder) > 1) send(encoding.toUint8Array(encoder));
        } else if (messageType === MESSAGE_AWARENESS) {
          awarenessProtocol.applyAwarenessUpdate(
            awareness,
            decoding.readVarUint8Array(decoder),
            socket,
          );
        } else {
          throw new Error('The collaboration server sent an unknown message');
        }
      } catch (error) {
        onError(error);
        socket.close(1003, 'Invalid collaboration message');
      }
    });

    socket.addEventListener('close', ({ code }) => {
      if (stopped) return;
      if ([4401, 4403, 4404, 4429, 1008].includes(code)) {
        stopped = true;
        onStatusChange('unauthorized');
        return;
      }
      onStatusChange('reconnecting');
      const delay = Math.min(250 * 2 ** reconnectAttempt, 10_000);
      reconnectAttempt += 1;
      reconnectTimer = window.setTimeout(connect, delay);
    });

    socket.addEventListener('error', () => {
      onStatusChange('disconnected');
    });
  };

  document.on('update', (update, origin) => {
    if (origin === socket) return;
    onLocalUpdate();
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_SYNC);
    syncProtocol.writeUpdate(encoder, update);
    send(encoding.toUint8Array(encoder));
  });

  awareness.on('update', ({ added, updated, removed }, origin) => {
    if (origin === socket) return;
    const changedClients = added.concat(updated, removed);
    if (changedClients.length === 0) return;
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, MESSAGE_AWARENESS);
    encoding.writeVarUint8Array(
      encoder,
      awarenessProtocol.encodeAwarenessUpdate(awareness, changedClients),
    );
    send(encoding.toUint8Array(encoder));
    onAwarenessChange(awareness.getStates());
  });

  awareness.setLocalState(null);
  connect();

  return {
    document,
    body: document.getText('body'),
    metadata: document.getMap('metadata'),
    awareness,
    close() {
      stopped = true;
      window.clearTimeout(reconnectTimer);
      awareness.destroy();
      document.destroy();
      socket?.close(1000, 'Editor closed');
      onStatusChange('disconnected');
    },
  };
}
