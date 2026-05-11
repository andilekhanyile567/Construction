# MuhleOps – Construction Management System
**Group 29 – CTRL ALT ELITE | ADPA301**

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
python app.py

# 3. Open in browser
http://localhost:5000
```

## Demo Login Credentials

| Role | Email | Password |
|------|-------|----------|
| Client | client@muhle.co.za | client123 |
| Project Manager | pm@muhle.co.za | pm123 |
| Engineer | engineer@muhle.co.za | eng123 |
| Quantity Surveyor | qs@muhle.co.za | qs123 |
| Resource Manager | resource@muhle.co.za | res123 |
| Procurement Officer | procurement@muhle.co.za | proc123 |
| Logistics Coordinator | logistics@muhle.co.za | log123 |
| Site Manager | sitemanager@muhle.co.za | sm123 |
| Finance Officer | finance@muhle.co.za | fin123 |

## Implemented Use Cases

| UC | Name | Role |
|----|------|------|
| UC01 | Submit Project Inquiry | Client |
| UC02 | Conduct Site Survey | Engineer |
| UC03 | Generate Internal BOQ | Quantity Surveyor |
| UC04 | Match Internal Teams | Resource Manager |
| UC05 | Finalize Service Agreement | PM + Client (sign) |
| UC07 | Execute Purchase Orders | Procurement Officer |
| UC08 | Dispatch Equipment & Crew | Logistics Coordinator |
| UC09 | Update Site Progress | Site Manager |
| UC13 | Process Milestone Payment | Client / Finance |
| UC14 | Issue Completion Certificate | Project Manager |

## Project Structure

```
muhleops/
├── app.py              # Flask backend (all API routes)
├── requirements.txt    # Python dependencies
├── README.md
└── templates/
    └── index.html      # Single-page frontend (HTML/CSS/JS)
```
