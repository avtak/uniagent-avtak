"""Rule cards (round R12): the university's rules, quoted from its own pages.

Every rule names its source page (full text in the University of Kassel policy pages (not included here),
inventory with exact quotes in the development notes (not included)). Nothing is
added that a page or the task's README does not say. Decision 12: what a page
only recommends is not a reason to reject.

FOCUS is the checklist in the system prompt; POLICIES is the shared rule text
in the evidence (lookup_policy).
"""

GENERAL = (
    "Allgemein: Geschwärzte oder ersetzte Namen "
    "(Pseudonymisierung) entscheiden "
    "nie. Fälle anderer Hochschulen (z. B. TH Sallstedt) werden ausschließlich nach den Belegen "
    "entschieden: Es gelten die Grenzen und Vorgaben, die in den Unterlagen dieser Hochschule selbst "
    "stehen (Formular, Merkblatt, Hinweis der Einkaufs- oder Reisekostenstelle). Die Kasseler Zahlen "
    "und Rahmenverträge dieser Karte gelten nur für Fälle der Universität Kassel bzw. Wernstadt. "
    "Enthält ein Antrag eine nicht erstattungsfähige Position oder fehlt ein verlangter Nachweis, ist "
    "er so nicht genehmigungsfähig und geht zur Korrektur zurück."
)

