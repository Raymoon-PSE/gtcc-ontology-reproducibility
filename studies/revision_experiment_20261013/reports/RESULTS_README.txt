ONTOLOGY COMPARISON — FINAL RESULTS
13 October 2026

DECISION
The experiment completed successfully, but it did not demonstrate an ontology-specific effectiveness advantage. RDF/RDFS and a competent centralized JSON implementation passed the same controlled integration tasks. JSON had lower parse/lookup time and Python allocation peaks in the measured metadata workload. These findings must be retained rather than presented as support for superiority.

This is a reproducible whole-process integration comparison. It is NOT a completed demonstration of reduced engineering effort, industrial productivity or operating-plant accuracy. It does not close the editor's central added-value objection. Do not resubmit an unchanged ontology-benefit claim with these results.

WHAT WAS DONE
An isolated source snapshot and experiment package were created. The working EKLM implementation was not edited. The source snapshot contains 547 hashed source/resource/test files, excludes secrets and runtime databases, and is byte-verified before and after execution. Physics runs use the existing linked GTCC solver and actual inputs to GT-to-HRSG, HP/hot-reheat/LP steam, ST exhaust, cold-reheat return and condensate return boundaries. Six existing mechanical models and existing rule/Bayesian diagnosis use the same numerical kernels in both arms. No external service or live plant connection was used.

The RDF arm uses RDF/RDFS engineering facts plus the existing RDF mechanical runtime. The conventional arm uses indexed JSON facts with the same inheritance traversal, unit converters, validators and lifecycle guarantees. Its mechanics use equivalent source configuration prepared in setup, then execute without graph operations. This intentionally avoids a weak conventional comparator.

FUNCTIONAL RESULTS
28 fixed cases across six task families, 56 arm runs.
56/56 expected outcomes passed.
28/28 paired outcomes matched.
10 accepted cases and 18 deliberate inconsistencies per arm. These are constructed cases, not estimates of real-world error rates.

S1: 4 paired cases, 1 accepted changes, 3 deliberate inconsistencies. Both arms matched expected outcomes.
S2: 2 paired cases, 1 accepted changes, 1 deliberate inconsistencies. Both arms matched expected outcomes.
S3: 6 paired cases, 3 accepted changes, 3 deliberate inconsistencies. Both arms matched expected outcomes.
S4: 7 paired cases, 3 accepted changes, 4 deliberate inconsistencies. Both arms matched expected outcomes.
S5: 4 paired cases, 1 accepted changes, 3 deliberate inconsistencies. Both arms matched expected outcomes.
S6: 5 paired cases, 1 accepted changes, 4 deliberate inconsistencies. Both arms matched expected outcomes.

S1: transitive GT-expander subtype compatibility and binding gates.
S2: actual HP-ST versioned execution adapter around an unchanged kernel, including a missing-output failure.
S3: GT-to-HRSG unit/schema migration at actual solver inputs, tested at 5, 15 and 25 C ambient.
S4: complete steam-water interface migration including both returns, also tested at three ambient conditions.
S5: actual full A-to-B recomputation, delayed A completion, mixed consumer revisions and a late failure. Delayed A is rejected while the already accepted B remains current. Other failed B cases leave no accepted current B and retain A only as history.
S6: exported superheater-output schema migration after diagnostics. Four declared compatibility gates are checked. This is not a full internal diagnostic-schema migration or four independent applications.

A separate six-outcome hierarchy control showed that both representations need ancestry traversal or pre-materialized type assertions to resolve a transitive subtype. This isolates hierarchy capability, not a unique benefit of RDF syntax.

NUMERICAL CHECKS
Unadapted physical runs at 5, 15 and 25 C were used as references and repeated exactly. Physical parity tolerances were frozen at rtol 1e-10 and atol 1e-6. Convergence and existing independent conservation checks were also required: external mass residual below 1e-6 kg/hr and external energy residual below 0.01 kW.
At 15 C the net power was 550668.890330 kW, with external mass residual 2.18279e-11 kg/hr and energy residual 4.67951e-06 kW. These are simulator outputs and numerical balance checks, not independent plant validation.

