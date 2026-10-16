# DonoFlow — Report di collaudo

**Data:** 30 settembre 2026 · **Versione testata:** `donoflow-migliorato` (con il refactoring di luglio)
**Esito:** 24 problemi corretti (più 3 minori) e verificati con test automatici e nel browser; 5 punti restano come raccomandazioni (§ 4).

---

## 1. Come è stato testato

| Livello | Cosa | Risultato finale |
|---|---|---|
| Test automatici Django | Regole di prenotazione, transizioni di stato, standby, moduli, permessi | **45 test, tutti verdi** (erano 8) |
| Browser (Playwright/Chromium) | Percorsi completi di donatore, operatore e admin + 3 profili smartphone | **42 controlli, tutti verdi** |
| Revisione indipendente | Un secondo revisore ha riletto le correzioni cercando regressioni | 4 problemi confermati + 3 plausibili → tutti corretti |
| Prestazioni | Numero di query per pagina al crescere degli slot | Vedi § 4 |

Le prove sono state fatte su un database pulito generato con `seed_demo`, senza credenziali reali; le email restano simulate in console.

---

## 2. Problemi trovati e corretti

### 🔴 Critici — dati errati o incoerenti

| # | Problema | Effetto concreto | Correzione |
|---|---|---|---|
| 1 | Prenotazione ammessa su raccolte **annullate, chiuse, in bozza o già passate** | Donatori convocati a giornate inesistenti | Unica regola `DonationSession.accepts_bookings` applicata in `book_slot` |
| 2 | Prenotare/annullare **riapriva** una raccolta chiusa; generare gli slot **pubblicava** una bozza | Raccolte chiuse dall'admin tornavano prenotabili da sole | `update_session_status` alterna solo OPEN ↔ FULL |
| 3 | Un donatore poteva prenotare **più slot nella stessa giornata** | Un solo utente poteva occupare l'intera raccolta | Massimo una prenotazione attiva per donatore e raccolta |
| 4 | Lo stesso slot poteva essere **assegnato a due sostituti**; si poteva accettare un'offerta già chiusa o scaduta | Il primo sostituto riceveva "posto confermato" e veniva poi rimpiazzato senza saperlo | Offerte accettabili solo se inviate e non scadute; assegnazione solo di offerte accettate |
| 5 | Si poteva **annullare una donazione già completata** (lo slot tornava libero) | Storico e statistiche falsati | Guardie di stato su annullamento, check-in, no-show ed esiti |
| 6 | Il **check-in riattivava** prenotazioni annullate | Slot mostrato "libero" ma impossibile da prenotare | Come sopra |
| 7 | **Doppio click su no-show** = doppia penalità (affidabilità 80 → 60) | Donatori penalizzati ingiustamente | Il no-show si registra una volta sola |
| 8 | **Campi data vuoti nei moduli**: `<input type=date>` riceveva "09/10/2026" invece di "2026-10-09" | Impossibile salvare una raccolta senza reinserire la data; la **data di nascita del donatore veniva cancellata** a ogni salvataggio del profilo | Widget con formato ISO in tutti i moduli |
| 9 | "Conferma" dell'operatore su una prenotazione annullata poteva **sovrascrivere una donazione completata** o dare al donatore due prenotazioni *(trovato dal revisore)* | Perdita di dati | Ripristino consentito solo se lo slot è libero e il donatore non ha altre prenotazioni |
| 10 | Un donatore **già arrivato** poteva essere sostituito dallo standby *(trovato dal revisore)* | Due persone per lo stesso posto | Il check-in chiude le offerte aperte e blocca la sostituzione |

### 🟠 Importanti — regole di dominio e sicurezza

