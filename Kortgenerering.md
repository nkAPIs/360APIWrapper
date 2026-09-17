# GIS Kortgenerering §3

FME genererer en json-fil med oplysninger om de ejendomme, der inden for den seneste måned har fået nye ejere, og hvor der på ejendommen er en eller flere beskyttelser af typen:

- Beskyttet natur
- Beskyttede diger
- Åbeskyttelseslinje
- Fredningsbeskyttelseslinje

Se eksempel: [nye_ejere_beskyttede_arealer.json](nye_ejere_beskyttede_arealer.json)

## Kortudsnit til breve

I forbindelse med automatisk udsendelse af breve til nye ejere af arealer med beskyttede arealer er der lavet en page, der danner et kortudsnit, som viser den pågældende ejendom sammen med det aktuelle lag, fx beskyttede naturtyper.

Pagen kaldes med url'en:

```
http://webgis.naestved.dk/spatialmap?profile=naestved_intern&page=dan_kortudsnit_beskyttede_arealer&bfenummer=xxxxxxxx&lag=bes_naturtyper&featurebuffer=10
```

Indtil videre dog kun i testversion på:

```
http://sandkasse.webgis.naestved.dk/spatialmap?profile=naestved_intern&page=dan_kortudsnit_beskyttede_arealer&bfenummer=xxxxxxxx&lag=bes_naturtyper&featurebuffer=10
```

### Parametre

Heri indsættes de parametre der fremgår af json-filen:

- **BFE-nr.** for den pågældende ejendom
- **Lagnavnet** der skal med i kortet:
  - Åbeskyttelseslinje: `aa_bes_linjer`
  - Beskyttede sten- og jorddiger: `bes_sten_jorddiger`
  - Beskyttede naturtyper: `bes_naturtyper`
  - Fortidsmindebeskyttelseslinje: `fundogfortidsminder_areal_beskyttelse`
- **Featurebuffer** (kan undlades, hvis kortet skal tilpasses præcis til ejendommen)

### Svar fra pagen

Pagen genererer en json-tekst som fx:

```json
{
  "": {
    "rowcount": 1,
    "xmin": 674882.456,
    "ymin": 6123882.845,
    "xmax": 675261.206,
    "ymax": 6124325.574,
    "result": {
      "scale": "1964.180786",
      "mapheight": "600",
      "layers": "theme-orto_foraar_orto_foraar_daf userpolygon_ejendomme_lois theme-01-ejendomme_gule",
      "img": "178887071311192.jpg",
      "scalebar": "sb178887071311192.jpg",
      "mapwidth": "600",
      "maxy": "6124380.915137",
      "maxx": "675348.536637",
      "legend": "leg178887071311192.jpg",
      "miny": "6123827.503863",
      "minx": "674795.125363",
      "dy": "553.411275",
      "mapext": "674795.125363 6123827.503863 675348.536637 6124380.915137",
      "dx": "553.411275"
    }
  }
}
```

- **img**: filnavnet på kortudsnittet
- **legend**: filnavnet på signaturforklaringen
- **scalebar**: filnavnet på målepinden

Kortudsnittene gemmes i mappen:

```
E:\spatialsuite\sites\sandkasse.webgis\appbase\spatialmap\tmp
```

Kortudsnittet kan vises med denne url:

```
http://sandkasse.webgis.naestved.dk/tmp/xxxxxxxx.jpg
```
