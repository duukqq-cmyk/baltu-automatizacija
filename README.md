# ⚙️ Procesu automatizācijas platforma (Baltu Investments atlases uzdevumi)

Viena Streamlit lietotne ar sākuma izvēlni un diviem moduļiem:

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

# Testi (verifikācija pret pamācības piemēru + līgumu ekstrakcija)
pytest tests/ -v
```

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
- Nogabali, kas nav mežaudze (lauces u.tml.), netiek vērtēti.

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
