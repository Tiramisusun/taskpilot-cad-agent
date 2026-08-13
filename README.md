# TaskPilot CAD Agent Runtime

TaskPilot is a lightweight Agent workflow system for architectural CAD review. It implements an end-to-end Agent Runtime for complex task execution, including task scheduling, tool calling, state management, standards retrieval, review execution, automatic repair, real-time streaming, event logging, replay, and Agent Evaluation.

The current product scenario is a CAD review assistant: users upload a DXF drawing and a standards document, then the system parses CAD entities, retrieves relevant clauses, runs review rules, generates an issue report, and outputs a repaired DXF for low-risk fixes.

## Core Capabilities

- Agent task lifecycle management: created, running, succeeded, failed, and state tracking
- Plan-Execute loop: task decomposition, step execution, observation, and state updates
- Tool Calling framework: tool registration, argument validation, routing, result return, and fallback handling
- Middleware Agent architecture: context injection, token estimation, tool auditing, and memory writes
- Memory management: structured storage and dynamic injection of preferences, task facts, and historical results
- Observability: event logs, tool call records, exception traces, and task replay
- Evaluation: run scoring, issue counts, auto-fix counts, and high-risk issue statistics
- SSE streaming: real-time Agent execution events in the frontend
- CAD review and repair: DXF parsing, standards lookup, rule checks, and low-risk automatic fixes

## Tech Stack

Current MVP:

| Layer | Technology | Purpose |
| --- | --- | --- |
| Backend | Python + FastAPI | API service, task creation, file upload, report download |
| Web Server | Uvicorn | Local development server |
| Agent Runtime | TaskPilot Runtime | Task lifecycle, plan execution, tool calling, middleware, memory, evaluation |
| Streaming | Server-Sent Events | Agent event stream and task status updates |
| Frontend | HTML + CSS + JavaScript | Uploads, review focus input, results, and runtime event display |
| CAD Parsing | Lightweight DXF Parser | Parses layers, text, lines, coordinates, and basic ASCII DXF entities |
| Review Rules | Python Rule Engine | Layer, annotation, duplicate line, door width, egress, and fire marker checks |
| Standards Retrieval | Keyword Search | Matches relevant clauses from uploaded standards and review focus text |
| Auto Repair | Python DXF Text Rewriter | Layer renaming, duplicate line removal, and text height adjustment |
| Report Output | JSON + HTML | Machine-readable and human-readable review reports |

Recommended production stack:

| Capability | Recommended Technology | Notes |
| --- | --- | --- |
| Agent Workflow | LangGraph | State machine, checkpointing, human confirmation, interruptible execution |
| LLM Orchestration | LangChain | Model calls, tool wrappers, RAG, and prompt management |
| Precise DXF I/O | ezdxf | Reliable DXF entity, block, attribute, and dimension read/write |
| Geometry | Shapely | Room boundaries, door/window relations, distances, areas, and egress paths |
| PDF Standards Parsing | PyMuPDF / pdfplumber | Extract clauses, page numbers, and context from standards PDFs |
| Vector Retrieval | Chroma / pgvector | Standards RAG, project document search, and clause recall |
| Database | PostgreSQL / SQLite | Projects, drawings, standards, review records, and repair logs |
| Frontend Framework | React / Vue | Drawing preview, issue navigation, human confirmation, and review workspace |
| CAD Visualization | SVG / Canvas / WebGL | Highlight issue locations and before/after diffs in the browser |
| DWG Conversion | ODA File Converter / AutoCAD Batch | Convert DWG files to DXF before parsing |
| Sandbox Execution | Sandbox | Isolate high-risk tool calls and file modification operations |

## System Architecture

```text
Web UI
  -> FastAPI API Layer
  -> TaskPilot Agent Runtime
      -> Planner
      -> Middleware Stack
      -> Tool Registry
      -> Memory Store
      -> Event Log / Replay
      -> Evaluation
  -> CAD Engine
      -> DXF Parser
      -> Rule Reviewer
      -> Safe Repair Executor
      -> Report Generator
```

## Agent Execution Flow

```text
Frontend request
  -> Create AgentTask
  -> Inject Memory context
  -> Build execution plan
  -> Call cad.parse
  -> Call norm.search
  -> Call cad.review
  -> Call cad.repair
  -> Call report.generate
  -> Write Memory
  -> Generate Evaluation
  -> Return review results / reports / repaired DXF
```

Plan-Execute steps in the current runtime:

```text
step-1: Parse CAD drawing       -> cad.parse
step-2: Retrieve standards      -> norm.search
step-3: Run CAD review rules    -> cad.review
step-4: Generate repaired DXF   -> cad.repair
step-5: Generate review report  -> report.generate
```

## CAD Review Scope

Current checks:

- Layer naming format
- Objects placed on layer `0`
- Duplicate line entities
- Text height
- Room name and area annotation completeness
- Door clear width text
- Egress exit and stair markers
- Fire door and fire compartment markers
- Additional focused checks triggered by the uploaded standards and user query

