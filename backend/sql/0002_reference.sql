-- Données de référence du prototype.
-- Valeurs nutritionnelles et prix INDICATIFS (ordre de grandeur, Côte d'Ivoire) :
-- à faire valider par un nutritionniste avant tout usage réel.

INSERT INTO settings (key, description) VALUES
  ('waste_price_per_kg', 'Prix par défaut du déchet payé au producteur (FCFA/kg)'),
  ('collection_price_per_kg', 'Rémunération du collecteur (FCFA/kg)'),
  ('commission_rate', 'Commission de la plateforme sur chaque vente'),
  ('degraded_discount', 'Décote appliquée à un lot dégradé'),
  ('soy_substitution', 'kg de soja évités par kg de farine de larves livrée'),
  ('co2_per_kg_waste', 'kg CO2e évités par kg de déchet valorisé au lieu de pourrir'),
  ('co2_per_kg_soy', 'kg CO2e évités par kg de soja importé évité');

INSERT INTO setting_versions (key, value) VALUES
  ('waste_price_per_kg', 15),
  ('collection_price_per_kg', 5),
  ('commission_rate', 0.05),
  ('degraded_discount', 0.30),
  ('soy_substitution', 0.95),
  ('co2_per_kg_waste', 0.5),
  ('co2_per_kg_soy', 1.6);

INSERT INTO waste_types (id, name, risk) VALUES
  ('manioc', 'Épluchures de manioc', 'acide cyanhydrique si non séché'),
  ('cajou', 'Pommes de cajou', 'tanins'),
  ('cacao', 'Cabosses de cacao', 'théobromine'),
  ('marche', 'Déchets de marché (fruits et légumes)', NULL);

INSERT INTO ingredients (id, name, kind) VALUES
  ('mais', 'Maïs grain', 'conventionnel'),
  ('tourteau_soja', 'Tourteau de soja', 'conventionnel'),
  ('son_ble', 'Son de blé', 'conventionnel'),
  ('farine_poisson', 'Farine de poisson', 'conventionnel'),
  ('tourteau_coton', 'Tourteau de coton', 'conventionnel'),
  ('paille', 'Paille et fourrage sec', 'conventionnel'),
  ('farine_larves', 'Farine de larves (mouche soldat noire)', 'larves'),
  ('manioc', 'Épluchures de manioc séchées', 'local'),
  ('cajou', 'Pommes de cajou séchées', 'local'),
  ('cacao', 'Cabosses de cacao séchées', 'local'),
  ('coquillage', 'Coquillage broyé', 'mineral'),
  ('phosphate', 'Phosphate bicalcique', 'mineral');

INSERT INTO ingredient_versions (ingredient_id, price_fcfa_kg, nutrients, alert) VALUES
  ('mais',           200, '{"pb": 8.5, "em": 3300, "ca": 0.02, "p": 0.25, "lys": 0.25, "fibre": 2.2}', NULL),
  ('tourteau_soja',  450, '{"pb": 44,  "em": 2250, "ca": 0.3,  "p": 0.6,  "lys": 2.8,  "fibre": 7}', NULL),
  ('son_ble',        120, '{"pb": 15,  "em": 1800, "ca": 0.1,  "p": 1.0,  "lys": 0.6,  "fibre": 10}', NULL),
  ('farine_poisson', 700, '{"pb": 60,  "em": 2800, "ca": 5,    "p": 3,    "lys": 4.5,  "fibre": 1}', NULL),
  ('tourteau_coton', 200, '{"pb": 40,  "em": 2200, "ca": 0.2,  "p": 1.0,  "lys": 1.6,  "fibre": 12}', 'gossypol'),
  ('paille',          30, '{"pb": 4,   "em": 1500, "ca": 0.3,  "p": 0.1,  "lys": 0.1,  "fibre": 35}', NULL),
  ('farine_larves',  350, '{"pb": 42,  "em": 2900, "ca": 5,    "p": 0.9,  "lys": 2.4,  "fibre": 7}', NULL),
  ('manioc',          80, '{"pb": 3,   "em": 2600, "ca": 0.2,  "p": 0.1,  "lys": 0.1,  "fibre": 8}', 'acide cyanhydrique : bien sécher'),
  ('cajou',           60, '{"pb": 10,  "em": 2000, "ca": 0.2,  "p": 0.2,  "lys": 0.3,  "fibre": 12}', 'tanins'),
  ('cacao',           40, '{"pb": 7,   "em": 1600, "ca": 0.4,  "p": 0.2,  "lys": 0.2,  "fibre": 25}', 'théobromine'),
  ('coquillage',      50, '{"pb": 0,   "em": 0,    "ca": 38,   "p": 0,    "lys": 0,    "fibre": 0}', NULL),
  ('phosphate',      600, '{"pb": 0,   "em": 0,    "ca": 23,   "p": 18,   "lys": 0,    "fibre": 0}', NULL);

INSERT INTO animal_profiles (id, family, name) VALUES
  ('poulet_demarrage', 'volaille', 'Poulet de chair, démarrage'),
  ('poulet_croissance', 'volaille', 'Poulet de chair, croissance'),
  ('pondeuse', 'volaille', 'Poule pondeuse'),
  ('porc_croissance', 'porc', 'Porc en croissance'),
  ('tilapia', 'poisson', 'Tilapia en grossissement'),
  ('bovin_embouche', 'ruminant', 'Bovin d''embouche'),
  ('ovin_embouche', 'ruminant', 'Ovin d''embouche');

-- Besoins en % de la ration (em en kcal/kg) ; caps = part maximale d'un ingrédient (0 = interdit).
INSERT INTO animal_profile_versions (profile_id, requirements, caps, daily_intake_kg) VALUES
  ('poulet_demarrage',
   '{"pb": {"min": 21}, "em": {"min": 2950}, "ca": {"min": 0.9, "max": 1.2}, "p": {"min": 0.45}, "lys": {"min": 1.1}, "fibre": {"max": 5}}',
   '{"farine_larves": 0.15, "manioc": 0.10, "cajou": 0.03, "cacao": 0, "paille": 0, "tourteau_coton": 0.05, "son_ble": 0.10}', 0.05),
  ('poulet_croissance',
   '{"pb": {"min": 19}, "em": {"min": 3000}, "ca": {"min": 0.85, "max": 1.1}, "p": {"min": 0.4}, "lys": {"min": 1.0}, "fibre": {"max": 5}}',
   '{"farine_larves": 0.15, "manioc": 0.10, "cajou": 0.03, "cacao": 0, "paille": 0, "tourteau_coton": 0.05, "son_ble": 0.10}', 0.12),
  ('pondeuse',
   '{"pb": {"min": 16}, "em": {"min": 2750}, "ca": {"min": 3.5, "max": 4.2}, "p": {"min": 0.35}, "lys": {"min": 0.75}, "fibre": {"max": 6}}',
   '{"farine_larves": 0.12, "manioc": 0.10, "cajou": 0.03, "cacao": 0, "paille": 0, "tourteau_coton": 0.05}', 0.115),
  ('porc_croissance',
   '{"pb": {"min": 16}, "em": {"min": 2900}, "ca": {"min": 0.6, "max": 0.9}, "p": {"min": 0.5}, "lys": {"min": 0.9}, "fibre": {"max": 7}}',
   '{"farine_larves": 0.10, "manioc": 0.15, "cajou": 0.05, "cacao": 0.02, "paille": 0, "tourteau_coton": 0.05}', 2.2),
  ('tilapia',
   '{"pb": {"min": 30}, "em": {"min": 2700}, "ca": {"min": 0.6}, "p": {"min": 0.7}, "lys": {"min": 1.4}, "fibre": {"max": 8}}',
   '{"farine_larves": 0.20, "farine_poisson": 0.20, "manioc": 0.10, "cajou": 0.03, "cacao": 0, "paille": 0, "tourteau_coton": 0.10}', 0.03),
  ('bovin_embouche',
   '{"pb": {"min": 12}, "em": {"min": 2300}, "ca": {"min": 0.4, "max": 0.9}, "p": {"min": 0.3}, "fibre": {"min": 15}}',
   '{"farine_larves": 0, "farine_poisson": 0, "manioc": 0.40, "cajou": 0.20, "cacao": 0.15, "tourteau_coton": 0.25}', 8),
  ('ovin_embouche',
   '{"pb": {"min": 13}, "em": {"min": 2300}, "ca": {"min": 0.4, "max": 0.9}, "p": {"min": 0.3}, "fibre": {"min": 15}}',
   '{"farine_larves": 0, "farine_poisson": 0, "manioc": 0.35, "cajou": 0.15, "cacao": 0.10, "tourteau_coton": 0.20}', 1.2);
