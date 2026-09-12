"""Genera el recurso geográfico europeo mediante una ejecución manual como módulo."""

# Ejecutar solo cuando sea necesario regenerar europe_countries.geojson: al cambiar
# el catálogo de países, actualizar los límites de Natural Earth, ajustar el recorte
# o el detalle de los contornos, o recuperar un archivo ausente o dañado.
# No es necesario al actualizar estadísticas, generar informes ni desplegar la
# aplicación: en producción se utiliza el GeoJSON ya generado.
# Comando: python -m app.shared.data.build_europe_geojson

from __future__ import annotations

import argparse
import tempfile
import urllib.request
from pathlib import Path

import geopandas as gpd
import shapely
from shapely.geometry import box

from app.shared.data.geography import ISO2_TO_ISO3

NATURAL_EARTH_URL = (
    "https://naturalearth.s3.amazonaws.com/50m_cultural/ne_50m_admin_0_countries.zip"
)
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "resources" / "europe_countries.geojson"
# Se conservan las partes europeas de países transcontinentales y se retiran
# territorios de ultramar que obligarían a Plotly a mostrar una extensión mundial.
EUROPE_WEB_BOUNDS = (-32.0, 25.0, 65.0, 82.0)


def build_europe_geojson(source: str, output: Path, *, tolerance: float = 0.02) -> None:
    """Construye la geometría web desde Natural Earth con el catálogo ISO de la aplicación."""
    source_frame = gpd.read_file(f"zip://{source}")
    countries_by_iso3 = {
        str(row.ADM0_A3).strip().upper(): row for _, row in source_frame.iterrows()
    }
    records = []
    for country_code, iso3 in ISO2_TO_ISO3.items():
        natural_earth_code = "KOS" if country_code == "XK" else iso3
        row = countries_by_iso3.get(natural_earth_code)
        if row is None:
            raise ValueError(f"Natural Earth geometry missing for {country_code}/{iso3}")
        records.append(
            {
                "country_code": country_code,
                "iso3": iso3,
                "name_en": str(row.ADMIN),
                "geometry": row.geometry,
            }
        )

    europe = gpd.GeoDataFrame(records, crs="EPSG:4326")
    europe.geometry = europe.geometry.intersection(box(*EUROPE_WEB_BOUNDS))
    europe.geometry = europe.geometry.simplify(tolerance, preserve_topology=True)
    geometry_values = europe.geometry.to_numpy()
    europe.geometry = shapely.set_precision(geometry_values, grid_size=0.00001)
    # Plotly interpreta los anillos exteriores en sentido horario. Se impone esa
    # orientación para que un país no se dibuje como un hueco en el resto del mundo.
    europe.geometry = shapely.orient_polygons(europe.geometry.to_numpy(), exterior_cw=True)
    if europe.geometry.is_empty.any() or not europe.geometry.is_valid.all():
        raise ValueError("Geometry simplification produced empty or invalid countries")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        europe.to_json(drop_id=True, to_wgs84=True, separators=(",", ":")),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="Local Natural Earth ZIP; downloaded when omitted")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--tolerance", type=float, default=0.02)
    args = parser.parse_args()

    if args.source:
        build_europe_geojson(args.source, args.output, tolerance=args.tolerance)
        return

    with tempfile.TemporaryDirectory(prefix="rainbowlens-geodata-") as directory:
        archive = Path(directory) / "ne_50m_admin_0_countries.zip"
        # El origen es un endpoint HTTPS fijo de Natural Earth, no una entrada del usuario.
        urllib.request.urlretrieve(NATURAL_EARTH_URL, archive)  # nosec B310
        build_europe_geojson(str(archive), args.output, tolerance=args.tolerance)


if __name__ == "__main__":
    main()