Issue classification:

| Type | Handling | Example |
| --- | --- | --- |
| Confirmed issue | Programmatically detectable with evidence | Door width below threshold, duplicate line, invalid layer name |
| Potential risk | Rule-based warning that needs review | Missing exit marker, missing area annotation |
| Human review | Professional judgment required | Fire compartment strategy, egress path suitability for occupancy |

## Auto-Repair Policy

The system only applies low-risk, deterministic fixes:

- Normalize layer names
- Remove duplicate lines
- Adjust very small text height

High-risk design issues are not modified automatically. They are reported as recommendations requiring human review:

- Adding or deleting stairs
- Changing egress exit counts
- Adjusting fire compartments
- Modifying load-bearing elements
- Changing primary spatial layout

## Code Structure

```text
app/
  main.py        FastAPI entrypoint, upload APIs, task APIs, SSE, downloads
  cad_parser.py Lightweight DXF parser
  norms.py      Standards chunking, keyword retrieval, rule category inference
  reviewer.py   CAD review rules
  repair.py     Low-risk DXF repair executor
  report.py     JSON / HTML report generation
  models.py     CAD, standard, and issue data models

app/taskpilot/
  runtime.py       Agent Runtime, task scheduling, Plan-Execute loop
  planner.py       Task decomposition and plan generation
  tools.py         Tool Registry, argument validation, tool calling
  middleware.py    Context injection, fallback handling, token estimation, auditing
  memory.py        Structured long-term Memory
  observability.py Event logs, run records, task replay
  evaluation.py    Agent Evaluation metrics
  schemas.py       Task, Step, Event, and Status schemas

static/
  index.html    Frontend page
  styles.css    Frontend styles
  app.js        Uploads, Agent task creation, SSE event stream, result rendering

examples/
  sample_plan.dxf Sample drawing
  fire_norm.txt   Sample standard
```

## Quick Start

```bash
python3 -m uvicorn app.main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

If the port is already in use:

```bash
lsof -i :8000
kill <PID>
```

Or run on another port:

```bash
python3 -m uvicorn app.main:app --reload --port 8001
```

## Usage

1. Open the local web page.
2. Upload `examples/sample_plan.dxf` or your own DXF drawing.
3. Upload `examples/fire_norm.txt` or your own standards text.
4. Enter the review focus in the input box.
5. Click `Start Agent`.
6. Inspect the Agent Runtime plan, real-time events, and review results.
7. Download the HTML report, JSON report, or repaired DXF.

## API

Upload a drawing:

```bash
curl -X POST http://127.0.0.1:8000/api/drawings \
  -H "X-Filename: sample_plan.dxf" \
  --data-binary @examples/sample_plan.dxf
```

Upload a standards document:

```bash
curl -X POST http://127.0.0.1:8000/api/norms \
  -H "X-Filename: fire_norm.txt" \
  --data-binary @examples/fire_norm.txt
```

Run an Agent task synchronously:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_id": "<drawing_id>",
    "norm_query": "Check door clear width, egress exits, stairs, fire doors, room areas, and layer annotations.",
    "objective": "TaskPilot CAD deep-research review task"
  }'
```

Create an asynchronous task:

```bash
curl -X POST http://127.0.0.1:8000/api/tasks/async \
  -H "Content-Type: application/json" \
  -d '{
    "drawing_id": "<drawing_id>",
    "norm_query": "Check door width, egress, fire safety, and area annotations.",
    "objective": "Streaming CAD review task"
  }'
```

Runtime endpoints:

```text
GET /api/tasks
GET /api/tasks/{task_id}
GET /api/tasks/{task_id}/events
GET /api/tasks/{task_id}/replay
GET /api/tools
```

## Outputs

Each task can generate:

- Review issue list
- Referenced standards snippets
- Agent execution events
- Evaluation metrics
- HTML review report
- JSON structured report
- Repaired DXF

## Current Limitations

- The MVP prioritizes ASCII DXF.
- DWG files should be converted to DXF first.
- Standards retrieval currently uses keyword matching and can be upgraded to vector RAG.
- The lightweight CAD parser is suitable for MVP validation; production use should adopt `ezdxf`.
- Auto-repair is limited to low-risk items. High-risk design issues are reported for human review.

## Roadmap

- Integrate `LangGraph` for checkpointing, human confirmation, interruption, recovery, and durable execution.
- Integrate `LangChain` for model calls, prompts, tool wrappers, and RAG.
- Add `ezdxf` for more accurate DXF reading and writing.
- Add `shapely` for room boundaries, door/window relations, area, distance, and egress path calculations.
- Add Chroma or pgvector for a standards vector knowledge base.
- Add PyMuPDF or pdfplumber for standards PDF parsing.
- Add a human confirmation UI for medium-risk repairs.
- Support a DWG-to-DXF conversion pipeline.
- Add drawing visualization and issue location highlights in the frontend.
