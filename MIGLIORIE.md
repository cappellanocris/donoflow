# DonoFlow — Migliorie e automazioni future

Documento di roadmap redatto dopo l'analisi completa del codice (luglio 2026).
Le voci sono ordinate per priorità all'interno di ogni sezione; per ognuna è indicato
lo sforzo stimato (S = ore, M = giorni, L = settimane).

> **Aggiornamento 30/09/2026 (collaudo, vedi `REPORT_TEST.md`).** Già realizzati:
> validatori password (2.1), test del service layer (3.1), blocco intervallo tra
> donazioni (4.6). Parzialmente: scadenza offerte (1.4, applicata alla risposta ma
> senza passaggio automatico al candidato successivo) e permessi per ruolo (2.6,
> il gruppo "operatori" ora ha la sua area; manca la distinzione con "responsabili").

---

## 1. Automazioni (il cuore del valore di DonoFlow)

Oggi molti flussi che il sistema modella bene vengono attivati **a mano** dall'operatore.
Automatizzarli è la miglioria a più alto impatto.

1. **Task scheduler (Celery + Redis, o `django-q2` per restare leggeri)** — prerequisito
   per tutte le automazioni seguenti. *(M)*
2. **Rilevamento automatico dei ritardi critici**: un job periodico che, superata l'ora di
   arrivo attesa senza check-in, marca lo slot come `RISK` senza intervento manuale
   (oggi lo fa l'operatore con il pulsante "Ritardo critico"). *(S, dopo il punto 1)*
3. **Attivazione automatica dello standby**: dopo N minuti in stato `RISK`, invio automatico
   delle offerte ai primi 3 candidati del ranking (`activate_standby_for_slot` esiste già,
   va solo schedulata). *(S)*
4. **Scadenza automatica delle offerte**: il campo `expires_at` esiste ma non viene mai
   applicato; un job dovrebbe portare a `EXPIRED` le offerte non risposte e passare al
   candidato successivo. *(S)*
5. **Promemoria automatici pre-donazione**: email/notifica a T-48h e T-2h dall'appuntamento,
   con link di riconferma (stato `TO_RECONFIRM` → `RECONFIRMED` già previsto dal modello,
   ma mai usato dal flusso reale). *(M)*
6. **Chiusura automatica delle raccolte**: a fine giornata, marcare `NO_SHOW` le prenotazioni
   senza check-in e portare la sessione a `CLOSED`. *(S)*
7. **Invio reale su SMS/WhatsApp**: il campo `preferred_channel` è già presente su tutta la
   filiera; integrare un provider (Twilio, Vonage, WhatsApp Business API) dietro
   un'interfaccia `NotificationBackend` così che `notify_appointment()` scelga il canale
   giusto senza modifiche al resto del codice. *(L)*
8. **Ricalcolo periodico dell'affidabilità**: oggi il punteggio scende solo sui no-show;
   un job mensile potrebbe farlo risalire gradualmente con i comportamenti positivi
   (donazioni completate, riconferme puntuali). *(S)*
9. **Promozione automatica dalla lista d'attesa**: quando un donatore annulla, offrire
   subito lo slot al primo in lista compatibile invece di rimetterlo semplicemente `FREE`. *(M)*

## 2. Sicurezza e produzione

1. **Riattivare i validatori password** (`AUTH_PASSWORD_VALIDATORS` è vuoto: accettabile solo
   in demo). *(S)*
2. **Sanitizzazione dell'HTML dei contenuti CMS** con `bleach`/`nh3`: oggi `content|safe` si
   fida degli admin; con più redattori è un rischio XSS. *(S)*
3. **Migrazione a PostgreSQL** e configurazione `DATABASE_URL` via `django-environ`;
   SQLite non regge la concorrenza di prenotazioni reali nonostante il
   `select_for_update` già presente. *(M)*
4. **Rate limiting** su login, registrazione e prenotazione (es. `django-ratelimit`). *(S)*
5. **Header di sicurezza per produzione**: `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`,
   `CSRF_COOKIE_SECURE`, HSTS, tutti condizionati a `DEBUG=False`. *(S)*
6. **Permessi più granulari**: distinguere davvero "operatore" da "responsabile" (oggi i
   gruppi esistono ma hanno gli stessi poteri) e limitare l'area `/gestione/` con permessi
   Django invece del solo `is_staff`. *(M)*
7. **Backup automatico del database e dei media** (cron + `dbbackup` o snapshot gestiti). *(S)*

## 3. Qualità del codice e test

1. **Estendere la suite di test** al service layer: `book_slot` (doppia prenotazione
   concorrente), `cancel → slot FREE`, `rank_standby_candidates` (pesi e fasce orarie),
   `assign_standby_offer` (sostituzione e chiusura offerte). Oggi i test coprono solo
   CMS, filtri e footer. *(M)*
2. **Convertire le choices in `models.TextChoices`** per avere costanti tipizzate
   (`Appointment.Status.CONFIRMED`) al posto delle stringhe. *(M, richiede attenzione
   alle migrazioni)*
3. **Macchina a stati esplicita** per `Appointment`/`Slot` (es. `django-fsm`): le transizioni
   valide oggi sono implicite nel service layer. *(M)*
4. **Type hints + mypy/ruff in CI** (GitHub Actions: lint, test, check migrazioni). *(M)*
5. **Componenti template riutilizzabili**: estrarre `{% include %}` per card-head, pill di
   stato, empty-state e menu azioni, oggi ripetuti nei template. *(S)*
6. **Rimuovere le cartelle `old_css/`, `old_template/`, `old_registration/` e
   `old_base.html`** una volta validato il nuovo frontend (sono backup della versione
   precedente). *(S)*

## 4. Esperienza utente

1. **Prenotazione senza cambio pagina**: usare htmx (già incluso) per prenotare/annullare
   uno slot aggiornando solo la griglia, con feedback immediato. *(M)*
2. **Aggiornamento live della console operatore**: polling htmx ogni 30–60 s (o SSE) su
   slot e statistiche, per non dover ricaricare durante la raccolta. *(M)*
3. **Vista calendario delle raccolte** accanto all'elenco, con esportazione iCal del
   proprio appuntamento. *(M)*
4. **Check-in via QR code**: QR nell'email di conferma, scansione dal telefono
   dell'operatore che chiama `mark_checkin`. *(M)*
5. **Ricerca per distanza**: i campi `latitude`/`longitude` delle sedi esistono già ma non
   vengono usati; ordinare le raccolte per vicinanza al donatore. *(M)*
6. **Blocco intelligente della prenotazione**: impedire (o segnalare) la prenotazione se
   non è trascorso l'intervallo minimo dall'ultima donazione (90 gg sangue intero,
   in base a `last_donation_date` e `donation_type`). *(S)*
7. **PWA / notifiche push** per le offerte urgenti, dove i secondi contano. *(L)*
8. **Accessibilità**: audit completo WCAG AA (focus trap nei menu Alpine, contrasti,
   navigazione da tastiera nelle tabelle azioni). *(M)*

## 5. Funzionalità di dominio

1. **Report e statistiche**: tasso di riempimento per sede, no-show rate, efficacia del
   recupero standby, esportazione CSV/Excel per il direttivo. *(M)*
2. **Gestione multi-associazione / multi-tenant** se DonoFlow dovrà servire più sezioni
   AVIS o associazioni diverse. *(L)*
3. **Storico donazioni certificato** del donatore con conteggio annuale e idoneità. *(M)*
4. **Questionario pre-donazione digitale** compilabile da casa, allegato al check-in. *(L)*
5. **Integrazione con i gestionali trasfusionali regionali** (quando disponibili API). *(L)*

---

## Percorso consigliato

**Fase 1 (fondamenta, ~2 settimane)** — scheduler + automazioni 1.2–1.6, PostgreSQL,
validatori password, test del service layer.
**Fase 2 (comunicazioni reali, ~3 settimane)** — provider SMS/WhatsApp, promemoria,
promozione automatica da lista d'attesa.
**Fase 3 (esperienza, ~3 settimane)** — prenotazione htmx senza reload, console live,
QR check-in, blocco intervallo donazioni.
**Fase 4 (crescita)** — report, PWA, multi-tenant.
