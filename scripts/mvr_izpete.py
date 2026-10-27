"""Pagaidu: MVR SHP struktūras izpēte (lauki, vērtības, CRS)."""
import glob
import sys

import pyogrio

shp = sorted(glob.glob(f"{sys.argv[1]}/**/*.shp", recursive=True))[0]
info = pyogrio.read_info(shp)
print(f"## {shp}\nCRS WKT:\n```\n{pyogrio.read_info(shp)['crs']}\n```")
df = pyogrio.read_dataframe(shp, max_features=20000, read_geometry=True)
print("bounds sample:", df.geometry.iloc[0].bounds)
print("\n```\n" + df.drop(columns="geometry").head(8).T.to_string()[:12000] + "\n```")
for c in ["zkat", "mt", "izc", "s10", "s11", "bon", "vgr", "p_darbv", "p_cirp", "plant_audz", "forestry_c", "vmd_headfo", "va_kods1", "adm1", "adm2"]:
    print(f"\n### {c}\n```\n{df[c].value_counts(dropna=False).head(25).to_string()}\n```")
print("\nformula samples:", df["formula"].dropna().sample(25, random_state=1).tolist())
print("kadastrs samples:", df["kadastrs"].dropna().head(10).tolist(), "null:", df["kadastrs"].isna().mean())
print("kadastrs uniq per 20k:", df["kadastrs"].nunique())
