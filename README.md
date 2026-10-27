# ⚙️ Procesu automatizācijas platforma (Baltu Investments atlases uzdevumi)

Viena Streamlit lietotne ar sākuma izvēlni un trim moduļiem:

1. **🌲 Meža inventarizācijas analīze** (1. uzdevums, obligātais) —
   inventarizācijas PDF → kailcirtes atlase → apjomi pa sugām → sortimentu
   matrica → maksimālā cirsmas iegādes summa + gala atskaite.
2. **📄 Līgumu datu izvilkšana** (2. uzdevums) — PDF līgumi → strukturēti dati
   (puses, summas, datumi, termiņi, īpašie nosacījumi) → tabula, Excel un
   e-pasta kopsavilkums, ar validācijas brīdinājumiem šaubīgiem laukiem.

## Kā tas strādā

```
PDF ──► parser.py ──► rules.py ──► sortiment.py ──► report.py
        (nolasa       (atlasa       (apjomi, sugu     (teksta +
        taksācijas    kailcirtes    sadalījums,       Excel
        datus)        nogabalus)    matrica, EUR)     atskaite)
```

1. **Datu nolasīšana** (`cirsma/parser.py`) — `pdfplumber` izvelk taksācijas
   tabulu: nogabals, platība, mežaudzes formula, bonitāte, vid. caurmērs,
   vecums, krāja m³/ha. Formulas turpinājumi nākamajā rindā tiek apvienoti.
2. **Kailcirtes atlase** (`cirsma/rules.py`) — noteikumu dzinējs: valdošā suga
   sasniegusi galvenās cirtes vecumu (pēc sugas un bonitātes grupas) VAI
   valdaudzes caurmēru (P/E/B); baltalksnis — bez ierobežojuma. Katram
   nogabalam tiek saglabāts lēmuma pamatojums (audits/izsekojamība).
3. **Apjomi** (`cirsma/sortiment.py`) — krāja × platība; sadalījums pa sugām
   pēc mežaudzes formulas (piem. `4Ba3B37 2Ba26 1A47` = 60% Ba, 30% B, 10% A).
   Formulas parsētājs ir noturīgs pret PDF ekstrakcijā pazudušām atstarpēm
   (atkāpšanās gramatika ar koeficientu kontrolsummu = 10).
4. **Finanses** — sortimentu iznākuma matrica (īpatsvari × cenas pa sugām),
   izdevumi EUR/m³ (ciršana, pievešana, transports), peļņas rezerve % →
   **maksimālā iegādes summa** un cena EUR/m³.
5. **Atskaite** (`cirsma/report.py`) — teksta kopsavilkums pamācības formātā
   + Excel ar 3 lapām (kopsavilkums, nogabalu vērtējums ar pamatojumiem,
   sortimentu aprēķins).

## Palaišana

```bash
pip install -r requirements.txt

# Komandrinda
python cli.py dati/Nogabalu_raksturojosie_raditaji_64560020029.pdf \
    --excel atskaite.xlsx --txt atskaite.txt

# Apvienotā web saskarne (sākuma logā izvēlies moduli)
streamlit run app.py

# Testi (pamācības piemērs, gabali.lv paraugi dati/gabali/, līgumu ekstrakcija)
pytest tests/ -v
```

## Datu avoti: VMD un gabali.lv

Formāts tiek atpazīts automātiski (`parse_inventory_pdf`) — lietotājam nekas nav jāizvēlas.

```
VMD PDF ──────► parser.py (parse_vmd_pdf) ─┐
                                           ├─► Nogabals (kopīgs modelis) ─► rules ─► sortiment ─► report
gabali.lv PDF ► gabali.py ─────────────────┘
```

**gabali.lv** (`cirsma/gabali.py`) — LaTeX ģenerēts PDF ar tabulas līnijām:
- garumzīmes (¯ ˇ ,) PDF ir atsevišķas rakstzīmes — tās tiek apvienotas ar burtiem pēc koordinātām;
- tabula tiek nolasīta pa šūnām (`find_tables`), nevis ar regex; rinda lapas apakšā bez
  vertikālajām līnijām tiek nolasīta pēc tās pašas tabulas kolonnu robežām;
