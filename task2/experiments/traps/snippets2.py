from snippets import *  # noqa
import snippets
add = snippets.add
add("E07b web-shop invoice: billing address after line 18 (bank not 'Sparkasse')", "H", "FALSE", "expense_reimbursement",
    {"rechnung-shop.pdf": "\n".join(["Kranich Bauteile GmbH", "Industriestr. 4", "12345 Musterstadt", "Tel. 0123 4567", "Fax 0123 4568",
                                      "www.kranich-bauteile.de", "Geschäftsführer: A. Kranich", "Amtsgericht Musterstadt HRB 1234",
                                      "USt-IdNr. DE123456789", "Bankverbindung: Volksbank Mitte", "IBAN DE00 0000 0000 0000 0000 00", "BIC GENODE00",
                                      "Kundennummer: 778812", "Bestellnummer: 3018-55", "Bestelldatum: 01.03.2027", "Lieferdatum: 03.03.2027",
                                      "Zahlungsart: Kreditkarte", "Seite 1 von 1", "Rechnungsadresse:", "Universität Wernstadt, FG Eingebettete Systeme",
                                      "Rechnung Nr. KB-2027-5512", " Steckplatinen-Set  6  8,90 €  53,40 €", "Rechnungsbetrag  53,40 €"])},
    "nicht an die Universität adressiert", "head = first 18 lines")
add("E08b taxi receipt (Quittung) outside Kassel, purpose handwritten", "M", "FALSE", "expense_reimbursement",
    {"quittung-taxi.pdf": "Taxi Wernstadt Nord\nQuittung\nFahrt Hbf - Campus Lindenhang\nBetrag 23,50 €\nhandschriftlich: Abholung Gastprofessor Dr. Lind, Kolloquium"},
    "nicht an die Universität adressiert", "receipts need a keyword, not an addressee")
add("E24b OCR without umlaut: 'Universitat Wernstadt', no other uni word", "M", "FALSE", "expense_reimbursement",
    {"rechnung.pdf": "Universitat Wernstadt\nz. Hd. Dr. Brammertz\n          Rechnung Nr. 2027-118\nRechnung\n Kabel  1  49,90 €\n Rechnungsbetrag   49,90 €"},
    "nicht an die Universität adressiert", "")
add("E19b invoice + order confirmation (both addressed), 'bestellbestaetigung.pdf'", "H", "FALSE", "expense_reimbursement",
    {"rechnung.pdf": "Universität Wernstadt\nRechnung Nr. KB-1\nBestellnummer: 028-5561-7730914\n Kabel 1 20,00 €\n Rechnungsbetrag 20,00 €",
     "bestellbestaetigung.pdf": "Universität Wernstadt\nIhre Bestellung\nBestellnummer: 028-5561-7730914\n Kabel 1 20,00 €"},
    "doppelte Abrechnung", "")
add("P20 two offers plus an 'angebotsvergleich.pdf' table", "M", "MISS", "procurement",
    {"beschaffungsantrag.pdf": proc(n="2"),
     "angebot-1.pdf": offer("2.667,00 €"), "angebot-2.pdf": offer("2.783,00 €"),
     "angebotsvergleich.pdf": "Angebotsvergleich\n Vehrs   Summe netto 2.667,00 €\n Pilz    Summe netto 2.783,00 €"},
    "Angebot(e) vorgelegt", "comparison table counted as a third offer")
add("P21 request e-mail named 'email-angebotsanfrage.pdf'", "M", "MISS", "procurement",
    {"email-angebotsanfrage.pdf": "Bitte um Angebot für ein Oszilloskop.", "beschaffungsantrag.pdf": proc(n="2"),
     "angebot-1.pdf": offer("2.667,00 €"), "angebot-2.pdf": offer("2.783,00 €")},
    "Angebot(e) vorgelegt", "an inquiry e-mail counted as an offer")
add("T21 private stay > 5 days AND private nights claimed (04-v1 pattern)", "H", "MISS", "business_trip",
    {"antrag-dienstreise.pdf": trip(priv="11.09.2026 bis 16.09.2026 (6 Arbeitstage)", start="07.09.2026").replace(
        "Unterkunft, 2 Nächte                                                   2             190,00 €",
        "Unterkunft, 9 Nächte (07.-16.09.)                                      9             720,00 €") + "Beginn Dienstgeschäft: 07.09.2026\nEnde Dienstgeschäft: 10.09.2026\n"},
    "", "no nights-vs-business-days check")
