# Architecture : macro vers portefeuille FX

## Chemin principal

```text
RSS officiels -> textes SourceDoc -> DeskSignal Pydantic + citations
                                         |
Calendrier gratuit -> attentes dat?es ----+-> comparaison annonc?/attendu
                                         |
R?f?rences FX BCE -> contexte dat? -------+-> expositions, stress, alertes de revue
                                         |
                                         +-> rapport + sources + audit local
```

`run_markets_lab` appelle `run_fx_copilot`. La pipeline principale ne d?pend pas des g?n?rateurs synth?tiques, du QIS, des options ou de Trading Economics.

| Responsabilit? | Emplacement |
|---|---|
| RSS, texte des articles, HTTP cache, attentes et FX | `src/data_sources/desk_sources.py` |
| Extraction structur?e, cache IA, v?rification des citations, comparaison | `src/copilot/desk.py` |
| Orchestration et budget | `src/copilot/fx_pipeline.py` |
| Contexte FX et stress par devise | `src/analytics/fx_desk.py` |
| Mod?les portefeuille et expositions conserv?s | `src/portfolio/` |
| Rapport desk | `src/reporting/fx_desk.py` |
| Recherche QIS ind?pendante | `src/strategies/`, `scripts/run_qis_lab.py` |

## R?utilisation et corrections

Les mod?les SourceDoc/portefeuille, les calculs d'exposition et le moteur QIS restent utilis?s. Les anciens MacroSignal et scripts daily restent compatibles. DeskSignal distingue explicitement ton interpr?t? et faits annonc?s ; la surprise provient d'une comparaison d?terministe, pas d'un score invent? par l'IA.

Le chemin principal corrige la collecte limit?e aux r?sum?s RSS, le budget IA non plafonn?, l'absence de cache et l'arr?t global lorsqu'un fournisseur ?choue. Les sources passent ? tour de r?le dans l'extraction. Les r?ponses invalides et les donn?es absentes ne deviennent pas des valeurs neutres artificielles.

Les variantes daily historiques restent une dette technique : leur migration peut se faire ensuite vers l'orchestrateur commun. Les conventions financi?res restent simplifi?es et ne pr?tendent pas r?pliquer un syst?me bancaire de production.

## Horodatage

Publication officielle, collecte de pr?vision et disponibilit? du march? sont des notions distinctes. Une pr?vision doit ?tre connue avant l'heure de l'?v?nement ET avant la publication utilis?e. Chaque r?vision du consensus re?oit une nouvelle date de collecte ; aucune r?vision n'est antidat?e. Cette archive se construit lors des lancements manuels, sans reconstitution magique des attentes pass?es.

Les snapshots de documents et de march? utilis?s sont export?s par ex?cution. Le XML historique t?l?charg? aujourd'hui ne garantit pas que toutes ses anciennes valeurs sont celles disponibles ? l'?poque : la pipeline ne pr?tend pas ?tre une base historique totalement point-in-time.

## ?volution pertinente

1. Int?grer les publications officielles BLS CPI/NFP avec p?riode, unit? et premi?re publication ; relier exactement chaque chiffre au consensus dat?.
2. ?valuer les extractions sur un petit corpus annot? : exactitude des chiffres, pertinence FX, citations et faux positifs d'alerte.
3. Am?liorer le portefeuille : quantit?s en devises, valorisation USD, carry, co?ts et historique de NAV pour le drawdown.
4. ?tudier hors ?chantillon une r?gle transparente de r?duction du risque avant ?v?nement, compar?e ? un portefeuille sans filtre macro, avec co?ts et historique d'attentes acquis avant annonce.

En entretien, les preuves les plus utiles seront la tra?abilit? d'une alerte r?elle, l'absence d'anticipation dans les comparaisons, le lien quantifi? exposition/stress et une ?valuation hors ?chantillon du filtre de risque.
