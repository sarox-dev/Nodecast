# Ask evaluation: saved-source scenarios

This checklist is based on the user's November 6 test saves and is intended for
manual end-to-end evaluation. Sources and reasons must be checked against the
active account, because the rest of the library can contain additional evidence.
Do not use this checklist to assert that the entire library lacks a fact.

| Question | Expected source or behavior |
| --- | --- |
| Which Python module creates and manages virtual environments? | Python tutorial: `venv`. |
| Kurš Python modulis izveido un pārvalda virtuālās vides? | Same Python tutorial; answer in Latvian. |
| How does Open WebUI distinguish Notes from Knowledge? | Open WebUI Knowledge documentation: full context versus retrieved passages. |
| Compare Open WebUI Focused Retrieval and Full Context in a table. | Open WebUI Knowledge documentation; show only supported differences. |
| Summarize the Markdown properties mentioned in the Joplin captures. | Joplin Markdown guide, import documentation and rich text editor documentation. |
| What happens to Docker volumes when a container is removed? | Docker volumes example; do not generalize one example to all volumes. |
| Why did I save the Ollama coding agent launch? | Ollama launch capture's confirmed user reason, if available to Ask. |
| Why did I save the Joplin underlying Markdown passage? | Joplin rich text capture's confirmed user reason, if available to Ask. |
| Which exact AMD GPU and driver version does Ollama support? | Saved excerpt mentions AMD/Intel Vulkan support but does not establish a particular GPU and driver combination. |
| What is the next Nodecast release date? | No release date appears in the selected test captures; check the broader library before asserting that it is absent. |
| Salīdzini Obsidian, Notion un Logseq. | Named rows should remain identifiable even when a property lacks supporting evidence. Do not infer unsupported properties. |

For each answer record: selected sources, relevant and irrelevant evidence,
whether the summary is supported, whether citations open the correct fragment,
the display format, and whether missing information is stated accurately.
Repeat with cache controlled (Generate again) when comparing changes.

## Local baseline, November 7

The account's database was copied with SQLite backup and searched locally in an
isolated temporary directory. Nine cases had one or more specifically expected
captures; all 12 expected capture matches across those cases appeared in the
selected evidence packets. This measures expected-source coverage only, not
precision, source completeness, AI answer quality, or citation correctness.
The Nodecast release-date query selected eight evidence items; their relevance
and whether the broader library contains an answer were not assessed.

Two test captures have confirmed reasons. Source enrichment and the current
AI synthesis packet do not include `save_reason`, so successful source retrieval
alone does not establish that Ask can answer those reason questions. AI
generation, provider expansion, browser rendering and the table fix still need
live evaluation. Some saved passages were captured more than once.
