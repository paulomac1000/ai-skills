# AFDS document starter

Copy only the profile you need from `references/document-types.md`. This starter intentionally avoids a universal body template.

```yaml
---
description: <question this document answers>
doc_id: <type>.<stable-slug>
type: workflow | reference | system | guide | decision | contract
status: draft
rigor: informative | operational | normative
owners: [<team-or-role>]
schema_version: 3
aliases: []
entities: []
upstream: []
---

# <Subject>

## <Answer-first section from the selected profile>

<content backed by evidence>
```

After writing, run `docs_validate.py`. Add optional fields only when they improve retrieval, ownership, or verification.
