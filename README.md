# GTCC ontology-driven digital twin: supporting computational artifacts

Standalone computational artifacts associated with **From Conceptual Model to Runtime Governance: An Ontology-Driven Multi-Domain Digital Twin for Combined Cycle Power Plants**. This is a research reproduction subset of EKLM, not the complete application or an operational plant controller.

**Coverage limitation:** the original individual records for the manuscript's initial 55-case RDF/non-RDF comparison have not been recovered and are not included. This release does not reproduce that historical experiment. The separate 79-case engineering-contract evaluation is included. See [coverage](docs/COVERAGE.md) before interpreting this package as supporting any particular claim.

## Run

Use Python **3.12**. From a fresh checkout:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/reproduce_numerical.py --quick
python scripts/reproduce_runtime.py
python scripts/reproduce_integrity.py
python scripts/reproduce_numerical.py
python scripts/export_tables.py
```

On Windows activate with `.venv\Scripts\activate`. Run from the repository root. No EKLM installation, web server, database, API key or network service is required after dependency installation. This reproduces the archived paper configuration, including its prescribed steam-turbine output and auxiliary-load boundary; it is not a validation of subsequently upgraded EKLM physics.

Expected full numerical outcome: 6 efficiency scenarios; 77 fuel blends with **70 successful and 7 failed** calculations; 500 Monte Carlo inputs with **479 successful and 21 failed** calculations. Failures are retained rather than discarded. The Monte Carlo replay uses archived inputs originally associated with seed 42; it does not claim a recovered version of the original random sampler.

Expected engineering-contract outcome: **54 invalid rejected, 25 valid accepted**, identical RDF and resolved non-RDF decisions. Both use the same contract and validation engine. Timings are machine-dependent; non-RDF timing starts from already-resolved records, whereas RDF includes graph projection. This is not an independent algorithm comparison or evidence of RDF speed/accuracy superiority.

Outputs are written to `outputs/` (ignored by git). `validation/` contains the tested release's summaries. Differences are checked with relative tolerance 1e-6 and absolute tolerance 1e-5; expected missing outputs cause failure.

## Contents

| Path | Contents |
|---|---|
| `eklm/vdt/` | Extracted process/mechanical numerical modules |
| `eklm/kas/legacy_bridge/` | Graph loading, runtime, diagnostic and engineering-contract logic |
| `eklm/kdl/schema/catalog/` | Five ontology Turtle files used by this package |
| `data/reference/` | Generic mechanical input assumptions; not measured plant data |
| `data/archived/` | Original archived numerical results and engineering-contract records |
| `scripts/` | Portable replay, runtime checks, benchmark and CSV export |
| `docs/COVERAGE.md` | Relationship to manuscript claims and explicit gaps |
| `docs/source_provenance.json` | Source hashes and packaging changes |
| `validation/` | Release validation summaries |

The 79-case script writes each graph, equivalent resolved non-RDF records and authoritative contract under `outputs/integrity/cases/`. CSV exports provide values for figures/tables; the package does not reproduce the paper's exact artwork layout. Thermal solver warnings and failed archived inputs are part of the declared model behavior.

## Provenance and interpretation

Numerical kernels were selected by matching the hashes stored with the archived paper run. The final engineering guard was taken from its dated source snapshot. Minimal package initializers replace application bootstrap. Compatible runtime support modules and packaging adaptations are itemized in the provenance file; this is a reconstructed executable subset, not a byte-identical archived full EKLM installation.

The public benchmark is NETL, *Cost and Performance Baseline for Fossil Energy Plants, Volume 1*, Revision 2a, DOE/NETL-2010/1397 (2013), Case 13. Mechanical coefficients are author-selected generic/reference assumptions, as qualified in the manuscript. No confidential commercial calibration records, credentials, manuscript files or application history are included.

## Citation and reuse

Use `CITATION.cff` and identify release `v0.1.0`. A Zenodo DOI has **not yet been issued**; do not substitute an invented DOI. Until archival publication, cite the versioned GitHub release. Code: [MIT](LICENSE). Author-created data, ontology/configuration descriptions and prose: [CC BY 4.0](LICENSE-DATA.md). Third-party dependencies retain their licenses.
