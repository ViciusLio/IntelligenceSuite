# Skill: Example Onboarding
> description: Guida un nuovo sviluppatore attraverso l'onboarding aziendale step by step.
> parameters: developer_name (str, required), focus (str, required, enum: backend|frontend|data)

## Step 1: Setup ambiente di sviluppo
**Domini:** doc, mentor
**Query:** setup ambiente sviluppo prerequisiti installazione {focus}
Configurazione dell'ambiente di sviluppo locale per {developer_name}.
Prerequisiti, installazione dipendenze, variabili d'ambiente e verifica del setup corretto.

## Step 2: Primo giro del codebase
**Domini:** code
**Query:** struttura codebase architettura moduli principali {focus}
Panoramica della struttura del codebase, moduli principali e pattern architetturali.
Focus sull'area {focus} e i punti di ingresso più rilevanti.

## Step 3: Prima task e convenzioni del team
**Domini:** code, mentor
**Query:** convenzioni sviluppo workflow git code review onboarding {focus}
Introduzione alle convenzioni di sviluppo del team per {developer_name}.
Workflow git, process di code review e indicazioni per la prima task assegnata.
