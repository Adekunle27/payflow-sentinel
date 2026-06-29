# 💸 PayFlow Sentinel

> **Agentic Procure-to-Pay Orchestration for African Enterprises**  
> UiPath AgentHack 2026 — Track 2: UiPath Maestro BPMN

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![UiPath](https://img.shields.io/badge/Platform-UiPath%20Automation%20Cloud-orange)](https://cloud.uipath.com)
[![Track](https://img.shields.io/badge/Track-Maestro%20BPMN-blue)](https://agenthack.devpost.com)
[![Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-purple)](https://claude.ai/code)

---

## 🤖 Agent Type Declaration

**PayFlow Sentinel utilizes BOTH Coded Agents and Low-Code Agents in a hybrid orchestration model:**

- **Low-Code Agent:** **`ReqParser`** is built natively within **UiPath Agent Builder**, leveraging declarative low-code flows combined with LangChain integrations.
- **Coded Agents:** **`VendorScout`** (CrewAI Python framework) and **`InvoiceGuard`** (built via Claude Code / UiPath for Coding Agents) are fully programmatically coded agents deployed as microservices and connected via UiPath API Workflows.

---

## 🎯 The Problem

African enterprises lose an estimated **₦2 trillion+** annually to procurement fraud, duplicate invoices, fake vendors, and manual approval bottlenecks. A typical mid-size Nigerian company processes 200–500 purchase requisitions monthly — each touching 6–9 people across departments, taking 3–14 days end-to-end, with zero real-time visibility.

PayFlow Sentinel eliminates this. It is a fully agentic Procure-to-Pay (P2P) automation that orchestrates AI agents, RPA bots, and human reviewers through a structured BPMN 2.0 process — from raw purchase requisition to confirmed payment — in hours, not weeks.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    UiPath Maestro BPMN                          │
│              (Primary Orchestration Layer)                      │
└───────────┬─────────────────────────────────────────────────────┘
            │
  ┌─────────▼──────────┐     ┌──────────────────────────────────┐
  │   Agent Builder    │     │     External Agent Frameworks    │
  │   (UiPath native)  │     │  LangChain · CrewAI · Claude API │
  └─────────┬──────────┘     └────────────────┬─────────────────┘
            │                                 │
            └──────────────┬──────────────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │           Three AI Agents           │
         │                                    │
         │  1. ReqParser  — LangChain+Claude  │
         │  2. VendorScout — CrewAI           │
         │  3. InvoiceGuard — Claude Code ★  │
         └─────────────────┬──────────────────┘
                           │
         ┌─────────────────▼──────────────────┐
         │         Mock ERP Backend           │
         │    FastAPI · SQLite · REST APIs    │
         └────────────────────────────────────┘
```

### Full BPMN Flow

```
[PR Submitted] → [ReqParser Agent] → {Budget Gateway}
      → [VendorScout Agent] → [Human: PO Approval]
      → [RPA: PO Creation] → [InvoiceGuard Agent]
      → {Match Gateway} → [Human: AP Exception Review]
      → [RPA: Payment Execution] → [END]
```

---

## 🤖 The Three Agents

### 1. ReqParser (LangChain + Claude Sonnet)

Built in **UiPath Agent Builder**. Ingests raw purchase requisition text (email, form, PDF) and outputs structured procurement JSON including line items, category classification, budget code extraction, and urgency scoring.

### 2. VendorScout (CrewAI Multi-Agent)

Two sub-agents working as a crew:

- **Researcher Agent**: Searches vendor registry, validates CAC registration numbers, detects duplicate/similar vendor names
- **Risk Scorer Agent**: Produces a 0–100 vendor trust score based on transaction history, blacklist hits, and name-similarity fraud patterns common in Nigerian procurement

### 3. InvoiceGuard (Claude Code ★ Bonus)

Built using **Claude Code** through UiPath for Coding Agents. Performs:

- **3-way match**: PO quantity/price vs. Goods Receipt Note vs. Invoice — flags any delta > 2%
- **Forex validation**: Live USD/NGN rate check for FX-denominated invoices
- **Fake invoice detection**: LLM-based anomaly scoring (duplicate invoice numbers, round-number fraud patterns, template inconsistency detection)
- Outputs a structured risk score (0–100) with full reasoning chain

---

## 🛠️ UiPath Components Used

| Component                    | Usage                                                          |
| ---------------------------- | -------------------------------------------------------------- |
| **UiPath Maestro BPMN**      | Primary orchestration — models full P2P flow as BPMN 2.0       |
| **UiPath Agent Builder**     | Hosts ReqParser agent (low-code + LangChain integration)       |
| **UiPath API Workflows**     | Connects agents to Mock ERP, ExchangeRate API, vendor registry |
| **UiPath Action Center**     | Human-in-the-loop tasks: PO approval + AP exception review     |
| **UiPath RPA (Studio Web)**  | PO creation automation + payment logging                       |
| **UiPath for Coding Agents** | Claude Code used to build InvoiceGuard logic end-to-end ★      |

> ★ **Bonus**: InvoiceGuard was built using Claude Code via UiPath for Coding Agents, qualifying for additional judging points under Platform Usage.

---

## 📁 Repository Structure

```
payflow-sentinel/
├── README.md
├── LICENSE
│
├── backend/                    # Mock ERP FastAPI server
│   ├── main.py                 # Entry point
│   ├── routes/
│   │   ├── vendors.py          # Vendor registry CRUD
│   │   ├── purchase_orders.py  # PO management
│   │   ├── invoices.py         # Invoice store
│   │   └── payments.py        # Payment execution log
│   ├── models/
│   │   └── schemas.py          # Pydantic models
│   └── data/
│       ├── vendors.json        # Seed vendor data (Nigerian context)
│       ├── blacklist.json      # Known fraudulent vendors
│       └── budget_codes.json   # Department budget codes
│
├── agents/
│   ├── req_parser/
│   │   ├── agent.py            # LangChain ReqParser agent
│   │   ├── prompts.py          # System + extraction prompts
│   │   └── requirements.txt
│   ├── vendor_scout/
│   │   ├── crew.py             # CrewAI crew definition
│   │   ├── agents.py           # Researcher + Risk Scorer agents
│   │   ├── tools.py            # Custom tools (registry search, CAC lookup)
│   │   └── requirements.txt
│   └── invoice_guard/
│       ├── guard.py            # Main InvoiceGuard logic (built w/ Claude Code)
│       ├── three_way_match.py  # PO/GRN/Invoice reconciliation
│       ├── forex_checker.py    # Live FX rate validation
│       ├── fake_detector.py    # LLM-based fraud scoring
│       └── requirements.txt
│
├── bpmn/
│   └── payflow_sentinel.bpmn   # BPMN 2.0 process definition (import to Maestro)
│
├── uipath-workflows/
│   ├── rpa_po_creator/         # UiPath Studio workflow: PO creation
│   └── rpa_payment_executor/   # UiPath Studio workflow: payment logging
│
├── demo-data/
│   ├── requisitions/           # Sample PRs (happy path + exceptions)
│   ├── invoices/               # Sample invoices (valid + fraudulent)
│   └── vendors/                # Vendor test cases
│
├── docs/
│   ├── architecture.md         # Detailed architecture doc
│   ├── setup-guide.md          # Step-by-step setup
│   └── demo-script.md          # Demo walkthrough guide
│
└── frontend/
    └── dashboard.html          # Live process monitor dashboard
```

---

## ⚡ Prerequisites

- Python 3.10+
- Node.js 18+ (for UiPath CLI)
- UiPath Automation Cloud account (UiPath Labs access)
- Anthropic API key (for Claude-powered agents)
- `ANTHROPIC_API_KEY` set in environment

---

## 🚀 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/Adekunle27/payflow-sentinel.git
cd payflow-sentinel
```

### 2. Start the Mock ERP Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# API docs available at http://localhost:8000/docs
```

### 3. Install Agent Dependencies

```bash
# ReqParser
cd agents/req_parser && pip install -r requirements.txt

# VendorScout
cd agents/vendor_scout && pip install -r requirements.txt

# InvoiceGuard
cd agents/invoice_guard && pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
# Fill in:
# ANTHROPIC_API_KEY=your_key_here
# UIPATH_CLOUD_URL=https://cloud.uipath.com
# EXCHANGE_RATE_API_KEY=your_key_here (free at exchangerate-api.com)
```

### 5. Install UiPath CLI + Configure Coding Agent

```bash
npm install -g @uipath/cli
uipath auth login
# Follow prompts to connect to your UiPath Automation Cloud
```

### 6. Import BPMN Process to Maestro

1. Log into UiPath Automation Cloud
2. Navigate to Maestro → Processes
3. Import `bpmn/payflow_sentinel.bpmn`
4. Configure agent endpoints in the process variables

### 7. Run a Test Case

```bash
cd demo-data
python run_demo.py --scenario happy_path
python run_demo.py --scenario fake_invoice      # Triggers InvoiceGuard
python run_demo.py --scenario blacklisted_vendor # Triggers VendorScout escalation
```

---

## 🎬 Demo Scenarios

| Scenario             | Description                      | Expected Outcome                           |
| -------------------- | -------------------------------- | ------------------------------------------ |
| `happy_path`         | Standard ₦2.4M office supply PR  | Fully automated, payment in ~2 min         |
| `budget_exceeded`    | ₦8.7M IT equipment PR            | Routes to CFO human approval               |
| `blacklisted_vendor` | PR with known fraudulent vendor  | VendorScout blocks, escalates              |
| `fake_invoice`       | Invoice with 23% price inflation | InvoiceGuard scores 87/100 risk, escalates |
| `forex_mismatch`     | USD invoice at wrong FX rate     | InvoiceGuard catches $0.18/₦ discrepancy   |

---

## 🏅 Judging Alignment

| Criterion               | How PayFlow Sentinel addresses it                                                                                               |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Business Impact**     | Quantifiable ROI: cuts P2P cycle from 14 days → 2 hours, blocks fraud at the gate                                               |
| **Platform Usage**      | Uses 6 UiPath components including Maestro BPMN, Agent Builder, Action Center, RPA, API Workflows, and UiPath for Coding Agents |
| **Technical Execution** | 3-way match, forex validation, LLM fraud scoring, exception paths, human escalation                                             |
| **Completeness**        | End-to-end working prototype, 5 demo scenarios, full docs                                                                       |
| **Creativity**          | African enterprise context, NGN/forex angle, fake-invoice LLM detection                                                         |
| **Presentation**        | BPMN diagram is self-documenting, live demo catches fraud in real time                                                          |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 👤 Author

**Abdulmalik Adekunle**  
Profile: https://github.com/Adekunle27

---

_Built for UiPath AgentHack 2026 — Track 2: UiPath Maestro BPMN_
