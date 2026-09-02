"""Ģenerē 2 parauga līgumu PDF failus testēšanai (izdomāti uzņēmumi un dati)."""
import os

from fpdf import FPDF

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

LIGUMS_1 = """NEKUSTAMĀ ĪPAŠUMA PIRKUMA LĪGUMS Nr. 2026/17

Rīgā, 2026. gada 14. augustā

SIA "Piemēra Invest", reģ. Nr. 40001234567, juridiskā adrese Brīvības iela 1, Rīga,
tās valdes locekļa Jāņa Parauga personā, turpmāk — Pārdevējs, no vienas puses, un

SIA "Demo Mežs", reģ. Nr. 40007654321, juridiskā adrese Meža iela 2, Liepāja,
tās valdes locekles Annas Piemēres personā, turpmāk — Pircējs, no otras puses,

noslēdz šādu līgumu:

1. LĪGUMA PRIEKŠMETS
1.1. Pārdevējs pārdod un Pircējs pērk nekustamo īpašumu "Paraugmeži",
kadastra Nr. 64560099999, Gaviezes pagastā, 6,65 ha platībā.

2. PIRKUMA MAKSA UN NORĒĶINU KĀRTĪBA
2.1. Pirkuma maksa ir 45 000,00 EUR (četrdesmit pieci tūkstoši eiro).
2.2. Pircējs samaksā avansu 10% apmērā, t.i. 4 500,00 EUR, 5 darba dienu laikā
pēc līguma parakstīšanas.
2.3. Atlikusī summa tiek samaksāta 30 dienu laikā pēc līguma parakstīšanas.

3. PUŠU ATBILDĪBA
3.1. Par maksājumu kavējumu Pircējs maksā līgumsodu 0,5% apmērā no kavētās
summas par katru kavējuma dienu, bet ne vairāk kā 10% no līguma summas.

4. CITI NOTEIKUMI
4.1. Līgums stājas spēkā parakstīšanas brīdī un ir spēkā līdz saistību pilnīgai izpildei.
4.2. Puses apņemas ievērot konfidencialitāti attiecībā uz līguma noteikumiem.
"""

LIGUMS_2 = """TELPU NOMAS LĪGUMS Nr. N-2026/42

Liepājā, 2026. gada 3. martā

SIA "Paraugs Properties", reģ. Nr. 40009876543, turpmāk — Iznomātājs, un
SIA "Testa Birojs", reģ. Nr. 40001112223, turpmāk — Nomnieks,

noslēdz šādu līgumu:

1. LĪGUMA PRIEKŠMETS
1.1. Iznomātājs nodod Nomniekam lietošanā biroja telpas 120 m² platībā
Graudu ielā 15, Liepājā.

2. NOMAS MAKSA
2.1. Nomas maksa ir 1 250,00 EUR mēnesī, papildus PVN.
2.2. Nomnieks iemaksā drošības naudu 2 500,00 EUR apmērā.

3. TERMIŅŠ
3.1. Līgums ir spēkā līdz 2028. gada 31. decembrim.

4. ATBILDĪBA
4.1. Par nomas maksas kavējumu Nomnieks maksā līgumsodu 0,1% dienā.
"""


def izveidot_pdf(teksts: str, cels: str) -> None:
    pdf = FPDF()
    pdf.add_font("DejaVu", "", FONT)
    pdf.add_font("DejaVu", "B", FONT_B)
    pdf.add_page()
    for rinda in teksts.splitlines():
        if not rinda.strip():
            pdf.ln(6)
            continue
        if rinda.strip().isupper() and len(rinda.strip()) > 10:
            pdf.set_font("DejaVu", "B", 11)
        else:
            pdf.set_font("DejaVu", "", 10)
        pdf.multi_cell(0, 6, rinda, new_x="LMARGIN", new_y="NEXT")
    pdf.output(cels)


if __name__ == "__main__":
    mape = os.path.join(os.path.dirname(__file__), "..", "dati", "ligumi")
    os.makedirs(mape, exist_ok=True)
    izveidot_pdf(LIGUMS_1, os.path.join(mape, "paraugs_pirkuma_ligums.pdf"))
    izveidot_pdf(LIGUMS_2, os.path.join(mape, "paraugs_nomas_ligums.pdf"))
    print("Paraugu līgumi izveidoti:", mape)
