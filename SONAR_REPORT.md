# Rapport qualité — Protéine circulaire (prototype)

> Analyse du 16/11/2026 · Périmètre : projet entier (`backend/`, `frontend/src/`)
> Langages : Python, JavaScript (React), SQL · NCLOC : 3 400 (dont tests 343) · Fichiers : 50 · Outils : sonar_metrics.py, pytest + coverage, vite build, relecture manuelle

État après corrections. L'état avant corrections est dans la section « Avant / Après ».

## Quality Gate : ❌ ÉCHOUÉ

| Condition | Seuil | Valeur | Statut |
|---|---|---|---|
| Note de fiabilité | A | A | ✅ |
| Note de sécurité | A | A | ✅ |
| Note de maintenabilité | A | A | ✅ |
| Hotspots revus | 100 % | 20 % (4 à trancher) | ❌ |
| Couverture | ≥ 80 % | backend 87 % · frontend non mesurée | ❌ |
| Duplication | ≤ 3 % | 0,9 % | ✅ |

Le gate échoue pour deux raisons qui demandent une décision humaine, pas une correction de code : les 5 hotspots ci-dessous doivent être tranchés, et le frontend n'a pas de tests.

## Vue d'ensemble

| Dimension | Note | Détail |
|---|---|---|
| 🐞 Fiabilité | A | 0 bug restant (5 corrigés : 2 Critical, 2 Major, 1 Minor) |
| 🔓 Sécurité | A | 0 vulnérabilité restante (3 corrigées : 1 Critical, 1 Major, 1 Minor) |
| 🔥 Revue sécurité | E | 4 hotspots à revoir (1 sur 5 traité) |
| 🧹 Maintenabilité | A | 14 code smells · dette ≈ 5 h · ratio ≈ 0,3 % |
| 📋 Duplication | — | 0,9 % (11 blocs, 32 lignes) : faux positif SQL, voir plus bas |
| 🧪 Couverture | — | backend 87 % (25 tests sur vraie base PostgreSQL) · frontend non mesurée |
| 🌀 Complexité | — | cyclomatique totale 694 · 0 fonction au-dessus du seuil cognitif 15 (1 avant) |

## Points chauds (fichiers les plus problématiques)

| Fichier | Issues | Dette | Complexité cognitive max |
|---|---|---|---|
| `frontend/src/roles/Breeder.jsx` | 1 smell | 30 min | 15 |
| `backend/app/formulator/solver.py` | 1 smell | 20 min | 14 |
| `backend/app/domain/impact.py` | 1 smell (S-004 corrigé) | 15 min | 14 (26 avant) |
| `frontend/src/pages/Login.jsx` | 2 smells | 30 min | 10 |
| `backend/seed/demo.py` | 2 smells | 30 min | 11 |

## Issues

