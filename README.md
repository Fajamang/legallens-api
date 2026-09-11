# LegalLens Pro 9.2 — Render-update

Deze versie herstelt de aangeleverde Python-backend en vervangt de ongeldige HTML/JavaScript door een samenhangende Nederlandse werkruimte. Bedoeld voor één besloten werkruimte. Iedereen met een geldige LegalLens-sleutel heeft toegang tot alle dossiers; dit is geen product met gescheiden klantaccounts of abonnementen.

## 1. Bestanden in Git vervangen

Pak `LegalLens-Pro-Render.zip` uit. Plaats de inhoud direct in de root van je bestaande repository:

```text
app.py
Dockerfile
requirements.txt
requirements-test.txt
README.md
.dockerignore
static/
  index.html
  styles.css
  app.js
tests/
  test_app.py
TESTRESULTATEN.md
```

De drie bestanden in `static` horen bij elkaar. Alleen `index.html` vervangen is onvoldoende. De oorspronkelijke HTML stond in de upload `Pasted text(1).txt`; JavaScript stond buiten het script-element en bevatte ongeldige drievoudige aanhalingstekens.

## 2. Bestaande data eerst behouden

Maak vóór een deployment een databaseback-up en kopie van je uploads als je al dossiers gebruikt. Een consistente SQLite-back-up maak je bij voorkeur met de SQLite backup-API (geen losse kopie tijdens actieve schrijfacties).

- De bestaande v9-tabellen blijven behouden: `CREATE TABLE IF NOT EXISTS` verwijdert niets.
- Het oude standaardpad voor de database is `/app/data/legallens.db` bij Docker.
- Oude uploads stonden standaard in `/app/uploads`. De nieuwe standaard is `DATA_DIR/uploads`. Bestaande bestanden worden NIET automatisch verplaatst. Kopieer ze naar de nieuwe permanente map of stel `UPLOAD_DIR` in op hun bestaande permanente locatie.
- Oude browserdossiers/analyses uit localStorage worden niet automatisch geïmporteerd. Gebruik in de oude browser en op hetzelfde domein **Instellingen → Oude browsergegevens downloaden**. De gegevens blijven in de browser staan; de download is een reservekopie.
- Het verwijderen van een dossier verwijdert diens bestanden. Analyses en gemaakte documenten blijven bestaan met lege dossierkoppeling. Die kun je afzonderlijk verwijderen.

## 3. Render controleren

Behoud je bestaande Render-service en je ingestelde geheimen. Deze bestanden deployen niets automatisch vanuit ChatGPT.

**Docker-service:** laat Render de bijgeleverde Dockerfile gebruiken. Startopdracht is `python app.py`.

**Native Python-service:** Build Command `pip install -r requirements.txt`; Start Command `python app.py`; gebruik Python 3.11 of nieuwer.

**Health Check Path:** `/health`. De server bindt aan `0.0.0.0` en gebruikt Render's `PORT` (standaard 10000). De Docker-healthcheck gebruikt dezelfde variabele.

### Jouw huidige situatie: gratis Render

De app kan voorlopig op **Render Free** blijven draaien. Voor deze testfase is geen betaald abonnement nodig, en Rechtspraak Open Data vraagt geen extra API-sleutel.

Gebruik de standaard lokale map `data`, of zet `DATA_DIR=data` als je dit expliciet wilt instellen. `STORAGE_MODE=temporary` is de standaard en toont een blijvende melding over tijdelijke opslag. Deze instelling maakt geen back-up.

**Dossiers, SQLite en uploads zijn op Render Free niet blijvend.** Ze kunnen verdwijnen na een deployment, herstart of het stilzetten van een inactieve service. Render zet een gratis service na circa 15 minuten zonder verkeer stil; de volgende bezoeker moet doorgaans ongeveer een minuut op het opstarten wachten. Bewaar belangrijke uploads zelf en download gemaakte documenten en analyses direct.

Wil je later dossiers blijvend bewaren terwijl de webservice gratis blijft, dan is een aparte persistente database én bestandsopslag nodig. Dat is nog niet aangesloten in dit pakket. Een gratis Render Postgres-database verloopt volgens Render na 30 dagen en is daarom geen duurzame oplossing voor dossierbewaring.

