"""Generate the Team 42 CareBridge breakout handout as a three-page PDF."""

from pathlib import Path

import pymupdf


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "Team_42_CareBridge_Breakout_Handout.pdf"

PURPLE = "#493f9f"
LAVENDER = "#f0eefb"
INK = "#202431"
MUTED = "#5c6475"

CSS = f"""
* {{ box-sizing: border-box; }}
body {{ font-family: Arial, Helvetica, sans-serif; color: {INK}; font-size: 9.2pt; line-height: 1.28; margin: 0; }}
h1 {{ color: {PURPLE}; font-size: 23pt; margin: 7px 0 2px; }}
h2 {{ font-size: 13.5pt; margin: 12px 0 4px; }}
h3 {{ color: {PURPLE}; font-size: 10.5pt; margin: 8px 0 3px; }}
p {{ margin: 3px 0 6px; }}
ul, ol {{ margin: 3px 0 7px 18px; padding: 0; }}
li {{ margin: 2px 0; }}
table {{ border-collapse: collapse; width: 100%; margin: 5px 0 7px; }}
th {{ background: {PURPLE}; color: white; text-align: left; padding: 5px; }}
td {{ border: 1px solid #ccd0e2; height: 24px; padding: 4px; }}
tr:nth-child(even) td {{ background: #f6f7fb; }}
.brand {{ color: {PURPLE}; font-weight: bold; font-size: 8.3pt; letter-spacing: .25px; }}
.rule {{ border-top: 3px solid #796be6; margin: 10px 0 8px; }}
.section-no {{ display: inline-block; color: white; background: {PURPLE}; padding: 1px 5px; margin-right: 6px; }}
.prompt {{ border-left: 4px solid #796be6; background: {LAVENDER}; padding: 7px 9px; margin: 5px 0 8px; }}
.answer {{ border: 1px solid #ccd0e2; padding: 7px 9px; margin: 4px 0 8px; }}
.callout {{ background: #fff7cc; border-left: 4px solid #e0b623; padding: 7px 9px; margin: 7px 0; }}
.small {{ color: {MUTED}; font-size: 8.2pt; }}
.tech {{ color: {PURPLE}; font-weight: bold; }}
.two-col {{ display: flex; gap: 10px; }}
.two-col > div {{ width: 50%; }}
.flow {{ background: #f6f7fb; border: 1px solid #d9dceb; padding: 7px; text-align: center; font-weight: bold; color: {PURPLE}; }}
"""


