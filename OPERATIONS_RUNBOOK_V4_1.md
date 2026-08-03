# Runbook V4.1 — exploitation navigateur uniquement

## Déployer

1. Ouvrir GitHub Actions.
2. Lancer **Deploy production**.
3. Attendre la fin des tests et du déploiement.
4. Vérifier `/api/ready` puis `/api/release`.
5. Confirmer la version `4.1.1`, le commit et le hash du modèle.

## Préparer une campagne sans crédit

1. Ouvrir **Run evidence campaign**.
2. Choisir `dry_run`.
3. Choisir le stage 30 et la baseline souhaitée.
4. Conserver un plafond prudent.
5. Télécharger le plan et vérifier `execution_allowed`, la période, le stage et le budget estimé.

## Lancer ou reprendre une campagne payante

- `start_next_stage` démarre uniquement le prochain stage autorisé.
- `continue_current_stage` reprend uniquement la campagne exacte, avec le même stage, la même baseline, la même période et le même plafond.
- Saisir `EXECUTE_CAMPAIGN` pour un mode payant.
- Ne cocher `retry_uncertain_discovery` qu’après avoir vérifié la facturation fournisseur des appels marqués incertains.

La découverte écrit un checkpoint après chaque appel facturable. Une reprise peut donc continuer avant même que le plan de backfill ait été créé.

## Lire le verdict

- `PASS` : les contrôles techniques, de couverture, de matching, de baseline et de stage sont satisfaits. Une revue humaine reste obligatoire.
- `HOLD` : campagne incomplète ou preuve insuffisante. Continuer ou corriger sans passer au stage suivant.
- `FAIL` : fuite temporelle, doublon, collision de matching ou dépassement du plafond. Arrêter et corriger avant tout nouvel appel.

## Incidents

### Checkpoint incompatible

Ne pas forcer la restauration. Vérifier la version, le `campaign_key`, le commit, le stage, la baseline, la période et le plafond.

### Appel de découverte incertain

Comparer le journal de crédits avec le tableau fournisseur. Rejouer seulement avec l’option explicite après confirmation.

### Railway répond mais n’est pas prêt

`/api/health` prouve seulement que le processus vit. Utiliser `/api/ready` pour la base, les modèles et les dépendances nécessaires.

### Conflit de déploiement

Les workflows modifiant la production partagent le groupe `production-change`. Ne pas annuler ce verrou pour accélérer une opération.

## Règles responsables

- aucune connexion à un compte bookmaker ;
- aucun pari automatique ;
- aucune recommandation de mise ;
- aucune promotion automatique de modèle ;
- aucune affirmation de rentabilité à partir d’un petit échantillon.

## Incident backup ou healthcheck V4.1.1

- `Healthcheck failure` sans logs applicatifs : confirmer que la version déployée est au moins `4.1.1`; `/api/ready` doit être joignable sans connexion.
- `invalid literal for int() with base 10: ''` : le secret de base contient un port vide. Créer `DATABASE_PUBLIC_URL` dans GitHub avec l’URL publique Railway résolue et relancer le backup.
- Une URL se terminant par `.railway.internal` fonctionne dans Railway, mais pas depuis un runner GitHub hébergé.
