EXECUTABLE ACCEPTANCE SUITE — 14 October 2026

Run:
  python3 -B evaluator/acceptance.py --candidate /absolute/candidate/adapter.py --stage 0 --output /new/report.json
Use stages 0, 1 or 2. Existing output paths are refused. Exit 0 means every case passed; exit 1 means at least one failure. Candidate import failures are fatal before a report is emitted. Import adds only the explicitly supplied adapter's parent to Python's search path and disables bytecode writes. This is a procedural runner, not a security sandbox. Candidate code is trusted to obey isolation rules.

The callable evaluate(module, stage) returns a JSON-serializable dictionary with every case, expected decision, observed result/query outputs, and failure type/detail. Each introduced family retains its original snapshot in later stages. Counts are 40, 48 and 56, respectively: 18/22/26 families times two ambient scenarios, plus four independent conversion examples. These counts are repeated observations, not independent engineering tasks. Exact inventory is in case_inventory.json.

Expected physical quantities are read directly from fixtures/whole_cycle.json. Endpoint identity, ancestry and provenance are derived independently from the unmodified declared provider metadata and canonical mappings. Candidate outputs never form an oracle. The suite generates synthetic endpoint payloads using the frozen encoding equations. Every planned mutation is applied to fresh deep-independent data. Rejected inputs are never used to derive expected accepted outputs.

Every call checks caller-input immutability, including failures and NaN-bearing cases. Accepted records check all seven stream identities, physical values, composition species and fractions, both full endpoint descriptors, sorted unique ancestry lists, and quantity provenance. Q1 must be sorted; Q2 and Q3 compare complete records without imposing order. Q3 also checks VERSION_MISMATCH for inconsistent requests according to pre-implementation amendment 001. Ordinary extra descriptive metadata is allowed; composition species must match exactly. Rejections require the documented code, nonempty string detail, and no boundaries member. Extra descriptive metadata may accompany rejections. Scalar tolerance is rtol 1e-10 and atol 1e-6; composition uses atol 1e-8 and zero relative tolerance. Boolean and nonfinite numeric outputs fail.

The four conversion examples invoke normalize_quantity directly. The frozen plan has no separate invalid-normalize family; invalid integration inputs remain the specified negative families. No extra post hoc task families are silently added. Family-specific metadata errors assume validation precedence recorded in amendment 001.

Evaluator tests:
  python3 -B -m unittest discover -s evaluator -v
These test evaluator construction, comparison, mutation detection, report continuation and oracle query sets. They do not implement a comparison arm or provide evidence that an arm is correct. Host-designed sentinel evaluation is separately recorded. Public helper functions expected_result(version_integer, ambient_string) and case_inputs(case_id_or_case_dict, ambient_string) support independent host verification. Keep the evaluator and its oracle sources withheld from fresh arm implementer contexts until first scoring.
