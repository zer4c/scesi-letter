import assert from 'node:assert/strict';
import test from 'node:test';

import {
  decryptSignatureImage,
  encryptSignatureImage,
  rewrapSignatureKey,
} from '../src/modules/signature/signatureEnvelope.js';

test('signature encryption rejects wrong password, tampering, and owner changes', { timeout: 120_000 }, async () => {
  const expectedImage = new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 1, 2, 3, 4]);
  const image = expectedImage.slice();
  const ownerId = '42424242-4242-4242-8242-424242424242';
  const envelope = await encryptSignatureImage(image, 'synthetic-password-long', ownerId);

  assert.deepEqual(await decryptSignatureImage(envelope, 'synthetic-password-long', ownerId), expectedImage);
  await assert.rejects(decryptSignatureImage(envelope, 'incorrect-password-long', ownerId));
  await assert.rejects(decryptSignatureImage(envelope, 'synthetic-password-long', 'other-user'));

  const alteredCiphertext = { ...envelope, ciphertext: `${envelope.ciphertext.slice(0, -4)}AAAA` };
  await assert.rejects(decryptSignatureImage(alteredCiphertext, 'synthetic-password-long', ownerId));
  const alteredNonce = { ...envelope, image_iv: envelope.wrapping_iv };
  await assert.rejects(decryptSignatureImage(alteredNonce, 'synthetic-password-long', ownerId));

  const replacement = await rewrapSignatureKey(
    envelope,
    'synthetic-password-long',
    'replacement-password-long',
    ownerId,
  );
  assert.deepEqual(await decryptSignatureImage(replacement, 'replacement-password-long', ownerId), expectedImage);
  await assert.rejects(decryptSignatureImage(replacement, 'synthetic-password-long', ownerId));
  assert.equal(replacement.ciphertext, envelope.ciphertext);
  assert.deepEqual(image, new Uint8Array(image.length));
  image.fill(0);
  expectedImage.fill(0);
});
