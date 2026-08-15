/*
 * The live server's frame-outcome contract, as a table plus a working fake.
 *
 * Nothing in this file is guessed from the client's own comments. Every row of
 * `SERVER_FRAME_OUTCOMES` and every entry of `SERVER_SEQUENCE_CONSUMED` is measured
 * off the production ingress by
 * `evidence/phase1/x2-capture-client/probes/measure_frame_outcome_contract_probe.py`,
 * which re-runs `LiveLaneIngress.accept` for each scenario, reads
 * `snapshot(lane).next_sequence` either side of the call, and exits non-zero if one
 * cell here disagrees with what it measured. Change the server and that probe fails
 * before any browser test does.
 *
 * The one fact the whole 429 story rests on: `LiveLaneIngress._check_capacity` raises
 * *before* `lane.next_sequence += 1` (`moss_transcribe_diarize/app/live_ingest.py`
 * :145 vs :171), so a lane-capacity 429 leaves the sequence unconsumed and the frame
 * MUST be resent. Queue backpressure is raised by the mixer after
 * `v2_session.accept` has already returned (`live_transport.py` :242 -> :244 -> :280),
 * so it IS consumed and the frame must NOT be resent. Both are HTTP 429; only
 * `failure.code` separates them, and the backpressure body has no `failure` key at all.
 */

export type ServerFrameScenario =
  | "in_order_first_frame"
  | "replay_of_acked_sequence"
  | "sequence_ahead_of_expected"
  | "epoch_advance_without_discontinuity"
  | "epoch_advance_with_discontinuity"
  | "stale_device_epoch"
  | "lane_retention_capacity_reached"
  | "resent_after_capacity_released"
  | "single_frame_exceeds_lane_budget"
  | "pruned_replay"
  | "queue_backpressure_after_accept";

/** [scenario, HTTP status, `failure.code` or null when the body carries no failure]. */
export const SERVER_FRAME_OUTCOMES: ReadonlyArray<
  readonly [ServerFrameScenario, number, string | null]
> = [
  ["in_order_first_frame", 200, null],
  ["replay_of_acked_sequence", 200, null],
  ["sequence_ahead_of_expected", 409, "v2_out_of_order_frame"],
  ["epoch_advance_without_discontinuity", 409, "v2_epoch_discontinuity_required"],
  ["epoch_advance_with_discontinuity", 200, null],
  ["stale_device_epoch", 409, "v2_stale_device_epoch"],
  ["lane_retention_capacity_reached", 429, "v2_lane_retention_capacity_reached"],
  ["resent_after_capacity_released", 200, null],
  ["single_frame_exceeds_lane_budget", 429, "v2_lane_retention_capacity_reached"],
  ["pruned_replay", 409, "v2_pruned_replay"],
  ["queue_backpressure_after_accept", 429, null],
] as const;

/** Did the lane's `next_sequence` advance? This is what decides resend vs advance. */
export const SERVER_SEQUENCE_CONSUMED: Readonly<Record<ServerFrameScenario, boolean>> = {
  "in_order_first_frame": true,
  "replay_of_acked_sequence": false,
  "sequence_ahead_of_expected": false,
  "epoch_advance_without_discontinuity": false,
  "epoch_advance_with_discontinuity": true,
  "stale_device_epoch": false,
  "lane_retention_capacity_reached": false,
  "resent_after_capacity_released": true,
  "single_frame_exceeds_lane_budget": false,
  "pruned_replay": false,
  "queue_backpressure_after_accept": true,
};

type WireFrame = {
  lane: string;
  sequence: number;
  device_epoch: number;
  discontinuity: boolean;
  sample_count: number;
};

type LaneIngressState = {
  nextSequence: number;
  retainedSamples: number;
  currentDeviceEpoch: number | null;
  ackedSequences: Set<number>;
  prunedThrough: number;
};

export type FakeResponse = {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
};

/**
 * A faithful in-test stand-in for `POST /api/live/sessions/{id}/frames`.
 *
 * Ordering mirrors `LiveLaneIngress.accept`: ack replay, prune window, sequence,
 * epoch, capacity, and only then consumption -- followed by the mixer's
 * post-admission backpressure. Frames arrive in whatever order the client's fetches
 * actually reach it, which is exactly how an unserialized client wedges its own lane.
 */
export class FakeLaneIngressServer {
  readonly received: WireFrame[] = [];
  readonly statuses: number[] = [];
  private readonly lanes = new Map<string, LaneIngressState>();
  private readonly maxRetainedSamples: number;
  private readonly maxRetainedAcks: number;
  private backpressureRemaining = 0;

