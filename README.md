# GTCC engineering-contract research artifacts

Supporting artifacts for **From Conceptual Model to Runtime Governance: An Ontology-Driven Multi-Domain Digital Twin for Combined Cycle Power Plants**. Version 0.4.0, 14 October 2026.

## New comparative evidence

The `studies/` directory adds three completed simulation studies. Neither the comparison nor the maintenance studies establish ontology-specific superiority. Both representations retain shared engineering semantics. JSON has lower metadata overhead in the measured workload.

```sh
python -m pip install -r requirements_revision.txt
python scripts/verify_revision_evidence.py
```

Python 3.12 is the recorded environment. This command verifies derived-file hashes, checks the 28 paired whole-process records and timing medians, reruns every original provider-integration checkpoint, and reproduces the adapter pilot including its post hoc failure and repair. It uses stored solved fixtures. This acceptance command does not rerun physics or timing. Separate commands below support fresh physical fixtures and metadata timings. The complete application is deliberately excluded.

See [release scope](docs/RELEASE_0.4.0.txt) for reproduction limits and [derivation manifest](studies/PUBLIC_DERIVATION.json) for original/public hashes and path sanitization. The three new studies use a later linked-cycle configuration with nominal net power 550668.890330 kW. The archived v0.3.0 baseline below is a different configuration, 560604.080347 kW. The earlier release and its source files remain preserved.

Versioned artifact: https://github.com/Raymoon-PSE/gtcc-ontology-reproducibility/releases/tag/v0.4.0. No DOI is claimed.

### Optional fresh numerical and timing runs

```sh
python -m pip install -r studies/revision_experiment_20261013/requirements_physics.txt
python -B studies/revision_experiment_20261013/reproduce_physics.py
python -B studies/revision_experiment_20261013/run_performance.py --results /tmp/gtcc-new-metadata-results
```

Choose a new timing output directory for each run. Fresh timings depend on the machine and do not replace the paper’s archived samples. The numerical subset regenerates the 5/15/25°C physical baselines, with source hashes and two explicitly disclosed package-initializer stubs. It does not run the full mechanical/ontology environment or all 28 paired integration cases. Those paired outcomes remain auditable archived records. See [physical reproduction scope](studies/revision_experiment_20261013/PHYSICS_REPRODUCTION.txt).

---

## Archived v0.3.0 instructions

# EKLM computational supplement — corrected CII evaluation

Supporting artifacts for **From Conceptual Model to Runtime Governance: An Ontology-Driven Multi-Domain Digital Twin for Combined Cycle Power Plants**. Version 0.3.0, 2 October 2026. This is a simulation research subset, not a live plant controller.

## Reproduce

Use Python 3.12; install `requirements.txt`. No account, API key, plant data, or full EKLM installation is needed after dependency installation.

```sh
python -m pip install -r requirements.txt
python scripts/reproduce_numerical.py
python scripts/reproduce_integrity.py
python scripts/reproduce_runtime.py
python scripts/evaluate_revision.py
python scripts/evaluate_audit_fixes.py
python scripts/evaluate_transaction.py
python scripts/evaluate_extension.py
python scripts/export_tables.py
```

The audit-fix and table-export commands depend on the preceding evaluation outputs. Figure regeneration uses `requirements_figures.txt` and `python scripts/plot_revision.py`.

## Results and comparison boundaries

- Four operational execution invariants cover eligibility, explicit-input precedence/provenance, typed interfaces, and completed-run publication. They compose established techniques; they are not a claim that transactions or schema checks are novel.
- 17 failure-path cases leave no current evidence and preserve static stream/variable/KPI reference values. Governed execution stages writes and commits only a completed run; the graph has a run identifier and complete/failed status. Single-writer operation is assumed; no concurrency/crash-recovery guarantee is made.
- Four meaningful margin overrides (10%/20%, in each input map) preserve values and provenance. Unknown/duplicate fields, nonfinite numbers, invalid types and declared domain violations are rejected. Known unbounded/censored lifetime outputs are explicitly labelled instead of numeric infinities in the graph.
- Eight inspection-indicator extension cases: four valid, four rejected, with identical paired results. A shared plugin adds remaining_life_hr / inspection_window_hr. Ratios 2.5, 1.5 and 5.0 match expectations; inactive/rejected cases expose no indicator. Four arm-specific declarations change in each representation, plus common plugin/reference additions. This is not a maintenance validation or measured productivity advantage.

- 583 archived physical replay records: zero mismatches, including 479 successful/21 failed Monte Carlo attempts and 70 successful/seven failed fuel-grid attempts. The original Monte Carlo sampler version was not recovered; archived inputs are replayed.
- 72 RDF/JSON routing cases: 48 valid and 24 invalid; separate adapters, shared models and router. Valid mechanical outputs, provenance, scores, and net power agree.
- 104 engineering-contract cases: 79 invalid rejected, 25 valid accepted. A separately implemented conventional validator reproduces decisions and finding locations. All arms receive the same contract and resolved class membership. Twenty-five audit-driven regression cases extend the original 79 cases.
- 36 graph-reuse checks: 24 activation/binding checks plus 12 omitted-device/status checks; rejected configurations clear previous evidence.
- 95 diagnostic threshold checks. Strict exceedance uses an explicit non-match at equality, including absolute 1e-10 and relative 1e-12 roundoff tolerances. These are not measurement uncertainty bounds. Deliberate threshold discontinuities remain outside the tolerance band.
- Six SPARQL queries and independently coded JSON joins return identical complete bindings: 1, 6, 1, 12, 6, 22 rows. JSON receives the same graph-exported relation snapshot; export effort and human productivity are not measured.
- One defined stream replacement changes three configuration fields and three contract fields in both representations, with no executable source edits. No editing-time advantage is claimed.

The corrected diagnostic reference is one fixed nominal EKLM run, with net power 560604.0803469602 kW. The legacy API field `posterior` is an uncalibrated normalized hypothesis score. Physical model kernels remain byte-identical to the source subset; gui_adapter.py now adds the governed-execution wrapper. Correcting threshold equality changes 32 historical diagnostic score entries under the legacy reference; these differences are saved separately in `outputs/numerical/results.json`, not hidden as physical replay failures or forced to match old values.

## Evidence

- `outputs/revision/`: scenario inputs, paired outputs, scores, lifecycle checks, queries and snapshots. **query_graph.nt is the authoritative lossless snapshot**. The Turtle convenience copy uses compact numeric formatting. Query bindings are checked after N-Triples reload.
- `outputs/integrity/`: all configurations, resolved records, contracts, decisions, findings, and timing repetitions. Timings compare the RDF adapter and shared JSON validator only; the independently implemented validator is compared for correctness.
- `outputs/transaction/` and `outputs/extension/`: failure-path, non-default override, lifetime-sentinel, and indicator-addition protocols/results.
- `outputs/audit_fixes/`: threshold and omission regressions, conventional query input/results, and protocol.
- `outputs/numerical/`: physical replay and separately reported diagnostic changes.
- `validation/`: summaries of the corrected release.
- `docs/source_provenance.json` and `docs/revision_provenance.json`: source lineage and changes.

The downloadable full archive contains recorded outputs; a source checkout regenerates them. All tests are development/regression evaluations, not blinded holdout studies. They do not establish field accuracy, calibrated fault probabilities, or RDF-specific numerical/productivity superiority. Original historical 55-case records remain unavailable and are not used as evidence. Earlier release metadata under `docs/historical_release/` is historical, not the current protocol.

Code is MIT licensed; author-created data and documentation retain CC BY 4.0 terms. Cite the versioned release using CITATION.cff. No new DOI is asserted without verification.
