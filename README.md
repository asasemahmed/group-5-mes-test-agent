# Autonomous LLM-Based Computer-Use Agent for MES Testing

<p align="center">
  <strong>End-to-End Autonomous Quality Assurance of Spare-Parts & Maintenance Workflows in Manufacturing Execution Systems</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/Playwright-Browser_Automation-green?style=for-the-badge&logo=playwright&logoColor=white" alt="Playwright" />
  <img src="https://img.shields.io/badge/Agentic_AI-Computer_Use-orange?style=for-the-badge&logo=openai&logoColor=white" alt="Agentic AI" />
  <img src="https://img.shields.io/badge/Target_SUT-OpenMES-purple?style=for-the-badge" alt="OpenMES" />
  <img src="https://img.shields.io/badge/Course-Case_Study:_Intelligent_Systems-red?style=for-the-badge" alt="Academic Project" />
  <img src="https://img.shields.io/badge/License-MIT-informational?style=for-the-badge" alt="License" />
</p>

---

## 📑 Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Industrial Problem & Motivation](#2-industrial-problem--motivation)
- [3. System Architecture](#3-system-architecture)
- [4. Agentic Computer-Use Workflow](#4-agentic-computer-use-workflow)
- [5. Core Experimental Scenarios](#5-core-experimental-scenarios)
- [6. Synthetic Industrial Dataset](#6-synthetic-industrial-dataset)
- [7. Independent Verification Oracle](#7-independent-verification-oracle)
- [8. Scientific Evaluation & Benchmarking](#8-scientific-evaluation--benchmarking)
- [9. Defect Reporting & Artifact Output](#9-defect-reporting--artifact-output)
- [10. Repository Structure](#10-repository-structure)
- [11. Quick Start Guide](#11-quick-start-guide)
- [12. Deliverables & Milestones](#12-deliverables--milestones)
- [13. Academic Context & References](#13-academic-context--references)

---

## 1. Executive Summary

Manufacturing companies rely heavily on **Manufacturing Execution Systems (MES)** and **Computerized Maintenance Management Systems (CMMS)** to orchestrate shop-floor operations, equipment maintenance, and spare-parts inventory. A software regression or logic defect—such as miscalculating stock balance, accepting an over-issue, or dropping a critical low-stock notification—can trigger sudden line halts, spare-parts starvation, and thousands of dollars per minute in unplanned downtime.

```
+-----------------------------------------------------------------------------------------+
|                                    PROJECT CORE GOAL                                    |
|                                                                                         |
|  Develop an autonomous, vision-enabled LLM Computer-Use Agent capable of testing MES   |
|  spare-parts and maintenance workflows directly through the Graphical User Interface   |
|  (GUI), validated against an independent database/API ground-truth oracle and benchmarked|
|  against conventional deterministic scripted browser tests.                            |
+-----------------------------------------------------------------------------------------+
```

### Key Highlights
* **Natural-Language-to-Execution**: Translates high-level industrial quality objectives into multimodal GUI actions (clicks, keyboard input, screen inspections).
* **Multi-Modal Vision & Planning**: Leverages LLM vision capabilities to perceive UI elements dynamically without brittle hardcoded XPath/CSS selectors.
* **Dual-Layer Independent Verification**: Decouples GUI interaction from verification; inspects underlying database/REST APIs to prevent confirmation bias and hallucinations.
* **Rigorous Empirical Comparison**: Directly benchmarks the agent against conventional deterministic Playwright test suites across precision, recall, execution cost, and flakiness.

---

## 2. Industrial Problem & Motivation

Modern assembly lines, CNC centers, packaging lines, and conveyor networks demand rapid maintenance repairs. When a machine breaks down, technicians requisition spare parts from the inventory module.

```
       [Machine Breakdown / Preventive Maintenance]
                           │
                           ▼
              [Technician Requests Part in MES]
                           │
         ┌─────────────────┴─────────────────┐
         ▼                                   ▼
[VALID TRANSACTION]                 [DEFECTIVE SYSTEM BEHAVIORS]
 • Stock deducted accurately        ❌ Allows issue exceeding stock (negative balance)
 • Low-stock reorder alert triggered ❌ Stock balance fails to update on screen
 • Work order logged with lot code   ❌ Reorder warning never fires
                                     ❌ Duplicate submission deducts stock twice
                                     ❌ Incorrect warehouse/bin movement
```

> [!WARNING]
> In an industrial plant, software defects in inventory management directly cause physical bottlenecks. If the MES states that 2 ball bearings are in stock when none exist, a critical maintenance repair stalls, prolonging **Mean Time to Repair (MTTR)**.

---

## 3. System Architecture

The project decouples **Action & Perception** (the agent executing tests via UI) from the **Evaluation & Ground-Truth Oracle** (verifying true database state).

```mermaid
flowchart TD
    subgraph Input_Layer["1. Specification & Data Layer"]
        NL["Natural Language Test Spec<br><i>(e.g., 'Attempt to issue 3 bearings...')</i>"]
        Data["Synthetic Spare-Parts Catalog<br><i>(BRG-6205, Stock: 2, Threshold: 5)</i>"]
        Rules["Expected Invariants & Rules<br><i>(Transaction rejected; balance >= 0)</i>"]
    end

    subgraph Agent_Core["2. Agentic Reasoning & Computer-Use Engine"]
        Planner["LLM Planner & Decomposer<br><i>(Sub-goal breakdown, Step sequencing)</i>"]
        Observer["Multimodal Screen Observer<br><i>(Screenshot capture, element bounding)</i>"]
        Actor["GUI Actuator<br><i>(Playwright CDP: Click, Type, Navigate)</i>"]
        Recovery["Self-Correction Loop<br><i>(Bounded retries, unexpected dialog handling)</i>"]
    end

    subgraph Target_SUT["3. System Under Test (SUT)"]
        MES_UI["MES Web Application GUI<br><i>(OpenMES / Demo MES)</i>"]
        MES_Backend["MES Server & REST API"]
        MES_DB[("PostgreSQL / SQLite<br>Inventory Tables")]
    end

    subgraph Verification_Layer["4. Independent Verification & Reporting"]
        Oracle["Verification Oracle<br><i>(Direct DB query & REST snapshot)</i>"]
        Comparator["Outcome Comparator<br><i>(Observed GUI vs Ground-Truth Invariant)</i>"]
        Reporter["Structured Test Reporter<br><i>(PASS / FAIL / AGENT ERROR, Evidence)</i>"]
    end

    Input_Layer --> Planner
    Planner --> Observer
    Observer --> Actor
    Actor --> MES_UI
    MES_UI --> MES_Backend --> MES_DB
    
    Actor -. Feedback .-> Recovery
    Recovery -. Re-plan .-> Planner

    MES_DB -. DB State Snapshot .-> Oracle
    MES_UI -. Visual Artifacts .-> Comparator
    Oracle --> Comparator
    Comparator --> Reporter
```

---

## 4. Agentic Computer-Use Workflow

The agent operates in a closed perception-action loop:

```mermaid
sequenceDiagram
    autonumber
    actor QA as QA Engineer / Harness
    participant P as LLM Planner
    participant Agent as Computer-Use Agent (Vision)
    participant UI as MES Application (GUI)
    participant DB as Backend Database
    participant Oracle as Independent Oracle

    QA->>P: Submit NL Instruction + Test Constraints
    P->>P: Generate Action Plan (Step 1..N)
    
    loop Perception-Action Cycle
        Agent->>UI: Capture Screen Snapshot
        Agent->>Agent: Locate Target Element (Button/Input/Table)
        Agent->>UI: Execute Action (Click, Type, Form Submit)
        UI-->>Agent: Rendered State Update / Dialog
    end

    Agent->>QA: Report Execution Finished (Observed UI Result)
    QA->>Oracle: Request Ground-Truth Verification
    Oracle->>DB: Query Actual Stock Balance & Transaction Log
    DB-->>Oracle: Database Records (Record Status, Balance)
    Oracle->>QA: Verify Invariant Satisfaction
    QA->>QA: Generate Evidence-Backed Defect Report
```

### The 5 Execution Steps:
1. **Test Request Ingestion**: The system consumes a structured test specification containing the natural-language goal, input preconditions, and test invariants.
2. **Action Planning**: The LLM parses the requirement and formulates an actionable plan (e.g., Navigate to Warehouse $\rightarrow$ Filter by Part ID $\rightarrow$ Open Material Issue $\rightarrow$ Enter Qty $\rightarrow$ Submit).
3. **Computer-Use Interaction**: Uses browser automation (via Playwright or OS-level computer-use APIs) guided by vision to click, type, and navigate.
4. **Independent Verification**: Instead of relying solely on the LLM's visual assertion, an automated oracle queries the database to confirm whether the record was written or rejected.
5. **Defect Artifact Generation**: Aggregates action history, time-stamped screenshots, console logs, and database diffs into a comprehensive report.

---

## 5. Core Experimental Scenarios

We establish three baseline scenarios targeting critical MES failure modes:

| Test ID | Scenario Name | Initial State | Agent Instruction | Expected Outcome | Target Defect Injected |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SP-01** | **Insufficient Stock Issue** | Part `BRG-6205` has **2 pcs** in stock | *"Attempt to issue 3 bearings to maintenance job #WO-402 and verify the resulting inventory balance."* | Transaction **rejected**; error modal shown; stock balance remains **2**. | Application permits issue; balance becomes `-1` or displays phantom stock. |
| **SP-02** | **Low-Stock Warning Trigger** | Part `SEN-015` stock = **3 pcs**, Reorder threshold = **4 pcs** | *"Navigate to the spare parts inventory, locate sensor SEN-015, and verify whether low-stock warning is visible."* | Warning badge/alert **visible**; replenishment flag set to `ACTIVE`. | Warning does not render; threshold condition ignored by UI/backend. |
| **SP-03** | **Accurate Stock Balance Update** | Part `BELT-010` has **10 pcs** in stock | *"Issue 2 conveyor belts to maintenance repair line #3 and verify the updated stock balance."* | Issue **accepted**; inventory balance updates to exactly **8 pcs**. | Quantity remains `10`, double-deducts to `6`, or fails to log warehouse transaction. |

---

## 6. Synthetic Industrial Dataset

The experiment runs against a synthetic catalog mirroring real industrial parts and specifications:

```
+----------+--------------------+---------------+---------------+--------+-----------+
| Part ID  | Spare Part Name    | Initial Stock | Reorder Level | Unit   | Bin Loc   |
+----------+--------------------+---------------+---------------+--------+-----------+
| BRG-6205 | Deep Groove Ball   | 2             | 5             | Pieces | WH-A-01-2 |
| MOT-001  | 3-Phase AC Motor   | 4             | 2             | Pieces | WH-B-04-1 |
| BELT-010 | Neoprene V-Belt    | 10            | 3             | Pieces | WH-A-02-5 |
| SEN-015  | PT100 Temp Sensor  | 3             | 4             | Pieces | WH-C-01-3 |
| FIL-020  | Hydraulic Filter   | 12            | 5             | Pieces | WH-B-02-2 |
+----------+--------------------+---------------+---------------+--------+-----------+
```

### Work Order & Maintenance Association
* **Work Order ID**: `WO-2026-0891` (Conveyor Drive Overhaul)
* **Equipment ID**: `CNC-MILL-04`, `CONV-LINE-B`
* **Technician ID**: `TECH-702`
* **Movement Types**: `ISSUE_MAINTENANCE`, `RETURN_SCRAP`, `RECEIPT_PO`, `TRANSFER_BIN`

---

## 7. Independent Verification Oracle

A known pitfall of testing with LLMs is **visual hallucination**—the LLM assuming an action succeeded because it clicked the button, or misunderstanding an ambiguous UI badge.

> [!IMPORTANT]
> **Separation of Concerns**: The Computer-Use Agent interacts strictly through the visual UI. The **Independent Oracle** inspects the underlying datastore or read-only REST API endpoint to determine Ground Truth.

```mermaid
graph LR
    subgraph UI_Observation["Visual UI Observation"]
        AgentScreen["Agent sees: 'Transaction Complete'"]
    end

    subgraph Truth_Oracle["Ground Truth Oracle (Database Query)"]
        Query["SELECT stock_qty FROM inventory WHERE part_id='BRG-6205'"]
        DBValue["Actual DB Balance: -1 (Defect!)"]
    end

    UI_Observation --> Comparator{"Discrepancy Detected?"}
    Truth_Oracle --> Comparator
    Comparator -->|"Mismatch Identified"| BugReport["Generate Defect: Invariant Violation"]
```

---

## 8. Scientific Evaluation & Benchmarking

We evaluate and compare three distinct testing paradigms across identical test cases and injected bugs:

```mermaid
graph TD
    A["Quality Assurance Test Benchmark"] --> B["Approach 1: Conventional Scripted Tests<br><i>(Playwright deterministic scripts)</i>"]
    A --> C["Approach 2: Pure LLM Computer-Use Agent<br><i>(Vision + Prompt, Zero-shot execution)</i>"]
    A --> D["Approach 3: Agent with Verification & Self-Correction<br><i>(Explicit invariants + Bounded recovery loops)</i>"]
```

### Quantitative Metrics Matrix

| Evaluation Metric | Mathematical Definition / Operational Meaning | Target Benchmark |
| :--- | :--- | :--- |
| **Test Completion Rate (TCR)** | $\frac{\text{Completed Tests}}{\text{Total Assigned Tests}} \times 100\%$ | $> 95\%$ |
| **Defect Detection Recall (DDR)** | $\frac{\text{Detected Injected Defects}}{\text{Total Injected Defects}} \times 100\%$ | $> 90\%$ |
| **Defect Report Precision (DRP)** | $\frac{\text{Confirmed True Defects}}{\text{Total Reported Defects}} \times 100\%$ | $> 95\%$ |
| **False Positive Rate (FPR)** | $\frac{\text{False Alarms}}{\text{Known Valid Behaviors}} \times 100\%$ | $< 5\%$ |
| **Execution Duration** | Wall-clock seconds per executed test scenario | Compare vs Scripted |
| **Token & Cost Efficiency** | Prompt + Completion token cost per test scenario ($ USD) | Tracked per model |
| **Human Intervention Rate** | Frequency of human interventions required to recover | $\to 0$ |

---

## 9. Defect Reporting & Artifact Output

When the agent detects a failure or an invariant violation, it produces a structured, actionable defect report.

<details>
<summary><strong>🔍 Click to view Sample Defect Report (Markdown / JSON)</strong></summary>

```markdown
# 🐞 AUTOMATED DEFECT REPORT

**Test Identifier:** `SP-01-INSUFFICIENT-STOCK`  
**Execution Timestamp:** `2026-10-23T15:32:00Z`  
**Target Module:** Material Release / Spare Parts Inventory  
**Status:** ❌ **DEFECT CONFIRMED (FAIL)**

---

### 1. Test Objective
Verify that the MES application rejects a material requisition when the requested quantity exceeds the warehouse on-hand stock.

### 2. Preconditions
* Part ID: `BRG-6205` (Deep Groove Ball Bearing)
* Initial On-Hand Stock: `2 Pieces`
* Requested Quantity: `3 Pieces`
* Target Work Order: `WO-2026-0891`

### 3. Expected Behavior (Invariant)
* The UI displays an error notification: `"Requested quantity exceeds available stock (2)."`
* The transaction is rejected.
* The stock quantity in table `inventory_stock` remains `2`.

### 4. Observed Behavior
* The UI posted a success notification: `"Material requisition posted successfully."`
* Database Inspection: Record inserted into `material_transactions` with `qty_issued = 3`.
* Ground-truth stock balance updated to `-1`.

### 5. Root Cause Classification
`[BUSINESS-LOGIC-ERROR]` Missing validation check in server-side controller `StockIssueService.handleIssue()` prior to executing balance update.

### 6. Evidence & Execution Trace
* **Screenshot at Submission:** `reports/SP-01/step_04_submit.png`
* **Screenshot of Result:** `reports/SP-01/step_05_result.png`
* **Agent Action Log:** `reports/SP-01/trace.jsonl`
* **Database State Diff:**
  ```diff
  - inventory_balance: 2
  + inventory_balance: -1
  ```
```

</details>

---

## 10. Repository Structure

```text
group-5-mes-test-agent/
│
├── .github/                      # CI/CD workflows and automated evaluation runs
│   └── workflows/
│       └── benchmark.yml
├── data/                         # Test fixtures & synthetic datasets
│   ├── spare_parts_catalog.csv   # Industrial parts, reorder thresholds, units
│   ├── work_orders.json          # Maintenance tickets and equipment assignments
│   └── injected_defects.yaml     # Catalog of seeded application defects
│
├── docs/                         # Technical documentation & case study reports
│   ├── architecture.md           # System design and prompt engineering specs
│   └── evaluation_protocol.md    # Experimental setup and metrics guide
│
├── src/                          # Primary source code
│   ├── agent/                    # Autonomous Agent implementation
│   │   ├── planner.py            # LLM decomposition & step planning
│   │   ├── observer.py           # Screen capture, DOM/vision parsing
│   │   ├── actuator.py           # Playwright/CDP browser actuation
│   │   └── self_correction.py    # Retry logic & recovery mechanisms
│   │
│   ├── oracle/                   # Independent Verification Engine
│   │   ├── db_inspector.py       # SQL database ground-truth reader
│   │   └── api_inspector.py      # REST API state verification
│   │
│   └── benchmark/                # Evaluation harness
│       ├── runner.py             # Benchmark executor across 3 paradigms
│       └── metrics_calculator.py # TCR, DDR, DRP calculation
│
├── tests/
│   ├── baseline_playwright/      # Conventional scripted Playwright test suite
│   │   ├── test_sp01_stock.py
│   │   ├── test_sp02_alert.py
│   │   └── test_sp03_update.py
│   └── agent_tests/              # Natural-language test definitions
│       └── test_scenarios.yaml
│
├── reports/                      # Generated test results, logs, and screenshots
│   └── sample_run/
│
├── .env.example                  # Environment variable configuration template
├── pyproject.toml                # Project metadata and dependencies
├── requirements.txt              # Python requirements
└── README.md                     # Project documentation (this file)
```

---

## 11. Quick Start Guide

### Prerequisites
* **Python 3.10+**
* **Node.js 18+** & **Playwright**
* Access to an LLM provider API key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY`)
* Docker (for hosting local OpenMES test instance)

### 1. Clone & Set Up Environment

```bash
# Clone the repository
git clone https://github.com/asasemahmed/group-5-mes-test-agent.git
cd group-5-mes-test-agent

# Create virtual environment
python -m venv venv
# Windows:
.\venv\Scripts\Activate.ps1
# Linux/macOS:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```ini
# LLM Configuration
LLM_PROVIDER=anthropic              # anthropic | openai | gemini
LLM_MODEL=claude-3-7-sonnet-latest
LLM_API_KEY=your_api_key_here

# SUT (System Under Test) Configuration
MES_BASE_URL=http://localhost:8080
MES_DB_CONNECTION=postgresql://mes_user:mes_pass@localhost:5432/mes_db

# Benchmark Parameters
MAX_AGENT_RETRIES=3
HEADLESS_MODE=false
```

### 3. Launch the Target SUT (OpenMES)

```bash
# Launch test MES instance via Docker Compose
docker compose -f docker-compose.mes.yml up -d
```

### 4. Run the Experiments

```bash
# 1. Run Conventional Playwright Baseline
pytest tests/baseline_playwright/

# 2. Run the Autonomous LLM Computer-Use Agent
python -m src.agent.runner --scenario SP-01

# 3. Run Complete Scientific Benchmark (All 3 Paradigms)
python -m src.benchmark.runner --output-dir reports/experiment_01/
```

---

## 12. Deliverables & Milestones

- [x] **Milestone 1**: Problem formulation, test scenario specification (SP-01, SP-02, SP-03), and synthetic dataset definition.
- [ ] **Milestone 2**: Deployment of controlled MES environment with seeded industrial defects.
- [ ] **Milestone 3**: Conventional Playwright benchmark test suite implementation.
- [ ] **Milestone 4**: Multimodal computer-use agent with planning, action, and recovery loops.
- [ ] **Milestone 5**: Independent verification oracle (DB/API inspector) and automated defect reporter.
- [ ] **Milestone 6**: Comparative benchmark execution, metrics compilation, and academic case-study presentation.

---

## 13. Academic Context & References

This project is developed as part of the **Case Study: Intelligent Systems** curriculum (Group 5).

### Key References & Software
* **OpenMES**: Open-source Manufacturing Execution System ([Repository](https://github.com/Mes-Open/OpenMes) | [Docs](https://getopenmes.com/documentation/))
* **Computer-Use Agents**: Vision-based GUI interaction frameworks and foundation models (Anthropic Computer Use, OpenAI Multimodal CUA).
* **Industrial Maintenance Metrics**: MTBF (Mean Time Between Failures), MTTR (Mean Time to Repair), and Spare-Parts Availability Invariants in Industry 4.0.

---

<p align="center">
  <sub>Developed by Group 5 · Case Study: Intelligent Systems · 2026</sub>
</p>
