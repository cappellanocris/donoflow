# DonoFlow MVP - Web app Django per prenotazione donazione sangue

Prima versione locale della web app **DonoFlow**, pensata per gestire raccolte sangue con autoemoteca, prenotazioni online, lista d’attesa, standby attivo, check-in, recupero degli slot a rischio e gestione operativa delle giornate di raccolta.

Questa versione è un **MVP dimostrativo locale**: usa SQLite, template Django e notifiche simulate salvate nel database. Non invia SMS, WhatsApp o email reali.

## Funzioni incluse

- Registrazione donatore.
- Login/logout.
- Gestione sedi sia tramite admin Django sia tramite area backend dedicata `/gestione/sedi/`.
- Area **Gestione admin** per inserire e modificare le giornate di raccolta.
- Inserimento raccolta con data, orario, capacità, slot pubblici, slot riservati, durata slot, anticipo check-in, stato, dati informativi pubblici, indicazioni per i donatori e **immagine in evidenza**.
- Generazione e ricalcolo slot dalla scheda raccolta: i primi slot sono pubblici/prenotabili, quelli riservati vengono creati come bloccati.
- Prenotazione online degli slot liberi.
- Annullamento prenotazione lato donatore.
- Gestione prenotazioni lato admin/operatore con azioni **Conferma**, **Annulla**, **Check-in**, **No-show**, **Donazione effettuata** e **Non effettuata**.
- Pagina **Elenco stampabile** per produrre elenco cartaceo con ora, arrivo richiesto, donatore, telefono, stato, firma/note e check-in.
- Inserimento in lista d’attesa.
- Conferma disponibilità standby.
- Dashboard donatore.
- **Area personale donatore** per modifica dati, riepilogo prossima donazione, storico prenotazioni e storico email.
- Dashboard operatore/responsabile.
- Check-in manuale.
- Marcatura slot come ritardo critico.
- Attivazione standby sui primi 3 candidati compatibili.
- Ranking greedy basato su ETA, posizione in lista, affidabilità e priorità.
- Simulazione risposta offerta urgente.
- Conferma manuale del sostituto.
- Notifiche simulate, audit log e invio email informativa con storico visibile nell’area personale.
- Riquadro home con riepilogo della prossima raccolta/donazione, al posto dello scenario demo statico.
- Dati demo per lo scenario Carini / Oleificio Failla / 11 luglio 2026.

## Requisiti

- Python 3.10 o superiore consigliato.
- pip.

## Installazione rapida

Apri il terminale nella cartella del progetto e lancia:

```bash
python -m venv venv
source venv/bin/activate      # Linux/macOS
# venv\Scripts\activate       # Windows PowerShell/CMD

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Poi apri:

```text
http://127.0.0.1:8000/
```

## Account demo

### Operatore / admin

```text
username: admin
password: admin12345
```

### Donatori demo

```text
username: mario
password: demo12345

username: luca
password: demo12345

username: anna
password: demo12345
```

## Dove si gestiscono sedi, raccolte e prenotazioni

Dopo il login come `admin`:

```text
http://127.0.0.1:8000/gestione/sedi/
http://127.0.0.1:8000/gestione/raccolte/
```

Area personale donatore:

```text
http://127.0.0.1:8000/area-personale/
```

Dalla sezione sedi puoi creare, modificare, attivare o disattivare una sede di raccolta.

Dalla sezione raccolte puoi:

1. creare una nuova giornata di raccolta;
2. caricare immagine in evidenza;
3. inserire dati informativi e indicazioni per i donatori;
4. generare gli slot in base a capacità, slot pubblici, slot riservati, durata slot e anticipo di arrivo;
5. aprire la gestione prenotazioni;
6. confermare, annullare, registrare check-in, no-show, donazione effettuata o non effettuata;
7. aprire l’elenco stampabile e mandarlo in stampa dal browser;
8. inviare manualmente una email di riepilogo al donatore dalla tabella prenotazioni.


## Email informative

La versione locale usa di default il backend console:

```python
DJANGO_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Quindi l’email viene stampata nel terminale dove è avviato `python manage.py runserver` e viene salvata anche nello **storico email** dell’area personale del donatore.

Le email vengono generate per questi eventi:

- prenotazione confermata;
- prenotazione annullata dal donatore;
- prenotazione confermata dall’operatore/admin;
- prenotazione annullata dall’operatore/admin;
- posto confermato last-minute da standby;
- no-show registrato;
- donazione registrata come effettuata;
- donazione registrata come non effettuata.

Per inviare email reali puoi configurare un SMTP tramite variabili d’ambiente, senza modificare il codice. Esempio:

```bash
export DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
export DEFAULT_FROM_EMAIL='DonoFlow <noreply@tuodominio.it>'
export EMAIL_HOST=smtp.tuodominio.it
export EMAIL_PORT=587
export EMAIL_HOST_USER=noreply@tuodominio.it
export EMAIL_HOST_PASSWORD='password-o-app-password'
export EMAIL_USE_TLS=1
python manage.py runserver
```

Se l’SMTP non è configurato, il sistema non perde il messaggio: crea una notifica email con stato `Fallita` o `Inviata` consultabile dall’area personale.

## Scenario di test consigliato

1. Accedi come `admin`.
2. Vai in **Gestione** oppure in **Dashboard operatore**.
3. Apri la seconda raccolta in elenco (completamente prenotata) presso **Oleificio Failla - Carini**.
4. Prova la pagina **Prenotazioni** e la pagina **Elenco stampabile**.
5. Dalla dashboard operatore trova lo slot delle **07:45**, prenotato da **Mario Rossi**.
6. Premi **Ritardo critico**.
7. Premi **Attiva standby**.
8. Il sistema crea offerte urgenti per i primi 3 standby compatibili.
9. Simula una o più risposte positive.
10. Premi **Assegna** su un candidato accettato.
11. Lo slot viene riassegnato al sostituto, gli altri restano in standby.

## Struttura progetto

```text
donoflow_mvp/
├── core/
│   ├── models.py
│   ├── forms.py
│   ├── services.py
│   ├── views.py
│   ├── admin.py
│   └── management/commands/seed_demo.py
├── donoflow/
│   ├── settings.py
│   └── urls.py
├── templates/
│   ├── core/
│   ├── management/
│   └── operator/
├── static/css/app.css
├── media/session_images/
├── requirements.txt
├── README.md
└── manage.py
```

## Modelli principali

- `Donor`
- `DonationCenter`
- `DonationSession`
- `Slot`
- `Appointment`
- `WaitlistEntry`
- `StandbyAvailability`
- `WaitlistOffer`
- `CheckIn`
- `Notification`
- `DonationOutcome`
- `AuditLog`

## Nota importante privacy/sicurezza

Questa è una prima versione locale per sviluppo e test. Prima di un uso reale servono almeno:

- configurazione produzione con `DEBUG=False`;
- database PostgreSQL;
- HTTPS;
- policy GDPR e consenso comunicazioni;
- ruoli/permessi più granulari;
- cifratura o protezione rafforzata dei dati sensibili;
- integrazione con provider reali per email/SMS/WhatsApp;
- backup e logging di produzione;
- revisione legale e sanitaria dei flussi operativi.

## Reset dati demo

Per ricreare i dati demo:

```bash
python manage.py seed_demo --reset
```

## Evoluzioni consigliate

- PostgreSQL.
- Celery + Redis per notifiche e timeout.
- Integrazione SMS/WhatsApp.
- Report PDF/Excel.
- Ruoli avanzati: donatore, volontario, responsabile, sanitario, admin.
- Predizione no-show in una versione futura.

## Pagine informative e contenuti CMS

Questa versione include un piccolo sistema di gestione pagine accessibile agli amministratori:

```text
http://127.0.0.1:8000/gestione/pagine/
```

Dal backend è possibile:

- creare nuove pagine pubbliche;
- modificare titolo, URL, descrizione e contenuto HTML;
- pubblicare o nascondere una pagina;
- scegliere se mostrarla nel menu principale e/o nel footer;
- impostare l’ordine di visualizzazione;
- aprire l’anteprima pubblica;
- eliminare una pagina.

Pagine iniziali incluse:

```text
/come-funziona/
/privacy/
/info/
```

La pagina Privacy è un modello tecnico iniziale. Prima dell’uso reale devono essere configurati il titolare del trattamento, i recapiti privacy, le basi giuridiche, i tempi di conservazione e i fornitori effettivamente utilizzati.


## Aggiornamento: hero, filtri e footer

- La home include una hero image nella cartella `static/img/hero-donoflow.png`.
- La pagina `/sessions/` permette di filtrare le raccolte per **Sede**, **Mese** e **Anno**.
- Il footer è diviso in tre sezioni standard modificabili dal backend su `/gestione/footer/`.

Dopo aver sostituito una versione precedente, eseguire:

```bash
python manage.py migrate
```

## Correzione layout 1920 px

Questa versione utilizza un contenitore fluido con larghezza massima di 1920 px. La hero della homepage occupa tutta la larghezza disponibile e non supera 400 px di altezza. Il riepilogo della prossima donazione rimane distribuito su una sola riga nelle visualizzazioni desktop e tablet, mentre le tre sezioni del footer restano affiancate fino alla soglia mobile.
