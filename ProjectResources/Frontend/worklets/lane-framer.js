// Descriptor-sized frames leave this worklet only through its message port. The
// main thread must use those messages as its only frame and heartbeat trigger.
class LaneFramer extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.lane = options.processorOptions.lane;
    this.frameSamples = options.processorOptions.frameSamples;
    this.buffer = new Float32Array(this.frameSamples);
    this.filled = 0;
    this.firstSampleFrame = null;
    this.framesSent = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (input.length === 0) return true;

    const samples = input[0];
    if (this.firstSampleFrame === null) this.firstSampleFrame = currentFrame;

    for (let index = 0; index < samples.length; index += 1) {
      this.buffer[this.filled] = samples[index];
      this.filled += 1;
      if (this.filled !== this.frameSamples) continue;

      const frame = this.buffer;
      this.port.postMessage(
        {
          type: "frame",
          lane: this.lane,
          samples: frame,
          startFrame: this.firstSampleFrame + this.framesSent * this.frameSamples,
        },
        [frame.buffer],
      );
      this.framesSent += 1;
      this.buffer = new Float32Array(this.frameSamples);
      this.filled = 0;
    }
    return true;
  }
}

registerProcessor("lane-framer", LaneFramer);

