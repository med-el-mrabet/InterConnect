# DevMateriels - Système de Microservices pour la Maintenance Ferroviaire

## 📋 Description

Solution d'interopérabilité basée sur des microservices pour **DevMateriels**, gérant les processus d'**inspection technique** et de **génération de devis** pour la maintenance curative des wagons.

## 🚀 Démarrage Rapide

```bash
# Lancer tous les services
cd InterV2
docker-compose up -d

# Vérifier l'état
docker-compose ps
```

## 📡 API Gateway (Port 8000)

### Flux d'Inspection

#### 1. Demander une inspection

Retourne les créneaux disponibles avec leurs IDs.

```bash
curl -X POST http://localhost:8000/api/inspection/request \
  -H "Content-Type: application/json" \
  -d '{
    "wagon_id": "WAG-001",
    "client_company": "WagonLits",
    "issue_description": "Système de freinage défaillant",
    "urgency": "high"
  }'
```

**Réponse:**

```json
{
  "inspection": {"id": 1, "status": "pending", ...},
  "available_slots": [
    {
      "slot_id": 1,
      "date": "2025-12-09",
      "start_time": "08:00:00",
      "end_time": "12:00:00",
      "technician_name": "Jean Dupont",
      "specialty": "Système de freinage"
    }
  ],
  "message": "Sélectionnez un slot_id pour planifier.",
  "next_step": "POST /inspection/schedule/{slot_id}"
}
```

#### 2. Planifier par slot_id

Utilise l'ID du créneau choisi.

```bash
curl -X POST http://localhost:8000/api/inspection/schedule/1 \
  -H "Content-Type: application/json" \
  -d '{
    "inspection_id": 1,
    "location": "Dépôt Paris Nord"
  }'
```

**Réponse de confirmation:**

```json
{
  "status": "confirmed",
  "message": "Inspection planifiée avec succès!",
  "schedule_details": {
    "date": "2025-12-09",
    "start_time": "08:00:00",
    "technician": {
      "name": "Jean Dupont",
      "specialty": "Système de freinage",
      "phone": "+33 1 23 45 67 89"
    }
  },
  "next_steps": [
    "Le technicien sera sur place à la date prévue",
    "Après l'inspection, un devis sera généré",
    "Les deux ERP ont été notifiés"
  ]
}
```

### Flux de Devis

#### 3. Générer un devis

Vérifie automatiquement le stock et suggère des modifications.

```bash
curl -X POST http://localhost:8000/api/devis/generate \
  -H "Content-Type: application/json" \
  -d '{
    "inspection_id": 1,
    "wagon_id": "WAG-001",
    "client_company": "WagonLits",
    "parts": [
      {"reference": "BP-001", "quantity": 4},
      {"reference": "HL-002", "quantity": 1}
    ],
    "intervention_hours": 8
  }'
```

**Réponse si stock OK:**

```json
{
  "devis": {"id": 1, "final_amount": 2305.00, ...},
  "can_validate": true,
  "message": "✅ Toutes les pièces sont disponibles.",
  "next_step": "POST /devis/1/validate avec {'confirmed_by': 'votre_nom'}"
}
```

**Réponse si stock insuffisant:**

```json
{
  "devis": {"id": 2, ...},
  "can_validate": false,
  "modifications_required": [
    {
      "action": "MODIFIER_QUANTITE",
      "reference": "BP-001",
      "quantite_demandee": 200,
      "quantite_disponible": 120,
      "message": "⚠️ Demandez 120 au lieu de 200. Réappro le 2025-12-16"
    },
    {
      "action": "RETIRER",
      "reference": "INVALID-REF",
      "message": "❌ Référence introuvable. Retirez-la du devis."
    }
  ],
  "message": "⚠️ Modifications nécessaires avant validation."
}
```

#### 4. Valider le devis

Envoie automatiquement vers Kafka et notifie les deux ERPs.

```bash
curl -X POST http://localhost:8000/api/devis/1/validate \
  -H "Content-Type: application/json" \
  -d '{"confirmed_by": "Jean Martin"}'
```

**Réponse:**

```json
{
  "confirmation": {
    "status": "validated",
    "message": "✅ Devis validé! Les deux ERP ont été notifiés.",
    "notifications_sent_to": ["ERP WagonLits", "ERP DevMateriels"]
  }
}
```

## � Endpoints Complets

| Endpoint                             | Méthode | Description                              |
| ------------------------------------ | ------- | ---------------------------------------- |
| `/api/inspection/request`            | POST    | Demander une inspection (retourne slots) |
| `/api/inspection/schedule/{slot_id}` | POST    | Planifier par ID de créneau              |
| `/api/inspection/availability`       | GET     | Lister créneaux disponibles              |
| `/api/inspection/{id}/complete`      | POST    | Compléter l'inspection                   |
| `/api/devis/generate`                | POST    | Générer devis (vérifie stock)            |
| `/api/devis/{id}/validate`           | POST    | Valider → Kafka → ERPs                   |
| `/api/devis/{id}/reject`             | POST    | Rejeter le devis                         |
| `/api/stock/parts`                   | GET     | Catalogue des pièces                     |
| `/api/stock/check`                   | POST    | Vérifier disponibilité                   |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│               ERP WagonLits (5010)                  │◄────┐
└─────────────────────────────────────────────────────┘     │
                         │                                   │
                         ▼                                   │
┌─────────────────────────────────────────────────────┐     │
│              API Gateway (8000)                      │     │
└─────────────────────────────────────────────────────┘     │
        │               │              │                     │
        ▼               ▼              ▼                     │
┌──────────────┐ ┌─────────────┐ ┌────────────────┐         │
│  Planning    │ │   Devis     │ │ Notification   │─────────┤
│  (5001)      │ │   (5002)    │ │   (5003)       │─────────┘
└──────┬───────┘ └──────┬──────┘ └───────┬────────┘
       │                │                │
       └────────────────┴────────────────┘
                        │
                  ┌─────┴─────┐
                  │   Kafka   │
                  │  (9093)   │
                  └───────────┘
```

## � Services

| Service          | Port | Description                        |
| ---------------- | ---- | ---------------------------------- |
| API Gateway      | 8000 | Point d'entrée, routage            |
| Planning         | 5001 | Techniciens, créneaux, inspections |
| Devis            | 5002 | Catalogue, devis, stock            |
| Notification     | 5003 | Consumer Kafka, webhooks ERPs      |
| ERP WagonLits    | 5010 | Simulation client                  |
| ERP DevMateriels | 5011 | Simulation interne                 |
| Kafka            | 9093 | Messagerie asynchrone              |

## 🧪 Tests Rapides

```bash
# Health check
curl http://localhost:8000/health

# Catalogue pièces
curl http://localhost:8000/api/stock/parts

# Créneaux disponibles
curl "http://localhost:8000/api/inspection/availability?start_date=2025-12-09"
```

## � Topics Kafka

- `inspection.requested` → Inspection demandée
- `inspection.scheduled` → Inspection planifiée
- `inspection.completed` → Inspection terminée
- `devis.generated` → Devis créé
- `devis.validated` → Devis validé → Notifications ERPs
- `devis.rejected` → Devis rejeté