Voor een latere betaalde service kun je een Persistent Disk koppelen, bijvoorbeeld op `/var/data`, met `DATA_DIR=/var/data`. Zet `STORAGE_MODE=persistent` alleen nadat je hebt gecontroleerd dat database en uploads op die echte disk staan. De ENV-vlag zelf maakt geen opslag permanent. Bestaande data verplaatsen blijft een aparte stap.

Officiële documentatie:
- [Render Free en tijdelijke bestanden](https://render.com/docs/free)
- [Render Persistent Disks](https://render.com/docs/disks)
- [Render Web Services en poortinstellingen](https://render.com/docs/web-services)

### Environment variables

| Variabele | Nodig | Betekenis |
| --- | --- | --- |
| `VALID_API_KEYS` | Ja | Eigen lange, willekeurige toegangssleutel; meerdere sleutels kommagescheiden. `demo-key` en `test-key` worden geweigerd. Alle sleutels delen één werkruimte. |
| `OPENAI_API_KEY` | Voor AI | Je bestaande OpenAI-sleutel, uitsluitend op de server. |
| `AI_PROVIDER` | Optioneel | `openai` (standaard). Andere providers geven een duidelijke fout, geen nepresultaat. |
| `OPENAI_MODEL` | Optioneel | Standaard `gpt-4o-mini`; kies een voor jouw account beschikbaar Chat Completions-model met JSON-objectondersteuning. |
| `TAVILY_API_KEY` | Voor zoeken op artikel | Voor zoeken in wetten.overheid.nl en rechtspraak.nl. ECLI-opvraging werkt zonder Tavily. AI-commentaar op zoekresultaten gebruikt OpenAI. |
| `DATA_DIR` | Optioneel | Op gratis Render: `data` (tijdelijk). Later: het echte mount path van een disk. |
| `STORAGE_MODE` | Optioneel | Standaard `temporary`. Alleen `persistent` gebruiken als opslag werkelijk permanent is geregeld. |
| `DB_PATH` | Optioneel | Volledig afwijkend databasepad, bijvoorbeeld voor een bestaande disk. |
| `UPLOAD_DIR` | Optioneel | Afwijkende uploadmap; moet eveneens op permanente opslag staan. |
| `PORT` | Door Render | Automatisch gebruikt; geen hardgecodeerde afwijkende poort nodig. |
| `MAX_UPLOAD_MB` | Optioneel | Standaard 10 MB. |
| `MAX_TEXT_CHARS` | Optioneel | Standaard 60000 tekens; grotere documenten worden expliciet geweigerd, nooit stil afgekapt. |
| `CORS_ALLOWLIST` | Optioneel | Kommagescheiden externe frontend-origins. Voor de meegeleverde frontend op hetzelfde domein leeg laten. |

`HF_API_TOKEN` wordt in deze versie niet gebruikt. De vorige versie implementeerde geen werkende Hugging Face-provider.

Geheimen horen niet in Git, de HTML of JavaScript. `.dockerignore` voorkomt dat lokale ENV-bestanden of dossierdata in de containerimage terechtkomen.

## 4. Eerste keer openen

1. Wacht tot Render de nieuwe deployment als geslaagd markeert.
2. Open je bestaande Render-adres. Kies eventueel een harde refresh als oude bestanden gecachet zijn.
3. Vul bij **Instellingen** één sleutel uit `VALID_API_KEYS` in. Dit is niet je OpenAI-sleutel.
4. Klik **Verbinden**. De sleutel wordt alleen in sessionStorage van dit tabblad bewaard.
5. Maak een dossier, upload een onschuldig testdocument en voer een analyse uit.
6. Open de analysegeschiedenis, laad de pagina opnieuw en controleer dat het resultaat blijft staan.
7. Maak een conceptdocument en test Word, PDF en TXT.
8. Zoek een wetsartikel als Tavily is ingesteld.
9. Op gratis Render: download je resultaten vóór een herstart/deployment. Bij permanente opslag: controleer daarna of het testdossier er nog staat.

**Belangrijk:** de statuspagina controleert of sleutels ingesteld zijn; pas een geslaagde live analyse/zoekopdracht bewijst dat sleutel, model, facturatie en externe verbinding werken.

## Werkende onderdelen

- Responsive overzicht, dossierkaarten, zoekfunctie, mobiel menu en duidelijke fout-/laadmeldingen.
- Dossiers aanmaken, openen, bewerken, archiveren/sluiten en verwijderen.
- Bestanden bij dossiers opslaan, downloaden, analyseren en verwijderen.
- Tekst, PDF, TXT en DOCX analyseren; DOCX-tabellen worden meegenomen.
- Analysemodus standaard/advocaat; contractanalyse, due diligence en twaalf rechtsgebieden als analysecontext.
- Geldige AI-resultaten opslaan; geschiedenis met zoekfunctie, dossierfilter en paginering.
- Samenvatting, partijen, datums, risico's, citaten, aanbevelingen, actieplan, onderhandelingsstrategie en due diligence tonen.
- Analyse afdrukken of via de browser als PDF opslaan, JSON downloaden, analyse verwijderen.
- De twee aangeleverde conceptsjablonen invullen, valideren, opslaan, heropenen, downloaden en verwijderen.
- Echte Word-, PDF- en TXT-documentdownloads.
- Wetgeving/jurisprudentie zoeken via Tavily, officiële bronlinks en op fragmenten gebaseerd AI-commentaar.
- Aanvullend: gratis Rechtspraak Open Data voor directe ECLI-opvraging en het verrijken van maximaal drie Tavily-resultaten met officiële metadata en beschikbare uitspraaktekst.
- Bij Rechtspraak- of AI-storing blijven beschikbare Tavily-bronnen zichtbaar met een foutmelding.
- Verplichte API-toegangssleutel, beperkte CORS, geparametriseerde SQL, foreign keys, gesloten databaseverbindingen, veilige uitvoer van documenttekst in de browser.

### Bewuste grenzen

- PDF-scans zonder tekstlaag vereisen vooraf OCR; OCR is niet ingebouwd.
- Een los bestand analyseren bewaart het resultaat en de gekozen dossierkoppeling, niet automatisch het originele bestand. Bewaar het origineel eerst via Dossiers als je het later wilt downloaden.
- De aangeleverde sjablonen zijn korte basisconcepten, geen juridisch gevalideerde complete contracten.
- Bronresultaten zijn zoekfragmenten, geen gegarandeerd volledige actuele wettekst. Geen verzonnen wijzigingsgeschiedenis, verwante artikelen of rechtspraak. De oude README beloofde deze onderdelen zonder ze te implementeren.
- Een AI-verwijzing in een analyse is niet automatisch live geverifieerd. Gebruik de bronknop en controleer de officiële tekst.
- Tijdbesparing is niet gemeten en wordt daarom niet als verzonnen dashboardcijfer getoond. De documenttoon is expliciet een modelinschatting, geen juridische kwaliteitsscore.
- Er is geen facturatie/abonnementensysteem of scheiding per gebruiker. De oude prijskaart was uitsluitend statische tekst.
- Documentinhoud gaat voor analyse naar OpenAI; zoektermen naar Tavily. Deze code biedt op zichzelf geen bewijs van AVG-compliance of een EU-verwerkingsgarantie.

Tavily gebruikt nu de gedocumenteerde Bearer-authenticatie: [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search).

## Tests lokaal uitvoeren

```bash
pip install -r requirements.txt -r requirements-test.txt
python -m pytest tests -q
python app.py
```

Zie TESTRESULTATEN.md voor uitgevoerde controles en hun beperkingen. Productie-CI kan dezelfde API-tests draaien. Een Dockerimage is hier niet gebouwd; Render moet de daadwerkelijke build en start nog bevestigen.

## API

Swagger: `/api/docs`. Gebruik **Authorize** met een sleutel uit `VALID_API_KEYS`.

| Doel | Routes |
| --- | --- |
| Gezondheid/configuratie | `GET /health`, `GET /api/status`, `GET /api/stats` |
| Dossiers | `GET/POST /api/dossiers`, `GET/PUT/DELETE /api/dossiers/{id}` |
| Dossierbestanden | `POST /api/dossiers/{id}/files`, `GET/DELETE /api/files/{id}` |
| Analyse | `POST /api/analyze-text`, `POST /api/analyze-file` |
| Geschiedenis | `GET /api/analyses`, `GET/DELETE /api/analyses/{id}` |
| Conceptdocumenten | `GET /api/templates`, `POST /api/templates/generate`, `GET /api/documents` |
| Export/verwijderen | `GET /api/documents/{id}/download?format=docx`, `DELETE /api/documents/{id}` |
| Bronnen | `POST /api/legal-commentary` |

Voor JSON-aanvragen: `Content-Type: application/json` en `X-API-Key`. Voor uploads: multipart FormData plus `X-API-Key`; de browser stelt zelf de multipart Content-Type in.


## Rechtspraak Open Data — toegevoegd in 9.2

De officiële koppeling gebruikt `GET https://data.rechtspraak.nl/uitspraken/content?id=ECLI:...` en verwerkt het XML-antwoord. Geen `RECHTSPRAAK_API_KEY` nodig. De dienst biedt geen vrije tekstzoekfunctie op wetsartikelen; daarvoor blijft Tavily actief.

In **Juridische bronnen**:

- Vul een volledig Nederlands ECLI-nummer in voor een rechtstreekse opvraging. Dit gebruikt geen Tavily en geen OpenAI.
- Vul een wetsartikel in voor Tavily-zoekresultaten. Herkenbare ECLI's uit resultaat-URL's/titels worden aanvullend opgehaald bij Rechtspraak, maximaal drie per zoekactie.
- Het label **Rechtspraak Open Data** betekent dat de data rechtstreeks uit die API komt, niet dat de uitspraak inhoudelijk relevant is bevonden.
- Open **Gepubliceerde uitspraaktekst bekijken** als die tekst beschikbaar is. Soms levert de API uitsluitend metadata.
- Bij uitval blijft het oorspronkelijke zoekfragment beschikbaar, herkenbaar aan **Tavily-zoekfragment**.

Aanvragen aan Rechtspraak worden na elkaar uitgevoerd, met maximaal 32 gecachte uitspraken gedurende vijf minuten. De app bouwt geen grote lokale jurisprudentiedatabase op. Veilige XML-verwerking weigert DTD's/entities.

Extra API-route: `GET /api/rechtspraak/{ecli}`, met de bestaande LegalLens-toegangssleutel. De Rechtspraak-dienst zelf is publiek en kosteloos.

[Officiële Rechtspraak Open Data-documentatie](https://www.rechtspraak.nl/uitspraken/open-data)

## Stap voor stap naar GitHub en Render

1. Download de nieuwste `LegalLens-Pro-Render.zip` en kies in Windows **Alles uitpakken**.
2. Open op GitHub de bestaande repository die aan jouw Render-service is gekoppeld. Controleer in Render bij Settings welke repository en branch worden gebruikt.
3. Ga in GitHub naar de root van die branch: je ziet daar `app.py`, `Dockerfile`, `requirements.txt` en de map `static`.
4. Kies **Add file → Upload files**.
5. Sleep de uitgepakte inhoud naar GitHub: de losse bestanden én de mappen `static` en `tests`. Upload niet de ZIP en ook niet een bovenliggende map `LegalLens-Pro-Render`.
6. Controleer vóór opslaan dat de paden kloppen: `app.py` staat in de root, en de pagina staat op `static/index.html`. Ook `static/styles.css` en `static/app.js` moeten erbij staan. Upload geen `.env`, sleutels of dossierdata.
7. Vul als commitbericht bijvoorbeeld `LegalLens 9.2: Rechtspraak API en herstelde werkruimte` in. Commit naar de aan Render gekoppelde branch als GitHub dit toestaat. Een beschermde branch kan eerst een pull request vereisen.
8. Bij automatische deployments start Render na deze commit. Anders kies je op je bestaande Render-service **Manual Deploy → Deploy latest commit**.
9. Controleer de deploymentlogs op een succesvolle start en test de pagina. De eerste opening van een gratis service kan ongeveer een minuut duren.
10. Open **Instellingen**, verbind met je LegalLens-sleutel uit `VALID_API_KEYS` en test bij **Juridische bronnen** een geldig ECLI-nummer. Daarna kun je Tavily testen met een wetsartikel.

De bovenstaande upload/commit via de website bereikt hetzelfde doel als een lokale Git-push. Als je liever VS Code en Git gebruikt, open dan eerst jouw bestaande clone en controleer branch/remote voordat je bestanden vervangt.

[GitHub: bestanden aan een repository toevoegen](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
