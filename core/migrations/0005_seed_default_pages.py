from django.db import migrations


HOW_IT_WORKS = r'''
<p>DonoFlow è la piattaforma online che consente di consultare le giornate di raccolta, scegliere un orario disponibile e gestire la propria prenotazione in autonomia.</p>

<div class="steps">
  <div class="step"><strong>1. Consulta le raccolte disponibili</strong><br>Visualizza data, sede, orari, posti disponibili e indicazioni fornite dagli organizzatori.</div>
  <div class="step"><strong>2. Registrati o accedi</strong><br>Crea il tuo profilo donatore oppure accedi al tuo account per prenotare e ricevere le comunicazioni.</div>
  <div class="step"><strong>3. Scegli lo slot</strong><br>Seleziona uno degli orari liberi. La prenotazione viene registrata e ricevi un messaggio email di riepilogo.</div>
  <div class="step"><strong>4. Gestisci l’appuntamento</strong><br>Dall’area personale puoi controllare la prossima donazione, aggiornare i tuoi dati e annullare la prenotazione quando non puoi partecipare.</div>
</div>

<h2>Quando gli orari sono completi</h2>
<p>Puoi entrare nella <strong>lista d’attesa</strong> e, per una specifica raccolta, confermare la disponibilità come donatore standby. Se uno slot si libera o un donatore non si presenta, il sistema può inviarti una richiesta urgente.</p>
<div class="info-box"><strong>La richiesta di disponibilità non equivale a una convocazione.</strong> Il posto è assegnato soltanto dopo la conferma definitiva dell’organizzazione.</div>

<h2>Il giorno della raccolta</h2>
<p>Presentati presso la sede indicata con l’anticipo riportato nella prenotazione, generalmente almeno 15 minuti prima dello slot. Il personale registra il check-in e aggiorna l’esito al termine della procedura.</p>

<h2>Comunicazioni</h2>
<p>DonoFlow può inviare email per conferma, annullamento, promemoria, variazioni e registrazione della donazione effettuata. Controlla che l’indirizzo inserito nell’area personale sia corretto.</p>

<h2>Perché usare DonoFlow</h2>
<ul>
  <li>riduce le attese e semplifica la prenotazione;</li>
  <li>aiuta a recuperare gli slot liberati all’ultimo momento;</li>
  <li>mantiene in un unico posto appuntamenti e comunicazioni;</li>
  <li>supporta il responsabile nella gestione della raccolta.</li>
</ul>

<div class="cta-box">
  <h2>Pronto a prenotare?</h2>
  <p>Consulta le prossime giornate disponibili e scegli il tuo orario.</p>
  <p><a class="btn" href="/sessions/">Vedi le raccolte</a> <a class="btn btn-outline" href="/accounts/register/">Registrati</a></p>
</div>
'''


