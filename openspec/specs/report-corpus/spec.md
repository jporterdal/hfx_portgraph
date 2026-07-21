## Purpose

Acquire, store, and inventory Port of Halifax public report PDFs with a durable, rebuildable local corpus for later RAG and agent phases.

## Requirements

### Requirement: Corpus stores Port of Halifax report PDFs locally
The system SHALL provide a local `corpus/raw/` directory for Port of Halifax public report PDF files acquired from Port Authority public reports (live site, Wayback Machine, or manual browser download).

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
The repository SHALL document how to (re)acquire corpus PDFs via a curated URL catalog and/or acquisition script and/or step-by-step manual browser instructions in `corpus/README.md`. Documented sources MUST include curated Port of Halifax PDF URLs and MAY include Internet Archive Wayback URLs. The live reports HTML page MUST NOT be the sole required acquisition path.

#### Scenario: Fresh machine can rebuild corpus
- **WHEN** a developer clones the repo without PDF binaries
- **THEN** they can follow committed instructions and/or run the acquisition script to populate `corpus/raw/` and refresh the manifest

#### Scenario: Automation blocked by Cloudflare
- **WHEN** automated fetch of live PDF URLs fails (for example Cloudflare challenge responses)
- **THEN** the documented rebuild path still succeeds by using Wayback URLs and/or manually placing correctly named PDFs into `corpus/raw/` and refreshing the manifest

### Requirement: Prefer annual and financials for v1 coverage
The Phase 0 inventory SHALL prioritize annual reports and consolidated financials across available years; other report types MAY be listed but MUST NOT block Phase 0 completion.

#### Scenario: Core types are present
- **WHEN** Phase 0 corpus work is marked complete
- **THEN** the manifest includes multiple years of `annual` and/or `financials` entries with `status: present`
