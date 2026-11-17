-- Protéine circulaire : schéma initial du prototype
-- PostgreSQL 16 + PostGIS + btree_gist
-- Principes : aucune suppression de données métier, versions SCD2 pour ce qui évolue,
-- transitions de statut contrôlées par la base, journal des changements (CDC) alimenté par déclencheurs.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------------------
-- Types
-- ---------------------------------------------------------------------------
CREATE TYPE user_role       AS ENUM ('producer', 'farm', 'breeder', 'collector', 'admin');
CREATE TYPE account_status  AS ENUM ('active', 'pending', 'disabled', 'closed');
CREATE TYPE offer_status    AS ENUM ('published', 'reserved', 'cancelled');
CREATE TYPE lot_status      AS ENUM ('reserved', 'collected', 'received', 'rejected', 'used', 'recalled');
CREATE TYPE lot_quality     AS ENUM ('conforme', 'degrade', 'rejete');
CREATE TYPE flour_status    AS ENUM ('available', 'sold_out', 'recalled');
CREATE TYPE order_status    AS ENUM ('ordered', 'delivered', 'cancelled', 'recalled');
CREATE TYPE payment_kind    AS ENUM ('waste', 'collection', 'flour', 'commission');
CREATE TYPE payment_status  AS ENUM ('due', 'settled', 'cancelled');
CREATE TYPE dispute_status  AS ENUM ('open', 'resolved');

-- ---------------------------------------------------------------------------
-- Fonctions de garde génériques
-- ---------------------------------------------------------------------------

-- Aucune suppression de ligne métier.
CREATE FUNCTION forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'suppression interdite sur % : les données sont historisées', TG_TABLE_NAME
    USING ERRCODE = 'P0001';
END $$;

-- Lignes en ajout seul (journaux).
CREATE FUNCTION forbid_update() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'modification interdite sur % : table en ajout seul', TG_TABLE_NAME
    USING ERRCODE = 'P0001';
END $$;

-- SCD2 : une version ne peut qu'être fermée (valid_to, is_current), jamais réécrite.
CREATE FUNCTION scd2_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NOT OLD.is_current THEN
    RAISE EXCEPTION 'version % de % déjà fermée : historique non modifiable', OLD.version_id, TG_TABLE_NAME
      USING ERRCODE = 'P0001';
  END IF;
  IF NEW.is_current OR NEW.valid_to IS NULL THEN
    RAISE EXCEPTION 'une version SCD2 ne peut être modifiée que pour être fermée'
      USING ERRCODE = 'P0001';
  END IF;
  IF (to_jsonb(OLD) - 'valid_to' - 'is_current') <> (to_jsonb(NEW) - 'valid_to' - 'is_current') THEN
    RAISE EXCEPTION 'les attributs d''une version SCD2 sont immuables : créer une nouvelle version'
      USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- Machine à états déclarée dans la base
-- ---------------------------------------------------------------------------
CREATE TABLE allowed_transitions (
  entity      text NOT NULL,
  from_status text NOT NULL,
  to_status   text NOT NULL,
  PRIMARY KEY (entity, from_status, to_status)
);

INSERT INTO allowed_transitions VALUES
  ('waste_offers', 'published', 'reserved'),
  ('waste_offers', 'published', 'cancelled'),
  ('waste_lots', 'reserved', 'collected'),
  ('waste_lots', 'reserved', 'recalled'),
  ('waste_lots', 'collected', 'received'),
  ('waste_lots', 'collected', 'rejected'),
  ('waste_lots', 'collected', 'recalled'),
  ('waste_lots', 'received', 'used'),
  ('waste_lots', 'received', 'recalled'),
  ('waste_lots', 'used', 'recalled'),
  ('flour_batches', 'available', 'sold_out'),
  ('flour_batches', 'sold_out', 'available'),
  ('flour_batches', 'available', 'recalled'),
  ('flour_batches', 'sold_out', 'recalled'),
  ('orders', 'ordered', 'delivered'),
  ('orders', 'ordered', 'cancelled'),
  ('orders', 'ordered', 'recalled'),
  ('payments', 'due', 'settled'),
  ('payments', 'due', 'cancelled'),
  ('disputes', 'open', 'resolved');

