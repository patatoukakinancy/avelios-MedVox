import { pcm16Base64ToFloat, SAMPLE_RATE } from './pcm'

// Head start for the first chunk of a reply, to absorb network jitter. Tune if there are gaps.
const LEAD_SECONDS = 0.05

interface Segment {
  start: number
  duration: number
}

// Plays audio.delta chunks back to back.
export function createAudioPlayer(onPlayingChange: (playing: boolean) => void) {
  let context: AudioContext | null = null
  const active = new Set<AudioBufferSourceNode>()
  let segments: Segment[] = []
  let nextStart = 0

  function stop() {
    active.forEach((source) => {
      source.onended = null
      source.stop()
    })
    active.clear()
    segments = []
    nextStart = 0
    onPlayingChange(false)
  }

  return {
    enqueue(base64: string) {
      let samples
      try {
        samples = pcm16Base64ToFloat(base64)
      } catch {
        console.warn('[audio] ignored a chunk that is not valid base64')
        return
      }
      if (samples.length === 0) return

      context ??= new AudioContext({ sampleRate: SAMPLE_RATE })
      void context.resume()
      const buffer = context.createBuffer(1, samples.length, SAMPLE_RATE)
      buffer.copyToChannel(samples, 0)
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(context.destination)

      const earliest = context.currentTime + (active.size === 0 ? LEAD_SECONDS : 0)
      const start = Math.max(nextStart, earliest)
      nextStart = start + buffer.duration
      segments.push({ start, duration: buffer.duration })
      active.add(source)
      source.onended = () => {
        active.delete(source)
        if (active.size === 0) onPlayingChange(false)
      }
      source.start(start)
      onPlayingChange(true)
    },
    stop,
    // Audio scheduled since the last stop() that the context has already rendered.
    playedMs() {
      const now = context?.currentTime ?? 0
      const seconds = segments.reduce(
        (sum, { start, duration }) => sum + Math.max(0, Math.min(duration, now - start)),
        0,
      )
      return Math.round(seconds * 1000)
    },
    isPlaying: () => active.size > 0,
    // The player can be used again afterwards; a new context is created on demand.
    close() {
      stop()
      void context?.close()
      context = null
    },
  }
}
