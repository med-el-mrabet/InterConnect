# 💾 Architecture Base de Données - DevMateriels

## Vue d'ensemble

```mermaid
flowchart LR
    subgraph PS["📅 Planning Service"]
        DB_PS[("db-planning<br/>:5432")]
    end

    subgraph DS["📄 Devis Service"]
        DB_DS[("db-devis<br/>:5433")]
    end

    subgraph NS["🔔 Notification Service"]
        DB_NS[("db-notification<br/>:5434")]
    end

    subgraph WL["🏢 ERP WagonLits"]
        DB_WL[("db-erp-wagonlits<br/>:5435")]
    end

    subgraph DM["🏭 ERP DevMateriels"]
        DB_DM[("db-erp-devmateriels<br/>:5436")]
    end
```

---

## 📅 Base Planning Service (db-planning)

```mermaid
erDiagram
    TECHNICIANS {
        int id PK
        varchar name
        varchar email
        varchar phone
        varchar specialty
        boolean is_available
    }

    INSPECTIONS {
        int id PK
        varchar wagon_id
        varchar client_company
        text issue_description
        varchar urgency
        date scheduled_date
        varchar location
        varchar status
        int technician_id FK
        text findings
        jsonb parts_needed
    }

    AVAILABILITY_SLOTS {
        int id PK
        int technician_id FK
        date slot_date
        time start_time
        time end_time
        boolean is_booked
        int inspection_id FK
    }

    TECHNICIANS ||--o{ INSPECTIONS : "assigne"
    TECHNICIANS ||--o{ AVAILABILITY_SLOTS : "a"
    INSPECTIONS ||--o| AVAILABILITY_SLOTS : "reserve"
```

---

## 📄 Base Devis Service (db-devis)

```mermaid
erDiagram
    PARTS {
        int id PK
        varchar reference UK
        varchar name
        varchar category
        decimal catalog_price
        int stock_quantity
        int reorder_threshold
    }

    DEVIS {
        int id PK
        int inspection_id
        varchar wagon_id
        varchar client_company
        decimal intervention_hours
        decimal hourly_rate
        decimal total_parts_cost
        decimal final_amount
        date proposed_intervention_date
        varchar status
        varchar confirmed_by
    }

    DEVIS_ITEMS {
        int id PK
        int devis_id FK
        int part_id FK
        varchar part_reference
        int quantity
        decimal negotiated_price
        decimal line_total
        boolean stock_available
    }

    STOCK_MOVEMENTS {
        int id PK
        int part_id FK
        varchar movement_type
        int quantity
        varchar reference_type
    }

    DEVIS ||--o{ DEVIS_ITEMS : "contient"
    PARTS ||--o{ DEVIS_ITEMS : "reference"
    PARTS ||--o{ STOCK_MOVEMENTS : "suivi"
```

---

## 🔔 Base Notification Service (db-notification)

```mermaid
erDiagram
    NOTIFICATIONS {
        int id PK
        varchar event_type
        varchar event_id
        varchar source_service
        varchar target_erp
        jsonb payload
        varchar status
        int http_status_code
        text error_message
        int retry_count
        timestamp sent_at
    }

    NOTIFICATION_TEMPLATES {
        int id PK
        varchar event_type UK
        jsonb template_wagonlits
        jsonb template_devmateriels
        text description
        boolean active
    }
```

---

## 🏢 Base ERP WagonLits (db-erp-wagonlits)

```mermaid
erDiagram
    WAGONS {
        int id PK
        varchar wagon_code UK
        varchar wagon_type
        int year_built
        date last_maintenance_date
        varchar status
    }

    INSPECTION_REQUESTS {
        int id PK
        int external_id
        varchar wagon_code
        text issue_description
        varchar urgency
        date scheduled_date
        varchar status
        varchar technician_name
    }

    DEVIS_RECEIVED {
        int id PK
        int external_devis_id
        int inspection_request_id FK
        varchar wagon_code
        decimal final_amount
        varchar status
        varchar validated_by
    }

    ORDERS {
        int id PK
        varchar order_number UK
        int devis_id FK
        varchar wagon_code
        decimal total_amount
        varchar status
    }

    NOTIFICATIONS_LOG {
        int id PK
        varchar event_type
        varchar source
        jsonb payload
        boolean processed
    }

    WAGONS ||--o{ INSPECTION_REQUESTS : "demande"
    INSPECTION_REQUESTS ||--o{ DEVIS_RECEIVED : "genere"
    DEVIS_RECEIVED ||--o| ORDERS : "valide"
```

---

## 🏭 Base ERP DevMateriels (db-erp-devmateriels)

```mermaid
erDiagram
    CLIENTS {
        int id PK
        varchar company_name UK
        varchar contact_name
        varchar contact_email
        varchar contract_type
        decimal annual_contract_value
    }

    INTERVENTIONS {
        int id PK
        int external_inspection_id
        int external_devis_id
        int client_id FK
        varchar wagon_code
        varchar intervention_type
        date scheduled_date
        varchar technician_assigned
        varchar status
        decimal total_amount
    }

    INVOICES {
        int id PK
        varchar invoice_number UK
        int intervention_id FK
        int client_id FK
        decimal amount_ht
        decimal tva_rate
        decimal amount_ttc
        varchar status
        date due_date
    }

    STOCK_RESERVATIONS {
        int id PK
        int intervention_id FK
        varchar part_reference
        varchar part_name
        int quantity
        varchar status
    }

    NOTIFICATIONS_LOG {
        int id PK
        varchar event_type
        varchar source
        jsonb payload
        boolean processed
    }

    CLIENTS ||--o{ INTERVENTIONS : "a"
    CLIENTS ||--o{ INVOICES : "recoit"
    INTERVENTIONS ||--o| INVOICES : "genere"
    INTERVENTIONS ||--o{ STOCK_RESERVATIONS : "reserve"
```

---

## 📊 Résumé des Tables par Service

| Service          | Base                | Tables                                                       | Rôle                    |
| ---------------- | ------------------- | ------------------------------------------------------------ | ----------------------- |
| **Planning**     | db-planning         | `technicians`, `inspections`, `availability_slots`           | Gestion planification   |
| **Devis**        | db-devis            | `parts`, `devis`, `devis_items`, `stock_movements`           | Catalogue, devis, stock |
| **Notification** | db-notification     | `notifications`, `notification_templates`                    | Suivi des webhooks      |
| **WagonLits**    | db-erp-wagonlits    | `wagons`, `inspection_requests`, `devis_received`, `orders`  | Données client          |
| **DevMateriels** | db-erp-devmateriels | `clients`, `interventions`, `invoices`, `stock_reservations` | Données internes        |

---

## 🔑 Points Clés à Mentionner au Prof

1. **Chaque microservice a sa propre BDD** → Isolation, indépendance
2. **Pas de foreign keys entre services** → Communication via API/Kafka
3. **Payload JSONB** dans notifications → Flexibilité des données
4. **ERPs ont des tables miroir** → Stockent les données reçues via webhooks
