"""
Configuration and Parameters for Synthetic Criminal Network Data Generator (SIH26189).
Focused on Human Trafficking and Exploitation scenarios with extensible multi-crime ontology.
"""

from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
EVIDENCE_DIR = OUTPUT_DIR / "evidence_dataset"
GROUND_TRUTH_DIR = OUTPUT_DIR / "ground_truth"

# Random Seed for 100% Reproducibility
DEFAULT_SEED = 42

# Target Quantities (Approximate targets for small prototype dataset)
TARGET_CONFIG = {
    "num_cases": 10,
    "num_global_entities": 75,       # Latent unique persons/individuals
    "num_observational_persons": 105, # Visible person records across cases (yielding ~25-35% cross-case repeats)
    "num_victims": 25,
    "num_phones": 150,
    "num_devices": 85,
    "num_vehicles": 40,
    "num_bank_accounts": 120,
    "num_social_accounts": 100,
    "num_cdrs": 2000,
    "num_chats": 1000,
    "num_movements": 500,
    "num_vehicle_records": 200,
    "num_device_logs": 350,
    "num_financial_transactions": 1000,
    "num_evidence_records": 200,
}

# Network Topology Configuration
# Network Alpha: Eastern Corridor Interstate Trafficking Syndicate
# Network Beta: Metro Sham Employment Exploitation Ring
# Independent: Localized, uncoordinated crimes
NETWORK_CLUSTERS = {
    "NETWORK_ALPHA": {
        "name": "Eastern Corridor Interstate Trafficking Syndicate",
        "cases": ["CASE_001", "CASE_003", "CASE_007", "CASE_009"],
        "crime_type": "Human Trafficking (Interstate Labor/Commercial Sex Exploitation)",
        "focus_locations": ["Murshidabad", "Siliguri", "Kolkata", "Delhi NCR", "Jaipur"],
    },
    "NETWORK_BETA": {
        "name": "Northern Placement Agency Exploitation Ring",
        "cases": ["CASE_002", "CASE_005", "CASE_008"],
        "crime_type": "Human Trafficking (Sham Placement Agency & Domestic Involuntary Servitude)",
        "focus_locations": ["Ranchi", "Patna", "Gurugram", "Chandigarh", "Panipat"],
    },
    "INDEPENDENT": {
        "name": "Unconnected Isolated Cases",
        "cases": ["CASE_004", "CASE_006", "CASE_010"],
        "crime_type": "Isolated Abduction & Local Exploitation",
        "focus_locations": ["Agra", "Kanpur", "Gwalior", "Bhopal", "Nagpur"],
    }
}

# Canonical True Roles in Ground Truth
ROLES = [
    "coordinator",
    "recruiter",
    "transporter",
    "financier",
    "document_facilitator",
    "local_associate",
    "victim",
    "legitimate_contact",
]

# Case Priority and Agency Types
AGENCIES = [
    "Anti-Human Trafficking Unit (AHTU)",
    "State Crime Investigation Department (CID)",
    "Special Task Force (STF)",
    "Railway Protection Force (RPF) Crime Cell",
    "Metro Central Police Division",
]

PRIORITIES = ["High", "Urgent", "Critical", "Medium"]
STATUSES = ["Under Investigation", "Chargesheet Filed", "Pending Trial", "Reopened"]