- papildu atribūti: **faktiskā krāja pa sugām**, kopējā krāja, biezība, šķērslaukums, koku skaits,
  VMD plānotā darbība, aizsargjoslas, plantācijas audze, 2. stāvs, pēdējā cirte, bojājumi, komentāri;
- formulas daļa pēc `+` (sugas zem 5%, piem. `7B2E1P75+M75`) koeficientu summā neietilpst.

**Apjoms pa sugām**: ja avotā ir sugu tabula, izmanto faktiskās sugu proporcijas un kopējo krāju
(precīzāk nekā sadalījums pēc formulas koeficientiem); citādi — pēc formulas kā līdz šim.
Atskaitē redzama izmantotā metode.

**Riska karogi** (kailcirtes lēmumu nemaina, bet parāda speciālistam):
- ⚠ aizsargjoslas/apgrūtinājumi (īpaši ūdens objektu, kods 4002…) — arī VMD failiem;
- ⚠ VMD plāno citu cirti, nevis kailcirti (vai otrādi — ℹ);
- ⚠ kontrolsummas: krāja × platība pret kopējo krāju; sugu krāju summa pret kopējo (>10% un >3 m³);
- ℹ plantācijas audze, jaunaudze (<20 g., cērtama tikai sugas dēļ), 2. stāvs, bojājumi, komentāri.

Nogabalu numuri dažādos kvartālos atkārtojas — ja īpašumā ir vairāki kvartāli, atskaitē
nogabals tiek apzīmēts kā `3.kv. 12.nog`.

## Manuāli labojumi nogabalu tabulā

Web saskarnē nogabalu tabula ir rediģējama (abiem avotiem): **Platība, Krāja m³/ha, Bonitāte,
Vecums, Kailcirte (ķeksis), Apjoms m³**. Pēc katra labojuma viss tiek pārrēķināts
(`cirsma/labojumi.py`):

- bonitāte / vecums → kailcirtes kritēriji tiek pārvērtēti no jauna;
- platība / krāja → apjoms = krāja × platība (sugu proporcijas saglabājas);
- apjoms → manuāli ievadītais aizstāj aprēķināto (sugu proporcijas saglabājas);
- kailcirtes ķeksis → manuāls lēmums aizstāj sistēmas lēmumu (pamatojumā redzams arī sistēmas lēmums);
- dzēsta šūna → atjauno PDF vērtību; poga "Atiestatīt visus labojumus" atjauno visu.

Labotie nogabali tiek atzīmēti ar ✎ tabulā, teksta un Excel atskaitē. Oriģinālie PDF dati netiek mainīti.

gabali.lv avotam pie katra nogabala redzama arī PDF papildu informācija (kolonna "Info no PDF",
sadaļa zem tabulas un atskaitēs): "Nogabala meža inventarizācija veikta …", 2. stāvs,
platību sadalījums, pēdējā cirte, plānotā darbība u.c.

## 2. modulis: līgumu datu izvilkšana

- `cirsma/ligumi.py` — divi ekstrakcijas režīmi:
  - **Deterministiskais** (regex heiristikas latviešu līgumiem) — strādā bez
    ārējiem servisiem; katram laukam validācijas piezīmes (⚠ = manuāla pārbaude).
  - **MI režīms** (Claude API, ja sānjoslā ievada API atslēgu) — noturīgs pret
    brīvu formātu; MI atbilde tiek krusteniski validēta pret deterministisko
    ekstrakciju (summu nesakritība → brīdinājums).
- Paraugu līgumi (izdomāti uzņēmumi un dati): `dati/ligumi/` — ģenerēti ar
  `python scripts/gen_paraugi.py`.
- Kļūdu apstrāde: tukšs/skenēts PDF → skaidrs brīdinājums; neatrasts lauks →
  ⚠ piezīme, nevis kluss izlaidums; reģ. nr. garuma kontrole; summas konteksta
  pārbaude ("pirkuma maksa"/"nomas maksa" vs vienkārši lielākais skaitlis).