FOCUS = {
    "business_trip": (
        "Prüfe jeden Punkt anhand der Belege (Quellen: Seite 'Dienstreisemanagement', HRKG):\n"
        "1. Genehmigung vorher: Reisekosten werden nur erstattet, wenn die Reise vorher angeordnet "
        "oder genehmigt ist. Ein Antrag nach Reisebeginn ist abzulehnen; eine nachträgliche "
        "Genehmigung geht nur über einen gesonderten Antrag.\n"
        "2. Antrag vollständig und widerspruchsfrei: Zweck (Einladung/Programm), Ort, Hin- und "
        "Rückreise, Daten. Ein Antrag wird VOR der Reise gestellt: Buchungsbestätigungen genügen, "
        "Hotel- oder Fahrkartenrechnungen können noch fehlen und sind dann kein Ablehnungsgrund.\n"
        "3. Ausland: Feld 'Reise ins Ausland' ausgefüllt. Die A1-Bescheinigung (EU, EWR, Schweiz, "
        "Abkommensstaaten) beantragt die Dienstreisesachbearbeitung selbst; es wird empfohlen, "
        "Auslandsreisen spätestens acht Wochen vor Beginn zu beantragen. Dienstreisen in die Russische Föderation, die Ukraine, nach Belarus, in die "
        "an die Ukraine grenzenden Gebiete Moldaus, nach Niger, Iran, Israel, in die Palästinensischen "
        "Gebiete und in den Libanon werden bis auf Weiteres nicht genehmigt.\n"
        "4. Übernachtung im Inland bis 80,00 € je Nacht; mehr nur mit schriftlicher Begründung der "
        "Notwendigkeit im Antrag. Im Ausland bis zum Betrag der Auslandsreisekostenverordnung.\n"
        "5. Privater Aufenthalt: bis 5 Arbeitstage wird abgerechnet, als habe nur die Dienstreise "
        "stattgefunden; über 5 Arbeitstage nur die dienstlich veranlassten Mehrkosten. Private "
        "Nächte und Mehrpreise müssen getrennt und selbst getragen sein.\n"
        "6. Flug: dem Antrag ist ein Preisvergleich beizufügen; Inlandsflug nur, wenn Alternativen "
        "teurer sind oder viel Arbeitszeit sparen; nur Economy. Bahn: nächsthöhere Klasse bei mehr als "
        "zwei Stunden einfacher Fahrt, bei sonstigen triftigen Gründen oder einem Grad der Behinderung "
        "von mindestens 50; eine private BahnCard ist einzusetzen. Taxi und Mietwagen ohne triftigen "
        "Grund höchstens bis zu den Kosten von Bus oder Bahn. Privates Kraftfahrzeug im Inland: 0,21 € je "
        "Kilometer, 0,35 € bei triftigen Gründen und vorheriger Genehmigung; Parkgebühren nur dann. Im "
        "Ausland 0,20 € je Kilometer, höchstens 130,00 €.\n"
        "7. Leistungen Dritter (z. B. Stipendium für dieselbe Reise) sind anzugeben und anzurechnen. "
        "Drittmittel, die die Universität selbst verwaltet, sind KEINE Leistungen Dritter. Reisen aus "
        "Drittmitteln unterliegen grundsätzlich den gleichen Regelungen wie Reisen aus Landesmitteln; "
        "abweichende Erstattungsregeln des Drittmittelgebers gelten nur, wenn sie dem Antrag in Kopie "
        "beigefügt sind.\n"
        "8. Begleit- und Abendprogramme (z. B. Conference Dinner) sind grundsätzlich nicht "
        "erstattungsfähig.\n"
        "9. Online-Konferenzen sind keine Dienstreisen.\n"
        "10. Honorare sind von Leistungen Dritter zu unterscheiden. Wird im Rahmen der Reise ein "
        "Honorar (z. B. für einen Vortrag) gezahlt, deutet das auf eine Nebentätigkeit und eine privat "
        "veranlasste Reise hin; eine Dienstreisegenehmigung und Reisekostenabrechnung aus Landes- oder "
        "Drittmitteln ist dann grundsätzlich nicht möglich.\n"
        "11. Die Anschaffungskosten einer privaten BahnCard werden nur erstattet, wenn sie sich durch "
        "Dienstreisen vollständig amortisiert haben, nicht vorab und nicht anteilig.\n"
        "12. Reisekosten (Fahrkarten, Übernachtungen), die für mehrere Personen verauslagt wurden, werden "
        "nur anteilig erstattet: Jede Person fordert ihren Anteil selbst an.\n"
        "13. Verpflegungskosten für Mittag- und Abendessen auf Rechnungen werden nur erstattet, wenn es "
        "sich nachweislich um eine notwendige Pauschale handelt (Tagungspauschale); sonst sind sie mit "
        "dem Tagegeld abgegolten.\n"
        "14. Nicht erstattungsfähig sind CO2-Kompensationen, selbst verauslagte Impf- und Arztkosten und "
        "eine Auslandskrankenversicherung."
    ),
    "expense_reimbursement": (
        "Prüfe jeden Punkt anhand der Belege (Quelle: Seite 'Finanzbuchhaltung und Steuern', "
        "Abschnitte Kostenerstattung und Bewirtungskostenrichtlinie):\n"
        "1. Echter Zahlungsbeleg (Originalquittung oder bezahlte Rechnung). Eine Pro-forma-Rechnung, "
        "ein Angebot oder ein Warenkorb genügt nicht.\n"
        "2. Dienstlicher Bezug: Rechnung an die Universität oder eine Einrichtung, oder bei einer "
        "Quittung ohne Artikelangabe ein handschriftliches Stichwort zum Zweck. Eine Rechnung an eine "
        "Privatperson ohne jeden dienstlichen Vermerk ist nicht erstattungsfähig.\n"
        "3. Dieselbe Bestellung darf nur einmal abgerechnet werden (gleiche Bestellnummer, gleiche "
        "Positionen).\n"
        "4. Gutschriften und Stornos sind abzuziehen; erstattet wird nur der tatsächliche Saldo.\n"
        "5. Nicht erstattungsfähig sind Bewirtungen ohne externe Personen und Arbeitsessen, d. h. "
        "Bewirtungen aus dienstlichem Interesse mit überwiegend Universitätsangehörigen; erstattet wird "
        "nur bei einem angemessenen Verhältnis von externen und internen Teilnehmern. Feiern, Trinkgeld "
        "und Pfand sind nicht erstattungsfähig. Kaffee, Tee, Wasser, Obst und Gebäck für Gäste der Universität sind "
        "erstattungsfähig. Bewirtung von Gästen braucht Anlass, Teilnehmerliste und eine an die "
        "Universität ausgestellte Rechnung mit genauer Bezeichnung. Höchstbeträge: Veranstaltungen 60,00 € "
        "je Person und Veranstaltungstag; Berufungsverfahren 280,00 € insgesamt; Absolventenfeier 20,00 € "
        "je Absolvent/in; Ehrungen, Promotions- und Habilitationsfeiern 150,00 € und Antrittsvorlesung "
        "200,00 € je Veranstaltung.\n"
        "6. Teilnahmegebühren für Online-Konferenzen werden als privat verauslagte Kosten erstattet.\n"
        "7. Nicht erstattungsfähig sind außerdem Geschenke an Bedienstete der eigenen Einrichtung, "
        "Bewirtungen von Begleitpersonen, gesellige Veranstaltungen (Betriebsausflug, Verabschiedung, "
        "Weihnachts- oder Geburtstagsfeier) und Dekorationsartikel; Gastgeschenke bei Dienstreisen bis "
        "30,00 €.\n"
        "8. Reisekosten (Fahrkarten, Übernachtungen), die für mehrere Personen verauslagt wurden, werden "
        "nur anteilig erstattet: Jede Person fordert ihren Anteil selbst an. Für Bewirtungen gilt Punkt 5.\n"
        "9. Nicht erstattungsfähig sind selbst verauslagte Impf- und Arztkosten und CO2-Kompensationen."
    ),
    "procurement": (
        "Prüfe jeden Punkt anhand der Belege (Quellen: Seiten 'Beschaffung', 'Rahmenverträge', "
        "'Nachhaltiges Catering'):\n"
        "1. Unter 1.000 € Auftragswert (netto) ist eine Direktvergabe mit einem Angebot zulässig; "
        "dann sind keine Vergleichsangebote nötig.\n"
        "2. Ab 1.000 € netto müssen grundsätzlich drei Angebote eingeholt werden; Ausnahme: "
        "Bestellung beim Rahmenvertragspartner. Kommt nur ein Anbieter in Frage, ist schriftlich "
        "festzuhalten, warum der Auftrag nicht anderweitig vergeben werden kann. Beschaffungen aus "
        "Drittmitteln unterliegen den gleichen Regeln; macht der Drittmittelgeber eigene Vorgaben, "
        "gelten immer die strengeren.\n"
        "3. Rahmenverträge bestehen u. a. für Büromaterial, PCs/Notebooks, Docking-Stations und "
        "Monitore, Büropapiere, Bürodrehstühle, Seminarstühle, Büromobiliar, Kopier- und "
        "Multifunktionsgeräte, Microsoft-Software, Flaschengase, Helium (Rahmenvertrag 01.05. bis "
        "31.07.2026) und flüssigen Stickstoff. Solche Produkte sind ausschließlich beim Rahmenvertragspartner zu "
        "bestellen, unabhängig vom Betrag. Ein WPS-Warenkorb aus einem als Rahmenvertrag bezeichneten "
        "Katalog gilt als Bestellung beim Rahmenvertragspartner.\n"
        "4. Das wirtschaftlichste, in der Regel günstigste Angebot bei gleicher technischer Eignung "
        "erhält den Zuschlag.\n"
        "5. Beträge in Antrag, Angeboten und Vergabevermerk müssen übereinstimmen; nur wesentliche "
        "Abweichungen zählen.\n"
        "6. Bestellungen müssen von der/dem Kostenstellenbevollmächtigten (meist Fachgebietsleitung) "
        "beauftragt sein.\n"
        "7. Nur falls Rechnungen vorliegen: sie müssen dem beauftragten Angebot entsprechen. Ein "
        "Beschaffungsantrag wird vor der Bestellung gestellt; eine fehlende Rechnung ist kein "
        "Ablehnungsgrund.\n"
        "8. Ab 50.000 € netto ist ein Leistungsverzeichnis als Grundlage eines förmlichen "
        "Vergabeverfahrens zu erstellen; ab 200.000 € einschließlich Mehrwertsteuer ist ein "
        "Großgeräteverfahren einzuleiten."
    ),
}

