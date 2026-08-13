// PROTOTYPE — throwaway. Lane framer: aggregate 128-sample render quanta into
// exact 8000-sample mono frames at context rate (16 kHz), per the MOSS v2 contract.
// Frames are pushed to the main thread via port messages (no timers involved),
// so background-tab timer throttling cannot stall the send cadence.

class LaneFramer extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.lane = options.processorOptions.lane;
    this.frameSamples = options.processorOptions.frameSamples; // 8000
    this.buf = new Float32Array(this.frameSamples);
    this.fill = 0;
    // 8000 samples = 62.5 quanta, so frame boundaries land mid-quantum; deriving
    // start times from currentFrame at fill time would jitter by up to 128
    // samples. Anchor once at the first delivered sample and advance
    // arithmetically instead — exact and monotonic.
    this.baseFrame = null;
    this.framesSent = 0;
    this.quanta = 0;
  }

  process(inputs) {
    const input = inputs[0];
    this.quanta += 1;
    if (input.length === 0) return true; // no channels yet (track not started)
    const ch = input[0];
    if (this.baseFrame === null) this.baseFrame = currentFrame;
    for (let i = 0; i < ch.length; i++) {
      this.buf[this.fill++] = ch[i];
      if (this.fill === this.frameSamples) {
        const samples = this.buf;
        this.port.postMessage(
          {
            type: "frame",
            lane: this.lane,
            samples,
            startFrame: this.baseFrame + this.framesSent * this.frameSamples,
            quanta: this.quanta,
            contextFrame: currentFrame,
          },
          [samples.buffer],
        );
        this.framesSent += 1;
        this.buf = new Float32Array(this.frameSamples);
        this.fill = 0;
      }
    }
    return true;
  }
}

registerProcessor("lane-framer", LaneFramer);
