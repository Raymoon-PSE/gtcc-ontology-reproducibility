# GitHub and Zenodo archival steps

1. Publish the reviewed repository and fixed `v0.1.0` release.
2. Sign into Zenodo with the intended author account and enable the GitHub repository in its GitHub integration.
3. If the release already exists before integration, archive its source ZIP manually or use Zenodo's import/archive controls; do not assume older releases are automatically imported.
4. Review the software title, creators, version, license and description. Note MIT code and CC BY 4.0 data/prose in the description.
5. Publish the archive and record its **version-specific DOI**. A draft/reserved identifier is not evidence that a public deposit exists.
6. Update the manuscript's Data Availability and reference list using the actual DOI and the declared coverage limitation. Update repository citation metadata in a subsequent documented commit.

Official guide: https://help.zenodo.org/docs/github/archive-software/github-upload/

CII uses double-anonymized review. The public repository identifies authors; supply it in accordance with the journal's review instructions. This package is not an anonymous review copy. Do not fabricate creator names or delete attribution from the public archival record to imply anonymity.

Suggested statement, only after publication and with actual identifiers:

> The simulation code, ontology models, archived inputs and results, and engineering-contract evaluation artifacts are available in [repository/release citation]. The available artifacts and reproduction coverage are described in the repository. The original case-level artifacts for the initial 55-case comparison are not included in this deposit.

The DOI and final manuscript statement remain pending until the archive is publicly available. No full-reproducibility claim is warranted while the identified artifact gap remains.
