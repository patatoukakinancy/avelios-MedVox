// Runs on the audio thread: groups microphone samples into 40 ms chunks.
const CHUNK_SAMPLES = 960 // 40 ms at 24 kHz

class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.chunk = new Float32Array(CHUNK_SAMPLES)
    this.length = 0
  }

  process(inputs) {
    const channel = inputs[0]?.[0]
    if (channel) {
      for (const sample of channel) {
        this.chunk[this.length++] = sample
        if (this.length === CHUNK_SAMPLES) {
          this.port.postMessage(this.chunk, [this.chunk.buffer])
          this.chunk = new Float32Array(CHUNK_SAMPLES)
          this.length = 0
        }
      }
    }
    return true
  }
}

registerProcessor('pcm-capture', PcmCapture)
