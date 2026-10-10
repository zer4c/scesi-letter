import { argon2id } from 'hash-wasm';

const encoder = new TextEncoder();
const ENVELOPE_VERSION = 1;
const KDF_PARAMETERS = Object.freeze({
  kdf: 'argon2id',
  memory_kib: 65536,
  iterations: 3,
  parallelism: 1,
});

function encodeBase64(bytes) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

function decodeBase64(value) {
  const binary = atob(value);
  const decoded = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  if (encodeBase64(decoded) !== value) throw new Error('Invalid signature envelope encoding');
  return decoded;
}

function additionalData(userId, purpose) {
  return encoder.encode(JSON.stringify({
    cipher: 'AES-256-GCM',
    envelope_version: ENVELOPE_VERSION,
    kdf: KDF_PARAMETERS.kdf,
    purpose,
    user_id: userId,
  }));
}

function validateEnvelope(envelope) {
  if (
    envelope.envelope_version !== ENVELOPE_VERSION
    || envelope.kdf !== KDF_PARAMETERS.kdf
    || envelope.memory_kib !== KDF_PARAMETERS.memory_kib
    || envelope.iterations !== KDF_PARAMETERS.iterations
    || envelope.parallelism !== KDF_PARAMETERS.parallelism
    || envelope.mime !== 'image/png'
  ) throw new Error('Unsupported signature envelope');
  const salt = decodeBase64(envelope.salt);
  const wrappedDek = decodeBase64(envelope.wrapped_dek);
  const wrappingIv = decodeBase64(envelope.wrapping_iv);
  const imageIv = decodeBase64(envelope.image_iv);
  const ciphertext = decodeBase64(envelope.ciphertext);
  if (
    salt.length !== 16
    || wrappedDek.length !== 48
    || wrappingIv.length !== 12
    || imageIv.length !== 12
    || envelope.wrapping_iv === envelope.image_iv
    || ciphertext.length < 17
    || ciphertext.length > 2 * 1024 * 1024 + 16
  ) throw new Error('Invalid signature envelope');
}

async function deriveWrappingKey(password, salt) {
  const rawKey = await argon2id({
    password,
    salt,
    parallelism: KDF_PARAMETERS.parallelism,
    iterations: KDF_PARAMETERS.iterations,
    memorySize: KDF_PARAMETERS.memory_kib,
    hashLength: 32,
    outputType: 'binary',
  });
  try {
    return await crypto.subtle.importKey('raw', rawKey, 'AES-GCM', false, ['encrypt', 'decrypt']);
  } finally {
    rawKey.fill(0);
  }
}

export async function encryptSignatureImage(imageBytes, password, userId) {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const wrappingIv = crypto.getRandomValues(new Uint8Array(12));
  const imageIv = crypto.getRandomValues(new Uint8Array(12));
  const dekBytes = crypto.getRandomValues(new Uint8Array(32));
  try {
    const kek = await deriveWrappingKey(password, salt);
    const dek = await crypto.subtle.importKey('raw', dekBytes, 'AES-GCM', false, ['encrypt', 'decrypt']);
    const [wrappedDek, ciphertext] = await Promise.all([
      crypto.subtle.encrypt(
        { name: 'AES-GCM', iv: wrappingIv, additionalData: additionalData(userId, 'signature-key') },
        kek,
        dekBytes,
      ),
      crypto.subtle.encrypt(
        { name: 'AES-GCM', iv: imageIv, additionalData: additionalData(userId, 'signature-image') },
        dek,
        imageBytes,
      ),
    ]);
    return {
      envelope_version: ENVELOPE_VERSION,
      ...KDF_PARAMETERS,
      salt: encodeBase64(salt),
      wrapped_dek: encodeBase64(new Uint8Array(wrappedDek)),
      wrapping_iv: encodeBase64(wrappingIv),
      ciphertext: encodeBase64(new Uint8Array(ciphertext)),
      image_iv: encodeBase64(imageIv),
      mime: 'image/png',
    };
  } finally {
    dekBytes.fill(0);
    imageBytes.fill(0);
  }
}

export async function decryptSignatureImage(envelope, password, userId) {
  validateEnvelope(envelope);
  const salt = decodeBase64(envelope.salt);
  const kek = await deriveWrappingKey(password, salt);
  const dekBytes = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: decodeBase64(envelope.wrapping_iv),
      additionalData: additionalData(userId, 'signature-key'),
    },
    kek,
    decodeBase64(envelope.wrapped_dek),
  );
  try {
    const dek = await crypto.subtle.importKey('raw', dekBytes, 'AES-GCM', false, ['decrypt']);
    return new Uint8Array(await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: decodeBase64(envelope.image_iv),
        additionalData: additionalData(userId, 'signature-image'),
      },
      dek,
      decodeBase64(envelope.ciphertext),
    ));
  } finally {
    new Uint8Array(dekBytes).fill(0);
  }
}

export async function rewrapSignatureKey(envelope, currentPassword, newPassword, userId) {
  validateEnvelope(envelope);
  const oldKek = await deriveWrappingKey(currentPassword, decodeBase64(envelope.salt));
  const dekBytes = await crypto.subtle.decrypt(
    {
      name: 'AES-GCM',
      iv: decodeBase64(envelope.wrapping_iv),
      additionalData: additionalData(userId, 'signature-key'),
    },
    oldKek,
    decodeBase64(envelope.wrapped_dek),
  );
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const wrappingIv = crypto.getRandomValues(new Uint8Array(12));
  try {
    const newKek = await deriveWrappingKey(newPassword, salt);
    const wrappedDek = await crypto.subtle.encrypt(
      {
        name: 'AES-GCM',
        iv: wrappingIv,
        additionalData: additionalData(userId, 'signature-key'),
      },
      newKek,
      dekBytes,
    );
    const sourceEnvelope = Object.fromEntries(
      Object.entries(envelope).filter(([key]) => key !== 'user_id' && key !== 'updated_at'),
    );
    return {
      ...sourceEnvelope,
      ...KDF_PARAMETERS,
      salt: encodeBase64(salt),
      wrapping_iv: encodeBase64(wrappingIv),
      wrapped_dek: encodeBase64(new Uint8Array(wrappedDek)),
    };
  } finally {
    new Uint8Array(dekBytes).fill(0);
  }
}
