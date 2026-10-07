"""Human-readable FX desk report with explicit coverage and decision limitations."""


def _percent(value: float | None) -> str:
    return "N/D" if value is None else f"{value:+.2%}"


def render_report(report: dict) -> str:
    risk = report["risk"]
    lines = [
        "# Macro & FX Risk Desk",
        "",
        f"Collecte : {report['as_of']}",
        "",
        "Sources réelles ; portefeuille fictif. Cours BCE quotidiens de référence, pas des prix intraday exécutables.",
        "",
        f"Exposition brute : {risk['gross_usd']:,.0f} USD | Levier : {risk['leverage']:.2f} / {risk['leverage_limit']:.2f}",
        f"Dépassement de levier : {risk['leverage_breach']}. Drawdown : indisponible sans historique de NAV.",
        "",
        "## Marché au moment du rapport",
        "",
        "| Paire | Référence | Niveau | Variation 1j | Variation 5j | Vol. 20j annualisée | État |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for pair, context in report["market"].items():
        level = f"{context['level']:.5f}" if "level" in context else "N/D"
        lines.append(
            f"| {pair} | {context.get('reference_date', 'N/D')} | {level} | {_percent(context.get('return_1d'))} | {_percent(context.get('return_5d'))} | {_percent(context.get('realised_vol_20d'))} | {context['status']} |"
        )
    lines += ["", "## Communiqués → signaux → portefeuille", ""]
    for item in report["publications"]:
        lines += [
            f"### {item['provider']} — {item['title']}",
            f"Publié : {item['published_at']} — [source]({item['url']})",
            f"Extraction : {item['status']}",
            "",
        ]
        if item.get("signal"):
            lines += [
                item["signal"]["rationale"],
                "",
                f"Pertinent FX : {item['signal']['relevant_to_fx']}. Ton hawkish/dovish : {item['signal']['hawkishness']} (interprétation IA).",
            ]
            lines += [f"> {q}" for q in item["signal"]["evidence_quotes"]]
        for comparison in item["comparisons"]:
            expected = comparison["expected_percent"]
            surprise = comparison["surprise_bps"]
            lines.append(
                f"- {comparison['indicator']} : annoncé {comparison['announced_percent']} %, attendu {str(expected) + ' %' if expected is not None else 'N/D'}, surprise {str(surprise) + ' pb' if surprise is not None else 'N/D'} — {comparison['status']}."
            )
        lines += [f"- {alert}" for alert in item["alerts"]]
        for pair, move in item["reactions"].items():
            before = move["before"]
            lines.append(
                f"- {pair} : référence connue avant publication {before.get('reference_date', 'N/D')} ({before['status']}) ; réaction après 1 / 5 références : {_percent(move['post_1_reference_return'])} / {_percent(move['post_5_reference_return'])}."
            )
        lines.append("")
    lines += ["## Prochains événements sur les devises exposées", ""]
    lines += [
        f"- {e['event_at']} — {e['currency']} — {e['title']} ({e['impact']}) : attendu {e['forecast'] or 'N/D'}, précédent {e['previous'] or 'N/D'} ; prévision collectée {e['observed_at']}. [Source]({e['source']})"
        for e in report["upcoming"]
    ]
    if not report["upcoming"]:
        lines.append(
            "Aucun événement couvert dans la fenêtre ; cela ne garantit pas l'absence de risque."
        )
    lines += [
        "",
        "## Stress FX indicatifs",
        "",
        "| Devise | Choc | P&L USD approx. | % equity |",
        "|---|---:|---:|---:|",
    ]
    lines += [
        f"| {s['currency']} | {s['shock']:+.1%} | {s['pnl_usd_approx']:+,.0f} | {s['equity_fraction']:+.2%} |"
        for s in risk["scenarios"]
    ]
    lines += [
        "",
        "USD : choc opposé sur toutes les devises étrangères ; notionnels USD simplifiés, hors carry et coûts.",
        "",
        "## Couverture / limites",
        "",
        "- Annoncé/consensus : comparaison automatique des niveaux de taux Fed, refinancement BCE et BoE uniquement. CPI/NFP : calendrier et prévisions brutes, pas encore d'extraction des publications statistiques.",
        "- Une attente collectée après l'annonce n'est jamais utilisée pour calculer une surprise. Le précédent n'est pas le consensus.",
        "- Pydantic contrôle le format ; les citations sont vérifiées, mais les chiffres extraits par IA restent à contrôler dans le communiqué.",
        "- Les mouvements associés à une publication ne prouvent pas sa causalité. Aucune instruction d'achat/vente automatique.",
        "- Le flux RSS et le calendrier hebdomadaire ne constituent pas un historique exhaustif.",
    ]
    lines += [f"- {issue}" for issue in report["issues"]]
    return "\n".join(lines) + "\n"