PAGES = [
    """
    <div class="brand">THE GEN ACADEMY &nbsp; | &nbsp; Mastering Agentic AI &nbsp; | &nbsp; Evals Week Breakout</div>
    <h1>Team 42 — Project Breakout Handout</h1>
    <p><b>Project:</b> CareBridge AI Care Companion</p>
    <div class="rule"></div>

    <h2><span class="section-no">1</span>Who is on this team</h2>
    <p class="small">Add each team member's full name and email.</p>
    <table>
      <tr><th style="width:7%">#</th><th style="width:43%">Full name</th><th>Email</th></tr>
      <tr><td>1</td><td></td><td></td></tr><tr><td>2</td><td></td><td></td></tr>
      <tr><td>3</td><td></td><td></td></tr><tr><td>4</td><td></td><td></td></tr>
      <tr><td>5</td><td></td><td></td></tr><tr><td>6</td><td></td><td></td></tr>
      <tr><td>7</td><td></td><td></td></tr>
    </table>
    <p><b>Point person:</b> __________________________________________________________</p>

    <h2><span class="section-no">2</span>Warm up: go around the room</h2>
    <div class="prompt"><b>Icebreaker.</b> Share your name, where you are joining from, and one repetitive task you would hand to an AI agent. Consider the work after a medical visit: reading notes, remembering instructions, coordinating appointments, and keeping family informed.</div>

    <h2><span class="section-no">3</span>Pick a topic and sketch the design</h2>
    <h3>Q1. Pick the use case</h3>
    <div class="answer"><b>CareBridge: an AI care companion for patients with glioblastoma and their authorized care partners.</b><br><br>
    After a visit, patients may receive a handwritten or scanned summary containing recommendations, tests, and follow-up details. CareBridge turns it into a clinician-approved digital record, answers patient questions from approved summaries, and creates an actionable preparation plan for the next visit.<br><br>
    <b>Roles:</b> Clinicians onboard patients and approve transcripts. Patients read summaries, ask questions, and approve plans. Authorized care partners assist within patient-granted permissions.</div>

    <h3>Q2. Knowledge and tools</h3>
    <div class="two-col">
      <div class="answer"><b>Knowledge and RAG</b><ul><li>Approved summary text and version history</li><li>Explicit recommendations, tests, and visit details</li><li>Pinecone semantic retrieval plus BM25 lexical ranking</li><li>Authorized sources and exact citations</li><li>SQLite for permissions, approvals, tasks, and state</li></ul></div>
      <div class="answer"><b>Tools and actions</b><ul><li>Camera/file upload and LlamaParse OCR</li><li>OpenAI generation and embeddings</li><li>Appointment, lab, imaging, and travel adapters</li><li>Reminders and ICS calendar export</li><li>LangSmith traces and RAGAS evaluation</li></ul></div>
    </div>
    """,
    """
    <div class="brand">TEAM 42 &nbsp; | &nbsp; CareBridge AI Care Companion</div>
    <h1>Autonomy and evaluation</h1>
    <div class="rule"></div>

    <h2><span class="section-no">3</span>Q3. Autonomy and evals</h2>
    <div class="prompt"><b>Design question.</b> What may the agent decide, which steps require a fixed workflow, and how will Team 42 detect good and bad outcomes?</div>

    <h3>Bounded autonomy</h3>
    <p>Agents may extract text, retrieve approved records, draft grounded answers, identify explicit preparation actions, and prepare scheduling options. Deterministic LangGraph routing invokes the matching specialist.</p>
    <div class="callout"><b>Human control:</b> Agents cannot diagnose, interpret scans, change treatment, create missing clinical orders, expose another patient's data, or confirm an external action without approval.</div>

    <h3>Control gates</h3>
    <ol>
      <li>A clinician reviews and approves the exact visit-summary version.</li>
      <li>The patient reviews and approves the generated preparation checklist.</li>
      <li>Missing dates, order references, pickup locations, or permissions block the affected action.</li>
      <li>The patient approves the exact appointment, lab, imaging, or travel proposal.</li>
      <li>Execution uses version checks and idempotency keys to prevent duplicates.</li>
    </ol>

    <h3>Agent and workflow map</h3>
    <div class="flow">Approved summary → Grounded Q&amp;A agent or Preparation planner → Independent verifier → Patient approval → Action orchestrator → Appointment / Laboratory / Imaging / Travel specialist → Exact proposal approval → Calendar</div>

    <h3>Evaluation strategy</h3>
    <table>
      <tr><th>Layer</th><th>What good looks like</th><th>How bad results are caught</th></tr>
      <tr><td>OCR</td><td>Original wording is preserved; corrections are versioned</td><td>Transcript comparison, critical-field review, image-based gold set</td></tr>
      <tr><td>Retrieval</td><td>Relevant approved passages rank highly</td><td>Recall@k, ranking metrics, tenant and authorization tests</td></tr>
      <tr><td>Answers</td><td>Claims are faithful and correctly cited</td><td>RAGAS, citation entailment, abstention and conflict cases</td></tr>
      <tr><td>Preparation</td><td>Every explicit action is captured without invention</td><td>Action precision/recall, prerequisite and ambiguity cases</td></tr>
      <tr><td>Routing</td><td>Correct specialist receives each approved task</td><td>Route coverage for clinic, lab, imaging, travel, and no-action</td></tr>
      <tr><td>Execution</td><td>One approved action produces one state transition</td><td>Approval, permissions, idempotency, retry, and cancellation tests</td></tr>
    </table>

    <h3>Release gates</h3>
    <ul>
      <li>Zero unauthorized record access or unapproved action execution.</li>
      <li>No unsupported clinical claims in reviewed critical cases.</li>
      <li>All documented appointments and ordered tests represented in the preparation plan.</li>
      <li>Ambiguous or missing prerequisites remain visibly blocked.</li>
    </ul>
    <p class="small">Versioned evaluation assets: grounded-answer dataset with optional RAGAS scoring; preparation/action dataset covering extraction, safety, prerequisites, routing, and travel-assistance behavior.</p>
    """,
    """
    <div class="brand">TEAM 42 &nbsp; | &nbsp; CareBridge AI Care Companion</div>
    <h1>Our project</h1>
    <div class="rule"></div>

    <h2><span class="section-no">4</span>CareBridge in one sentence</h2>
    <div class="callout"><b>CareBridge converts a clinician-reviewed visit document into a trusted patient record, grounded answers, and approved actions for the next visit.</b></div>

    <h3>End-to-end agentic workflow</h3>
    <ol>
      <li><b>Document intake:</b> the clinician uploads or photographs the visit summary.</li>
      <li><b>OCR and review:</b> LlamaParse extracts the complete transcript; the original and text appear side by side for correction and approval.</li>
      <li><b>Publication and indexing:</b> the approved version is persisted and indexed through a durable outbox.</li>
      <li><b>Grounded Q&amp;A:</b> hybrid retrieval finds authorized passages; the answering agent cites them or abstains.</li>
      <li><b>Preparation planning:</b> the planner prioritizes each explicit appointment, laboratory test, and imaging requirement.</li>
      <li><b>Patient approval:</b> no specialist workflow runs until the patient approves the checklist.</li>
      <li><b>Specialist coordination:</b> LangGraph routes actions to appointment, laboratory, imaging, and travel specialists.</li>
      <li><b>Resolve gaps:</b> missing orders and patient logistics remain visible as blocked items.</li>
      <li><b>Confirm and prepare:</b> the patient approves exact proposals and downloads a preparation calendar.</li>
    </ol>

    <h3>Technology</h3>
    <div class="answer tech">React + TypeScript &nbsp; · &nbsp; FastAPI + Python &nbsp; · &nbsp; LangGraph &nbsp; · &nbsp; OpenAI &nbsp; · &nbsp; LlamaParse/LlamaIndex &nbsp; · &nbsp; Pinecone &nbsp; · &nbsp; BM25 &nbsp; · &nbsp; SQLite &nbsp; · &nbsp; LangSmith &nbsp; · &nbsp; RAGAS</div>

    <h3>What makes it agentic</h3>
    <p>The system observes an approved record, reasons over explicit next steps, produces a source-linked plan, routes each action to a bounded specialist, pauses when prerequisites are missing, and resumes after human approval. It maintains state across the workflow instead of producing a one-time summary.</p>

    <h3>Success criteria</h3>
    <div class="two-col">
      <div><ul><li>Patients understand what was documented and can open every cited source.</li><li>Explicit appointments and tests are not omitted.</li><li>Unsupported clinical claims are never introduced.</li></ul></div>
      <div><ul><li>Patients control sharing, checklist approval, and arrangements.</li><li>Corrections and permission changes invalidate affected work.</li><li>Repeated requests never create duplicate confirmed actions.</li></ul></div>
    </div>

    <h3>Next step</h3>
    <div class="prompt">Complete the Team 42 roster, rehearse the sub-five-minute role-based demo, run the evaluation suites, capture representative LangSmith traces, and record remaining limitations before submission.</div>

    <p class="small"><b>Implementation status:</b> The repository contains the responsive role-based UI, FastAPI/SQLite workflow, OCR adapter, hybrid retrieval, grounded Q&amp;A, preparation and specialist graphs, arrangements, reminders, calendar export, activity history, and versioned evaluation datasets. External provider actions remain contained until a production integration is authorized.</p>
    """,
]


