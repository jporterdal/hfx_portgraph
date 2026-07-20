## ADDED Requirements

### Requirement: Corpus stores Port of Halifax report PDFs locally
The system SHALL provide a local `corpus/raw/` directory for Port of Halifax public report PDF files acquired from the Port Authority reports page.

#### Scenario: Raw corpus directory exists
- **WHEN** Phase 0 corpus setup is complete
- **THEN** `corpus/raw/` exists and is designated as the location for original PDF binaries

### Requirement: Manifest inventories every acquired report
The system SHALL maintain `corpus/manifest.yaml` listing each report with at least: stable `id`, `year`, `report_type`, `language`, `source_url`, `filename` (relative to `corpus/raw/`), and `status` (`present` or `missing`).

#### Scenario: Present report is listed
- **WHEN** a PDF has been downloaded into `corpus/raw/`
- **THEN** the manifest contains an entry with `status: present` and a `filename` that resolves to that file

#### Scenario: Known gap is listed
- **WHEN** a desired year/type/language combination is known but the PDF is unavailable
- **THEN** the manifest MAY include an entry with `status: missing` and without a local file

### Requirement: Stable report filenames
Acquired PDFs SHALL use the filename pattern `{year}_{report_type}_{lang}.pdf` where `report_type` is `annual`, `financials`, or `other`, and `lang` is `en`, `fr`, or `unknown`.

#### Scenario: Annual English report naming
- **WHEN** the 2022 English annual report is stored
- **THEN** its filename is `2022_annual_en.pdf` (or equivalent year matching the document)

### Requirement: Corpus acquisition is reproducible
The repository SHALL document how to (re)download corpus PDFs, via a script under the repo and/or step-by-step instructions in `corpus/README.md`, using https://www.porthalifax.ca/about-us/port-authority/reports/ as the primary source.

#### Scenario: Fresh machine can rebuild corpus
- **WHEN** a developer clones the repo without PDF binaries
- **THEN** they can follow committed instructions or run the acquisition script to populate `corpus/raw/` and refresh the manifest

### Requirement: Prefer annual and financials for v1 coverage
The Phase 0 inventory SHALL prioritize annual reports and consolidated financials across available years; other report types on the source page MAY be listed but MUST NOT block Phase 0 completion.

#### Scenario: Core types are present
- **WHEN** Phase 0 corpus work is marked complete
- **THEN** the manifest includes multiple years of `annual` and/or `financials` entries with `status: present`
