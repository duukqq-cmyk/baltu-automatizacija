"""Pagaidu: MVR SHP struktūras izpēte (lauki, tipi, piemēri, CRS)."""
import glob
import sys

import pyogrio

for shp in sorted(glob.glob(f"{sys.argv[1]}/**/*.shp", recursive=True)):
    info = pyogrio.read_info(shp)
    print(f"\n## {shp}\n- features: {info['features']}  crs: {info['crs']}  geom: {info['geometry_type']}")
    print("- fields: " + ", ".join(f"{n}:{t}" for n, t in zip(info["fields"], info["dtypes"])))
    df = pyogrio.read_dataframe(shp, max_features=3, read_geometry=False)
    print("\n```\n" + df.to_string()[:3000] + "\n```")
