---
type: decision
updated: 2026-11-17
status: current
---

# Design direction

Related: [[design-preview]], [[stack-decision]], [[project-choice]]

The user replaced root `DESIGN.md` and asked to remake the interface from it. The
museum-collection direction supersedes the earlier anthropic.com-inspired archive
with teal accents. The new specification is the source of truth.

Quotes are catalogue objects: Source Serif 4, exact text and complete provenance.
The interface uses Cooper Hewitt, labels use IBM Plex Mono, and numbers/activity
use SVG dot matrices. Archival paper, ink, square corners and hairline rules define
the layout. Yellow marks search matches; parties receive small normalized swatches
only after their official colours are verified. Until then all use neutral gray.

The existing Python/Jinja stack stays. React-specific examples in the new design
are behavior references, implemented in templates, plain CSS and small JavaScript
modules. This avoids changing the stack just to achieve the same design.

See DESIGN.md §17 for preview adaptations and [[design-preview]] for verification
and remaining production work.
