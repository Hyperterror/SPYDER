# Synthetic Criminal Network Data Generator (SIH26189)

**AI-Powered Criminal Network Analysis System**
Focus Domain: Crimes against women, specifically organized human trafficking and exploitation networks (with extensible multi-crime architecture).

---

## 1. Architectural Overview: Ground Truth First

This system employs a strict **Ground Truth First** paradigm:
1. **Latent Ground-Truth Network**: A hidden, structured criminal network graph is generated first, defining global entities, true roles, syndicates, communication edges, financial channels, transit corridors, and true cross-case linkages.
2. **Fragmented Observational Evidence**: The 11 investigation evidence tables (`.csv`) are derived directly from this ground truth by introducing realistic real-world noise, alias variations, observational phone/device records, and case-scoped identifiers.
3. **Strict Latent/Observational Separation**: Evidence CSV files **never** expose global entity IDs (e.g., `GLOBAL_ENT_xxx`). Instead, records use case-scoped identifiers (e.g., `CASE_001_PER_01`, `CASE_007_PER_03`) or observable signals (phone numbers, IMEIs, bank accounts, vehicle license plates). The global mapping is stored exclusively in `output/ground_truth/` for post-hoc evaluation of entity resolution and graph algorithms.

---

## 2. Directory Structure

```
synthetic_data_generator/
│
├── config.py                     # Configuration (seed, target counts, cluster topology)
├── generate_dataset.py           # Master CLI generation script
├── requirements.txt              # Dependencies (standard library core + pandas/pytest)
├── README.md                     # Documentation and usage guide
│
├── generators/
│   ├── __init__.py
│   ├── ground_truth_generator.py # Latent network, syndicates, hard negatives, and mappings
│   ├── case_generator.py         # cases.csv
│   ├── person_generator.py       # persons.csv & victims.csv
│   ├── communication_generator.py# cdr.csv & chat_logs.csv
│   ├── movement_generator.py     # travel_movements.csv
│   ├── vehicle_generator.py      # vehicle_records.csv
│   ├── device_generator.py       # device_logs.csv
│   ├── financial_generator.py    # financial_transactions.csv
│   ├── social_generator.py       # social_media.csv
│   └── evidence_generator.py     # evidence.csv
│
├── output/
│   ├── evidence_dataset/         # 11 Observational Evidence CSVs
│   │   ├── cases.csv
│   │   ├── persons.csv
│   │   ├── victims.csv
│   │   ├── cdr.csv
│   │   ├── chat_logs.csv
│   │   ├── travel_movements.csv
│   │   ├── vehicle_records.csv
│   │   ├── device_logs.csv
│   │   ├── financial_transactions.csv
│   │   ├── social_media.csv
│   │   └── evidence.csv
│   │
│   └── ground_truth/             # 5 Hidden Ground Truth JSONs (Strictly Isolated)
│       ├── ground_truth.json
│       ├── true_entities.json
│       ├── true_relationships.json
│       ├── true_case_links.json
│       └── true_roles.json
│
└── tests/
    └── test_dataset.py           # Automated 14-point validation suite (role leakage, overlap, isolation, schema, reproducibility)
```

---

## 3. Quickstart: Commands to Run and Validate

### Step 1: Generate the Prototype Dataset
Run the generator using Python (runs with standard library):
```bash
python synthetic_data_generator/generate_dataset.py --seed 42
```

### Step 2: Run Automated Validation Tests
Run the comprehensive test suite verifying schemas, counts, referential integrity, isolation, role leakage prevention, identifier overlap distributions, and reproducibility:
```bash
python -m unittest synthetic_data_generator/tests/test_dataset.py -v
```

### Step 3: Run Data Quality Audit
Audit role leakage, device logs, and cross-case identifier overlap distributions:
```bash
python synthetic_data_generator/audit_data_quality.py
```

---

## 4. Evidence Dataset Schemas (11 CSVs)

| Table | Primary Key | Key Columns |
| :--- | :--- | :--- |
| `cases.csv` | `case_id` | `case_type, reported_date, incident_date, origin_location, destination_location, status, agency, priority` |
| `persons.csv` | `person_id` | `name, alias, age_group, role, phone_id, device_id, address, occupation, case_id` *(case-scoped person_id)* |
| `victims.csv` | `victim_id` | `case_id, age_group, reported_location, last_known_location, recruitment_channel, status, sensitive_flag` |
| `cdr.csv` | `cdr_id` | `timestamp, caller, receiver, duration_sec, call_type, cell_tower, case_id` |
| `chat_logs.csv` | `message_id` | `timestamp, sender, receiver, message_text, platform, language, case_id` |
| `travel_movements.csv` | `movement_id` | `person_id, vehicle_id, timestamp, source, destination, transport_mode, evidence_source, case_id` |
| `vehicle_records.csv` | `vehicle_id` | `registration_no, vehicle_type, owner_id, driver_id, timestamp, location, case_id` |
| `device_logs.csv` | `device_id` | `imei, phone_id, ip_address, timestamp, location, case_id` |
| `financial_transactions.csv` | `transaction_id` | `timestamp, sender_account, receiver_account, amount, transaction_type, reference, case_id` |
| `social_media.csv` | `account_id` | `username, platform, linked_phone, linked_email, created_date, location, case_id` |
| `evidence.csv` | `evidence_id` | `case_id, evidence_type, source_file, timestamp, sha256_hash, extraction_method, reliability, chain_of_custody` |

---

## 5. Hidden Ground Truth Schemas (5 JSONs)

Stored strictly in `output/ground_truth/`:
- `ground_truth.json`: Master aggregate containing all latent entities, network clusters, relationship graph, observational mapping, and hard negatives registry.
- `true_entities.json`: Array of latent global entities (`GLOBAL_ENT_xxx`) with true names, canonical roles, base locations, and case memberships.
- `true_relationships.json`: Typed graph edges (`COORDINATES_WITH`, `DIRECTS_TRANSPORT`, `AUTHORIZES_FUNDS`, `HANDS_OVER_TRANSIT`, `DISBURSES_PAYMENT`, `RECRUITS_OR_LURES`).
- `true_case_links.json`: Ground truth link matrix between case pairs (genuine syndicate connections vs. unrelated independent pairs).
- `true_roles.json`: Canonical role classification dictionary.

---

## 6. Case Structure & Syndicates

- **Network Alpha (Interstate Trafficking Syndicate - 4 Cases):**
  - `CASE_001`, `CASE_003`, `CASE_007`, `CASE_009`
  - Focused on cross-border / interstate procurement (Murshidabad, Siliguri, Kolkata to Delhi NCR, Jaipur).
- **Network Beta (Placement Agency Exploitation Ring - 3 Cases):**
  - `CASE_002`, `CASE_005`, `CASE_008`
  - Focused on sham domestic labor contracts (Ranchi, Patna to Gurugram, Panipat, Chandigarh).
- **Independent Unrelated Cases (3 Cases):**
  - `CASE_004`, `CASE_006`, `CASE_010`
  - Localized independent crimes sharing 0 syndicate links.