| ID | Type | Sévérité | Règle | Emplacement | Problème | Effort | État |
|---|---|---|---|---|---|---|---|
| S-001 | 🔓 Vulnérabilité | Critical | SEC-HARDCODED-SECRET | `backend/app/config.py:14` | Clé de signature JWT par défaut connue : sans variable `JWT_SECRET`, n'importe qui peut fabriquer un jeton admin | 15 min | Corrigé |
| S-002 | 🔓 Vulnérabilité | Major | SEC-IDOR | `backend/app/domain/orders.py` | Une clé d'idempotence réutilisée renvoyait la commande d'un autre éleveur | 15 min | Corrigé |
| S-003 | 🔓 Vulnérabilité | Minor | SEC-ERROR-LEAK | `backend/app/errors.py` | Erreurs 500 renvoyaient le message brut de PostgreSQL (noms de tables, contraintes) | 5 min | Corrigé |
| S-004 | 🐞 Bug | Critical | BUG-RACE | `backend/app/domain/impact.py` | Curseur d'impact lu avant le verrou : deux appels simultanés comptaient deux fois les mêmes changements ou faisaient reculer le curseur | 30 min | Corrigé |
| S-005 | 🐞 Bug | Critical | BUG-API-AVAILABILITY | `frontend/src/api.js:24` | `crypto.randomUUID` n'existe pas en http hors localhost : toute action sensible plantait sur un téléphone du réseau local | 10 min | Corrigé |
| S-006 | 🐞 Bug | Major | BUG-INFINITE-LOOP | `backend/app/domain/changes.py` | Page pleine du journal : le jeton suivant relisait la même page, un client bouclait sans fin | 30 min | Corrigé |
| S-008 | 🐞 Bug | Major | BUG-STATE | `frontend/src/api.js`, `auth.jsx` | Jeton expiré (401) effacé du stockage mais pas de l'état React : application bloquée sans retour à la connexion | 15 min | Corrigé |
| S-007 | 🐞 Bug | Minor | BUG-FALSY-ZERO | `backend/app/domain/offers.py` | Latitude ou longitude 0 traitée comme absente | 5 min | Corrigé |
| S-009 | 🔥 Hotspot | — | SEC-DEBUG-MODE | `backend/app/config.py:17` | `DEV_OTP=1` par défaut : le code SMS est renvoyé dans la réponse | — | À revoir |
| S-010 | 🔥 Hotspot | — | SEC-CONTAINER-ROOT | `backend/Dockerfile`, `frontend/Dockerfile` | Conteneurs exécutés en root | — | Corrigé (utilisateurs `app` et `node`) |
| S-011 | 🔥 Hotspot | — | SEC-CREDENTIALS | `docker-compose.yml:8,21` | Mot de passe PostgreSQL et clé JWT de développement en clair | — | À revoir |
| S-012 | 🔥 Hotspot | — | SEC-ENUMERATION | `backend/app/api/routes.py:208` | `/trace/{code}` public, codes séquentiels (FB-2026-000001…) : on peut lister tous les lots et leurs communes | — | À revoir |
| S-013 | 🔥 Hotspot | — | SEC-ACCESS-CONTROL | `backend/app/api/routes.py:92` | `/offers/{id}/history` lisible par tout utilisateur connecté | — | À revoir |
| S-014 | 🧹 Code Smell | Major | SMELL-CYCLO | `backend/app/formulator/solver.py:21` | `solve()` cyclomatique 19 | 20 min | Restant |
| S-015 | 🧹 Code Smell | Major | SMELL-CYCLO | `backend/app/domain/impact.py:12` | `_metrics_for()` cyclomatique 15 (table de correspondance par type de changement) | 15 min | Restant |
| S-016 | 🧹 Code Smell | Major | SMELL-CYCLO | `backend/app/domain/rations.py:74` | `compute()` cyclomatique 12 (23 avant) | 10 min | Réduit |
| S-017 | 🧹 Code Smell | Major | SMELL-CYCLO | `backend/app/repositories/scd2.py:34` | `change()` cyclomatique 12 | 15 min | Restant |
| S-018 | 🧹 Code Smell | Major | SMELL-CYCLO / LONG-FN | `backend/seed/demo.py:34` | `main()` 81 lignes, cyclomatique 14 | 30 min | Restant |
| S-019 | 🧹 Code Smell | Major | SMELL-CYCLO / LONG-FN | `frontend/src/roles/Breeder.jsx:37` | `FormulatorPage()` 76 lignes, cyclomatique 18 | 30 min | Restant |
| S-020 | 🧹 Code Smell | Major | SMELL-CYCLO / LONG-FN | `frontend/src/pages/Login.jsx:14` | `Login()` 94 lignes, cyclomatique 12 | 30 min | Restant |
| S-021 | 🧹 Code Smell | Major | SMELL-CYCLO | `frontend/src/api.js:20` | `api()` cyclomatique 11 | 10 min | Restant |
| S-022 | 🧹 Code Smell | Minor | SMELL-PARAMS / CYCLO | `backend/tests/` | `make_actor()` 8 paramètres, 2 tests de parcours cyclomatique 11 | — | Accepté (tests de scénario) |
| S-023 | 🧹 Code Smell | Major | — | `frontend/` | Aucun test frontend | 1 j | Action humaine |

### Détail des issues Blocker et Critical

#### S-001 · Clé JWT par défaut
- **Pourquoi** : la valeur par défaut est publique (dans le dépôt). Un déploiement qui oublie `JWT_SECRET` accepte des jetons forgés, y compris avec le rôle admin.
- **Code** :
  ```python
  jwt_secret: str = os.getenv("JWT_SECRET", "dev-uniquement-changer-cette-cle-en-production")
  ```
- **Correction appliquée** : le serveur refuse de démarrer si la clé de développement est utilisée hors mode démo.
  ```python
  if not settings.dev_otp and settings.jwt_secret == DEV_JWT_SECRET:
      raise RuntimeError("JWT_SECRET doit être défini (32 caractères ou plus) quand DEV_OTP=0")
  ```

#### S-004 · Curseur d'impact non protégé
- **Pourquoi** : le filigrane était lu avant de verrouiller le curseur ; deux appels concurrents pouvaient appliquer deux fois les mêmes deltas (tonnes de déchets, CO2) ou faire reculer le curseur.
- **Correction appliquée** : création du curseur si absent, `SELECT … FOR UPDATE`, puis lecture du filigrane ; on sort sans rien faire si le filigrane n'avance pas. Calcul des métriques extrait dans `_metrics_for()` (complexité cognitive 26 → 14).