CREATE TRIGGER allowed_transitions_no_update BEFORE UPDATE OR DELETE ON allowed_transitions
  FOR EACH ROW EXECUTE FUNCTION forbid_update();

CREATE FUNCTION check_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status AND NOT EXISTS (
      SELECT 1 FROM allowed_transitions
      WHERE entity = TG_TABLE_NAME AND from_status = OLD.status::text AND to_status = NEW.status::text) THEN
    RAISE EXCEPTION 'transition interdite sur % : % -> %', TG_TABLE_NAME, OLD.status, NEW.status
      USING ERRCODE = 'P0002';
  END IF;
  RETURN NEW;
END $$;

-- Journal métier des statuts (ajout seul), écrit dans la même transaction.
CREATE TABLE status_events (
  id          bigserial PRIMARY KEY,
  entity      text NOT NULL,
  entity_id   uuid NOT NULL,
  from_status text,
  to_status   text NOT NULL,
  actor_id    uuid,
  at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX status_events_entity_idx ON status_events (entity, entity_id, id);
CREATE TRIGGER status_events_append_only BEFORE UPDATE OR DELETE ON status_events
  FOR EACH ROW EXECUTE FUNCTION forbid_update();

CREATE FUNCTION log_status_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_actor uuid := nullif(current_setting('app.actor_id', true), '')::uuid;
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO status_events (entity, entity_id, from_status, to_status, actor_id)
    VALUES (TG_TABLE_NAME, NEW.id, NULL, NEW.status::text, v_actor);
  ELSIF OLD.status IS DISTINCT FROM NEW.status THEN
    INSERT INTO status_events (entity, entity_id, from_status, to_status, actor_id)
    VALUES (TG_TABLE_NAME, NEW.id, OLD.status::text, NEW.status::text, v_actor);
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- Journal des changements (CDC)
-- ---------------------------------------------------------------------------
CREATE TABLE change_log (
  seq        bigserial PRIMARY KEY,
  table_name text NOT NULL,
  op         text NOT NULL CHECK (op IN ('INSERT', 'UPDATE')),
  row_key    text NOT NULL,
  old_data   jsonb,
  new_data   jsonb,
  actor_id   uuid,
  txid       xid8 NOT NULL DEFAULT pg_current_xact_id(),
  at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX change_log_table_idx ON change_log (table_name, seq);
CREATE TRIGGER change_log_append_only BEFORE UPDATE OR DELETE ON change_log
  FOR EACH ROW EXECUTE FUNCTION forbid_update();

CREATE FUNCTION capture_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_new jsonb := to_jsonb(NEW);
  v_old jsonb := CASE WHEN TG_OP = 'UPDATE' THEN to_jsonb(OLD) END;
  v_key text  := coalesce(v_new->>'id', v_new->>'version_id',
                          v_new->>'flour_batch_id' || ':' || (v_new->>'waste_lot_id'));
BEGIN
  INSERT INTO change_log (table_name, op, row_key, old_data, new_data, actor_id)
  VALUES (TG_TABLE_NAME, TG_OP, v_key, v_old, v_new,
          nullif(current_setting('app.actor_id', true), '')::uuid);
  RETURN NEW;
END $$;

-- Curseurs des lecteurs du journal.
-- Le curseur est un identifiant de transaction (xid8) : toutes les transactions d'identifiant
-- inférieur à pg_snapshot_xmin(pg_current_snapshot()) sont terminées, donc un lecteur qui lit
-- l'intervalle [last_xid, xmin) ne rate jamais une ligne validée en retard.
CREATE TABLE cdc_cursors (
  consumer text PRIMARY KEY,
  last_xid xid8 NOT NULL DEFAULT '0'
);
CREATE INDEX change_log_txid_idx ON change_log (txid);

-- ---------------------------------------------------------------------------
-- Utilisateurs : identité stable + versions SCD2
-- ---------------------------------------------------------------------------
CREATE TABLE users (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone      text NOT NULL UNIQUE CHECK (phone ~ '^\+?[0-9]{8,15}$'),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_versions (
  version_id bigserial PRIMARY KEY,
  user_id    uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  name       text NOT NULL CHECK (length(trim(name)) > 0),
  role       user_role NOT NULL,
  status     account_status NOT NULL,
  is_woman   boolean NOT NULL DEFAULT false,
  commune    text,
  location   geography(Point, 4326),
  valid_from timestamptz NOT NULL DEFAULT clock_timestamp(),
  valid_to   timestamptz,
  is_current boolean NOT NULL DEFAULT true,
  CHECK ((valid_to IS NULL) = is_current),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  EXCLUDE USING gist (user_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
);
CREATE UNIQUE INDEX user_versions_current_uq ON user_versions (user_id) WHERE is_current;
CREATE INDEX user_versions_location_idx ON user_versions USING gist (location) WHERE is_current;

CREATE VIEW users_current AS
  SELECT u.id, u.phone, u.created_at, v.version_id, v.name, v.role, v.status, v.is_woman,
         v.commune, v.location, v.valid_from
  FROM users u JOIN user_versions v ON v.user_id = u.id AND v.is_current;

-- ---------------------------------------------------------------------------
-- Paramètres (tarifs) versionnés
-- ---------------------------------------------------------------------------
CREATE TABLE settings (
  key         text PRIMARY KEY,
  description text NOT NULL
);

CREATE TABLE setting_versions (
  version_id bigserial PRIMARY KEY,
  key        text NOT NULL REFERENCES settings (key) ON DELETE RESTRICT,
  value      numeric NOT NULL CHECK (value >= 0),
  valid_from timestamptz NOT NULL DEFAULT clock_timestamp(),
  valid_to   timestamptz,
  is_current boolean NOT NULL DEFAULT true,
  CHECK ((valid_to IS NULL) = is_current),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  EXCLUDE USING gist (key WITH =, tstzrange(valid_from, valid_to) WITH &&)
);
CREATE UNIQUE INDEX setting_versions_current_uq ON setting_versions (key) WHERE is_current;

-- ---------------------------------------------------------------------------
-- Référentiels
-- ---------------------------------------------------------------------------
CREATE TABLE waste_types (
  id   text PRIMARY KEY,
  name text NOT NULL,
  risk text
);

CREATE TABLE ingredients (
  id     text PRIMARY KEY,
  name   text NOT NULL,
  kind   text NOT NULL CHECK (kind IN ('conventionnel', 'local', 'larves', 'mineral'))
);

CREATE TABLE ingredient_versions (
  version_id    bigserial PRIMARY KEY,
  ingredient_id text NOT NULL REFERENCES ingredients (id) ON DELETE RESTRICT,
  price_fcfa_kg integer NOT NULL CHECK (price_fcfa_kg >= 0),
  nutrients     jsonb NOT NULL,
  alert         text,
  valid_from    timestamptz NOT NULL DEFAULT clock_timestamp(),
  valid_to      timestamptz,
  is_current    boolean NOT NULL DEFAULT true,
  CHECK ((valid_to IS NULL) = is_current),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  EXCLUDE USING gist (ingredient_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
);
CREATE UNIQUE INDEX ingredient_versions_current_uq ON ingredient_versions (ingredient_id) WHERE is_current;

CREATE TABLE animal_profiles (
  id     text PRIMARY KEY,
  family text NOT NULL,
  name   text NOT NULL
);

CREATE TABLE animal_profile_versions (
  version_id      bigserial PRIMARY KEY,
  profile_id      text NOT NULL REFERENCES animal_profiles (id) ON DELETE RESTRICT,
  requirements    jsonb NOT NULL,   -- {"pb": {"min": 19}, "fibre": {"max": 5}, ...}
  caps            jsonb NOT NULL,   -- {"farine_larves": 0.15, ...} part maximale de la ration
  daily_intake_kg numeric NOT NULL CHECK (daily_intake_kg > 0),
  valid_from      timestamptz NOT NULL DEFAULT clock_timestamp(),
  valid_to        timestamptz,
  is_current      boolean NOT NULL DEFAULT true,
  CHECK ((valid_to IS NULL) = is_current),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  EXCLUDE USING gist (profile_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
);
CREATE UNIQUE INDEX animal_profile_versions_current_uq ON animal_profile_versions (profile_id) WHERE is_current;

-- ---------------------------------------------------------------------------
-- Offres de déchets : identité + versions SCD2 (quantité, prix, lieu, statut)
-- ---------------------------------------------------------------------------
CREATE TABLE waste_offers (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  producer_id   uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  waste_type_id text NOT NULL REFERENCES waste_types (id) ON DELETE RESTRICT,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE waste_offer_versions (
  version_id   bigserial PRIMARY KEY,
  offer_id     uuid NOT NULL REFERENCES waste_offers (id) ON DELETE RESTRICT,
  quantity_kg  numeric(10, 1) NOT NULL CHECK (quantity_kg > 0),
  price_per_kg integer NOT NULL CHECK (price_per_kg >= 0),
  frequency    text NOT NULL DEFAULT 'ponctuelle',
  description  text,
  commune      text,
  location     geography(Point, 4326) NOT NULL,
  status       offer_status NOT NULL,
  valid_from   timestamptz NOT NULL DEFAULT clock_timestamp(),
  valid_to     timestamptz,
  is_current   boolean NOT NULL DEFAULT true,
  CHECK ((valid_to IS NULL) = is_current),
  CHECK (valid_to IS NULL OR valid_to > valid_from),
  EXCLUDE USING gist (offer_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
);
CREATE UNIQUE INDEX waste_offer_versions_current_uq ON waste_offer_versions (offer_id) WHERE is_current;
CREATE INDEX waste_offer_versions_location_idx ON waste_offer_versions USING gist (location) WHERE is_current;

-- Une transition de statut d'offre passe aussi par la machine à états (entre deux versions).
CREATE FUNCTION check_offer_version_transition() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  v_prev offer_status;
BEGIN
  SELECT status INTO v_prev FROM waste_offer_versions
   WHERE offer_id = NEW.offer_id AND version_id <> NEW.version_id
   ORDER BY valid_from DESC LIMIT 1;
  IF v_prev IS NOT NULL AND v_prev <> NEW.status AND NOT EXISTS (
      SELECT 1 FROM allowed_transitions
      WHERE entity = 'waste_offers' AND from_status = v_prev::text AND to_status = NEW.status::text) THEN
    RAISE EXCEPTION 'transition interdite sur waste_offers : % -> %', v_prev, NEW.status
      USING ERRCODE = 'P0002';
  END IF;
  IF v_prev IS NOT NULL AND v_prev <> 'published' AND v_prev = NEW.status THEN
    RAISE EXCEPTION 'une offre % ne peut plus être modifiée', v_prev USING ERRCODE = 'P0002';
  END IF;
  IF v_prev IS NOT NULL AND v_prev IS DISTINCT FROM NEW.status THEN
    INSERT INTO status_events (entity, entity_id, from_status, to_status, actor_id)
    VALUES ('waste_offers', NEW.offer_id, v_prev::text, NEW.status::text,
            nullif(current_setting('app.actor_id', true), '')::uuid);
  ELSIF v_prev IS NULL THEN
    INSERT INTO status_events (entity, entity_id, from_status, to_status, actor_id)
    VALUES ('waste_offers', NEW.offer_id, NULL, NEW.status::text,
            nullif(current_setting('app.actor_id', true), '')::uuid);
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER waste_offer_versions_transition BEFORE INSERT ON waste_offer_versions
  FOR EACH ROW EXECUTE FUNCTION check_offer_version_transition();

CREATE VIEW waste_offers_current AS
  SELECT o.id, o.producer_id, o.waste_type_id, o.created_at, v.version_id, v.quantity_kg,
         v.price_per_kg, v.frequency, v.description, v.commune, v.location, v.status, v.valid_from
  FROM waste_offers o JOIN waste_offer_versions v ON v.offer_id = o.id AND v.is_current;

-- ---------------------------------------------------------------------------
-- Lots de déchets
-- ---------------------------------------------------------------------------
CREATE SEQUENCE waste_lot_code_seq;
CREATE SEQUENCE flour_batch_code_seq;

CREATE TABLE waste_lots (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code             text NOT NULL UNIQUE
                   DEFAULT 'DL-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('waste_lot_code_seq')::text, 6, '0'),
  offer_id         uuid NOT NULL REFERENCES waste_offers (id) ON DELETE RESTRICT,
  offer_version_id bigint NOT NULL REFERENCES waste_offer_versions (version_id) ON DELETE RESTRICT,
  farm_id          uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  collector_id     uuid REFERENCES users (id) ON DELETE RESTRICT,
  weight_kg        numeric(10, 1) CHECK (weight_kg > 0),
  quality          lot_quality,
  status           lot_status NOT NULL DEFAULT 'reserved',
  version          integer NOT NULL DEFAULT 1,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  CHECK (status = 'reserved' OR status = 'recalled' OR weight_kg IS NOT NULL),
  CHECK (status NOT IN ('received', 'used') OR quality IN ('conforme', 'degrade')),
  CHECK (status <> 'rejected' OR quality = 'rejete')
);
CREATE UNIQUE INDEX waste_lots_one_per_offer ON waste_lots (offer_id);
CREATE INDEX waste_lots_farm_idx ON waste_lots (farm_id, status);
CREATE INDEX waste_lots_collector_idx ON waste_lots (collector_id, status);

-- ---------------------------------------------------------------------------
-- Farine
-- ---------------------------------------------------------------------------
CREATE TABLE flour_batches (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code         text NOT NULL UNIQUE
               DEFAULT 'FB-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('flour_batch_code_seq')::text, 6, '0'),
  farm_id      uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  quantity_kg  numeric(10, 1) NOT NULL CHECK (quantity_kg > 0),
  stock_kg     numeric(10, 1) NOT NULL,
  price_per_kg integer NOT NULL CHECK (price_per_kg > 0),
  status       flour_status NOT NULL DEFAULT 'available',
  version      integer NOT NULL DEFAULT 1,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  CHECK (stock_kg BETWEEN 0 AND quantity_kg)
);
CREATE INDEX flour_batches_status_idx ON flour_batches (status, price_per_kg);

CREATE TABLE flour_batch_sources (
  flour_batch_id uuid NOT NULL REFERENCES flour_batches (id) ON DELETE RESTRICT,
  waste_lot_id   uuid NOT NULL REFERENCES waste_lots (id) ON DELETE RESTRICT,
  PRIMARY KEY (flour_batch_id, waste_lot_id)
);
CREATE INDEX flour_batch_sources_lot_idx ON flour_batch_sources (waste_lot_id);
CREATE TRIGGER flour_batch_sources_append_only BEFORE UPDATE ON flour_batch_sources
  FOR EACH ROW EXECUTE FUNCTION forbid_update();

-- ---------------------------------------------------------------------------
-- Commandes et paiements
-- ---------------------------------------------------------------------------
CREATE TABLE orders (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  breeder_id      uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  flour_batch_id  uuid NOT NULL REFERENCES flour_batches (id) ON DELETE RESTRICT,
  quantity_kg     numeric(10, 1) NOT NULL CHECK (quantity_kg > 0),
  unit_price      integer NOT NULL CHECK (unit_price > 0),
  total_fcfa      integer NOT NULL CHECK (total_fcfa >= 0),
  status          order_status NOT NULL DEFAULT 'ordered',
  idempotency_key text UNIQUE,
  version         integer NOT NULL DEFAULT 1,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX orders_batch_idx ON orders (flour_batch_id, status);
CREATE INDEX orders_breeder_idx ON orders (breeder_id, created_at DESC);

CREATE TABLE payments (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind              payment_kind NOT NULL,
  payer_id          uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  payee_id          uuid REFERENCES users (id) ON DELETE RESTRICT,   -- NULL = la plateforme
  waste_lot_id      uuid REFERENCES waste_lots (id) ON DELETE RESTRICT,
  order_id          uuid REFERENCES orders (id) ON DELETE RESTRICT,
  amount_fcfa       integer NOT NULL CHECK (amount_fcfa >= 0),
  tariff_version_id bigint REFERENCES setting_versions (version_id) ON DELETE RESTRICT,
  reference         text,
  status            payment_status NOT NULL DEFAULT 'due',
  idempotency_key   text UNIQUE,
  created_at        timestamptz NOT NULL DEFAULT now(),
  settled_at        timestamptz,
  CHECK (num_nonnulls(waste_lot_id, order_id) = 1),
  CHECK ((kind = 'commission') = (payee_id IS NULL)),
  CHECK (status <> 'settled' OR (reference IS NOT NULL AND settled_at IS NOT NULL))
);
CREATE INDEX payments_payer_idx ON payments (payer_id, status);
CREATE INDEX payments_payee_idx ON payments (payee_id, status);

-- Un paiement réglé ou annulé est figé.
CREATE FUNCTION payment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status <> 'due' THEN
    RAISE EXCEPTION 'paiement % déjà %, non modifiable', OLD.id, OLD.status USING ERRCODE = 'P0001';
  END IF;
  IF NEW.amount_fcfa <> OLD.amount_fcfa OR NEW.payer_id <> OLD.payer_id
     OR NEW.payee_id IS DISTINCT FROM OLD.payee_id OR NEW.kind <> OLD.kind THEN
    RAISE EXCEPTION 'montant et parties d''un paiement sont immuables' USING ERRCODE = 'P0001';
  END IF;
  RETURN NEW;
END $$;

-- ---------------------------------------------------------------------------
-- Retraits, notifications, litiges, prix, élevages, rations
-- ---------------------------------------------------------------------------
CREATE TABLE recalls (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  waste_lot_id   uuid REFERENCES waste_lots (id) ON DELETE RESTRICT,
  flour_batch_id uuid REFERENCES flour_batches (id) ON DELETE RESTRICT,
  reason         text NOT NULL,
  initiated_by   uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  created_at     timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(waste_lot_id, flour_batch_id) = 1)
);
CREATE TRIGGER recalls_append_only BEFORE UPDATE ON recalls
  FOR EACH ROW EXECUTE FUNCTION forbid_update();

CREATE TABLE notifications (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  kind       text NOT NULL,
  message    text NOT NULL,
  ref_code   text,
  read_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user_idx ON notifications (user_id, created_at DESC);

CREATE TABLE disputes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  author_id   uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  subject     text NOT NULL,
  body        text NOT NULL,
  ref_code    text,
  status      dispute_status NOT NULL DEFAULT 'open',
  resolution  text,
  resolved_by uuid REFERENCES users (id) ON DELETE RESTRICT,
  created_at  timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  CHECK (status = 'open' OR (resolution IS NOT NULL AND resolved_by IS NOT NULL))
);

CREATE TABLE price_reports (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  item          text NOT NULL,
  price_fcfa_kg integer NOT NULL CHECK (price_fcfa_kg > 0),
  commune       text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX price_reports_item_idx ON price_reports (item, created_at DESC);
CREATE TRIGGER price_reports_append_only BEFORE UPDATE ON price_reports
  FOR EACH ROW EXECUTE FUNCTION forbid_update();

CREATE TABLE herds (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  breeder_id uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  profile_id text NOT NULL REFERENCES animal_profiles (id) ON DELETE RESTRICT,
  name       text NOT NULL,
  headcount  integer NOT NULL CHECK (headcount > 0),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rations (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  breeder_id         uuid NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
  profile_version_id bigint NOT NULL REFERENCES animal_profile_versions (version_id) ON DELETE RESTRICT,
  soy_price          integer NOT NULL,
  result             jsonb NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE otp_codes (
  id         bigserial PRIMARY KEY,
  phone      text NOT NULL,
  code_hash  text NOT NULL,
  attempts   integer NOT NULL DEFAULT 0,
  expires_at timestamptz NOT NULL,
  used_at    timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX otp_codes_phone_idx ON otp_codes (phone, created_at DESC);

-- Totaux d'impact tenus à jour à partir du journal des changements.
CREATE TABLE impact_totals (
  metric text PRIMARY KEY,
  value  numeric NOT NULL DEFAULT 0
);
INSERT INTO impact_totals (metric) VALUES
  ('waste_received_kg'), ('flour_delivered_kg'), ('revenue_waste_fcfa'),
  ('revenue_collection_fcfa'), ('revenue_flour_fcfa'), ('revenue_women_fcfa');

-- ---------------------------------------------------------------------------
-- Pose des déclencheurs
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  t text;
BEGIN
  -- Aucune suppression sur les tables métier
  FOREACH t IN ARRAY ARRAY['users', 'user_versions', 'settings', 'setting_versions', 'waste_types',
    'ingredients', 'ingredient_versions', 'animal_profiles', 'animal_profile_versions',
    'waste_offers', 'waste_offer_versions', 'waste_lots', 'flour_batches', 'flour_batch_sources',
    'orders', 'payments', 'recalls', 'notifications', 'disputes', 'price_reports', 'herds', 'rations']
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE DELETE ON %I FOR EACH ROW EXECUTE FUNCTION forbid_delete()',
                   t || '_no_delete', t);
  END LOOP;

  -- Versions SCD2 : seule la fermeture est permise
  FOREACH t IN ARRAY ARRAY['user_versions', 'setting_versions', 'ingredient_versions',
    'animal_profile_versions', 'waste_offer_versions']
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION scd2_guard()',
                   t || '_scd2_guard', t);
  END LOOP;

  -- Machine à états + journal des statuts
  FOREACH t IN ARRAY ARRAY['waste_lots', 'flour_batches', 'orders', 'payments', 'disputes']
  LOOP
    EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE OF status ON %I FOR EACH ROW EXECUTE FUNCTION check_transition()',
                   t || '_transition', t);
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OF status ON %I FOR EACH ROW EXECUTE FUNCTION log_status_event()',
                   t || '_status_event', t);
  END LOOP;

  -- Capture des changements (CDC)
  FOREACH t IN ARRAY ARRAY['users', 'user_versions', 'setting_versions', 'ingredient_versions',
    'animal_profile_versions', 'waste_offers', 'waste_offer_versions', 'waste_lots', 'flour_batches',
    'flour_batch_sources', 'orders', 'payments', 'recalls', 'disputes', 'price_reports', 'herds']
  LOOP
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION capture_change()',
                   t || '_cdc', t);
  END LOOP;
END $$;

CREATE TRIGGER payments_guard BEFORE UPDATE ON payments
  FOR EACH ROW EXECUTE FUNCTION payment_guard();