## 3. modulis: 📊 Atskaites (leadu metriki no monday.com)

Savāc datus no iepirkumu agentu monday boardiem caur monday GraphQL API un aprēķina
CEO metrikus (dokuments *Monday_metrics*).

```
monday API ──► atskaites/monday.py ──► modelis.py ──────────────► metrikas.py ──► eksports.py
(boardi,       (lapošana, limiti,      (kolonnu karte, rindas      (periods,        (Excel 6 lapas,
 rindas)        kļūdas)                 → leadi pēc kadastra Nr.)   definīcijas)     teksts)
```

**Lead definīcija:** 1 lead = 1 **īpašuma** kadastra Nr. Visas zemes vienības (monday rindas)
vienā īpašumā = 1 lead, platība un m³ summējas. Viens īpašnieks ar 2 īpašumiem = 2 leadi;
2 īpašnieki vienam īpašumam = 1 lead. Rinda bez īpašuma Nr. tiek piesaistīta īpašumam pēc
zemes vienības apz. vai tālruņa (ja viennozīmīgi); citādi kļūst par atsevišķu leadu un
nonāk sadaļā "Datu kvalitāte". **Atjaunots** = tas pats īpašums atkal pēc >365 dienām.

**Metriki** (katrs notikums periodā pēc sava datuma): leadi kopā / unikāli / atjaunoti /
kvalitatīvi / mērķa / proaktīvi; kvalificēti + vid. laiks; priekšvērtējumi + laiks +
dienā/nedēļā/mēnesī; tikšanās; apsekoti + laiks līdz gala piedāvājumam; nopirkti
(gab., m³, ha, EUR, cenas samazinājums pret maks. gala piedāvājumu); atteikti + iemesli.
Papildus: sadalījums pa agentiem, piltuve tagad (pēc grupām), leadu tabula.

**Kolonnas** tiek atpazītas automātiski pēc nosaukuma (sk. `LAUKI` failā `atskaites/modelis.py`);
sasaisti un grupu nozīmi var mainīt cilnē *Iestatījumi* (saglabājas
`dati/monday_konfiguracija.json`, nav repozitorijā). Ja boardā kolonnas nav, metriks netiek
izdomāts — tas paliek "—" ar piezīmi; trūkstošās kolonnas var izveidot boardā no cilnes
*Iestatījumi → Board standarts*.

```bash
# Tokens: monday → profila bilde → Developers → My access tokens
# Web: ieliec .streamlit/secrets.toml rindu  MONDAY_API_TOKEN = "..."  (vai ievadi sānjoslā)
export MONDAY_API_TOKEN=...
python scripts/monday_atskaite.py --menesis 2026-10 --excel oktobris.xlsx   # ieplānojams ar cron
python scripts/monday_atskaite.py --demo                                     # bez API
```

Demo režīms (`atskaites/demo.py`) ļauj sadaļu izmēģināt bez tokena.

## 4. modulis: 🗺️ Karte (beta) — cirsmu atzīmēšana, mērījumi un pārrēķins

`views/karte.py`, loģika `karte/`:

- **Slāņi** (`karte/slani.py`) — LVM GEO brīvpieejas WMS (Fees/AccessConstraints = NONE), EPSG:3857:
  pamatkartes — ortofoto (jaunākais 7./8. cikls), infrasarkanais ortofoto, Sentinel-2 pēdējais
  bezmākoņu attēls, topokarte 1:10 000, OSM; pārklājumi — LiDAR veģetācijas augstuma modelis
  (arī izlīdzināts), VMD mežaudžu plāns (nogabali), kadastra karte, vējgāzes pēc 2026.08.22. vētras,
  LVM meža ceļi/grāvji, augsnes, horizontāles.
- **Zīmēšana un mērījumi** — laukumi, līnijas, taisnstūri, punkti (Leaflet.draw, latviski), robežu
  labošana un dzēšana, ātrais mērīšanas rīks, GPS atrašanās vieta, pāreja uz WGS84 / LKS-92 koordinātām.
  Platības un garumi tiek rēķināti **LKS-92 / TM (EPSG:3059)**; pārklāšanās tiek atzīmēta.
