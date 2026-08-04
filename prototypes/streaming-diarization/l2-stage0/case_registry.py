"""Frozen A1 case membership and split intent; hashes are generated from local truth."""

from __future__ import annotations


CASES = [
    # Existing short-corpus provenance; zero mechanical flags required by validation.
    dict(case_id="1m-acquired-jamie-dimon", rel="real/benchmark_diarization_1min/samples/acquired_jamie_dimon", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
    dict(case_id="1m-acquired-nfl", rel="real/benchmark_diarization_1min/samples/acquired_nfl", split="development", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="1m-acquired-rolex", rel="real/benchmark_diarization_1min/samples/acquired_rolex", split="validation", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="1m-lex-bill-ackman", rel="real/benchmark_diarization_1min/samples/lex_bill_ackman", split="validation", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="1m-lex-javier-milei", rel="real/benchmark_diarization_1min/samples/lex_javier_milei", split="blind_holdout", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="1m-lex-keyu-jin", rel="real/benchmark_diarization_1min/samples/lex_keyu_jin", split="blind_holdout", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="3m-acquired-jamie-dimon", rel="real/calibration_diarization_3min/samples/acquired_jamie_dimon_3min", split="development", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="3m-lex-adam-frank", rel="real/calibration_diarization_3min/samples/lex_adam_frank", split="validation", accepted=True, status="accepted_existing_provenance_zero_flags"),
    dict(case_id="3m-lex-shapiro-destiny", rel="real/calibration_diarization_3min/samples/lex_shapiro_destiny", split="blind_holdout", accepted=True, status="accepted_existing_provenance_zero_flags"),
    # Only long acceptance case: operator-audited, post-audit frozen v2 reference.
    dict(case_id="5m-acquired-alphabet", rel="real/benchmark_5m/acquired_alphabet", split="validation", accepted=True, status="post_audit_frozen"),
    # Long cases below remain exploratory. No reference edits are authorized in A1.
    dict(case_id="5m-acquired-coca-cola", rel="real/benchmark_5m/acquired_coca_cola", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
    dict(case_id="5m-acquired-jamie-dimon", rel="real/benchmark_5m/acquired_jamie_dimon", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
    dict(case_id="5m-acquired-nfl", rel="real/benchmark_5m/acquired_nfl", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
    dict(case_id="5m-acquired-rolex", rel="real/benchmark_5m/acquired_rolex", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
    dict(case_id="5m-lex-bill-ackman", rel="real/benchmark_5m/lex_bill_ackman", split="exploratory", accepted=False, status="exploratory_acoustic_audit_required"),
    dict(case_id="5m-lex-javier-milei", rel="real/benchmark_5m/lex_javier_milei", split="exploratory", accepted=False, status="exploratory_acoustic_audit_required"),
    dict(case_id="5m-lex-keyu-jin", rel="real/benchmark_5m/lex_keyu_jin", split="exploratory", accepted=False, status="exploratory_acoustic_audit_required"),
    dict(case_id="30m-acquired-jamie-dimon", rel="real/benchmark_30m/acquired_jamie_dimon", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
    dict(case_id="30m-lex-bill-ackman", rel="real/benchmark_30m/lex_bill_ackman", split="exploratory", accepted=False, status="exploratory_reference_audit_required"),
]
