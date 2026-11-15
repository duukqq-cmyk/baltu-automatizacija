# Automatizācijas rīka uzlabojumi — kas izdarīts un kas vajadzīgs

Pēc dokumenta "Automatizācijas rīka uzlabojumi" (7 punkti). Visi aprēķini ir deterministiski un
pārklāti ar testiem (`pytest tests/` — 125 testi, t.sk. visi dokumenta piemēri).

## Kopējā loģika

Katram nogabalam ir viens lēmums **Cirtes veids** (`cirsma/rules.py`, `cirsma/cirtes.py`):

1. **Kailcirte**: vecums vai caurmērs sasniegts. Platību ierobežo meža tips, lielāku nogabalu sadala.
2. **Izlases cirte**: tikai manuāli (kolonna *Cirtes veids*), G − (Gkrit + 1).
3. **Kopšanas cirte**: automātiski, ja kailcirte nav atļauta un G − (Gmin + 1) ≥ 4 m²/ha.
4. **Necirst**.

Cenas, sortimenti, izdevumi un noteikumi nāk no **viena Cenrāža**. To izmanto Meža inventarizācija,
Karte un Cirsmas novērtējums.

## Pa punktiem

| # | Uzdevums | Statuss |
|---|---|---|
| 1 | Max kailcirtes platības pēc meža tipa (5 / 2 ha), sadale ar 0,5 ha joslu | ✅ Atskaitē katra kailcirte atsevišķā rindā (3,2 ha → 2,0 + 0,7 ha = 675 m³) |
| 1 | Blakus esošās kailcirtes skaitās kopā | ✅ Kartē (pēc MVR robežām): brīdinājums, ja saskarošās kailcirtes kopā > limits. ⚠ Tikai PDF režīmā (bez kartes) robežu nav, tur nav pārbaudes |
| 2 | Kopšanas cirtes (automātiski) un izlases cirtes (manuāli) | ✅ Šķērslaukums no VMD PDF, gabali.lv un MVR; Gmin/Gkrit un veidaugstuma tabulas; dokumenta piemērs 17,86 m³ ✓ |
| 2 | Kopšanai tikai tara / papīrmalka / malka, izlasei arī zāģbaļķi / finieris | ✅ Atsevišķas matricas un izdevumi katram cirtes veidam |
| 3 | Sortimentu % un cenas maināmas un saglabājamas kā noklusējums | ✅ Lapa **Cenrādis**: izmaiņas strādā uzreiz sesijā, "Saglabāt kā noklusējumu" — visiem, ar vēsturi |
| 4 | Cirsmas novērtējuma kalkulators | ✅ Resnā / Vidējā / Tievā / P. malka / Malka → sortimenti × cenas − izmaksas; abi PDF formāti; salīdzinājums ar Mežvērti; nogabals un platība beigās |
| 5 | Karte: poligoni uzreiz pēc kadastra nr., rediģējami | ✅ Kailcirtes un kopšanas poligoni tiek uzzīmēti automātiski; lielu kailcirti sistēma pati sagriež: kailcirte + josla + kailcirte. Laukuma statuss nosaka cirtes veidu |
| 6 | Atmiņa / saglabāšana | ✅ Datubāze (SQLite vai Postgres) + lapa **Saglabātie** (meklē pēc kadastra, atver tieši tādu, kāds bija) + **PDF atskaite** ar cirsmu skici + teksts monday. ⏳ Automātiska augšupielāde monday |
| 7 | Baltalksnis: ≥ 25 g. VAI ≥ 16 cm | ✅ (līdz šim bija "bez ierobežojuma") |

## Pieņēmumi, ko izdarīju (pārbaudi)

- **Atdalošā josla** vienmēr ir 0,5 ha. Nākamo kailcirti veido, ja tai paliek vismaz 0,5 ha, un visu
  atlikumu ieskaita tajā: 3,6 ha → 2,0 + 1,1 ha (dokumentā bija "2 + 1"). Abas vērtības maināmas
  Cenrādī → Noteikumi.
- Ja saskaras dažādi meža tipi, kopējai platībai izmanto **stingrāko limitu**. Nezināmam meža tipam
  izmanto 2 ha.
- Ja augstums < 12 m, kopšanu nerēķina (tabulā normatīva nav).
- Veidaugstumu ņem **valdošajai sugai** (kā dokumenta piemērā), apjomu sadala pa sugām pēc formulas.
- Sugām bez savas veidaugstuma kolonnas (kļava, goba u.c. → ozols; skujkoki → egle; pārējās → baltalksnis).
- Slieksnis "vismaz 4 m²/ha" pēc noklusējuma attiecas arī uz izlases cirti (Cenrādī var izslēgt).
- Kopšanas un izlases cirtes **izdevumi pagaidām ir tādi paši kā kailcirtei** (11 + 7 + 6 €/m³).
  Kopšanā tie parasti ir lielāki, tāpēc ievadi reālos.
- Kopšanas sortimentu % ir mans sākuma pieņēmums (piem., bērzs: tara 30 %, papīrmalka 50 %, malka 20 %).
- Novērtējuma kartējums lapu kokiem: bērzs Īp.kval → finieris A, Resnā → finieris B, Vidējā → finieris C,
  Tievā → tara; apse Resnā → zāģbaļķi, Vidējā/Tievā → tara; baltalksnis viss → tara/malka.
  Maināms Cenrādī → Novērtējuma kartējums.
- Kopšanas apjomu rēķina tikai, ja PDF / reģistrā ir šķērslaukums. Jaunaudzēm VMD PDF G nav, tur
  sistēma brīdina un ļauj ievadīt apjomu manuāli.

## Kas vajadzīgs no tevis

1. **Datubāze serverī.** Ja lietotne darbojas Streamlit Community Cloud, lokālais SQLite fails pēc
   restarta pazūd. Streamlit Secrets ieliec `DATABASE_URL = "postgresql://..."`, piemēram, no
   Supabase vai Neon (bezmaksas līmenis, ES reģions). Tabulas izveidojas pašas. Uz VPS / lokāli
   strādā arī bez tā (`dati/baltu.db`).
2. **monday automātiskā augšupielāde.** Vajag boardu, kolonnu ar kadastra nr. un kolonnas, kurās
   rakstīt m³ / summu (un vai pievienot PDF failu kolonnā vai Updates). Līdz tam ir poga ar gatavu
   tekstu un PDF lejupielāde.
3. **Veidaugstuma tabulas turpinājums virs 32 m.** Pagaidām virs 32 m izmanto 32 m vērtību un parāda
   piezīmi. Vēl vajag zemsvītras piezīmi "priede¹" no šķērslaukuma tabulas.
4. **Pārbaudi tabulas.** Gmin/Gkrit un veidaugstums pārrakstīti no dokumenta attēliem
   (`cirsma/cirtes.py`).
5. **Reālas kopšanas/izlases izmaksas un sortimentu %**, tad saglabā Cenrādī.
6. **Pievešanas izmaksas pēc attāluma** (novērtējuma PDF ir "Pievešanas attālums"). Ja vajag,
   iedod diapazonus un cenas.

## Ierobežojumi

- Automātiski sagriežot karti, griež ar taisnēm pa nogabala garāko asi. Neregulārām formām josla var
  būt šaura vai nepraktiska, tāpēc pārvelc to ar ✎.
- Ja blakus esošās kailcirtes kopā pārsniedz limitu, sistēma brīdina, bet automātiski nepārzīmē
  (tas jāizlemj dabā).
- Lietotāju pieteikšanās vēl nav. Vārdu vēsturei ievada sānjoslā "👤 Tavs vārds".