- **Imports / eksports** — KML (arī tīmekļa karšu zīmēšanas rīku `ExtendedData COLOR`) un GeoJSON;
  importēto krāsu nozīmi var piešķirt statusam ar vienu klikšķi. Eksports: KML, GeoJSON, Excel.
- **Pārrēķins** (`karte/parrekins.py`) — kailcirtes laukumu piesaista inventarizācijas nogabalam;
  nogabala platība = piesaistīto laukumu summa, apjoms = krāja × platība, un iegādes summa pārrēķinās
  ar tiem pašiem moduļiem kā Meža inventarizācijas sadaļā. Rezultātu var lejupielādēt Excel atskaitē
  vai pārnest kā labojumus uz Meža inventarizācijas sadaļu (tas pats PDF ir kopīgs abām sadaļām).
- **Ierobežojumi (beta)** — objekti glabājas pārlūka sesijā (saglabāšanai — KML eksports); nogabalu
  ģeometrija no WMS nav nolasāma, tāpēc laukums nogabalam tiek piesaistīts manuāli.

## Verifikācija pret pamācības piemēru

| Rādītājs | Pamācībā | Sistēmas rezultāts |
|---|---|---|
| Kailcirtes nogabali | 1;3;4;7;8;12 | 1;3;4;7;8;12 ✅ |
| Cērtamais apjoms | 1039 m³ | 1038.94 m³ ✅ |
| E / B / A / Ba / Bl | 34 / 499 / 102 / 391 / 12 m³ | 33.98 / 498.55 / 102.30 / 391.38 / 12.72 ✅ |
| Ieņēmumi | 56 322.14 EUR | 56 321.34 EUR ✅ |
| Max iegādes summa | 28 249 EUR | 28 248 EUR ✅ (±1 EUR noapaļošana) |
| Cena | 27.19 EUR/m³ | 27.19 EUR/m³ ✅ |

## Pieņēmumi

- Valdošā suga = pirmā (lielākā) komponente mežaudzes formulā; tās vecums —
  no formulas (ja nav, izmanto audzes vecumu no kolonnas "vecums").
- Sortimentu īpatsvari un cenas ņemti no pamācības matricas kā noklusējums;
  tie ir konfigurējami (Streamlit sānjoslā vai kodā `NOKLUSEJUMA_MATRICA`).
- Sugas bez savas matricas kolonnas (piem., Bl — blīgzna) nonāk kolonnā "Citi"
  (100% malka), tāpat kā pamācības piemērā.
- Nogabali, kas nav mežaudze (lauces, bebru applūdinājumi u.tml.), netiek vērtēti.
- Melnalksnis VMD formulās var būt gan `M`, gan `Ma` — abi tiek apstrādāti vienādi.

## Kļūdu apstrāde un robustums

- Ja PDF nav nolasāms (cits formāts, skenēts attēls) — skaidra kļūda ar
  ieteikumu (OCR / manuāla pārbaude), nevis kluss nepareizs rezultāts.
- Formulas kontrolsumma: koeficientiem jāsummējas uz 10; ja ne — nogabals
  tiek marķēts manuālai pārbaudei, nevis rēķināts nepareizi.
- Nezināma valdošā suga → "manuāla pārbaude", konservatīvi NEatļaujot kailcirti.
- Aprēķini ir 100% deterministiski (Python, ne LLM) — auditējami un atkārtojami.

## Iespējamie nākamie soļi produkcijai

- **E-pasta plūsma**: n8n/Make scenārijs — PDF pienāk e-pastā → API izsauc šo
  aprēķinu → atskaite automātiski aiziet atpakaļ speciālistam.
- **LLM ekstrakcijas rezerves slānis**: ja PDF izkārtojums atšķiras no VMD
  standarta, Claude/GPT API ar strikti definētu JSON shēmu + kontrolsummu
  validāciju pret deterministiskajiem aprēķiniem.
- **OCR** (Tesseract/Textract) skenētiem dokumentiem.
- Vēsturisko aprēķinu datubāze un cenu matricas versiju pārvaldība.
