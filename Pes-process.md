# 🎤 Présentation

## 1. Introduction

**Contexte du problème :**

> "DevMateriels maintient des wagons pour WagonLits et ConstructWagons. Le problème : **communication manuelle par email/téléphone**, **pas de visibilité temps réel**, et **planification inefficace**."

**Notre solution :**

> "Un système de microservices avec API centralisée et notifications automatiques."

---

## 2. Architecture Technique

### Schéma simplifié :

```
┌─────────────┐     ┌─────────────┐
│  WagonLits  │     │ConstructWag │
│    (ERP)    │     │    (ERP)    │
└──────┬──────┘     └──────┬──────┘
       │    Webhooks       │
       ▼                   ▼
┌──────────────────────────────────┐
│         API Gateway (8000)        │
└──────────────────────────────────┘
       │         │          │
       ▼         ▼          ▼
┌──────────┐ ┌─────────┐ ┌──────────────┐
│ Planning │ │  Devis  │ │ Notification │
│ (5001)   │ │ (5002)  │ │   (5003)     │
└──────────┘ └─────────┘ └──────────────┘
                 │
                 ▼
           ┌──────────┐
           │  Kafka   │
           └──────────┘
```

### Justifications techniques :

| Choix              | Problème résolu                     |
| ------------------ | ----------------------------------- |
| **API Gateway**    | Point d'entrée unique, sécurité     |
| **Microservices**  | Indépendance, scalabilité           |
| **Kafka**          | Communication asynchrone, fiabilité |
| **Webhooks**       | Notifications temps réel            |
| **Docker Compose** | Déploiement simplifié               |

---

## 3. Démo du Prototype

---

### 🔹 Étape 1 : Demande d'inspection

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

**👀 Vérifier côté ERPs (montrer au prof) :**

```bash
# WagonLits : nouvelle notification reçue
curl -s http://localhost:5010/notifications | python3 -m json.tool | tail -20

# DevMateriels : intervention créée
curl -s http://localhost:5011/interventions | python3 -m json.tool
```

---

### 🔹 Étape 2 : Confirmer un créneau

```bash
curl -X POST http://localhost:8000/api/inspection/schedule/{slot_id} \
  -H "Content-Type: application/json" \
  -d '{"inspection_id": {id}, "location": "Dépôt Paris Nord"}'
```

**👀 Vérifier côté ERPs (montrer au prof) :**

```bash
# WagonLits : inspection mise à jour avec date/technicien
curl -s http://localhost:5010/inspections | python3 -m json.tool

# DevMateriels : intervention mise à jour
curl -s http://localhost:5011/interventions | python3 -m json.tool
```

---

### 🔹 Étape 3 : Générer un devis

```bash
curl -X POST http://localhost:8000/api/devis/generate \
  -H "Content-Type: application/json" \
  -d '{
    "inspection_id": {id},
    "wagon_id": "WAG-001",
    "client_company": "WagonLits",
    "parts": [{"reference": "BP-001", "quantity": 4}],
    "intervention_hours": 8
  }'
```

**👀 Vérifier côté ERPs (montrer au prof) :**

```bash
# WagonLits : devis reçu avec montant
curl -s http://localhost:5010/devis | python3 -m json.tool

# DevMateriels : intervention mise à jour avec montant
curl -s http://localhost:5011/interventions | python3 -m json.tool
```

---

### 🔹 Étape 4 : Valider le devis

```bash
curl -X POST http://localhost:8000/api/devis/{devis_id}/validate \
  -H "Content-Type: application/json" \
  -d '{"confirmed_by": "Jean Martin"}'
```

**👀 Vérifier côté ERPs (montrer au prof) :**

```bash
# WagonLits : commande créée !
curl -s http://localhost:5010/orders | python3 -m json.tool

# DevMateriels : facture créée + stock réservé
curl -s http://localhost:5011/invoices | python3 -m json.tool
curl -s http://localhost:5011/stock-reservations | python3 -m json.tool
```

---

### 📊 Résumé : Toutes les notifications reçues

```bash
# Voir toutes les notifications WagonLits
curl -s http://localhost:5010/notifications | python3 -m json.tool

# Voir toutes les notifications DevMateriels
curl -s http://localhost:5011/notifications | python3 -m json.tool
```

---

## 4. Conclusion

### ⚠️ Limites du prototype :

- Pas d'authentification (JWT/OAuth)
- Pas d'interface utilisateur graphique
- Tests automatisés limités
- Monitoring absent

### 🚀 Pour finaliser :

- Interface web React/Vue
- Authentification + contrôle d'accès
- Tests unitaires/intégration
- Dashboard de monitoring

### ✅ Ce que le prototype démontre :

- Communication inter-systèmes automatisée
- Planification centralisée
- Gestion de stock intégrée
- Notifications temps réel bidirectionnelles

---

## 📌 Avant la démo

```bash
# Vérifier les services
docker-compose ps

# Si problème, redémarrer
docker-compose restart
```
