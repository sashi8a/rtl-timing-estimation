# Decision log

Record meaningful decisions as they are made. Unresolved choices are not commitments.

## 2026-09-24: Repository and experiment organization

**Decision:** Use a private assessment repository. Use notebooks for exploration and explanation, and Python modules/scripts for reusable, reproducible work.

**Reason:** Experiments must be understandable and repeatable without duplicating pipeline logic in notebooks.

**Alternative considered:** Notebook-only implementation, which makes shared logic and unattended reproduction harder to maintain.

**Verification:** Notebooks will run top-to-bottom and call the same implementation as scripts. Document verified commands with each implemented stage.

**Status:** Organization agreed; pipeline implementation pending.

## Template for future entries

- Date and decision
- Motivation and alternatives
- Expected consequence
- Verification method and evidence
- Status: proposed, accepted, or superseded
