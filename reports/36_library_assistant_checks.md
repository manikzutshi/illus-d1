# 36 — Library, AI Assistant, Checks and Inspector

## 1. Library (left panel)

Tabs: **Library** (parts), **Building blocks** (design patterns), **Examples**.

* **Search** over names, short names, aliases, tags, families, categories and descriptions; every
  token must match; results ranked name > alias/tag > description (`ui/library.ts::searchLibrary`).
* **Kind filter**: all / real parts / idealised primitives.
* **Categories** come from the registry and are shown as collapsible groups with counts, in a preferred
  order for known categories and alphabetically for any new ones (`groupLibrary`, `categoryLabel`).
  Nothing depends on today's 86 parts; the tests include an unknown future category. Searching expands
  the matching groups.
* **Part detail**: clicking a part expands a card with the registry summary (what it does), pins,
  family, package and mounting, breadboard fit, interfaces, headline electrical figures and curriculum
  concepts, with **Add to design**. Details are fetched once per part and cached.
* **Building blocks**: the 16 design patterns of the knowledge base with purpose, parts, ports and
  **Insert block**, which uses the existing `insert_pattern` engineering op (undoable).

## 2. AI Assistant (right panel)

* **Composer pinned at the bottom** (Ctrl+Enter), model choice, a clear message when no provider key
  is configured.
* **Roles stated up front**: "AI proposes" / "Deterministic checks decide".
* **The generation as a process**: a checklist of phases derived from the job's real events
  (`ui/jobPhases.ts`): understand the request, search the library, calculate values, draft, validate
  electrically and functionally, repair, generate and verify the schematic, build and verify the
  breadboard. Each phase is tagged **AI** or **engine**, shows counts (lookups, checks, rejections,
  repair rounds) and its state (active spinner, done, failed, skipped).
* **Verdicts come from the result, not the AI**: when the job finishes, the validate / schematic /
  physical phases and the result card take their status from the returned `StudioState`
  (electrical, functional, schematic LVS, physical verification). The result card links to the
  checks, the schematic and the 3D build.
* The raw event log is still available, folded.

## 3. Checks (right panel)

One hub for "is this design right?": three cards (**Electrical**, **Function**, **Physical build**)
with verdict, tone and detail (`ui/checks.ts::checkCards`), each opening its detail panel. The
existing Electrical and Function panels are reused unchanged; the physical section shows the
verification summary, findings and the checks run. **Assumptions and limits** lists the design's
assumptions and what could not be checked (functional NOT_CHECKABLE findings, pins without voltage
data). A reminder states that all three are deterministic checks on the engineering design.

## 4. Inspector

Part card (reference, category, name, id), **◎ Schematic / ◎ 3D** locate buttons, role and
rationale, actions, parameters, pins with nets, **Checks for this part** (everything the electrical,
functional and physical checks say about this instance, `issuesForPart`), the physical build section
(holes per pin, geometry source, move / rotate on the board), registry electrical data, design rules,
what it does and curriculum concepts. Nets show where they are on the breadboard (nodes, wires, rail).

## 5. Limitations

* No conversational refinement yet: a new request starts a new design.
* Library thumbnails are schematic symbols; there are no per-part 3D thumbnails.
* Building blocks insert with unbound ports; wiring them into the design is manual.