| # | Problema | Correzione |
|---|---|---|
| 11 | Nessun controllo sull'**intervallo minimo tra donazioni** | Blocco configurabile per tipo (90 gg sangue intero, 14 plasma/piastrine) in `DONOFLOW_MIN_DONATION_INTERVAL_DAYS`. **Da validare con il direttore sanitario.** |
| 12 | Password "1" accettata (validatori disattivati) | Validatori Django attivi (min. 8 caratteri, no password comuni o solo numeriche) |
| 13 | Registrazione con **email già usata** | Email unica in registrazione e nel profilo |
| 14 | Scheda pubblica visibile per le raccolte **in bozza** | 404 per il pubblico, visibile a operatori e admin |
| 15 | Lista d'attesa e standby accettati su raccolte annullate | Ammessi solo su raccolte pubbliche e future |
| 16 | Durata slot **0 minuti** accettata (la validazione la trattava come 15) | Minimo 5 minuti |
| 17 | Nuove raccolte creabili **nel passato** | Bloccato in creazione; le raccolte esistenti restano modificabili |
| 18 | Standby con orario "dalle" successivo ad "alle" | Validazione del modulo |
| 19 | Posizioni **duplicate** in lista d'attesa dopo una rimozione | Posizione = massimo + 1 |

### 🟡 Esperienza d'uso

| # | Problema | Correzione |
|---|---|---|
| 20 | **Dati demo scaduti**: le date fisse di luglio rendevano vuote home ed elenco | `seed_demo` usa date relative a oggi e si può rilanciare senza errori |
| 21 | Operatori del **gruppo "operatori"** (non staff) senza menu operatore e con link che portavano a errori | Ruoli esposti ai template (`user_is_operator`, `user_is_admin`, `user_is_donor`) |
| 22 | Utente loggato senza permessi **rimandato al login** in un giro senza uscita | 403 esplicito con pagina d'errore dedicata (anche la 404) |
| 23 | Console operatore su smartphone: il **Check-in era fuori schermo** | Righe impilate a scheda sotto i 768 px |
| 24 | Il pulsante Check-in restava attivo dopo l'arrivo; le offerte scadute sembravano ancora valide | Badge "✓ Arrivato", offerte "Scaduta", messaggio al donatore "attendi conferma" |

Correzioni minori: i valori predefiniti degli orari nel modello erano stringhe (crash creando raccolte da codice) e sono stati sostituiti con oggetti `time` tramite la migrazione `0007`. Lo staff che clicca "Prenota" riceve un messaggio chiaro invece di un 403. Il "presentati X minuti prima" usa il valore reale della raccolta.

---

## 3. Punti verificati e risultati corretti

- Un donatore **non può** vedere, annullare o rispondere a prenotazioni e offerte altrui (404).
- Donatori e anonimi non accedono alle aree operatore e gestione.
- Le azioni operative via semplice link (GET) non vengono eseguite; la protezione CSRF è attiva.
- Nessuno scroll orizzontale indesiderato sulle 12 pagine testate da smartphone.
- Nessun errore JavaScript o di console durante i percorsi.

---

## 4. Ancora aperti (raccomandazioni)

1. **HTML delle pagine CMS non filtrato.** Oggi solo gli admin possono scriverlo, quindi il rischio è contenuto. Con più redattori va sanificato (libreria `nh3`).
2. **Query che crescono con gli slot.** La console operatore passa da 27 query con 8 slot a 51 con 32, per via di `active_appointment` calcolato slot per slot. Non è un problema con 18–20 slot; da ottimizzare con `prefetch_related` se le raccolte crescono.
3. **Pagina "Gestisci prenotazioni" (admin):** fino a 7 pulsanti per riga. Andrebbe portata allo stesso menu "Altro" della console.
4. **Concorrenza reale:** su SQLite `select_for_update` non blocca davvero. Con PostgreSQL in produzione le guardie aggiunte diventano pienamente efficaci.
5. **Scadenza offerte:** ora è applicata quando il donatore risponde. Il passaggio automatico al candidato successivo richiede lo scheduler descritto in `MIGLIORIE.md`.

---

## 5. Come rilanciare i test

```bash
# Test automatici (≈3 secondi)
python manage.py test core

# Test nel browser (database demo pulito + server avviato)
python manage.py migrate && python manage.py seed_demo
python manage.py runserver 127.0.0.1:8765          # in un altro terminale
pip install playwright && playwright install chromium
python scripts/e2e_browser.py screenshots/
```

I test di regressione sono in `core/tests_rules.py`: ogni test corrisponde a un problema di questo report. Se uno fallisce, un bug già corretto è tornato.
