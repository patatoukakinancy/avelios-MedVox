import { SAMPLE_RATE } from './pcm'

export interface MicCapture {
  stop(): void
}

// onLost is called if the device disappears (for example, headphones unplugged).
export async function startMicCapture(
  onChunk: (samples: Float32Array) => void,
  onLost: () => void,
): Promise<MicCapture> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  let context: AudioContext | undefined
  const release = () => {
    stream.getTracks().forEach((track) => track.stop())
    void context?.close()
  }

  try {
    // The browser resamples the microphone to the context's rate (Chrome and Edge).
    context = new AudioContext({ sampleRate: SAMPLE_RATE })
    await context.audioWorklet.addModule('/pcm-capture-worklet.js')
    const source = context.createMediaStreamSource(stream)
    const worklet = new AudioWorkletNode(context, 'pcm-capture', {
      numberOfOutputs: 0,
      channelCount: 1,
      channelCountMode: 'explicit',
    })
    worklet.port.onmessage = (event: MessageEvent<Float32Array>) => onChunk(event.data)
    source.connect(worklet)
    await context.resume()
    stream.getAudioTracks().forEach((track) => (track.onended = onLost))

    return {
      stop() {
        worklet.port.onmessage = null
        release()
      },
    }
  } catch (error) {
    release()
    throw error
  }
}
