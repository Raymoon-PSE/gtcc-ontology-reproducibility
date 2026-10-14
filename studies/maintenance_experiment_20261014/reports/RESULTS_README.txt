MAINTENANCE COMPARISON — COMPLETED PILOT
14 October 2026

FINDING
This pilot did not establish a maintenance advantage for ontology. Independently implemented RDF and JSON adapters both passed the original acceptance checks on their first attempts. The RDF implementation was shorter in this pair, but line counts cannot be interpreted as engineering effort or attributed causally to ontology. Post hoc code review found one RDF-only over-rejection defect, which was repaired. It is an implementation defect, not evidence that RDF is generally less reliable.

The previous experiment showed functional parity using shared validators. This pilot went further by assigning the changes to separate implementers, preserving before/after code and withholding acceptance code by instruction. It still provides a small agent-executed pilot, not a human developer study or a conclusive superiority comparison.

DESIGN AND ACTUAL ROLES
Two fresh implementer contexts received the same change requirements and equivalent frozen RDF/JSON stores. They were instructed to read only their assigned arm and released requirement files. One implemented RDF and one JSON. They did not receive the acceptance code, other arm or previous experimental outputs. Their work logs record compliance. This restriction was procedural, not enforced by filesystem access control. No claim of secure blinding is made.

An independent evaluator authored the 14 publication checks without reading candidate code. The host authored the 29 adapter checks without inspecting candidates, generated fresh full-cycle fixtures, added three physical-data publication checks, froze candidate checkpoints and executed each arm in a separate interpreter. The evaluator and host inspected candidate code after initial acceptance.

CHANGE 1
Extend a trivial canonical pass-through adapter to accept a versioned external stream schema. Native configuration supplies arbitrary field aliases and dimensional units. Convert to canonical stream values and reject malformed schema, incompatible units, invalid physical values and composition. The frozen store implementation was not modified.

This first task is mostly an adapter implementation task, not maintenance of a mature application. Its original acceptance set contained 29 requirement-based checks.

CHANGE 2
Release a new request after CHANGE 1 was checkpointed and evaluated. Extend the existing adapter with atomic publication of all seven boundary streams to dashboard, report and diagnostics output views, each with independently configured units. Handle pending revisions, late obsolete results, retry after failure, historical snapshots and defensive copies. Retain CHANGE 1 behavior.

The original second-stage suite contained 46 checks per arm: the 29 adapter regressions, 14 independent publication checks and three checks using fresh complete-cycle simulation results at 5 and 25 C ambient. These views are new output adapters. They are not three separately maintained production applications or the existing Bayesian/mechanical diagnostic models.

RESULTS
                         RDF                  JSON
Change 1 first attempt   29/29 passed         29/29 passed
Change 2 first attempt   46/46 passed         46/46 passed
Original-suite repairs  0                    0
Post hoc empty-alias     Failed initially     Passed initially
Post hoc repair rounds   1                    0
Final regression suite   46/46 passed         46/46 passed
Final post hoc check     Passed               Passed
Final own unittest set   8 methods passed     9 methods passed

The 29 adapter checks repeat in the second stage. These counts must not be presented as independent engineering tasks, developers or industrial incidents. Self-test method counts differ in granularity and do not indicate better coverage or productivity.

POST HOC DEFECT, PRESERVED TRANSPARENTLY
The written specification permitted arbitrary unique string field aliases. RDF initially rejected an empty string alias, while JSON accepted it. Independent inspection identified the mismatch after original acceptance. A separately labeled native-fixture check reproduced the failure. The RDF implementer removed the extra nonempty restriction, added its own regression and passed the original 46 checks plus the new check. Original checkpoints and scores were retained. The post hoc case is not described as part of the initially withheld suite.

Repeated identical RDF triples collapse under graph set semantics. The original tests check conflicting declarations, not rejection of every textual repetition. JSON's raw duplicate-key/list checks and RDF graph deduplication are different. The broad wording about duplicate declarations therefore has a representation-dependent boundary that this pilot does not settle. No broader duplicate-detection superiority is claimed.

ACTUAL CODE CHANGES
Counts below come from immutable adapter.py diffs. They include comments and blank lines. Each request changed one implementation file per arm. Self-tests and work logs are separate artifacts.

                         Added/removed lines      Resulting source lines
RDF change 1             +89 / -2                  91
JSON change 1            +102 / -2                 104
RDF change 2             +79 / -1                  169
JSON change 2           +90 / -8                  186
RDF post hoc repair      one-line guard change     169

Both implementers reused their existing conversion and validation code and expanded the schema acceptance rules for the new consumer subjects. The difference in source size reflects these two implementations, including style and defensive parsing choices. It is not a measured reduction in maintenance effort. Agent elapsed time and self-test execution time are not used as human labor measures. No measured developer-hours or independent productivity effect is available.

WHOLE-PROCESS CONNECTION
The unchanged linked-cycle solver was executed at 5 and 25 C. The generated fixtures include GT exhaust, HP steam, hot reheat, LP steam, ST exhaust, cold reheat and condensate. Both runs met convergence and existing external mass/energy balance checks. Every solved boundary was supplied to each new output view, and A-to-B publication was checked against the correct physical scenario. These are simulated data, not plant measurements.

This pilot changes adapters around solved stream outputs. It does not modify physical solver scheduling or run the existing diagnosis kernels through the new publication views. The earlier experiment separately tested actual solver-input conversion hooks. The two scopes must remain distinct.

WHAT THE EVIDENCE SUPPORTS
- Both independently written adapters satisfy the declared requirements and final tested cases.
- Both adapt to a subsequent multi-consumer publication request without a change to their frozen store.
- Actual code changes, original acceptance results, the post hoc failure and its repair are reproducible.
- The numerical source remained unchanged.

WHAT IT DOES NOT SUPPORT
- Lower human engineering effort, faster onboarding or industrial maintenance savings.
- Ontology superiority, RDF necessity or a general reliability ranking.
- General RDFS/OWL reasoning benefits. No new inference or federated ontology task was requested in this pilot.
- Operating-plant validation or proof of scalability.
- A causal interpretation of code length or one agent's defect as a representation effect.

PAPER DECISION
The agreed stopping point has been reached: neither the initial shared-rule comparison nor this bounded independent-implementation pilot demonstrates ontology-specific added value. Do not keep adding equipment or similar adapter tests to try to obtain a favorable result.

The next paper work should reframe the contribution around the implemented engineering-contract architecture, reproducibility and explicitly measured tradeoffs. Ontology can remain the chosen representation, but claims of demonstrated comparative maintenance benefits should be removed. If such a benefit is essential to the intended contribution, submission should wait for genuinely different evidence such as observed engineer work on independently sourced integration changes. This pilot alone does not resolve CII's added-value objection or justify resubmission to the same journal.

No original manuscript or title was changed, and submission readiness is not claimed. The accompanying PAPER_REVISION_NOTE.txt gives bounded insertion text and a concrete claim-edit checklist.

READ NEXT
reports/final_independent_review.txt — independent evaluator's review and repair disposition.
reports/change_metrics.csv and *.diff — actual before/after changes.
results/change1_attempt1.json and change2_attempt1.json — immutable first-attempt results.
results/change2_attempt2.json — final original-suite regressions.
results/posthoc_before_repair.json and posthoc_after_repair.json — separate review discovery.
protocol/CHANGE_1.txt and CHANGE_2.txt — exact requirements.
checkpoints/ — original implementations and corrected delivery versions.
