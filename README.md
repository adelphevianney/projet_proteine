# Protéine circulaire : prototype

Application web mobile qui relie producteurs de déchets agricoles, fermes à larves (mouche soldat noire),
éleveurs et collecteurs en Côte d'Ivoire, avec traçabilité de chaque lot et formulateur de ration.

Architecture détaillée : voir le document d'architecture (lien dans le projet) et `docs/`.

| Couche | Technologie |
| --- | --- |
| Application | React 18, Vite, React Router, TanStack Query, Leaflet (PWA installable depuis le navigateur) |
| API | Python, FastAPI, SQLAlchemy 2 (requêtes SQL explicites), Pydantic, SciPy (HiGHS) pour le formulateur |
| Base | PostgreSQL 16 + PostGIS, migrations Alembic |

## Démarrer

### Avec Docker (le plus simple)

```bash
docker compose up --build
```

Ouvrez http://localhost:5173 sur l'ordinateur, ou `http://<adresse-ip-de-l-ordinateur>:5173` sur un téléphone
du même réseau Wi-Fi. La documentation de l'API est sur http://localhost:8000/docs.

### Sans Docker

Prérequis : PostgreSQL 16 avec PostGIS, Python 3.12+, Node 20+.

```bash
# Base
createuser -s proteine && createdb -O proteine proteine   # mot de passe : proteine

# API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head          # schéma + données de référence
python -m seed.demo           # acteurs et lots de démonstration
uvicorn app.main:app --reload --port 8000

# Application (autre terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Comptes de démonstration

Connexion par numéro de téléphone. En prototype, le SMS est simulé : le code s'affiche à l'écran.

| Téléphone | Rôle | Nom |
| --- | --- | --- |
| +2250700000000 | Administration | Équipe plateforme |
| +2250700000001 | Producteur | Awa Koné (attiéké), Yopougon |
| +2250700000002 | Producteur | Coopérative Cajou du Gbêkê, Bouaké |
| +2250700000003 | Producteur | Adjoua Kouassi (marché), Adjamé |
| +2250700000004 | Producteur | Konan Yao (cacao), Agboville |
| +2250700000011 | Ferme à larves | BioLarve Songon |
| +2250700000012 | Ferme à larves | Insecta Bouaké |
| +2250700000013 | Ferme à larves | Nouvelle ferme Dabou (en attente de validation) |
| +2250700000021 | Collecteur | Koffi (tricycle), Abidjan |
| +2250700000022 | Collecteur | Moussa (moto), Bouaké |
| +2250700000031 | Éleveur | Élevage Bamba (poulets), Anyama |
| +2250700000032 | Éleveur | Pisciculture de la Lagune, Songon |
| +2250700000033 | Éleveur | Porcherie Yao, Bouaké |

Codes à tracer : `FB-2026-000001`, `FB-2026-000002` (farine), `DL-2026-000001` (déchets).

### Scénario de démonstration (10 minutes)

1. **Collecteur** (…21) : « Ma tournée » montre 2 enlèvements triés par distance. Saisir un poids.
2. **Ferme** (…11) : « Mes lots », réceptionner le lot (Conforme, Dégradé −30 % ou Rejeter).
3. **Ferme** : « Farine », cocher le lot réceptionné et déclarer un lot de farine.
4. **Éleveur** (…31) : « Formulateur », bouger le curseur du prix du soja et voir l'économie ; puis « Farine », commander.
5. **Ferme** : « Commandes », marquer livrée. **Éleveur** : « Paiements », « J'ai payé » avec une référence.
6. **Traçabilité** (loupe en haut) : saisir le code de farine, on remonte aux déchets d'origine.
7. **Ferme** : « Mes lots », retirer un lot transformé : la farine et les commandes non livrées sont retirées,
   les éleveurs reçoivent une alerte.
8. **Administration** (…00) : valider la ferme de Dabou, lire le « Journal » des changements.
9. **Producteur** (…01) : « Profil », changer de lieu : l'historique garde toutes les versions.

## Garde-fous de la base

- **Transactions** : chaque opération métier (réservation, collecte, réception, farine, commande, paiement,
  retrait) est une transaction unique ; verrous de ligne `FOR UPDATE`, retrait en `SERIALIZABLE` avec relance.
- **Contraintes** : clés étrangères `ON DELETE RESTRICT`, `CHECK` (stock entre 0 et la quantité produite,
  montants positifs, un paiement lié à un seul lot ou une seule commande), types `ENUM`.
- **Machine à états dans la base** : table `allowed_transitions` et déclencheur ; une transition interdite
  est refusée même par une requête SQL directe.
- **Idempotence** : en-tête `Idempotency-Key` sur les commandes.
- **Aucune suppression** : déclencheur sur toutes les tables métier ; un paiement réglé est figé.
- **SCD2** : utilisateurs, offres, tarifs, ingrédients et profils d'animaux ont une table de versions
  (`valid_from`, `valid_to`, `is_current`), une seule version courante (index unique partiel) et aucun
  chevauchement (contrainte d'exclusion). Chaque lot garde la version de l'offre convenue, chaque paiement
  la version du tarif appliqué.
- **CDC** : chaque écriture alimente `change_log` dans la même transaction. Les lecteurs (impact, route
  `GET /api/v1/changes?since=`) lisent seulement les transactions terminées depuis leur dernier jeton
  (identifiant de transaction), donc rien n'est relu ni oublié.

## Tests

```bash
cd backend
createdb -O proteine proteine_test
DATABASE_URL=postgresql+psycopg://proteine:proteine@localhost:5432/proteine_test pytest -q
```

24 tests sur une vraie base PostgreSQL : parcours complet, quatre fermes qui réservent la même offre en même
temps (une seule réussit), dix commandes simultanées sur un stock de 100 kg (jamais de survente),
idempotence, retrait en cascade, transitions et suppressions refusées par la base, historique SCD2,
lecture incrémentale du journal, formulateur (besoins et plafonds respectés pour les 7 profils).

## Limites du prototype

- SMS simulé (le code s'affiche) ; brancher un fournisseur SMS dans `app/domain/accounts.py`.
- Paiements enregistrés seulement : le règlement se fait hors plateforme, comme prévu dans la fiche.
- Valeurs nutritionnelles, prix et facteurs d'impact indicatifs : à faire valider par un nutritionniste.
- Une offre donne un seul lot ; une offre récurrente se republie.
- Notifications dans l'application uniquement (pas de push).
