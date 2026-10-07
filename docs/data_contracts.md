# Donn?es du FX desk

La pipeline principale exporte `source_docs.json`, `expectations.json`, `fx_reference.csv`, `summary.json` et `desk_report.md` par lancement.

- `SourceDoc` : identifiant stable du lien, fournisseur, date de publication avec fuseau, URL, texte extrait (plafonn? ? 24 000 caract?res).
- `DeskSignal` : pertinence FX, ton optionnel, justification, citations, taux annonc?s en pourcentage. Une ponctuation finale ajout?e par le mod?le peut ?tre retir?e seulement si le fragment restant est copi? de la source ; les mots ne sont pas corrig?s pour faire passer la validation.
- `Expectation` : ?v?nement, devise, date de publication pr?vue, date r?elle de collecte, source, pr?vision brute et pr?c?dent. Les taux pris en charge ont aussi une d?finition exacte et une valeur num?rique en pourcentage. La surprise est `(annonc? - attendu) * 100` en points de base.
- `fx_reference.csv` : date BCE, disponibilit? conventionnelle ? minuit UTC suivant, paires reconstruites comme `taux_quote_par_EUR / taux_base_par_EUR`. Une observation future est exclue ; les champs manquants ne sont pas remplis par des donn?es fictives.
- `summary.json` : configuration, march? courant, expositions, stress, sources et signaux, comparaisons, contexte pr?-publication/r?actions et incidents. Montants de risque en USD ?quivalents.

L'archive locale `data/cache/fx_desk/expectations.jsonl` est append-only et pr?serve la premi?re collecte de chaque r?vision observ?e. Le cache HTTP expire ; aucune r?ponse HTTP en erreur n'est enregistr?e comme donn?e valide. La collecte du calendrier courant n'est pas exhaustive, notamment au changement de semaine.

Les conventions suivantes concernent l'outil de recherche QIS / event studies, s?par? du lancement RSS.

# Contrats de données et conventions

## Prix : `market.csv` et `intraday.csv`

```csv
timestamp,EURUSD,USDJPY,SPX_USD,SX5E_EUR,US2Y,US10Y,VIX
2025-01-02T22:00:00Z,1.03,157,5800,4900,4.25,4.40,18
```

Exemple de format uniquement, valeurs illustratives. Timestamps explicites avec fuseau, uniques et croissants ; pas de cellules manquantes ou infinies. La table quotidienne contient au plus une observation par jour UTC. Chaque timestamp doit représenter la disponibilité réelle de l'observation, pas minuit artificiel avant la clôture.

Le format large exige un panel aligné. Pour des marchés aux horaires différents, appeler `event_reaction` séparément sur leurs séries propres ; ne pas utiliser une heure commune fictive pour une étude intraday. Les fonctions n'effectuent aucun remplissage rétroactif.

Les prix de backtest doivent être positifs. Préciser dans la provenance s'il s'agit de prix, prix ajustés ou indices total return. Une série de prix sans dividendes ne mesure pas un rendement total. L'univers est fixe ; une série du survivant actuel ne corrige pas le survivorship bias.

Métadonnées requises dans la configuration lors d'un import :

```json
"assets": {
  "SX5E_EUR": {"kind": "price", "source": "nom/source/date de collecte", "currency": "EUR"},
  "US2Y": {"kind": "yield_percent", "source": "nom/source/date de collecte", "currency": "USD"},
  "VIX": {"kind": "vol_index", "source": "nom/source/date de collecte", "currency": "USD"}
}
```

Définir chaque colonne. Les séries de taux contiennent des pourcentages (`4.25`), pas des décimales (`0.0425`). Les changements de taux sont en bp ; les changements du VIX sont en points. La volatilité des prix est annualisée sqrt(252), celle des variations de taux/VIX est un écart-type quotidien en bp/points.

## Cash : `cash.csv`

```csv
timestamp,annual_rate
2025-01-02T22:00:00Z,0.03
```

Même index que le panel de backtest. Taux annuel **décimal**, connu au timestamp de la ligne, dans la devise de reporting du portefeuille. Il rémunère l'intervalle suivant selon ACT/360. Les taux négatifs sont acceptés. La démo utilise un taux fictif de type money market, pas une série officielle €STR.

Pour reproduire un véritable indice €STR, il faudrait en plus modéliser précisément dates de référence/publication, calendrier TARGET et conventions de composition ; l'entrée actuelle est un taux de financement connu à la date considérée.

## Événements : `events.csv`

```csv
event_id,name,timestamp,currency,source,actual,consensus,unit
EXAMPLE_CPI,US CPI,2025-01-15T13:30:00Z,USD,fixture illustrative,0.3,0.2,percentage_points
```

Les champs numériques peuvent être vides. La surprise est `actual - consensus`, dans l'unité de la statistique ; un zéro est conservé. Fournir le consensus connu avant la publication et la première valeur publiée, pas une révision obtenue ultérieurement. Aucune reconstruction point-in-time automatique n'est fournie.

La réaction quotidienne part de la dernière clôture strictement antérieure à l'événement. `post_1_close` et `post_5_closes` désignent les première et cinquième clôtures observées après publication, et non exactement 24/120 heures. Les timestamps utilisés sont exportés. Le seuil de fraîcheur par défaut est quatre jours pour les points d'ancrage ; le calendrier est celui des observations fournies.

Une réaction intraday nécessite `intraday.csv` : dernier point avant la release et premier point au moins 60 minutes après, chacun à moins de cinq minutes de sa cible. Sans ces points, le résultat reste indisponible. Les résultats sont coupés à `as_of` ; les historiques comparables excluent les événements dont la fenêtre n'était pas encore terminée à la date interrogée.

## Provenance et limites

`summary.json` exporte configuration, instant de référence, métadonnées et SHA-256 des entrées. Les hashes établissent quelle version a été utilisée, pas la véracité ou la licence des données. Respecter les droits de redistribution avant de publier un dataset réel sur GitHub.
