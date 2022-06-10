"""
DripTorch I/O helper functions
"""

# Internal imports
from re import I
from driptorch.errors import GeojsonError

# External imports
from folium import Polygon
import pyproj
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform


class Projector:
    """
    Helper class to handle reprojections during I/O operations.
    """

    def __init__(self, src_epsg, dst_epsg):
        """Constructor will initialize a function for forward projection and
        a function for backwards projection.
        """

        # Configure transformer for forward projections
        self.forward_proj = pyproj.Transformer.from_proj(
            pyproj.Proj(f'epsg:{src_epsg}'),
            pyproj.Proj(f'epsg:{dst_epsg}'),
            always_xy=True
        )

        # Configure transform for inverse projections
        self.backward_proj = pyproj.Transformer.from_proj(
            pyproj.Proj(f'epsg:{dst_epsg}'),
            pyproj.Proj(f'epsg:{src_epsg}'),
            always_xy=True
        )

    def forward(self, geometry: BaseGeometry) -> BaseGeometry:
        """Project from source EPSG to destination EPSG

        Args:
            geometry (BaseGeometry): Input geometry to reproject

        Returns:
            BaseGeometry: Reprojected geometry
        """

        return transform(self.forward_proj.transform, geometry)

    def backward(self, geometry: BaseGeometry) -> BaseGeometry:
        """Project from destimation EPSG to source EPSG

        Args:
            geometry (BaseGeometry): Input geometry to reproject

        Returns:
            BaseGeometry: Reprojected geometry
        """

        return transform(self.backward_proj.transform, geometry)

    @staticmethod
    def estimate_utm_epsg(lon, lat):
        return int(32700-round((45+lat)/90, 0)*100+round((183+lon)/6, 0))

    @classmethod
    def web_mercator_to_utm(cls, geometry: BaseGeometry) -> BaseGeometry:

        lon, lat = list(geometry.centroid.coords[0])
        utm_epsg = cls.estimate_utm_epsg(lon, lat)

        projector = cls(4326, utm_epsg)

        return utm_epsg, projector.forward(geometry)

    @classmethod
    def to_web_mercator(cls, geometry: BaseGeometry | dict, src_epsg: int) -> BaseGeometry | dict:
        """Convenience method to project a shapely geometry or GeoJSON feature to web mercator

        Args:
            geometry (BaseGeometry | dict): Either a shapely geometry or GeoJSON
                feature (not a feature collection).
            src_epsg (int): EPSG code of the CRS that the spatial data are currently projected in.

        Returns:
            BaseGeometry | dict: A shapely geometry or GeoJSON feature projected in 4326
        """

        projector = cls(src_epsg, 4326)

        if isinstance(geometry, dict):
            geometry = shape(geometry)
            return mapping(projector.forward(geometry))

        return projector.forward(geometry)


def read_geojson_polygon(geojson: dict) -> Polygon:
    """Parse a GeoJSON to a shapely Polygon

    Args:
        geojson (dict): Input GeoJSON dictionary projected in 4326

    Raises:
        GeojsonError: Raise error if we can't figure out the formatting

    Returns:
        Polygon: Shapely polygon geometry
    """

    # If the geojson is a feature collection then we loop over the features
    # and find the first instance of a polygon geometry type
    if geojson['type'] == 'FeatureCollection':
        for feature in geojson['features']:
            if feature['geometry']['type'].lower() == 'polygon':
                geometry = shape(feature['geometry'])
                break

    # Maybe it's just the geometry?
    elif geojson['type'].lower() == 'Polygon':
        geometry = shape(geojson)

    # Fix your shit, we're not gonna to keep trying to guess
    else:
        raise GeojsonError(GeojsonError.read_error)

    return geometry


def write_geojson(geometries: list[BaseGeometry], utm_epsg: int, properties={}, style={}) -> dict:
    """Write a list of shapely geometries to GeoJSON

    Args:
        geometries (list[BaseGeometry]): List of shapely geometries
        properties (dict, optional): Properties for each feature. Defaults to {}.
        style (dict, optional): Rendering style applied to all features. Defaults to {}.

    Returns:
        dict: GeoJSON
    """

    # Get a projector instance for inverse projection
    projector = Projector(utm_epsg, 4326)

    # Get the names of all the props
    property_names = properties.keys()

    # Loop over each geometry in the input list and write to GeoJSON
    features = []
    for i, geometry in enumerate(geometries):

        props = {}
        for name in property_names:
            props[name] = properties[name][i]

        features.append(
            {
                'type': 'Feature',
                'properties': props | style,
                'geometry': mapping(projector.forward(geometry))
            }
        )

    # Compile the features in a feature collection
    geojson = {
        'type': 'FeatureCollection',
        'features': features
    }

    return geojson
