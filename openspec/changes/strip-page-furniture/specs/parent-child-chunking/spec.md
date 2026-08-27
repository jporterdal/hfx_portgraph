## MODIFIED Requirements

### Requirement: Hierarchical parent chunks
The system SHALL create parent chunks corresponding to document sections (prefer H2/H3 or equivalent heading structure from parse output), each with a stable `chunk_id`, `report_id`, and provenance. Parent section boundaries SHALL NOT be determined by a section heading that is a **running header** — heading text whose fuzzy/normalized form has already appeared earlier in the same document as a heading. Running-header detection SHALL be scoped to heading-labeled items only (independent of the page-furniture signal in `document-parse`, which handles non-heading furniture upstream) and SHALL be based on a full-document pass identifying repeated heading-text families before chunk boundaries are decided, so that a family's first occurrence is correctly kept as a real boundary rather than needing retroactive correction. Every later occurrence of a registered running-header family SHALL be folded into the section it interrupts rather than starting a new parent.

#### Scenario: Section parents emitted
- **WHEN** a parsed document is chunked
- **THEN** parent records exist for major sections with identifiers usable as citation targets

#### Scenario: Multi-page section is not fragmented by a repeated running header
- **WHEN** a document section spans multiple pages and a heading's fuzzy-normalized text repeats verbatim as a heading between those pages
- **THEN** the resulting parent chunk SHALL contain the section's full content as one continuous parent, with only the first occurrence of the repeated heading treated as the section boundary, not split into separate parents at each repeated-heading occurrence

#### Scenario: Distinct headings for the same logical topic are not folded
- **WHEN** a multi-page note uses distinct (non-repeating) heading text across its pages, such as an initial heading and a "(CONTINUED)"-suffixed variant
- **THEN** each SHALL still be treated as its own section boundary — running-header folding SHALL NOT be applied based on topical similarity, only on fuzzy/normalized text repetition of the same heading family

### Requirement: Child passage chunks
The system SHALL create child chunks of approximately 300–800 tokens (or equivalent character budget if tokenizer unavailable) linked to a parent via `parent_id`, and SHALL store page range or section provenance on each child. Page-furniture artifacts (letterhead, mailing address, running header/footer text not itself a heading) are excluded upstream per `document-parse`'s "Strip page furniture" requirement and SHOULD NOT reappear in child chunk text. Separately, **running subtext** — a line immediately following a running-header occurrence whose fuzzy-normalized text itself independently repeats under other occurrences of the same running-header family — SHALL be included in the child chunk text only for the family's first occurrence; later occurrences of that subtext line SHALL be dropped along with the running header they follow.

#### Scenario: Children link to parents
- **WHEN** chunking completes for a report
- **THEN** every child record includes `parent_id` referencing an existing parent and includes provenance fields for citation

#### Scenario: Repeated furniture text does not dilute child chunk content
- **WHEN** a child chunk's source text includes a line that was classified as page furniture by `document-parse`'s furniture-detection signal
- **THEN** that line SHALL NOT be included in the child chunk's stored text (it was already excluded upstream)

#### Scenario: Running subtext is included once, not on every repeat
- **WHEN** a line directly follows a running-header occurrence, and that same line (fuzzy-matched) also appears directly following other occurrences of the same running-header family
- **THEN** that line SHALL be included in child chunk text only where it follows the family's first occurrence, and SHALL be dropped everywhere it follows a later, folded occurrence

#### Scenario: Content adjacent to a running header is preserved when it doesn't itself repeat
- **WHEN** a line directly follows a running-header occurrence but does not itself repeat under other occurrences of that family
- **THEN** that line SHALL be treated as ordinary section content and included in child chunk text, not dropped as running subtext