PRIVACY = r'''
<div class="warning-box"><strong>Nota per la messa in produzione:</strong> questa informativa è un modello tecnico iniziale. Prima dell’utilizzo reale devono essere indicati il titolare effettivo, i responsabili, i tempi di conservazione definitivi, i fornitori utilizzati e le basi giuridiche applicabili all’organizzazione che gestisce la raccolta.</div>

<p><strong>Ultimo aggiornamento:</strong> 7 luglio 2026</p>

<h2>1. Normativa di riferimento</h2>
<p>Il trattamento dei dati personali tramite DonoFlow è disciplinato dal Regolamento (UE) 2016/679 (GDPR), dal decreto legislativo 30 giugno 2003, n. 196, come modificato dal decreto legislativo 10 agosto 2018, n. 101, nonché dai provvedimenti e dalle linee guida del Garante per la protezione dei dati personali applicabili.</p>

<h2>2. Titolare del trattamento</h2>
<p><strong>Da configurare prima della pubblicazione:</strong> inserire denominazione dell’ente o associazione che utilizza DonoFlow, sede, codice fiscale o partita IVA, email e recapiti per l’esercizio dei diritti. Lo sviluppatore tecnico non assume automaticamente il ruolo di titolare del trattamento.</p>

<h2>3. Dati trattati</h2>
<p>La web app può trattare dati anagrafici e di contatto, credenziali di accesso, codice fiscale, data di nascita, informazioni relative alle prenotazioni, alle liste d’attesa, agli accessi, alle comunicazioni inviate e agli esiti organizzativi della donazione. Qualora venga registrato il gruppo sanguigno o altra informazione sanitaria, tali dati rientrano nelle categorie particolari di dati personali previste dall’articolo 9 del GDPR.</p>

<h2>4. Finalità del trattamento</h2>
<ul>
  <li>registrazione e gestione dell’account;</li>
  <li>prenotazione, conferma, modifica e annullamento degli appuntamenti;</li>
  <li>gestione di lista d’attesa, standby, check-in e mancata presentazione;</li>
  <li>invio di comunicazioni operative e promemoria;</li>
  <li>gestione e rendicontazione delle giornate di raccolta;</li>
  <li>sicurezza applicativa, prevenzione degli abusi e registrazione delle operazioni amministrative;</li>
  <li>adempimento di obblighi normativi e organizzativi applicabili.</li>
</ul>

<h2>5. Basi giuridiche</h2>
<p>Le basi giuridiche devono essere determinate dal titolare in relazione alla propria natura e alle finalità effettive. Possono comprendere l’esecuzione di misure richieste dall’interessato, l’adempimento di obblighi di legge, lo svolgimento di compiti di interesse pubblico, il legittimo interesse per la sicurezza del servizio e, quando necessario, il consenso. Per le categorie particolari di dati occorre inoltre individuare una delle condizioni previste dall’articolo 9, paragrafo 2, del GDPR.</p>

<h2>6. Modalità e sicurezza</h2>
<p>I dati sono trattati con strumenti informatici secondo principi di liceità, correttezza, trasparenza, minimizzazione, esattezza, limitazione della conservazione, integrità e riservatezza. In produzione devono essere adottate misure adeguate quali HTTPS, controllo degli accessi per ruolo, password sicure, backup protetti, aggiornamento del software, registrazione delle operazioni e procedure per la gestione delle violazioni dei dati.</p>

<h2>7. Destinatari e fornitori</h2>
<p>I dati possono essere consultati dal personale autorizzato e comunicati a fornitori strettamente necessari, ad esempio hosting, posta elettronica, SMS o messaggistica, nominati responsabili del trattamento quando previsto. L’elenco effettivo dei fornitori deve essere indicato o reso disponibile dal titolare.</p>

<h2>8. Trasferimenti fuori dallo Spazio economico europeo</h2>
<p>Qualora siano utilizzati fornitori che trattano dati fuori dallo Spazio economico europeo, il titolare deve verificare l’esistenza di una decisione di adeguatezza o di altre garanzie previste dal GDPR e fornire le relative informazioni agli interessati.</p>

<h2>9. Conservazione</h2>
<p>I dati devono essere conservati per il tempo necessario alle finalità indicate e agli obblighi applicabili. Il titolare deve definire tempi specifici per account, prenotazioni, notifiche, audit log, cancellazioni, no-show ed eventuali informazioni sanitarie, prevedendo cancellazione o anonimizzazione al termine.</p>

<h2>10. Diritti dell’interessato</h2>
<p>Nei casi previsti dagli articoli 15-22 del GDPR, l’interessato può chiedere accesso, rettifica, cancellazione, limitazione, portabilità, opposizione e revoca del consenso senza pregiudicare la liceità del trattamento precedente. Può inoltre proporre reclamo al Garante per la protezione dei dati personali.</p>

<h2>11. Cookie e dati tecnici</h2>
<p>La versione base di DonoFlow utilizza cookie tecnici necessari per autenticazione, sessione e sicurezza CSRF. Se in futuro verranno introdotti strumenti analitici non anonimizzati, profilazione, mappe, video o servizi di terze parti, dovranno essere valutati banner, consenso preventivo e gestione delle preferenze secondo le linee guida del Garante sui cookie e gli altri strumenti di tracciamento.</p>

<h2>12. Minori</h2>
<p>Le regole per l’accesso dei minori e per l’eventuale consenso devono essere definite dal titolare in coerenza con la disciplina applicabile e con i requisiti previsti per la donazione.</p>

<h2>13. Contatti</h2>
<p>Per richieste privacy utilizzare i recapiti del titolare che dovranno essere pubblicati in questa sezione. Se è stato designato un Responsabile della protezione dei dati (RPD/DPO), devono essere indicati anche i relativi contatti.</p>

<h2>14. Riferimenti ufficiali</h2>
<ul>
  <li><a href="https://eur-lex.europa.eu/eli/reg/2016/679/oj/ita" target="_blank" rel="noopener">Regolamento (UE) 2016/679</a></li>
  <li><a href="https://www.garanteprivacy.it/codice" target="_blank" rel="noopener">Codice in materia di protezione dei dati personali</a></li>
  <li><a href="https://www.garanteprivacy.it/home/docweb/-/docweb-display/docweb/9677876" target="_blank" rel="noopener">Linee guida cookie e altri strumenti di tracciamento</a></li>
</ul>
'''