  constructor(options: { maxRetainedSamples?: number; maxRetainedAcks?: number } = {}) {
    this.maxRetainedSamples = options.maxRetainedSamples ?? Number.MAX_SAFE_INTEGER;
    this.maxRetainedAcks = options.maxRetainedAcks ?? Number.MAX_SAFE_INTEGER;
  }

  /** Free retained lane audio, the way the mixer does when it consumes a prefix. */
  releaseRetained(lane: string): void {
    this.lane(lane).retainedSamples = 0;
  }

  /** Make the next `count` admitted frames answer with the failure-less queue 429. */
  applyQueueBackpressure(count: number): void {
    this.backpressureRemaining = count;
  }

  laneState(lane: string): LaneIngressState {
    return this.lane(lane);
  }

  /** How many frames this lane has actually admitted -- the only real progress metric. */
  admitted(lane: string): number {
    return this.lane(lane).nextSequence;
  }

  handle(frame: WireFrame): FakeResponse {
    this.received.push(frame);
    const response = this.decide(frame);
    this.statuses.push(response.status);
    return response;
  }

  private lane(name: string): LaneIngressState {
    let state = this.lanes.get(name);
    if (!state) {
      state = {
        nextSequence: 0,
        retainedSamples: 0,
        currentDeviceEpoch: null,
        ackedSequences: new Set(),
        prunedThrough: -1,
      };
      this.lanes.set(name, state);
    }
    return state;
  }

  private decide(frame: WireFrame): FakeResponse {
    const lane = this.lane(frame.lane);
    if (lane.ackedSequences.has(frame.sequence)) return ok();
    if (frame.sequence <= lane.prunedThrough) {
      return conflict(409, {
        code: "v2_pruned_replay",
        lane: frame.lane,
        sequence: frame.sequence,
        pruned_through_sequence: lane.prunedThrough,
      });
    }
    if (frame.sequence !== lane.nextSequence) {
      return conflict(409, {
        code: "v2_out_of_order_frame",
        lane: frame.lane,
        expected_sequence: lane.nextSequence,
        received_sequence: frame.sequence,
      });
    }
    const current = lane.currentDeviceEpoch;
    if (current !== null && frame.device_epoch !== current) {
      if (frame.device_epoch < current) {
        return conflict(409, {
          code: "v2_stale_device_epoch",
          lane: frame.lane,
          sequence: frame.sequence,
          current_device_epoch: current,
          received_device_epoch: frame.device_epoch,
        });
      }
      if (!frame.discontinuity) {
        return conflict(409, {
          code: "v2_epoch_discontinuity_required",
          lane: frame.lane,
          sequence: frame.sequence,
          current_device_epoch: current,
          received_device_epoch: frame.device_epoch,
        });
      }
    }
    // Capacity is checked before anything is consumed. This is the whole point.
    if (
      frame.sample_count > this.maxRetainedSamples ||
      lane.retainedSamples + frame.sample_count > this.maxRetainedSamples
    ) {
      return conflict(429, {
        code: "v2_lane_retention_capacity_reached",
        lane: frame.lane,
        max_retained_samples: this.maxRetainedSamples,
        retained_samples: lane.retainedSamples,
        frame_sample_count: frame.sample_count,
      });
    }

    lane.ackedSequences.add(frame.sequence);
    if (lane.ackedSequences.size > this.maxRetainedAcks) {
      const oldest = Math.min(...lane.ackedSequences);
      lane.ackedSequences.delete(oldest);
      lane.prunedThrough = Math.max(lane.prunedThrough, oldest);
    }
    lane.retainedSamples += frame.sample_count;
    lane.nextSequence += 1;
    lane.currentDeviceEpoch = frame.device_epoch;

    if (this.backpressureRemaining > 0) {
      this.backpressureRemaining -= 1;
      // The mixer raises after admission, so the sequence above stays consumed and the
      // body carries no `failure` key at all.
      return {
        ok: false,
        status: 429,
        json: async () => ({ detail: "live session queue is full.", snapshot: null }),
      };
    }
    return ok();
  }
}

function ok(): FakeResponse {
  return { ok: true, status: 200, json: async () => ({ ack: {}, queued_item_ids: [] }) };
}

function conflict(status: number, failure: Record<string, unknown>): FakeResponse {
  return {
    ok: false,
    status,
    json: async () => ({ detail: String(failure.code), failure, snapshot: null }),
  };
}
