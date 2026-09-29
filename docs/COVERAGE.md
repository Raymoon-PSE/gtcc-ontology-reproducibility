# Coverage and limitations

| Manuscript evidence | Included artifacts and reproduction status |
|---|---|
| NETL design-point comparison | Recomputed from archived kernels/inputs; GT/net power and HHV efficiency checked |
| Mechanical life and efficiency scenarios | Six scenarios, original device models and reference assumptions; outputs checked against archives |
| Diagnostic margin sensitivity | Archived prescribed margins plus eight fault posteriors for each scenario; numerical replay |
| DataStatus/runtime chain | Three governed runs; NONE disables compressor evidence; FULL rejects missing explicit parameters |
| 500 Monte Carlo attempts | All successful and failed inputs retained; 479/21 outcome reproduced; exact sampler source version unrecovered, replay uses archived inputs |
| H2/NH3 fuel grid | All 77 attempted inputs; 70/7 outcome reproduced |
| Engineering contract | Original 79-case construction and raw archived results; RDF and non-RDF cases regenerated |
| Initial 55-case matched comparison | **Original case-level implementation/results not recovered. Not independently reproducible from this release.** No replacement experiment is presented as the historical experiment |
| Physical field validation | Not claimed or supplied; this is a public reference/synthetic evaluation |
| Exact figure typography/layout | Not regenerated; underlying recorded values can be exported as CSV |
| All EKLM features and later upgrades | Out of scope |

This package should not be described as making every manuscript claim fully reproducible. Recover the initial 55-case artifacts or explicitly state their unavailability when finalizing the data availability statement. Publishing this repository does not by itself establish journal policy compliance or editorial acceptance.

The original engineering benchmark uses a shared validator and an RDF-to-records adapter. The resolved non-RDF control is strong and centralized. Identical decisions demonstrate policy equivalence/adapter fidelity, not superiority of the ontology representation.

Archived timings are retained as historical measurements; new timings are logged separately. Cross-version floating-point deviations are checked against a stated tolerance, not forced to match by altering saved results.