INFO = r'''
<p>DonoFlow è un progetto software dedicato alla gestione delle prenotazioni per le giornate di donazione del sangue, con funzioni per slot, lista d’attesa, standby, check-in, comunicazioni e supporto operativo ai responsabili della raccolta.</p>

<h2>Sviluppatore</h2>
<p><strong>Cris Cappellano</strong><br>Consulente informatico e sistemista con esperienza professionale dal 1996, con sede operativa nell’area di Carini, in provincia di Palermo.</p>

<h2>Competenze</h2>
<ul>
  <li>sviluppo di applicazioni web e software gestionali;</li>
  <li>amministrazione di sistemi, server e reti;</li>
  <li>database e integrazione di servizi;</li>
  <li>WordPress, WooCommerce ed e-commerce;</li>
  <li>automazione, analisi dei dati e soluzioni basate su intelligenza artificiale;</li>
  <li>assistenza e consulenza informatica per professionisti e imprese.</li>
</ul>

<h2>Contatti dello sviluppatore</h2>
<p>Email: <a href="mailto:criscappellano@gmail.com">criscappellano@gmail.com</a></p>

<div class="info-box"><strong>Nota:</strong> lo sviluppatore cura la realizzazione tecnica dell’applicazione. L’organizzazione che utilizza DonoFlow resta responsabile della gestione delle raccolte, dei contenuti pubblicati e del trattamento dei dati personali secondo i ruoli definiti dalla normativa.</div>
'''


def create_pages(apps, schema_editor):
    CmsPage = apps.get_model('core', 'CmsPage')
    pages = [
        {
            'slug': 'come-funziona',
            'title': 'Come funziona',
            'menu_label': 'Come funziona',
            'summary': 'Tutto ciò che serve per prenotare, gestire l’appuntamento e utilizzare la lista d’attesa.',
            'content': HOW_IT_WORKS,
            'is_published': True,
            'show_in_navigation': True,
            'show_in_footer': True,
            'sort_order': 10,
        },
        {
            'slug': 'privacy',
            'title': 'Privacy e protezione dei dati',
            'menu_label': 'Privacy',
            'summary': 'Informazioni sul trattamento dei dati personali nella piattaforma DonoFlow.',
            'content': PRIVACY,
            'is_published': True,
            'show_in_navigation': False,
            'show_in_footer': True,
            'sort_order': 90,
        },
        {
            'slug': 'info',
            'title': 'Informazioni sul progetto',
            'menu_label': 'Info',
            'summary': 'Presentazione di DonoFlow e dello sviluppatore del progetto.',
            'content': INFO,
            'is_published': True,
            'show_in_navigation': True,
            'show_in_footer': True,
            'sort_order': 80,
        },
    ]
    for page in pages:
        slug = page.pop('slug')
        CmsPage.objects.update_or_create(slug=slug, defaults=page)


def remove_pages(apps, schema_editor):
    CmsPage = apps.get_model('core', 'CmsPage')
    CmsPage.objects.filter(slug__in=['come-funziona', 'privacy', 'info']).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0004_cmspage'),
    ]

    operations = [
        migrations.RunPython(create_pages, remove_pages),
    ]
