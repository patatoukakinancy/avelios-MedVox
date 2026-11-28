// Audio format from CONTRACT.md: PCM16 little-endian, 24 kHz, mono, base64.
export const SAMPLE_RATE = 24_000

// Loudness of a block of samples, from 0 (silence) to 1.
export function rms(samples: Float32Array) {
  let sum = 0
  for (const sample of samples) sum += sample * sample
  return Math.sqrt(sum / (samples.length || 1))
}

export function floatToPcm16Base64(samples: Float32Array): string {
  const bytes = new Uint8Array(samples.length * 2)
  const view = new DataView(bytes.buffer)
  samples.forEach((sample, i) => {
    const clipped = Math.max(-1, Math.min(1, sample))
    view.setInt16(i * 2, Math.round(clipped * (clipped < 0 ? 0x8000 : 0x7fff)), true)
  })
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

// Throws if the input is not valid base64.
export function pcm16Base64ToFloat(data: string) {
  const binary = atob(data)
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0))
  const view = new DataView(bytes.buffer)
  const samples = new Float32Array(Math.floor(bytes.length / 2))
  for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 0x8000
  return samples
}