POLICIES = {
    "business_trip": {
        "advance_approval": "Reisekosten können nur für Dienstreisen erstattet werden, die vorher angeordnet oder genehmigt sind; nachträglich nur über einen gesonderten Antrag. (Dienstreisemanagement; HRKG)",
        "foreign_travel": "A1-Bescheinigung für Tätigkeit innerhalb der EU, des EWR, der Schweiz oder in Abkommensstaaten; Genehmigung spätestens acht Wochen vor Beginn wird empfohlen. (Dienstreisemanagement)",
        "hotel_costs": "Nachgewiesene Übernachtungskosten bis 80,00 € je Nacht; mehr nur mit schriftlicher Begründung; ohne Nachweis 20,00 € pauschal. Ausland: bis zum ARV-Betrag. Bei der Abrechnung nach der Reise: Rechnungen nur mit der Universität als Adressat; im Antrag vor der Reise genügen Buchungsbestätigungen. (Dienstreisemanagement)",
        "private_extension": "Privataufenthalt bis 5 Arbeitstage: Abrechnung, als habe nur die Dienstreise stattgefunden; über 5 Arbeitstage: nur zusätzliche, dienstlich notwendige Kosten. (Dienstreisemanagement; HRKG § 14)",
        "flights": "Bei Flugreisen ist dem Antrag ein Preisvergleich beizufügen; Inlandsflüge nur bei höheren Kosten anderer Verkehrsmittel oder erheblicher Zeitersparnis; nur Economy. (Dienstreisemanagement)",
        "third_party": "Leistungen von dritter Seite für dieselbe Dienstreise (z. B. ein Stipendium) sind anzugeben und anzurechnen, sonst liegt eine Doppelfinanzierung vor; von der Universität verwaltete Drittmittel gelten nicht als Leistungen Dritter. (HRKG § 4; Dienstreisemanagement)",
        "evening_programmes": "Kosten für Begleit- und Abendprogramme (z. B. Conference Dinner) sind grundsätzlich nicht erstattungsfähig. (Antwort der Reisekostenstelle)",
        "online_conferences": "Online durchgeführte Konferenzen und Tagungen sind keine Dienstreisen; Gebühren über das Formular für privat verauslagte Kosten. (Dienstreisemanagement)",
        "settlement_deadline": "Die Reisekostenabrechnung ist innerhalb von sechs Monaten nach Reiseende einzureichen; das betrifft die Abrechnung, nicht den Antrag. (HRKG; Dienstreisemanagement)",
    },
    "expense_reimbursement": {
        "receipt": "Erstattungsformular mit Originalquittung (Kassenbon, Beleg oder bezahlte Rechnung); ist auf der Quittung kein Artikel ausgewiesen, muss ein Stichwort dazugeschrieben werden. (Finanzbuchhaltung und Steuern)",
        "business_reference": "Rechnung an die Universität oder eine Einrichtung, oder dienstlicher Vermerk auf dem Beleg; Rechnung an eine Privatperson ohne Vermerk ist nicht erstattungsfähig.",
        "proforma": "Eine Pro-forma-Rechnung ist keine Rechnung und kein Zahlungsbeleg.",
        "duplicates_and_credits": "Dieselbe Bestellung wird nur einmal erstattet; Gutschriften und Stornos werden abgezogen.",
        "hospitality": "Nicht erstattungsfähig: Bewirtung ohne externe Personen, Arbeitsessen mit überwiegend Universitätsangehörigen, Trinkgeld und Pfand. Gästebewirtung: Anlass, Teilnehmerliste, Rechnung an die Universität mit genauer Bezeichnung. (Bewirtungskostenrichtlinie, Finanzbuchhaltung und Steuern)",
        "foreign_currency": "Bei Zahlung in Fremdwährung belegt ein Zahlungsnachweis (z. B. Kreditkartenabrechnung) den Euro-Betrag.",
    },
    "procurement": {
        "direct_award": "Die Pflicht zu drei Vergleichsangeboten entfällt, wenn der Auftragswert unter 1.000 Euro liegt, da dann eine Direktvergabe möglich ist. (Nachhaltiges Catering, Verweis auf die Beschaffungsordnung)",
        "three_offers": "Grundsätzlich müssen 3 Angebote eingeholt werden, Ausnahme bei Rahmenvertragspartnern. (Beschaffung)",
        "framework_contracts": "Rahmenverträge u. a. für Büromaterial, PCs/Notebooks und Monitore, Büropapiere, Bürodrehstühle, Seminarstühle, Büromobiliar, Kopiergeräte, Microsoft-Software. Ein solches Produkt ist ausschließlich beim Rahmenvertragspartner zu bestellen; dafür sind keine Vergleichsangebote nötig. Bestellung über WPS. (Rahmenverträge; Beschaffung)",
        "cost_centre": "Bestellungen müssen vom Kostenstellenbevollmächtigten (meist Fachgebietsleitung) beauftragt werden. (Beschaffung)",
        "cheapest_offer": "Zuschlag für das wirtschaftlichste (günstigste) Angebot bei gleicher technischer Eignung. (Vergabevermerk-Formular)",
        "consistency": "Beträge in Antrag, Angeboten, Vergabevermerk und Rechnungen müssen übereinstimmen; nur wesentliche Abweichungen zählen. (Aufgaben-README)",
        "third_party_funds": "Die Beschaffung aus Drittmitteln unterliegt grundsätzlich den gleichen Regeln wie die Beschaffung aus Landesmitteln; macht ein Drittmittelgeber eigene Vorgaben, gelten immer die strengeren Regelungen. (Glossar Drittmittelbewirtschaftung)",
    },
}