def add_footer(page: pymupdf.Page, page_number: int) -> None:
    footer = pymupdf.Rect(44, 757, 568, 778)
    page.draw_line((44, 754), (568, 754), color=(0.75, 0.75, 0.82), width=0.6)
    page.insert_textbox(
        footer,
        f"THE GEN ACADEMY  |  Team 42  |  CareBridge  |  Page {page_number} of 3",
        fontsize=7.2,
        color=(0.31, 0.32, 0.41),
        align=pymupdf.TEXT_ALIGN_CENTER,
    )


def build() -> None:
    document = pymupdf.open()
    for page_number, html in enumerate(PAGES, start=1):
        page = document.new_page(width=612, height=792)
        content = pymupdf.Rect(44, 38, 568, 747)
        spare_height, scale = page.insert_htmlbox(content, html, css=CSS, scale_low=0.72)
        if spare_height < 0:
            raise RuntimeError(f"Page {page_number} did not fit (scale={scale}).")
        add_footer(page, page_number)
    metadata = {
        "title": "Team 42 — CareBridge Project Breakout Handout",
        "author": "Team 42",
        "subject": "Mastering Agentic AI — Evals Week Breakout",
        "keywords": "CareBridge, agentic AI, RAG, evals, LangGraph",
    }
    document.set_metadata(metadata)
    document.save(OUTPUT, garbage=4, deflate=True)
    document.close()
    print(OUTPUT)


if __name__ == "__main__":
    build()