#### S-005 · `crypto.randomUUID` indisponible en http
- **Pourquoi** : le navigateur ne fournit `randomUUID` qu'en https ou sur localhost. Sur un téléphone qui ouvre `http://192.168.x.x:5173`, réserver, payer ou commander levait une exception.
- **Correction appliquée** :
  ```js
  const newKey = () =>
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now().toString(36)}-${Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("")}`;
  ```

## Security Hotspots à revoir

| ID | Emplacement | Catégorie | Question à trancher |
|---|---|---|---|
| S-009 | `backend/app/config.py:17` | Mode debug | Le prototype sera-t-il exposé à de vrais utilisateurs ? Si oui, passer `DEV_OTP=0` et brancher un vrai fournisseur SMS. |
| S-011 | `docker-compose.yml` | Identifiants en clair | Acceptable pour la démo locale ; en dehors, passer par un fichier `.env` non versionné. |
| S-012 | `routes.py:208` | Énumération | La traçabilité publique doit-elle montrer la commune d'origine ? Sinon, codes aléatoires ou commune masquée. |
| S-013 | `routes.py:92` | Contrôle d'accès | L'historique d'une offre (prix, quantités successives) doit-il être visible des autres producteurs ? |

## Duplications

| Bloc | Occurrences | Lignes |
|---|---|---|
| Listes de colonnes `CREATE TABLE` / `INSERT` (`0001_schema.sql:70-79` ↔ `0002_reference.sql:30-41`) | 11 | 32 |

Faux positif : ce sont des déclarations de colonnes et des valeurs de référence, pas de la logique. Duplication réelle ≈ 0 %.

## Recommandations

1. Trancher les 4 hotspots restants (10 minutes de lecture) : c'est ce qui bloque le gate.
2. Ajouter quelques tests frontend (Vitest + Testing Library) sur `api.js`, la connexion et le formulateur.
3. Découper `FormulatorPage` et `Login` en sous-composants (résultat, formulaire d'inscription) au prochain changement de ces écrans.
4. Avant tout usage réel : faire valider les valeurs nutritionnelles de `0002_reference.sql` par un nutritionniste.

## Corrections appliquées

| ID | Fichier | Changement | Vérification |
|---|---|---|---|
| S-001 | `backend/app/config.py` | Refus de démarrer avec la clé de développement hors mode démo | tests ✅ |
| S-002 | `backend/app/domain/orders.py` | Recherche par clé limitée à l'éleveur ; sinon 409 | tests ✅ |
| S-003 | `backend/app/errors.py` | Message générique pour les erreurs 500 | tests ✅ |
| S-004 | `backend/app/domain/impact.py` | Verrou du curseur avant lecture du filigrane ; extraction `_metrics_for()` | `test_impact_incremental` ✅ |
| S-005 | `frontend/src/api.js` | Repli si `randomUUID` est absent | `vite build` ✅ |
| S-006 | `backend/app/domain/changes.py`, `api/routes.py` | Jeton `debut:fin:seq` pour reprendre après une page pleine | nouveau test `test_journal_pagine_sans_boucle` ✅ |
| S-007 | `backend/app/domain/offers.py` | Test `is not None` au lieu de la valeur vraie | tests ✅ |
| S-008 | `frontend/src/api.js`, `frontend/src/auth.jsx` | Événement `pc-logout` sur 401 ; le contexte revient à l'écran de connexion | `vite build` ✅ |
| S-010 | `backend/Dockerfile`, `frontend/Dockerfile`, `.dockerignore` ×2 | Utilisateur sans privilèges (`app` pour l'API, `node` pour l'interface), code de l'API en lecture seule | images construites et lancées : `id` = app / node, connexion OK ✅ |
| S-016 | `backend/app/domain/rations.py` | `compute()` découpé en `_profile`, `_solve_both`, `_alerts`, `_quantities` (sans changement de résultat) | `test_formulator` ✅ |

Résultat : 25 tests sur 25 passent (24 existants + 1 nouveau), couverture backend 83 % → 87 %, build frontend OK.

## Non corrigé : action humaine requise

| ID | Raison |
|---|---|
| S-009, S-011 à S-013 | Hotspots : la bonne réponse dépend de l'usage prévu (démo locale ou pilote réel). |
| S-014, S-015, S-017 | Découpage possible, mais logique métier dense (solveur, SCD2, table d'impact) : gain faible pour un prototype, risque non nul. Maintenabilité déjà A. |
| S-018 à S-021 | Écrans et script de démo : à découper au prochain changement fonctionnel. |
| S-023 | Écrire des tests frontend demande de choisir l'outillage (Vitest proposé). |

## Avant / Après

| Indicateur | Avant | Après |
|---|---|---|
| Quality Gate | ❌ | ❌ (hotspots et tests frontend uniquement) |
| Bugs / Vulnérabilités / Smells | 5 / 3 / 15 | 0 / 0 / 14 |
| Notes F / S / M | D / D / A | A / A / A |
| Revue sécurité | E | E (4 hotspots à trancher) |
| Dette technique | ≈ 6 h (ratio 0,4 %) | ≈ 5 h (ratio 0,3 %) |
| Couverture backend | 83 % | 87 % |
| Duplication | 1,0 % | 0,9 % (faux positif) |
| Complexité cognitive max | 26 | 15 |

Fichiers modifiés : `backend/app/config.py`, `backend/app/errors.py`, `backend/app/domain/{orders,offers,impact,changes,rations}.py`, `backend/app/api/routes.py`, `backend/tests/test_history.py`, `frontend/src/api.js`, `frontend/src/auth.jsx`, `backend/Dockerfile`, `frontend/Dockerfile`, `backend/.dockerignore`, `frontend/.dockerignore`.
