# Macro & Market Intelligence Pipeline

**Official macro releases, market expectations and FX risk in one auditable Python pipeline.**

Macro & Market Intelligence Pipeline est un projet personnel orienté Global Markets qui transforme des publications macroéconomiques publiques en informations exploitables pour le suivi d'un portefeuille FX fictif. La pipeline collecte les communiqués officiels de banques centrales, structure les faits avec un LLM et Pydantic, compare les annonces aux attentes disponibles avant publication, mesure le contexte de marché et relie chaque événement aux expositions et scénarios de risque du portefeuille.

Le projet privilégie la traçabilité : chaque signal conserve sa source et ses citations, une prévision récupérée après l'annonce n'est jamais présentée comme un consensus antérieur, et une donnée indisponible reste explicitement indisponible. Il s'agit d'un outil d'aide à l'analyse de desk, sans exécution automatique de transactions.

## Ce que fait le projet

```text
RSS Fed / BCE / BoE ──→ publications officielles ──→ extraction LLM + Pydantic
                                                               │
Calendrier public ──→ attentes datées ──→ annoncé / attendu ────┤
                                                               ▼
Cours FX BCE ──→ contexte de marché ──→ portefeuille ──→ risque et alertes
                                                               │
                                                               ▼
                                                rapport Markdown + audit JSON
```

La pipeline principale :

1. récupère les publications présentes dans les RSS officiels de la Fed, de la BCE et de la BoE ;
2. télécharge le texte de chaque publication sélectionnée ;
3. extrait les faits macro pertinents, les niveaux de taux et leurs citations dans un schéma Pydantic strict ;
4. archive les attentes du calendrier avec leur date réelle de collecte ;
5. compare un taux annoncé à une attente connue avant la publication ;
6. récupère les cours de référence FX quotidiens de la BCE ;
7. calcule expositions, levier et stress du portefeuille ;
8. relie les événements aux devises exposées et produit un rapport auditable.

## Lancer dans VS Code

Python 3.11 ou plus récent est requis. Le projet est testé sous Python 3.13.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev,llm]"
.\.venv\Scripts\python.exe -m scripts.run_markets_lab
```

`scripts.run_markets_lab` est l'entrée compatible ; elle appelle la pipeline réelle de `scripts.run_fx_copilot`.

Renseigner `LLM_API_KEY`, `LLM_BASE_URL` et `LLM_MODEL` à partir de `.env.example` dans un fichier `.env` privé. Les RSS, le calendrier et les cours BCE ne demandent pas de clé payante. L'extraction OpenAI utilise l'API et peut être facturée.

Pour collecter les vraies données publiques sans appel OpenAI :

```powershell
.\.venv\Scripts\python.exe -m scripts.run_markets_lab --no-llm
```

Ce mode produit les documents, le calendrier, le contexte FX et le risque. Il ne produit pas d'interprétation macro ni d'alerte fondée sur cette interprétation.

## Sorties

Chaque lancement crée un dossier horodaté dans `reports/fx_desk/` :

| Fichier | Contenu |
|---|---|
| `desk_report.md` | Synthèse lisible de type desk |
| `summary.json` | Résultats structurés, risque, signaux et incidents |
| `source_docs.json` | Publications officielles réellement utilisées |
| `expectations.json` | Prévisions disponibles et dates de collecte |
| `fx_reference.csv` | Références FX BCE utilisées dans l'analyse |

Les réponses HTTP et extractions validées sont mises en cache dans `data/cache/`, exclu de Git. Par défaut, un lancement autorise trois nouveaux appels IA maximum, sans nouvelle tentative automatique.

## Annoncé contre attendu

La comparaison numérique automatique couvre actuellement :

- la borne supérieure du taux des Fed Funds ;
- le taux de refinancement principal de la BCE ;
- le Bank Rate de la BoE.

La surprise vaut `(annoncé - attendu) × 100` en points de base. L'attente doit concerner exactement le même indicateur et avoir été collectée avant l'événement et avant la publication analysée. Une prévision collectée trop tard est rejetée ; la valeur précédente n'est jamais assimilée au consensus.

CPI et NFP peuvent apparaître dans le calendrier avec leurs prévisions brutes, mais l'extraction de leurs publications statistiques officielles reste une évolution à réaliser. L'historique des attentes se construit lors des lancements successifs : le projet ne fabrique pas de consensus historique.

## Portefeuille et risque

Le portefeuille de démonstration se trouve dans `data/portfolio_demo.json`. Il est fictif, même lorsque les données macro et FX sont réelles.

Le moteur calcule :

- l'exposition nette par devise en notionnels USD équivalents ;
- l'exposition brute et le levier ;
- les dépassements de limite de levier ;
- des chocs indicatifs de plus ou moins 2 % par devise ;
- le P&L approximatif et son poids dans l'equity ;
- les variations FX sur une et cinq observations et la volatilité réalisée sur vingt observations.

Le drawdown reste indisponible sans historique de NAV. Les stress sont statiques et n'intègrent ni carry ni coûts de transaction.

## Limites importantes

- Les cours BCE sont des références quotidiennes, pas des cotations intraday exécutables.
- Les mouvements après publication indiquent une association temporelle, pas une causalité.
- Pydantic contrôle la structure. Les citations sont vérifiées dans le texte, mais l'interprétation économique reste à contrôler.
- La couverture des RSS et du calendrier n'est pas exhaustive. Une panne produit une donnée manquante, jamais une valeur synthétique.
- Le système propose des alertes à examiner ; il ne prend pas de décision de trading et ne passe aucun ordre.
- Le portefeuille utilise actuellement des notionnels USD équivalents simplifiés.

## Module QIS séparé

Le moteur de recherche systématique est conservé séparément. Il comprend momentum, volatility targeting, lag d'exécution, cash, coûts, turnover, benchmark, statistiques de performance et génération d'une méthodologie d'indice.

```powershell
.\.venv\Scripts\python.exe -m scripts.run_qis_lab
```

Cette commande utilise une démonstration synthétique explicitement identifiée et écrit dans `reports/qis_lab/`. Les résultats ne constituent pas une performance historique. Le module options a été retiré du projet actuel.

## Vérification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src scripts tests
```

Voir également [l'architecture](docs/architecture.md) et [les contrats de données](docs/data_contracts.md).

Sources publiques : [RSS Fed](https://www.federalreserve.gov/feeds/press_monetary.xml), [RSS BCE](https://www.ecb.europa.eu/rss/press.html), [RSS BoE](https://www.bankofengland.co.uk/rss/news), [références FX BCE](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html) et [calendrier public](https://www.forexfactory.com/calendar).
