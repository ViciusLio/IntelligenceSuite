# Skill: Example Deploy
> description: Guida attraverso il processo di deploy verificando prerequisiti e dipendenze.
> parameters: service_name (str, required), environment (str, required, enum: staging|production)

## Step 1: Verifica dipendenze
**Domini:** code, doc
**Query:** dipendenze e requisiti di {service_name} per ambiente {environment}
Analisi delle dipendenze del servizio nel codice sorgente e nella documentazione tecnica.
Verifica che tutte le librerie e i servizi esterni richiesti siano disponibili.

## Step 2: Configurazione ambiente
**Domini:** doc
**Query:** configurazione {environment} variabili d'ambiente {service_name}
Verifica della configurazione corretta per l'ambiente target.
Controlla variabili d'ambiente, secrets, endpoint e parametri specifici per {environment}.

## Step 3: Checklist pre-deploy
**Domini:** doc, mentor
**Query:** checklist pre-deploy best practice {service_name}
Verifica della checklist pre-deploy con le best practice del team.
Include test superati, code review approvata, monitoring configurato.

## Step 4: Piano di rollback
**Domini:** doc
**Query:** piano rollback procedura ripristino {service_name}
Definizione del piano di rollback in caso di problemi post-deploy.
Procedura, responsabili e criteri di attivazione del rollback.
