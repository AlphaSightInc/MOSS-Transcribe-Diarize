"""THROWAWAY: construct isolated runtime candidate; never edits production files."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'runtime/app'
def edit(name, changes):
    text = (ROOT/'moss_transcribe_diarize/app'/name).read_text()
    for old,new in changes:
        assert old in text, (name, old[:80])
        text=text.replace(old,new)
    (OUT/name).write_text(text)
edit('live_session.py', [
 ('    analysis_pcm: bytes | None = None','    analysis_pcm: bytes | None = None\n    lane_pcm: tuple[tuple[str, bytes], ...] = ()\n    lane_silent: tuple[tuple[str, bool], ...] = ()'),
 ('    authority: str\n','    authority: str\n    source_lane: str | None = None\n'),
 ('    local_speakers: tuple[str, ...] = ()\n','    local_speakers: tuple[str, ...] = ()\n    source_lanes: tuple[str, ...] = ()\n'),
 ('    revised_transcript: str | None = None','    revised_transcript: str | None = None\n    source_lanes: tuple[str, ...] = ()'),
 ('            identity_snapshot_version=identity_snapshot.version,','            identity_snapshot_version=identity_snapshot.version,\n            source_lanes=result.source_lanes,'),
 ('            for parsed in span_segments(published, sample_count=commit.end_sample - commit.start_sample):','            for index, parsed in enumerate(span_segments(published, sample_count=commit.end_sample - commit.start_sample)):'),
 ('                        authority="provisional",','                        authority="provisional",\n                        source_lane=commit.source_lanes[index] if commit.source_lanes else None,'),
 ('        previous_end = proposal.start_sample\n','        previous_ends = {}\n        previous_key = None\n'),
 ('            if segment.start_sample < previous_end:\n                return "segments_out_of_order"\n            previous_end = segment.end_sample','            key = (segment.start_sample, {None: 0, "system": 0, "microphone": 1}[segment.source_lane], segment.end_sample)\n            if previous_key is not None and key < previous_key:\n                return "segments_out_of_order"\n            if segment.start_sample < previous_ends.get(segment.source_lane, proposal.start_sample):\n                return "segments_out_of_order"\n            previous_ends[segment.source_lane] = segment.end_sample\n            previous_key = key'),
 ('                    segment.start_sample, segment.end_sample, base','                    segment.start_sample, segment.end_sample, tuple(s for s in base if s.source_lane == segment.source_lane)'),
])
edit('live_mixer.py', [
 ('            analysis_pcm=analysis_pcm,','            analysis_pcm=analysis_pcm,\n            lane_pcm=tuple((lane.value, struct.pack("<" + "h" * sample_count, *(max(-32768, min(32767, int(x * 32768))) for x in lane_values[lane]))) for lane in (LiveLane.SYSTEM, LiveLane.MICROPHONE)),\n            lane_silent=tuple((lane.value, lane_silent[lane] == sample_count) for lane in (LiveLane.SYSTEM, LiveLane.MICROPHONE)),')])
edit('live_identity.py', [
 ('        base_snapshot: LiveIdentitySnapshot,\n    ) -> LiveIdentityPreparation:\n        expected_pcm_bytes', '        base_snapshot: LiveIdentitySnapshot,\n        allowed_speakers: tuple[str, ...] | None = None,\n    ) -> LiveIdentityPreparation:\n        expected_pcm_bytes'),
 ('self._assign(local_speakers, base_snapshot.canonical_speakers, evidence)', 'self._assign(local_speakers, base_snapshot.canonical_speakers if allowed_speakers is None else allowed_speakers, evidence)'),
])
# Independent albums and sweepers; encoder and numeric policy remain shared.
edit('live_provider_bundle.py', [
 ('    return BoundedCausalIdentityPreparer(\n        config=identity_config,', '    preparer = BoundedCausalIdentityPreparer(\n        config=identity_config,'),
 ('\n\ndef _identity_evidence_provider(', '\n    preparer.lane_factory = lambda: _identity_preparer(config, encoder=encoder)\n    return preparer\n\ndef _identity_evidence_provider('),
])
edit('live_coordinator.py', [
 ('    analysis_pcm: bytes | None = None\n','    analysis_pcm: bytes | None = None\n    lane_pcm: tuple[tuple[str, bytes], ...] = ()\n'),
 ('    decode_salvage: str | None = None\n\n\nclass LiveCoordinator:', '    decode_salvage: str | None = None\n    source_lanes: tuple[str, ...] = ()\n\n\nclass LiveCoordinator:'),
 ('        self._analysis_pcm = _PcmRetention()', '        self._analysis_pcm = _PcmRetention()\n        self._lane_pcm = {}\n        self.lane_tapes = {}\n        self._lane_preparers = {}\n        self._lane_speakers = {}\n        self._tape_capacity = tape_capacity_bytes'),
 ('        staged = self._staged_frame\n', '        for lane, pcm in frame.lane_pcm:\n            if dict(frame.lane_silent).get(lane, False):\n                pcm = bytes(len(pcm))\n            self._lane_pcm.setdefault(lane, _PcmRetention()).append(ack.start_sample, ack.end_sample, pcm)\n            if self._tape_capacity is not None:\n                self.lane_tapes.setdefault(lane, CompleteMixedTape(epoch=self.session.epoch, capacity_bytes=self._tape_capacity)).append(start_sample=ack.start_sample, pcm=pcm)\n        staged = self._staged_frame\n'),
 ('            analysis_pcm=self._analysis_pcm.extract(span.start_sample, span.end_sample),','            analysis_pcm=self._analysis_pcm.extract(span.start_sample, span.end_sample),\n            lane_pcm=tuple((lane, retained.extract(span.start_sample, span.end_sample)) for lane, retained in self._lane_pcm.items()),'),
 ('        span = work.span\n        pcm = work.pcm\n        try:', '        span = work.span\n        pcm = work.pcm\n        if work.lane_pcm:\n            from .wp1_lane import prepare_lanes\n            return prepare_lanes(self, work, on_decoded)\n        try:'),
 ('                local_speakers=self._local_speakers(span, work.transcript),','                local_speakers=self._local_speakers(span, work.transcript),\n                source_lanes=work.source_lanes,'),
 ('            self._analysis_pcm.prune_before(snapshot.committed_samples)','            self._analysis_pcm.prune_before(snapshot.committed_samples)\n            for retained in self._lane_pcm.values():\n                retained.prune_before(snapshot.committed_samples)'),
 ('        self.tape.release()','        self.tape.release()\n        for tape in self.lane_tapes.values():\n            tape.release()'),
 ('        if self.rolling_decoder is None:\n            raise LiveCoordinatorError', '        if self.lane_tapes:\n            from .wp1_lane import decode_refinement\n            return decode_refinement(self, request)\n        if self.rolling_decoder is None:\n            raise LiveCoordinatorError'),
 ('        proposal = converger.complete(decode.request.id, decode.outcome)','        proposal = converger.complete(decode.request.id, decode.outcome)\n        if proposal is not None and hasattr(decode, "lane_segments"):\n            proposal = replace(proposal, segments=decode.lane_segments)'),
])
edit('live_service_runtime.py', [
 ('            finalization = self._terminal_finalizer.finalize(', '            from .wp1_lane import finalize_lanes\n            finalizer = (lambda **kwargs: finalize_lanes(state.coordinator, self._terminal_finalizer, **kwargs)) if state.coordinator.lane_tapes else self._terminal_finalizer.finalize\n            finalization = finalizer('),
])
print('THROWAWAY overlay ready; production files unchanged')
p=OUT/'live_coordinator.py'
s=p.read_text().replace('        take = getattr(self.identity_preparer, "take_identity_revision", None)\n        revision = None if take is None else take()', '''        from .live_identity_sweep import SweepRevision
        preparers = tuple(self._lane_preparers.values()) or (self.identity_preparer,)
        revisions = [r for p in preparers if (r := p.take_identity_revision()) is not None]
        revision = SweepRevision(corrections=tuple(x for r in revisions for x in r.corrections), merges=tuple(x for r in revisions for x in r.merges))''')
s=s.replace('                finalize(base_snapshot=self.session.snapshot().identity_snapshot)', '''                for preparer in tuple(self._lane_preparers.values()) or (self.identity_preparer,):
                    preparer.finalize_identity(base_snapshot=self.session.snapshot().identity_snapshot)''')
p.write_text(s)

p=OUT/"live_session.py"
s=p.read_text().replace("if segment.canonical_speaker is not None\n", "if segment.canonical_speaker is not None or segment.source_lane is not None\n")
p.write_text(s)