PERFORMANCE
Only the matched metadata workload supports the performance comparison. Full mechanical-runtime timing is excluded because JSON preparation and RDF publication paths differ. The test replicated the same 90-fact configuration at four sizes. Each workload checked transitive subtype resolution and boundary endpoint/version/unit declarations. Cold parsing used six balanced samples per arm/size; warm lookup used twenty. Timing samples are repeated measurements, not independent industrial tasks.

    90 facts | parse ms RDF 1.093, JSON 0.041 | lookup ms RDF 0.154, JSON 0.012 | peak Python MiB RDF 0.15, JSON 0.05
   900 facts | parse ms RDF 9.923, JSON 0.402 | lookup ms RDF 1.478, JSON 0.096 | peak Python MiB RDF 1.07, JSON 0.50
 9,000 facts | parse ms RDF 97.374, JSON 4.743 | lookup ms RDF 15.532, JSON 1.005 | peak Python MiB RDF 11.05, JSON 5.08
90,000 facts | parse ms RDF 1281.879, JSON 207.582 | lookup ms RDF 158.682, JSON 10.769 | peak Python MiB RDF 106.91, JSON 50.57

The indexed JSON implementation was faster and used fewer traced Python allocations at every tested size. These results describe this implementation and access pattern. They do not establish whole-plant scalability or that JSON is universally better than RDF. Memory is a tracemalloc peak during parsing, not total process RSS. Shared physical computation is excluded.

CHANGE COST
Native before/after TTL and JSON artifacts and machine-readable fact diffs are retained. Equivalent changes are generated from the same authored facts, so equal logical change counts are configuration parity by construction. They are not observed human maintenance effort, editing time or an error-rate advantage. We did not conduct a developer study. The broad proposed maintenance comparison is therefore only partially addressed.

INDEPENDENT REVIEW AND TESTS
Three actual roles executed: physical-harness implementation, matched-mechanics implementation, and independent fairness/mutation review. The host implemented stores, contracts, scenarios, runner and reporting and checked all final outputs.
32 harness tests passed, including 17 independently written negative controls.
17 selected existing physical regressions passed.
19 existing ontology/runtime regressions passed.
Total: 68 automated tests, separate from the 56 comparison arm runs and six semantic-control outcomes.
The reviewer caught and the host corrected incomplete consumer-manifest checks, normalized-value overflow, unused scenario configuration and timing contaminated by prior-object deallocation. A development recycle mutation correctly broke conservation; the independent test was corrected to expect that rejection. Development performance runs with known timing or concurrent-load limitations remain archived and are explicitly excluded. Final measurements ran after tests completed.

LIMITS THAT MUST STAY IN THE PAPER
- The physical calculation order remains Python-configured. This study does not establish ontology-driven physical scheduling or arbitrary flowsheet rewiring.
- The new shared boundary/revision adapters are experiment additions, not previously existing EKLM features.
- The conventional implementation shares engineering rules and numerical kernels. Functional parity is therefore not independent physical validation.
- S1 is an external subtype gate. S6 is an exported-result schema change.
- Revision stamps are checked assertions, not authenticated data lineage.
- The matched mechanics JSON configuration is prepared from current source configuration. It is not an independently engineered production product, and its setup cost is excluded from runtime claims.
- There is no operating-plant accuracy study, user study, measured maintenance labor or industrial error-frequency estimate.
- Related KCER acquisition/missing-input results were not reused as these revision results.

REVISION CONSEQUENCE
The defensible contribution is a transparent implementation and controlled evaluation of explicit integration contracts across a simulated combined-cycle workflow. The experiment shows that a centralized conventional implementation can supply the tested capabilities as well. Ontology can be described as the chosen knowledge representation, but cannot be credited with a demonstrated maintenance or accuracy advantage here.

Recommended next paper action: use the attached bounded Methods/Results/Discussion draft as revision material, remove unmeasured comparative benefits, and reconsider whether a descriptive engineering-architecture contribution is sufficient for the intended venue. A stronger superiority claim would require different evidence, such as a genuinely observed multi-consumer migration study with independent change requirements and recorded engineer actions. Repeating these tests or adding more equipment models is not a substitute. No submission-ready manuscript or guaranteed publishable novelty is claimed.

FILES TO OPEN
reports/RESULTS_README.txt — this report.
reports/MANUSCRIPT_REVISION_DRAFT.txt — factual insertion draft, not an edited or submission-ready manuscript.
reports/metadata_performance.pdf — standalone vector figure with caption in figure_caption.txt.
reports/independent_implementation_review.txt — independent review.
results/main/ — authoritative final case outcomes and raw evidence.
results/performance/ — authoritative final performance samples.
protocol/ — frozen fixtures, expected labels and explicit scope amendment.
README.txt — reproduction and isolation instructions.
