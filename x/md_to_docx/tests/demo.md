# Purpose
Scope: This is what a purpose section looks like. The words before the colon
become an underlined lead-in title, and everything after them is ordinary body
text running on from it.

Authority: A section can hold as many of these as it needs. Each one is a
separate numbered paragraph, so they come out as a., b., c. underneath the
section number.

# SUMMARY OF CHANGES
This is what a paragraph with no lead-in title looks like. There is no colon
near the front, so the whole line is plain body text and nothing is
underlined.

# Scope and Applicability
Covered Organizations: This section heading was written as "Scope and
Applicability" rather than "Applicability", which is one of the accepted
alternate spellings. It still matched and still comes out as section 3.

## Exclusions
This is what a subsection heading looks like. It sits one level in, takes the
next letter in the sequence, and its own body text drops another level to (1),
(2) and so on.

# Definations
DLAI: Defense Logistics Agency Instruction. Definitions are the one section
that breaks the pattern. They sit flush left with no number at all, and only
the term before the colon is underlined.

TDR: Transportation Discrepancy Report. One paragraph per term, and the
section heading above was deliberately misspelled to show that the matcher
does not care.

SDR: Supply Discrepancy Report. Case, spacing and trailing punctuation are all
ignored when a heading is matched against the required list.

# POLICY
General: This is what a policy statement reads like. It is Agency policy that
the thing described in this issuance be done consistently and be auditable
afterwards.

Before anything is released the following must all be satisfied by the office
of responsibility: approval, verification and documentation. The colon here
sits too deep into the sentence to count as a lead-in title, so the line stays
plain. A shorter run-up such as "The requirements are as follows:" would be
underlined, because the rule only measures how far in the colon falls.

# Responsibilities
Director: This is what a responsibility reads like. One role per paragraph,
with the role name as the lead-in title.

Program Managers: Roles can be listed in any order. The numbering follows the
order they appear in, not the order anyone expects.

# Proceedures
Discovery: This is what a procedure step reads like, and this heading is
another deliberate misspelling that still matched.

# Releaseability
Cleared for public release. This issuance is available on the Agency issuances
website.

# References
This is what an enclosure looks like. Every top level heading below the
required sections becomes an enclosure, starts on its own page, and is titled
ENCLOSURE 1, ENCLOSURE 2 and so on in the order written here.

## Statutory and Regulatory
Title 49: This is what a reference entry reads like. The authority is the
lead-in title and the description follows it.

Title 40: Enclosure subheadings appear in the table of contents indented one
level under their enclosure.

## Agency Issuances
- This is what a bulleted list looks like.
- Each bullet becomes its own numbered paragraph, nested one level under the
  heading above it.

# Reporting Timelines
Ownership: This is what a second enclosure looks like. Numbering restarts at 1
inside every enclosure, so this paragraph is 1. again rather than continuing
from the enclosure before it.

## Initial Report
The steps below show what a numbered list looks like. The list marker written
in the markdown is ignored and replaced by the cascade.

1. This is the first step.
2. This is the second step, which nests one level under the heading.
3. This is the third step.

## Escalation
Threshold: This is what a table looks like. The header row is shaded and
repeats itself if the table runs across a page break.

| Value | Reviewer | Due |
|---|---|---|
| Under $2,500 | Local office | 10 days |
| $2,500 to $25,000 | Regional officer | 5 days |
| Over $25,000 | Headquarters | 2 days |

### Third Level
This is what a third level heading looks like. Three levels is as deep as the
table of contents goes; anything deeper still renders and still numbers, it
just does not get a row in the contents.

# Nesting Depth
The list below goes six levels deep to show the numbering cascade wrapping
around. A list sits one level below the line that introduces it, so this one
starts at a. rather than 1. Note that a line of ordinary prose must never begin
with something like "1." because markdown reads that as the start of a
numbered list.

- This first level comes out as a.
  - The second comes out as (1).
    - The third comes out as (a).
      - The fourth is where the cascade wraps back around to 1.
        - The fifth follows it to a.
          - The sixth comes out as (1) again.
- A second item here continues the outer sequence at b. rather than restarting.


# Closeout
Closure: This is what the last enclosure looks like. The Glossary, TABLES and
FIGURES pages are added automatically after it, so they are not written here.

## Records Retention
Case files are retained for six years following closure. This document is
missing INFORMATION REQUIREMENTS and INTERNAL CONTROLS on purpose, so the
build reports two findings and puts a placeholder under each.
